"""'Type it out' paste mode — types Unicode directly instead of clipboard+shortcut.

Targets the classic Windows console (cmd/conhost), which has no paste shortcut
(paste is right-click only). Typing reaches any focused window.
"""

import spuk.paste as paste


def _reset():
    paste._paste_mode = "shortcut"
    paste._paste_combo = None
    paste._injector = None
    paste._typer = None


def test_utf16_units_ascii_umlaut_emoji():
    assert paste._utf16_units("ab") == (0x61, 0x62)
    assert paste._utf16_units("ä") == (0x00E4,)          # layout-independent codepoint
    assert paste._utf16_units("😀") == (0xD83D, 0xDE00)  # non-BMP -> surrogate pair
    assert paste._utf16_units("") == ()


def test_set_paste_shortcut_type_enables_type_mode():
    _reset()
    paste._typer = object()  # pretend a typer is cached
    paste.set_paste_shortcut("type")
    assert paste._paste_mode == "type"
    assert paste._typer is None                          # cache invalidated
    # switching back to a real combo leaves type mode
    paste.set_paste_shortcut("<ctrl>+<shift>+v")
    assert paste._paste_mode == "shortcut"
    assert paste._paste_combo == "<ctrl>+<shift>+v"
    _reset()


def test_type_mode_types_text_and_does_not_touch_clipboard(monkeypatch):
    _reset()
    typed, copied = [], []
    monkeypatch.setattr(paste, "_build_typer", lambda: typed.append)
    monkeypatch.setattr(paste.pyperclip, "copy", lambda s: copied.append(s))
    monkeypatch.setattr(paste.pyperclip, "paste", lambda: "")
    paste.set_paste_shortcut("type")
    paste.paste_text("hä llo")
    assert typed == ["hä llo"]      # typed exactly, umlaut intact
    assert copied == []             # clipboard never used in type mode
    _reset()


def test_type_unavailable_falls_back_to_clipboard_paste(monkeypatch):
    _reset()
    copied, pasted = [], []

    def boom():
        raise paste.TypingUnavailable("no ydotool")

    monkeypatch.setattr(paste, "_build_typer", boom)
    monkeypatch.setattr(paste.pyperclip, "copy", lambda s: copied.append(s))
    monkeypatch.setattr(paste.pyperclip, "paste", lambda: "old")
    paste._injector = lambda: pasted.append("paste")  # fake shortcut injector
    paste.set_paste_shortcut("type")
    paste._typer = None
    paste.paste_text("text")
    assert "text" in copied         # fell back to clipboard
    assert pasted == ["paste"]      # and sent the paste shortcut
    _reset()
