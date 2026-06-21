"""Start/stop the dual-⌘ screenshot gesture for the tray and floating-bar apps.

macOS-only. Owns nothing about capture mechanics (see screenshot.py) — it just
connects the MacFlagsTap to an off-thread shoot_and_paste, and asks for the
Screen Recording permission the first time it's enabled.
"""

from __future__ import annotations

import logging
import platform
import threading
from typing import Callable

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


def start_if_enabled(
    config,
    on_fn_press: "Callable[[], None] | None" = None,
    on_fn_release: "Callable[[], None] | None" = None,
) -> "MacFlagsTap | None":
    """Start the flags tap when on macOS and at least one gesture is enabled.

    Starts if screenshot is enabled OR Fn callbacks are provided. A single tap
    handles both gestures so the CGEventTap is registered only once.
    Returns the tap or None.
    """
    if platform.system() != "Darwin":
        return None

    screenshot_enabled = getattr(config.screenshot, "enabled", False)
    fn_enabled = on_fn_press is not None or on_fn_release is not None

    if not screenshot_enabled and not fn_enabled:
        return None

    if screenshot_enabled:
        if screen_recording_trusted() is False:
            request_screen_recording()
        dual_cmd_cb = run_capture_async
        log.info("Dual-⌘ screenshot gesture armed (press both Command keys).")
    else:
        dual_cmd_cb = lambda: None  # noqa: E731 — tap needed for Fn, screenshot off

    if fn_enabled:
        log.info("Fn dictation gesture armed.")

    return MacFlagsTap(
        on_dual_cmd=dual_cmd_cb,
        on_fn_press=on_fn_press,
        on_fn_release=on_fn_release,
    ).start()
