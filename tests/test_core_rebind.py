from spuk.config import HotkeyConfig
from spuk.core import with_hotkey, hotkey_settings


def _hk():
    return HotkeyConfig(mode="push_to_talk", key="<ctrl>+<alt>",
                        cycle_language="<ctrl>+<shift>+l", handsfree=True, double_tap_seconds=0.4)


def test_with_hotkey_builds_new_immutable_config():
    hk = _hk()
    new = with_hotkey(hk, key="<ctrl>+<shift>+<space>", mode="toggle")
    assert new.key == "<ctrl>+<shift>+<space>"
    assert new.mode == "toggle"
    assert new.cycle_language == hk.cycle_language  # untouched
    assert new.double_tap_seconds == hk.double_tap_seconds
    assert hk.key == "<ctrl>+<alt>"                 # original NOT mutated


def test_with_hotkey_no_changes_returns_equivalent():
    hk = _hk()
    new = with_hotkey(hk)
    assert new == hk


def test_hotkey_settings_maps_only_changed_fields():
    assert hotkey_settings(key="<ctrl>+<alt>+x") == {"hotkey_key": "<ctrl>+<alt>+x"}
    out = hotkey_settings(mode="toggle", handsfree=False)
    assert out == {"hotkey_mode": "toggle", "hotkey_handsfree": False}
    assert hotkey_settings() == {}


def test_with_hotkey_and_settings_handle_paste_key():
    hk = _hk()
    new = with_hotkey(hk, paste_key="<ctrl>+<shift>+v")
    assert new.paste_key == "<ctrl>+<shift>+v"
    assert hk.paste_key == ""  # default, original unchanged
    assert hotkey_settings(paste_key="<ctrl>+<shift>+v") == {"paste_key": "<ctrl>+<shift>+v"}
