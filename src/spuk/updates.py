"""Check GitHub Releases for a newer Spuk.

This is the *only* network call Spuk makes besides the one-time model download,
and it runs solely when the user clicks "Check for updates" in Settings — never
automatically — so the "nothing leaves your computer / no required network calls"
promise still holds. We just compare the latest published release tag to the
running version and, if it's newer, hand back the release page URL so the UI can
open it in the browser. (Spuk ships as unsigned zips, so the user does the final
download + reinstall themselves.)

Uses only the standard library (urllib) — no extra dependency.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger("spuk.updates")

REPO = "1mp3ctz/spuk"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of an update check. `status` is 'current', 'available', or 'error'."""

    status: str
    message: str
    latest: str | None = None
    url: str = RELEASES_PAGE


def _parse_version(value: str) -> tuple[int, ...]:
    """Turn 'v0.3.1' / '0.3.1' / '1.2.3-beta' into a comparable tuple of ints."""
    cleaned = value.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break  # stop at the first non-digit (e.g. '1-rc' -> 1)
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    """True if release tag `latest` is a newer version than `current`."""
    return _parse_version(latest) > _parse_version(current)


def check_for_update(current: str, timeout: float = 6.0) -> UpdateResult:
    """Ask GitHub for the latest release and compare it to `current`.

    Never raises — network/parse problems come back as a friendly 'error' result.
    """
    request = urllib.request.Request(
        LATEST_API,
        headers={
            "User-Agent": f"Spuk/{current}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        log.warning("Update check failed: %s", exc)
        return UpdateResult(
            "error",
            "Couldn't check for updates — please check your internet connection and try again.",
        )

    tag = (data.get("tag_name") or "").strip()
    url = data.get("html_url") or RELEASES_PAGE
    if not tag:
        return UpdateResult("error", "Couldn't read the latest version from GitHub.")

    if is_newer(tag, current):
        version = tag.lstrip("vV")
        return UpdateResult(
            "available",
            f"Spuk {tag} is available — you have v{current}.",
            latest=version,
            url=url,
        )
    return UpdateResult("current", f"You're on the latest version (v{current}).", latest=current)
