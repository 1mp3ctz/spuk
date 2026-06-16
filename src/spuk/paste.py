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

# Sentinel stored in `paste_key` selecting "type the text" instead of sending a
# paste shortcut. The classic Windows console (cmd/conhost) has NO paste shortcut
# — paste is right-click only — so clipboard+shortcut can't reach it. Typing the
# characters reaches any focused window. See `_type_text`.
TYPE_OUT = "type"
_paste_mode: str = "shortcut"  # "shortcut" (clipboard + key combo) or "type"
# A typer is "inject this text as keystrokes now". Built lazily by platform.
Typer = Callable[[str], None]
_typer: Typer | None = None


class TypingUnavailable(Exception):
    """The platform can't type here (e.g. no ydotool on Linux) → fall back to paste."""


def _default_paste_combo() -> str:
    return "<cmd>+v" if platform.system() == "Darwin" else "<ctrl>+v"


def _resolve_combo(combo: str | None) -> str:
    """The combo to actually send: the user's choice, or the OS default."""
    return combo if combo else _default_paste_combo()


def set_paste_shortcut(combo: str | None) -> None:
    """Choose how Spuk inserts text; applied on the next paste.

    ``combo`` is a canonical combo string ("<ctrl>+<shift>+v"), None/"" for the OS
    default paste shortcut, or the ``TYPE_OUT`` sentinel ("type") to type the text
    out as keystrokes instead (for the classic Windows console / paste-blocked
    apps). Safe to call anytime — the injector/typer is rebuilt on the next paste.
    """
    global _paste_combo, _injector, _paste_mode, _typer
    if combo == TYPE_OUT:
        _paste_mode = "type"
        _typer = None  # force a rebuild
        return
    _paste_mode = "shortcut"
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


# --- "type it out" mode ----------------------------------------------------


def _utf16_units(text: str) -> tuple[int, ...]:
    """UTF-16 code units for ``text`` (non-BMP chars become surrogate pairs).

    This is what Windows' ``SendInput`` + ``KEYEVENTF_UNICODE`` injects per event,
    independent of the active keyboard layout — so umlauts/dead-key characters
    (ä ö ü ß ^ ´) come through exactly, unlike naive scan-code typing.
    """
    import struct

    data = text.encode("utf-16-le")
    return struct.unpack(f"<{len(data) // 2}H", data) if data else ()


def _build_windows_typer() -> Typer:
    """Windows typer: inject each character via SendInput + KEYEVENTF_UNICODE.

    Layout-independent (Unicode), so it works in the classic console and is
    umlaut-safe. All ctypes/wintypes access is inside here so non-Windows never
    touches it.
    """
    import ctypes
    from ctypes import wintypes

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _KBUnion(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _KBUnion)]

    send_input = ctypes.windll.user32.SendInput

    def typer(text: str) -> None:
        units = _utf16_units(text)
        if not units:
            return
        buf = (INPUT * (len(units) * 2))()
        i = 0
        for code in units:
            for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                buf[i].type = INPUT_KEYBOARD
                buf[i].u.ki = KEYBDINPUT(0, code, flags, 0, None)
                i += 1
        send_input(len(buf), buf, ctypes.sizeof(INPUT))

    return typer


def _build_pynput_typer() -> Typer:
    """macOS typer: pynput's Controller.type, which injects Unicode (umlaut-safe)."""
    from pynput.keyboard import Controller

    keyboard = Controller()

    def typer(text: str) -> None:
        keyboard.type(text)

    return typer


def _build_typer() -> Typer:
    """Pick the typer for this platform. Raises TypingUnavailable when none works."""
    system = platform.system()
    if system == "Windows":
        return _build_windows_typer()
    if system == "Darwin":
        return _build_pynput_typer()
    # Linux: typing arbitrary Unicode via /dev/uinput needs ydotool; when it's
    # absent we raise so the caller falls back to clipboard paste (Linux terminals
    # accept Ctrl+Shift+V, so there's no console gap to work around there).
    from .linux_input import build_linux_typer

    typer = build_linux_typer()
    if typer is None:
        raise TypingUnavailable("no ydotool found for type-out on Linux")
    return typer


def _type_text(text: str) -> None:
    """Type ``text`` as keystrokes via the cached platform typer."""
    global _typer
    if _typer is None:
        _typer = _build_typer()  # may raise TypingUnavailable
    _typer(text)


def paste_text(text: str) -> None:
    """Insert ``text`` into the focused field.

    In "type" mode, type it out as keystrokes (works in the classic Windows
    console, doesn't touch the clipboard). Otherwise set the clipboard, send the
    paste shortcut, and restore the clipboard.
    """
    if not text:
        return

    if _paste_mode == "type":
        try:
            _type_text(text)
            return
        except TypingUnavailable as exc:
            # Nothing was typed yet → safe to fall back to clipboard paste.
            log.warning("Type-out unavailable (%s) — falling back to clipboard paste.", exc)
        except Exception as exc:  # noqa: BLE001
            # A mid-typing failure may have inserted part of the text; do NOT also
            # paste (that would double-insert). Log and stop.
            log.error("Type-out failed: %s", exc)
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
