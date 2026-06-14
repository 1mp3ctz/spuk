"""Insert text into the focused field via clipboard + synthetic Cmd+V.

Why clipboard-paste and not per-character keystroke injection:
synthetic key events pass through the active keyboard layout and dead-key state
machine. On a German layout, umlauts (ä ö ü ß) and dead keys (^ ´ `) get
mangled, dropped, or combined with the next character. Clipboard + Cmd+V inserts
the EXACT string in one atomic, layout-independent action — umlaut-safe.

The cost is clobbering the user's clipboard, which we mitigate by saving and
restoring it. Known limitation: pyperclip handles text only, so a non-text
clipboard item (image/files) won't round-trip. Logged when relevant; a faithful
NSPasteboard save/restore is a Phase 2 upgrade.
"""

from __future__ import annotations

import logging
import time

import pyperclip
from pynput.keyboard import Controller, Key

log = logging.getLogger("spuk.paste")

_keyboard = Controller()

# Small settle delays. Too short and the target app pastes stale clipboard
# contents or we restore before it has read the new value.
_SET_SETTLE_S = 0.05
_PASTE_SETTLE_S = 0.15


def paste_text(text: str) -> None:
    """Set the clipboard to ``text``, send Cmd+V, then restore the prior clipboard."""
    if not text:
        return

    try:
        previous = pyperclip.paste()
    except Exception as exc:  # non-text clipboard, or pasteboard access issue
        log.warning("Could not read existing clipboard (will not restore): %s", exc)
        previous = None

    try:
        pyperclip.copy(text)
        time.sleep(_SET_SETTLE_S)
        _send_cmd_v()
        time.sleep(_PASTE_SETTLE_S)
    finally:
        if previous is not None:
            try:
                pyperclip.copy(previous)
            except Exception as exc:
                log.warning("Could not restore clipboard: %s", exc)


def _send_cmd_v() -> None:
    _keyboard.press(Key.cmd)
    _keyboard.press("v")
    _keyboard.release("v")
    _keyboard.release(Key.cmd)
