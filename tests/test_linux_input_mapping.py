"""Tests for the Linux evdev→canonical-key mapping and availability guard.

These are pure-logic tests: the mapping is keyed on evdev KEY_* *names* (strings),
so the real ``evdev`` C extension (which only builds on Linux) is never imported.
The canonical keys are the same ``pynput.keyboard`` objects the chord FSM matches
against, which import fine on macOS.
"""

import unittest

from pynput.keyboard import Key, KeyCode

from spuk import linux_input


class CanonicalKeyMapping(unittest.TestCase):
    def test_left_and_right_ctrl_collapse_to_generic_ctrl(self):
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_LEFTCTRL"), Key.ctrl)
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_RIGHTCTRL"), Key.ctrl)

    def test_left_and_right_alt_collapse_to_generic_alt(self):
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_LEFTALT"), Key.alt)
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_RIGHTALT"), Key.alt)

    def test_left_and_right_shift_collapse_to_generic_shift(self):
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_LEFTSHIFT"), Key.shift)
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_RIGHTSHIFT"), Key.shift)

    def test_meta_maps_to_cmd(self):
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_LEFTMETA"), Key.cmd)
        self.assertIs(linux_input.canonical_key_for_keyname("KEY_RIGHTMETA"), Key.cmd)

    def test_letter_maps_to_lowercase_keycode(self):
        self.assertEqual(linux_input.canonical_key_for_keyname("KEY_L"), KeyCode.from_char("l"))
        self.assertEqual(linux_input.canonical_key_for_keyname("KEY_A"), KeyCode.from_char("a"))

    def test_digit_maps_to_keycode(self):
        self.assertEqual(linux_input.canonical_key_for_keyname("KEY_5"), KeyCode.from_char("5"))

    def test_unrelated_key_is_none(self):
        # Keys Spuk's hotkeys never use return None so the reader skips them.
        self.assertIsNone(linux_input.canonical_key_for_keyname("KEY_F1"))
        self.assertIsNone(linux_input.canonical_key_for_keyname("KEY_ENTER"))
        self.assertIsNone(linux_input.canonical_key_for_keyname("KEY_SPACE"))
        self.assertIsNone(linux_input.canonical_key_for_keyname("BTN_LEFT"))

    def test_matches_what_hotkey_parse_produces(self):
        # The whole point: evdev-derived keys must equal the FSM's expected set.
        from pynput import keyboard

        expected = set(keyboard.HotKey.parse("<ctrl>+<alt>"))
        evdev_derived = {
            linux_input.canonical_key_for_keyname("KEY_LEFTCTRL"),
            linux_input.canonical_key_for_keyname("KEY_RIGHTALT"),
        }
        self.assertEqual(evdev_derived, expected)


class CanonicalKeyForNames(unittest.TestCase):
    def test_resolves_first_meaningful_name_from_list(self):
        # evdev sometimes maps one keycode to a list of aliases.
        names = ["KEY_LEFTCTRL", "KEY_LEFTCTRL_ALIAS"]
        self.assertIs(linux_input.canonical_key_for_keynames(names), Key.ctrl)

    def test_list_with_no_match_is_none(self):
        self.assertIsNone(linux_input.canonical_key_for_keynames(["KEY_F1", "KEY_F2"]))

    def test_single_string_name(self):
        self.assertIs(linux_input.canonical_key_for_keynames("KEY_LEFTALT"), Key.alt)


class Availability(unittest.TestCase):
    def test_linux_input_available_is_false_without_evdev(self):
        # evdev is not installed on the dev (macOS) machine; the guard must
        # return False rather than raising.
        self.assertFalse(linux_input.linux_input_available())


if __name__ == "__main__":
    unittest.main()
