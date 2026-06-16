"""Check GitHub Releases for a newer Spuk — and install it in place.

Two halves:

* `check_for_update()` — compares the latest published release tag to the running
  version and, when newer, also resolves the download URL of this platform's asset.
* `self_update()` — downloads that asset, then stages a tiny detached helper that
  waits for Spuk to quit, swaps the app bundle/folder in place, and relaunches it.
  The caller quits the app right after.

Both run only when the user clicks in Settings — never automatically — so the
"nothing leaves your computer / no required network calls" promise still holds.

Self-update only works for the packaged build (`Spuk.app` / `Spuk.exe`). When
running from source there's nothing to replace, so `can_self_update()` is False
and the UI falls back to opening the release page. Standard library only.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("spuk.updates")

REPO = "1mp3ctz/spuk"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of a check. `status` is 'current', 'available', or 'error'."""

    status: str
    message: str
    latest: str | None = None
    url: str = RELEASES_PAGE          # release page (browser fallback)
    asset_url: str | None = None      # this platform's downloadable zip


# --- version comparison ---------------------------------------------------


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
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    """True if release tag `latest` is a newer version than `current`."""
    return _parse_version(latest) > _parse_version(current)


def _asset_for_platform(assets: list[dict], plat: str | None = None) -> str | None:
    """Pick this platform's release-zip download URL from the GitHub asset list."""
    plat = plat or sys.platform
    key = {"darwin": "macos", "win32": "windows"}.get(plat)
    if key is None:
        return None
    for asset in assets:
        name = (asset.get("name") or "").lower()
        if key in name and name.endswith(".zip"):
            return asset.get("browser_download_url")
    return None


# --- the check -------------------------------------------------------------


def check_for_update(current: str, timeout: float = 6.0) -> UpdateResult:
    """Ask GitHub for the latest release and compare it to `current`.

    Never raises — network/parse problems come back as a friendly 'error' result.
    """
    request = urllib.request.Request(
        LATEST_API,
        headers={"User-Agent": f"Spuk/{current}", "Accept": "application/vnd.github+json"},
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
        return UpdateResult(
            "available",
            f"Spuk {tag} is available — you have v{current}.",
            latest=tag.lstrip("vV"),
            url=url,
            asset_url=_asset_for_platform(data.get("assets") or []),
        )
    return UpdateResult("current", f"You're on the latest version (v{current}).", latest=current)


# --- self-update (packaged builds only) ------------------------------------


# Directory prefixes a Linux package manager (deb/rpm) owns. A build installed
# under one of these must NOT self-update: overwriting package-managed files is
# wrong (it breaks the package DB and needs root). Such installs update via apt /
# dnf, so we fall back to opening the release page instead.
_LINUX_MANAGED_PREFIXES = ("/usr", "/opt", "/bin", "/sbin", "/lib")


def _is_packaged_linux_install() -> bool:
    """Whether we're a Linux build living under a package-manager-owned prefix."""
    if sys.platform != "linux":
        return False
    try:
        exe = Path(sys.executable).resolve()
    except Exception:  # noqa: BLE001
        return False
    return any(str(exe).startswith(prefix + os.sep) for prefix in _LINUX_MANAGED_PREFIXES)


def can_self_update() -> bool:
    """True only when Spuk may overwrite its own files to update in place.

    In-place self-update is for the frozen .app / .exe on macOS / Windows. It is
    OFF on Linux: a deb/rpm owns its files (so we never clobber a package-managed
    install — see ``_is_packaged_linux_install``), and a from-source checkout has
    nothing to swap. Either way the UI falls back to opening the release page.
    Running from source on macOS/Windows keeps the existing (False) behaviour too,
    since it isn't frozen.
    """
    if sys.platform == "linux" or _is_packaged_linux_install():
        return False
    return bool(getattr(sys, "frozen", False)) and sys.platform in ("darwin", "win32")


def _installed_macos_app() -> Path | None:
    """The running Spuk.app bundle (…/Spuk.app/Contents/MacOS/Spuk → …/Spuk.app)."""
    exe = Path(sys.executable).resolve()
    for parent in [exe, *exe.parents]:
        if parent.name.endswith(".app"):
            return parent
    return None


def _download_zip(url: str, dest_dir: Path, timeout: float = 180.0) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": "Spuk-updater"})
    zip_path = dest_dir / "update.zip"
    with urllib.request.urlopen(request, timeout=timeout) as response, open(zip_path, "wb") as out:
        shutil.copyfileobj(response, out)
    return zip_path


def _apply_macos(extract_dir: Path) -> None:
    new_app = next(iter(extract_dir.rglob("*.app")), None)
    cur_app = _installed_macos_app()
    if new_app is None or cur_app is None:
        raise RuntimeError("Couldn't locate the app bundle to update.")
    # The download is quarantined; clear it so the relaunch doesn't trip Gatekeeper.
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(new_app)], check=False)
    helper = extract_dir.parent / "spuk_update.sh"
    helper.write_text(
        "#!/bin/sh\n"
        'PID="$1"\n'
        'while kill -0 "$PID" 2>/dev/null; do sleep 0.3; done\n'
        "sleep 0.5\n"
        f'rm -rf "{cur_app}"\n'
        f'mv "{new_app}" "{cur_app}"\n'
        f'xattr -dr com.apple.quarantine "{cur_app}" 2>/dev/null\n'
        f'open "{cur_app}"\n'
    )
    helper.chmod(0o755)
    subprocess.Popen(["/bin/sh", str(helper), str(os.getpid())], start_new_session=True)


def _apply_windows(extract_dir: Path) -> None:
    new_exe = next(iter(extract_dir.rglob("Spuk.exe")), None)
    if new_exe is None:
        raise RuntimeError("Couldn't locate Spuk.exe in the download.")
    new_dir = new_exe.parent
    cur_dir = Path(sys.executable).resolve().parent
    pid = os.getpid()
    bat = extract_dir.parent / "spuk_update.bat"
    bat.write_text(
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
        f'robocopy "{new_dir}" "{cur_dir}" /MIR /NFL /NDL /NJH /NJS /NP >nul\r\n'
        f'start "" "{cur_dir}\\Spuk.exe"\r\n'
    )
    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=DETACHED_PROCESS, close_fds=True)


def self_update(asset_url: str | None) -> None:
    """Download this platform's release asset and stage an in-place swap + relaunch.

    Spawns a detached helper that waits for THIS process to exit, replaces the
    installed app, and relaunches it. The caller must quit Spuk immediately after
    this returns. Raises on any failure so the UI can fall back to the browser.
    """
    if not asset_url:
        raise RuntimeError("No download is available for this platform.")
    if not can_self_update():
        raise RuntimeError("Self-update only works in the installed app, not when run from source.")

    tmp = Path(tempfile.mkdtemp(prefix="spuk-update-"))
    extract_dir = tmp / "extracted"
    extract_dir.mkdir()
    zip_path = _download_zip(asset_url, tmp)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)

    if sys.platform == "darwin":
        _apply_macos(extract_dir)
    elif sys.platform == "win32":
        _apply_windows(extract_dir)
    else:  # pragma: no cover - guarded by can_self_update()
        raise RuntimeError("Self-update isn't supported on this platform.")
