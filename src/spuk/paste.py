"""Insert text into the focused field via clipboard + a synthetic paste shortcut.

Why clipboard-paste and not per-character keystroke injection:
synthetic key events pass through the active keyboard layout and dead-key state
machine. On a German layout, umlauts (ä ö ü ß) and dead keys (^ ´ `) get
mangled, dropped, or combined with the next character. Clipboard + paste inserts
the EXACT string in one atomic, layout-independent action — umlaut-safe.

The cost is clobbering the user's clipboard, which we mitigate by saving and
restoring it. Known limitation: pyperclip handles text only, so a non-text
clipboard item (image/files) won't round-trip. Logged when relevant; a faithful
NSPasteboard save/restore is a Phase 2 upgrade.

This module owns two separable responsibilities:

  * **clipboard** save / set / restore (text via pyperclip) — see ``paste_text``;
  * sending the **paste shortcut** itself, delegated to a pluggable *injector*
    chosen by platform (``_get_injector``). macOS and Windows use pynput
    (Cmd+V / Ctrl+V); Linux uses uinput/ydotool (see ``linux_input``).

Splitting the injector out keeps pynput off the import path on Linux — importing
``paste`` on Linux must NOT construct a pynput ``Controller`` (pynput cannot
inject under Wayland), so the controller is built lazily inside the pynput
injector only.
"""

from __future__ import annotations

import logging
import platform
import time
from typing import Callable

import pyperclip

log = logging.getLogger("spuk.paste")

# Small settle delays. Too short and the target app pastes stale clipboard
# contents or we restore before it has read the new value.
_SET_SETTLE_S = 0.05
_PASTE_SETTLE_S = 0.15

# A paste injector is just "send the paste shortcut now". Built once, lazily, by
# the platform factory below so the wrong backend is never imported/constructed.
PasteInjector = Callable[[], None]
_injector: PasteInjector | None = None
# The paste shortcut Spuk sends. None/"" = the OS default (Cmd+V on macOS, Ctrl+V
# elsewhere). Set via set_paste_shortcut() from config/Settings — e.g.
# "<ctrl>+<shift>+v" so dictation works in terminals (VS Code / Cursor), where
# plain Ctrl+V is not "paste".
_paste_combo: str | None = None


def _default_paste_combo() -> str:
    return "<cmd>+v" if platform.system() == "Darwin" else "<ctrl>+v"


def _resolve_combo(combo: str | None) -> str:
    """The combo to actually send: the user's choice, or the OS default."""
    return combo if combo else _default_paste_combo()


def set_paste_shortcut(combo: str | None) -> None:
    """Choose the shortcut Spuk sends to paste; applied on the next paste.

    ``combo`` is a canonical combo string ("<ctrl>+<shift>+v") or None/"" for the
    OS default. Safe to call anytime — the injector is rebuilt on the next paste.
    """
    global _paste_combo, _injector
    _paste_combo = combo or None
    _injector = None  # force a rebuild with the new combo


def _build_pynput_injector(combo: str | None) -> PasteInjector:
    """macOS/Windows injector: synthesize the paste combo via pynput.

    Imported and constructed lazily so Linux never builds a pynput Controller.
    """
    from pynput.keyboard import Controller, HotKey

    keyboard = Controller()
    keys = HotKey.parse(_resolve_combo(combo))  # e.g. [Key.ctrl, Key.shift, KeyCode('v')]

    def send_paste() -> None:
        for k in keys:
            keyboard.press(k)
        for k in reversed(keys):
            keyboard.release(k)

    return send_paste


def _build_injector() -> PasteInjector:
    """Pick the paste injector for this platform (built once, cached)."""
    if platform.system() == "Linux":
        from .linux_input import build_linux_paste_injector

        return build_linux_paste_injector(_resolve_combo(_paste_combo))
    return _build_pynput_injector(_paste_combo)


def _get_injector() -> PasteInjector:
    global _injector
    if _injector is None:
        _injector = _build_injector()
    return _injector


def paste_text(text: str) -> None:
    """Set the clipboard to ``text``, send the paste shortcut, then restore it."""
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
        _send_paste_shortcut()
        time.sleep(_PASTE_SETTLE_S)
    finally:
        if previous is not None:
            try:
                pyperclip.copy(previous)
            except Exception as exc:
                log.warning("Could not restore clipboard: %s", exc)


def _send_paste_shortcut() -> None:
    """Send the OS paste shortcut via the platform injector. Logs on failure."""
    try:
        _get_injector()()
    except Exception as exc:  # noqa: BLE001 - never let a paste failure crash the loop
        log.error("Could not send paste shortcut: %s", exc)
