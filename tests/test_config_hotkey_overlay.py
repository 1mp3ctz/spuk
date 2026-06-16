import spuk.settings_store as ss
from spuk.config import _overlay_user_hotkey


def _defaults() -> dict:
    return {
        "key": "<ctrl>+<alt>",
        "cycle_language": "<ctrl>+<shift>+l",
        "mode": "push_to_talk",
        "handsfree": True,
        "double_tap_seconds": 0.4,
    }


def test_overlay_applies_saved_values(monkeypatch):
    monkeypatch.setattr(ss, "load_user_settings", lambda: {
        "hotkey_key": "<ctrl>+<shift>+<space>",
        "hotkey_cycle_language": "<ctrl>+<alt>+c",
        "hotkey_mode": "toggle",
        "hotkey_handsfree": False,
    })
    h = _defaults()
    _overlay_user_hotkey(h)
    assert h["key"] == "<ctrl>+<shift>+<space>"
    assert h["cycle_language"] == "<ctrl>+<alt>+c"
    assert h["mode"] == "toggle"
    assert h["handsfree"] is False


def test_overlay_ignores_missing_and_invalid(monkeypatch):
    monkeypatch.setattr(ss, "load_user_settings", lambda: {
        "hotkey_key": "",            # blank -> ignored
        "hotkey_mode": "nonsense",   # invalid -> ignored
    })
    h = _defaults()
    _overlay_user_hotkey(h)
    assert h["key"] == "<ctrl>+<alt>"       # unchanged
    assert h["mode"] == "push_to_talk"      # unchanged
    assert h["handsfree"] is True           # unchanged


def test_overlay_no_settings_keeps_defaults(monkeypatch):
    monkeypatch.setattr(ss, "load_user_settings", lambda: {})
    h = _defaults()
    _overlay_user_hotkey(h)
    assert h == _defaults()
