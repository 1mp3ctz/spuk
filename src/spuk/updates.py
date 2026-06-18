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
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("spuk.updates")

# How much to read per socket chunk while downloading — small enough that the
# progress bar moves smoothly and a Cancel is noticed within a fraction of a second.
_CHUNK = 256 * 1024


class UpdateCancelled(Exception):
    """Raised when the user cancels a download in progress (not an error)."""

REPO = "1mp3ctz/spuk"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def _ssl_context() -> ssl.SSLContext:
    """A cert-verifying TLS context backed by certifi's CA bundle.

    A frozen (PyInstaller) build doesn't always have a usable system CA store —
    on Windows especially, bare ``urllib`` can fail TLS verification with
    CERTIFICATE_VERIFY_FAILED even though a browser on the same machine works,
    which silently breaks both the update check and the download. ``certifi``
    (already a transitive dependency, and bundled into the build because this
    import makes PyInstaller collect it) ships a known-good root bundle, so we
    point urllib at it for consistent verification everywhere. Falls back to the
    system default context if certifi is somehow unavailable — still verifying.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - any import/IO problem → system default
        return ssl.create_default_context()


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
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
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


def relaunch_macos_app() -> bool:
    """Quit-safe relaunch of the installed macOS app.

    Stages a detached helper that waits for THIS process to exit, then reopens the
    bundle — so the caller can quit Spuk and have it come straight back (used by
    the permissions window, since macOS only applies a fresh grant to a newly
    started app). Returns False when not running as a packaged ``.app`` (dev /
    source / other OS), so the caller can fall back to a plain close. The caller
    must quit Spuk right after this returns True.
    """
    if sys.platform != "darwin":
        return False
    app = _installed_macos_app()
    if app is None:
        return False
    helper = Path(tempfile.mkdtemp(prefix="spuk-relaunch-")) / "relaunch.sh"
    helper.write_text(
        "#!/bin/sh\n"
        'PID="$1"\n'
        'while kill -0 "$PID" 2>/dev/null; do sleep 0.3; done\n'
        "sleep 0.5\n"
        f'open "{app}"\n'
    )
    helper.chmod(0o755)
    subprocess.Popen(["/bin/sh", str(helper), str(os.getpid())], start_new_session=True)
    return True


def _download_zip(
    url: str,
    dest_dir: Path,
    timeout: float = 180.0,
    progress: Callable[[int, int], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    """Stream the release zip to disk.

    ``progress(downloaded_bytes, total_bytes)`` is called as data arrives so the
    UI can show a real progress bar instead of a frozen-looking spinner (total is
    0 when the server omits Content-Length). ``cancel()`` is polled between chunks;
    returning True aborts with ``UpdateCancelled`` so the user can back out of a
    large download. Raises on network errors so the caller can fall back.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "Spuk-updater"})
    zip_path = dest_dir / "update.zip"
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        if progress is not None:
            progress(done, total)
        with open(zip_path, "wb") as out:
            while True:
                if cancel is not None and cancel():
                    raise UpdateCancelled("Update cancelled.")
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
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


def _windows_update_script(new_dir: Path, cur_dir: Path, pid: int) -> str:
    """The .bat that waits for Spuk to quit, swaps in the new build, relaunches.

    It runs DETACHED (no console), which dictates two non-obvious choices:

    * **No ``timeout``.** ``timeout`` reads the console input handle and aborts
      instantly ("Input redirection is not supported") when there's no console,
      which turned the wait into a CPU-pegging busy-loop. ``ping -n 2`` is the
      console-free ~1s sleep instead.
    * **Always relaunch.** The caller quits Spuk the moment this is staged, so a
      failed swap used to leave the user with a vanished app ("closes and never
      comes back"). If ``robocopy`` can't write the install dir (file locked, or
      an admin-only location like Program Files) we relaunch the freshly
      downloaded copy instead, so Spuk always returns. robocopy output is logged
      to ``%TEMP%\\spuk_update.log`` for post-mortem.
    """
    return (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul && (ping -n 2 127.0.0.1 >nul & goto wait)\r\n'
        f'robocopy "{new_dir}" "{cur_dir}" /MIR /NFL /NDL /NJH /NJS /NP >"%TEMP%\\spuk_update.log" 2>&1\r\n'
        f'if exist "{cur_dir}\\Spuk.exe" (start "" "{cur_dir}\\Spuk.exe") '
        f'else (start "" "{new_dir}\\Spuk.exe")\r\n'
    )


def _apply_windows(extract_dir: Path) -> None:
    new_exe = next(iter(extract_dir.rglob("Spuk.exe")), None)
    if new_exe is None:
        raise RuntimeError("Couldn't locate Spuk.exe in the download.")
    bat = extract_dir.parent / "spuk_update.bat"
    bat.write_text(
        _windows_update_script(new_exe.parent, Path(sys.executable).resolve().parent, os.getpid())
    )
    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=DETACHED_PROCESS, close_fds=True)


def self_update(
    asset_url: str | None,
    progress: Callable[[int, int], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> None:
    """Download this platform's release asset and stage an in-place swap + relaunch.

    Spawns a detached helper that waits for THIS process to exit, replaces the
    installed app, and relaunches it. The caller must quit Spuk immediately after
    this returns. ``progress`` / ``cancel`` are forwarded to the download so the UI
    can show a progress bar and let the user back out. Raises on any failure (and
    ``UpdateCancelled`` on cancel) so the UI can react accordingly.
    """
    if not asset_url:
        raise RuntimeError("No download is available for this platform.")
    if not can_self_update():
        raise RuntimeError("Self-update only works in the installed app, not when run from source.")

    tmp = Path(tempfile.mkdtemp(prefix="spuk-update-"))
    extract_dir = tmp / "extracted"
    extract_dir.mkdir()
    zip_path = _download_zip(asset_url, tmp, progress=progress, cancel=cancel)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)

    if sys.platform == "darwin":
        _apply_macos(extract_dir)
    elif sys.platform == "win32":
        _apply_windows(extract_dir)
    else:  # pragma: no cover - guarded by can_self_update()
        raise RuntimeError("Self-update isn't supported on this platform.")
