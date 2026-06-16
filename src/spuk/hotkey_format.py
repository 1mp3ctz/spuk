"""Pure helpers for hotkey combos: format pressed keys, label, validate.

The canonical combo string is the pynput parse format that ``hotkey.py`` parses
via ``keyboard.HotKey.parse`` and ``linux_input.py`` maps: modifiers as
``<ctrl>``/``<alt>``/``<shift>``/``<cmd>``, special keys as ``<name>`` (e.g.
``<f8>``), printable keys as the bare lowercased character. Joined with ``+``,
modifiers first in a fixed order so two presses of the same chord normalise
identically.
"""

from __future__ import annotations

import platform

_MOD_ORDER = ("cmd", "ctrl", "alt", "shift")
_MOD_TOKENS = {m: f"<{m}>" for m in _MOD_ORDER}
_MOD_TOKEN_SET = set(_MOD_TOKENS.values())

# Friendly, deterministic labels. The only OS-dependent name is the Super key,
# which is genuinely "Cmd" on macOS and "Win" elsewhere.
_MAC = platform.system() == "Darwin"
_LABELS = {
    "<ctrl>": "Ctrl",
    "<alt>": "Alt",
    "<shift>": "Shift",
    "<cmd>": "Cmd" if _MAC else "Win",
}


def keys_to_combo_string(keys) -> str:
    """Build a canonical ``<ctrl>+<alt>+l`` string from pynput Key/KeyCode objects."""
    from pynput.keyboard import Key, KeyCode

    mods: list[str] = []
    others: list[str] = []
    for k in keys:
        if isinstance(k, Key):
            name = k.name  # 'ctrl','alt','shift','cmd','f8','space',...
            if name in _MOD_ORDER:
                if name not in mods:
                    mods.append(name)
            else:
                tok = f"<{name}>"
                if tok not in others:
                    others.append(tok)
        elif isinstance(k, KeyCode) and getattr(k, "char", None):
            tok = k.char.lower()
            if tok not in others:
                others.append(tok)
    ordered = [_MOD_TOKENS[m] for m in _MOD_ORDER if m in mods]
    return "+".join(ordered + others)


def _tokens(combo: str) -> list[str]:
    return [t for t in combo.split("+") if t]


def combo_to_label(combo: str) -> str:
    """``<ctrl>+<shift>+l`` -> ``Ctrl + Shift + L`` (OS-aware modifier names)."""
    out = []
    for t in _tokens(combo):
        if t in _LABELS:
            out.append(_LABELS[t])
        elif t.startswith("<") and t.endswith(">"):
            out.append(t[1:-1].upper())  # <f8> -> F8
        else:
            out.append(t.upper())  # l -> L
    return " + ".join(out)


def validate_combo(combo: str, *, mode: str = "push_to_talk", other_combo: str | None = None):
    """Return ``(ok: bool, message: str | None)``.

    ``message`` is an error when ok is False, or a non-blocking warning when ok
    is True (e.g. the AltGr caveat).
    """
    tokens = _tokens(combo)
    if not tokens:
        return False, "Press at least one key."

    mods = [t for t in tokens if t in _MOD_TOKEN_SET]
    non_mods = [t for t in tokens if t not in _MOD_TOKEN_SET]
    printable = [t for t in non_mods if not t.startswith("<")]
    specials = [t for t in non_mods if t.startswith("<")]

    # A bare printable key with no modifier and no special would fire while typing.
    if not mods and printable and not specials:
        return False, "Add a modifier (like Ctrl or Alt) — a plain key would fire while you type."

    if other_combo and tokens == _tokens(other_combo):
        return False, "That combo is already used by the other shortcut."

    if set(tokens) == {"<ctrl>", "<alt>"}:
        return True, "Heads-up: on German/Austrian keyboards AltGr sends Ctrl+Alt, which can trigger Spuk."

    return True, None
