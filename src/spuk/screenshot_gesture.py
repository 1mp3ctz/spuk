"""Start/stop the dual-⌘ screenshot gesture for the tray and floating-bar apps.

macOS-only. Owns nothing about capture mechanics (see screenshot.py) — it just
connects the MacFlagsTap to an off-thread shoot_and_paste, and asks for the
Screen Recording permission the first time it's enabled.
"""

from __future__ import annotations

import logging
import platform
import threading

from .mac_flags_tap import MacFlagsTap
from .permissions import request_screen_recording, screen_recording_trusted

log = logging.getLogger("spuk.screenshot_gesture")


def run_capture_async() -> None:
    """Run capture→clipboard→paste off the tap thread (it blocks on screencapture)."""
    from .screenshot import shoot_and_paste

    def work() -> None:
        try:
            shoot_and_paste()
        except Exception as exc:  # noqa: BLE001
            log.error("screenshot gesture failed: %s", exc)

    threading.Thread(target=work, name="spuk-shoot", daemon=True).start()


def start_if_enabled(config) -> MacFlagsTap | None:
    """Start the dual-⌘ tap when on macOS and enabled. Returns the tap or None."""
    if platform.system() != "Darwin":
        return None
    if not getattr(config.screenshot, "enabled", False):
        return None
    if screen_recording_trusted() is False:
        request_screen_recording()
    log.info("Dual-⌘ screenshot gesture armed (press both Command keys).")
    return MacFlagsTap(on_dual_cmd=run_capture_async).start()
