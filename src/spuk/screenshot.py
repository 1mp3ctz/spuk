"""Capture the frontmost window to a PNG and put it on the clipboard (macOS).

Pure helpers (pick_window) and the screencapture argv are unit-tested; the Cocoa
calls (NSWorkspace, CGWindowListCopyWindowInfo, NSPasteboard) sit behind thin
wrappers exercised by the opt-in integration check and the live app.
"""

from __future__ import annotations

import logging
import subprocess

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
