"""Capture the frontmost window to a PNG and put it on the clipboard (macOS).

Pure helpers (pick_window) and the screencapture argv are unit-tested; the Cocoa
calls (NSWorkspace, CGWindowListCopyWindowInfo, NSPasteboard) sit behind thin
wrappers exercised by the opt-in integration check and the live app.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile

log = logging.getLogger("spuk.screenshot")


def pick_window(window_infos: list[dict], pid: int) -> int | None:
    """Pick the frontmost on-screen window (layer 0) owned by ``pid``.

    Among that owner's layer-0 windows, choose the largest by area — the real
    document window rather than a small panel. Returns its window number, or None.
    """
    candidates = [
        w
        for w in window_infos
        if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0
    ]
    if not candidates:
        return None

    def area(w: dict) -> float:
        b = w.get("kCGWindowBounds") or {}
        return float(b.get("Width", 0)) * float(b.get("Height", 0))

    best = max(candidates, key=area)
    number = best.get("kCGWindowNumber")
    return int(number) if number is not None else None


def capture_window_to_png(window_id: int, path: str, *, runner=subprocess.run) -> None:
    """Capture exactly ``window_id`` to ``path``: no sound (-x), no shadow (-o)."""
    runner(["screencapture", "-x", "-o", "-l", str(window_id), path], check=True)


def front_window_png() -> str | None:
    """Capture the frontmost app's front window to a temp PNG; return path or None."""
    try:
        from AppKit import NSWorkspace
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception as exc:  # noqa: BLE001 - non-macOS / framework missing
        log.debug("screenshot frameworks unavailable: %s", exc)
        return None

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    pid = app.processIdentifier()
    infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    window_id = pick_window(list(infos), pid)
    if window_id is None:
        log.info("No capturable front window for pid %s.", pid)
        return None

    fd, path = tempfile.mkstemp(suffix=".png", prefix="spuk-shot-")
    os.close(fd)
    try:
        capture_window_to_png(window_id, path)
        return path
    except Exception as exc:  # noqa: BLE001
        log.error("screencapture failed: %s", exc)
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def copy_image_to_clipboard(path: str) -> None:
    """Write the PNG at ``path`` to the general pasteboard as image data."""
    import platform
    if platform.system() != "Darwin":
        raise RuntimeError("clipboard image copy is macOS-only")
    from AppKit import NSPasteboard, NSPasteboardTypePNG
    from Foundation import NSData

    data = NSData.dataWithContentsOfFile_(path)
    if data is None:
        raise FileNotFoundError(path)
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setData_forType_(data, NSPasteboardTypePNG)


# macOS ships the camera-shutter sound used for screenshots; play it so the user
# HEARS that a capture happened (screencapture itself is silenced with -x).
_SHUTTER_SOUNDS = (
    "/System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds/system/Shutter.aif",
    "/System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds/system/Grab.aif",
    "/System/Library/Sounds/Pop.aiff",
)


def play_capture_sound() -> None:
    """Best-effort: play the macOS shutter sound so the capture is audible.

    Fire-and-forget (non-blocking) and never raises — a missing sound file or
    afplay just means no sound, not a failed screenshot. No-op off macOS.
    """
    import platform

    if platform.system() != "Darwin":
        return
    path = next((p for p in _SHUTTER_SOUNDS if os.path.exists(p)), None)
    if path is None:
        return
    try:
        subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001 - sound is optional feedback
        log.debug("could not play capture sound: %s", exc)


def shoot_and_paste(
    *, capture=front_window_png, copy=copy_image_to_clipboard, paste=None,
    sound=play_capture_sound,
) -> bool:
    """Capture the front window → clipboard → sound → paste into the focused field.

    Returns False (and does nothing further) when capture fails. The image is left
    on the clipboard on purpose, so the user can paste it again. We deliberately do
    NOT restore the previous clipboard — "copy it right away" is the feature. The
    shutter sound fires only after a real capture lands on the clipboard.
    """
    if paste is None:
        from .paste import send_paste_shortcut

        paste = send_paste_shortcut
    path = capture()
    if not path:
        return False
    try:
        copy(path)
        sound()
        paste()
        return True
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
