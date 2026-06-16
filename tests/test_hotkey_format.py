import pytest
from pynput.keyboard import Key, KeyCode

from spuk.hotkey_format import keys_to_combo_string, combo_to_label, validate_combo


def test_keys_to_combo_string_modifier_only():
    assert keys_to_combo_string({Key.ctrl, Key.alt}) == "<ctrl>+<alt>"


def test_keys_to_combo_string_orders_modifiers_consistently():
    # order of input must not matter; output order is fixed (cmd,ctrl,alt,shift)
    assert keys_to_combo_string({Key.alt, Key.ctrl}) == "<ctrl>+<alt>"
    assert keys_to_combo_string({Key.shift, Key.ctrl}) == "<ctrl>+<shift>"


def test_keys_to_combo_string_with_letter():
    assert keys_to_combo_string([Key.ctrl, Key.shift, KeyCode.from_char("L")]) == "<ctrl>+<shift>+l"


def test_keys_to_combo_string_special_key():
    assert keys_to_combo_string({Key.f8}) == "<f8>"


def test_combo_to_label_is_friendly():
    assert combo_to_label("<ctrl>+<alt>") == "Ctrl + Alt"
    assert combo_to_label("<ctrl>+<shift>+l") == "Ctrl + Shift + L"


@pytest.mark.parametrize(
    "combo, ok",
    [
        ("<ctrl>+<alt>", True),       # modifier-only is fine (it's the default)
        ("<ctrl>+<shift>+l", True),   # modifier + letter
        ("<f8>", True),               # lone special/function key is fine
        ("l", False),                 # bare printable letter would type
        ("", False),                  # empty
    ],
)
def test_validate_combo_basic(combo, ok):
    result_ok, _msg = validate_combo(combo, mode="push_to_talk")
    assert result_ok is ok


def test_validate_combo_rejects_collision_with_other():
    ok, msg = validate_combo("<ctrl>+<alt>", mode="push_to_talk", other_combo="<ctrl>+<alt>")
    assert ok is False
    assert "already" in msg.lower()


def test_validate_combo_warns_on_altgr_but_allows():
    ok, msg = validate_combo("<ctrl>+<alt>", mode="push_to_talk")
    assert ok is True
    assert msg is not None and "altgr" in msg.lower()
