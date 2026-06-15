"""macOS Accessibility permission helper.

The global hotkey and synthetic paste need Accessibility trust. macOS shows no
automatic popup for command-line tools, so we explicitly trigger the system
prompt via AXIsProcessTrustedWithOptions. That call also *registers* the app in
System Settings → Privacy & Security → Accessibility, so the user no longer has
to add it by hand with the "+" button.
"""

from __future__ import annotations

import logging
import platform

log = logging.getLogger("spuk.permissions")


def ensure_accessibility(prompt: bool = True) -> bool:
    """Return True if trusted for Accessibility. On macOS, optionally prompt.

    Non-macOS platforms always return True (no equivalent gate for the hotkey).
    """
    if platform.system() != "Darwin":
        return True
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not check Accessibility trust: %s", exc)
        return True

    trusted = bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)}))
    if not trusted:
        log.warning(
            "Not trusted for Accessibility yet. macOS should have opened a prompt — "
            "click 'Open System Settings', enable this app under Accessibility, then "
            "FULLY QUIT (Cmd+Q) the app and relaunch. The hotkey won't work until then."
        )
    return trusted
