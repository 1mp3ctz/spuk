import pynput.keyboard as kb
from pynput.keyboard import Key, KeyCode

import spuk.paste as paste


def test_resolve_default_per_platform(monkeypatch):
    monkeypatch.setattr(paste.platform, "system", lambda: "Darwin")
    assert paste._resolve_combo(None) == "<cmd>+v"
    assert paste._resolve_combo("") == "<cmd>+v"
    monkeypatch.setattr(paste.platform, "system", lambda: "Windows")
    assert paste._resolve_combo(None) == "<ctrl>+v"
    monkeypatch.setattr(paste.platform, "system", lambda: "Linux")
    assert paste._resolve_combo(None) == "<ctrl>+v"


def test_resolve_keeps_explicit_combo(monkeypatch):
    monkeypatch.setattr(paste.platform, "system", lambda: "Windows")
    assert paste._resolve_combo("<ctrl>+<shift>+v") == "<ctrl>+<shift>+v"


def test_pynput_injector_sends_combo_in_press_then_reverse_release(monkeypatch):
    events = []

    class FakeController:
        def press(self, k):
            events.append(("press", k))

        def release(self, k):
            events.append(("release", k))

    monkeypatch.setattr(kb, "Controller", FakeController)
    inj = paste._build_pynput_injector("<ctrl>+<shift>+v")
    inj()
    assert events == [
        ("press", Key.ctrl),
        ("press", Key.shift),
        ("press", KeyCode.from_char("v")),
        ("release", KeyCode.from_char("v")),
        ("release", Key.shift),
        ("release", Key.ctrl),
    ]


def test_set_paste_shortcut_updates_combo_and_invalidates_cache():
    paste._injector = object()  # pretend an injector is cached
    paste.set_paste_shortcut("<ctrl>+<shift>+v")
    assert paste._paste_combo == "<ctrl>+<shift>+v"
    assert paste._injector is None
    paste.set_paste_shortcut("")  # empty normalises to None (OS default)
    assert paste._paste_combo is None
