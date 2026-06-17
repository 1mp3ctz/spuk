"""The hotkey FSM must not wedge when a modifier key-up is dropped.

macOS/pynput reliably delivers key-DOWN events but routinely drops modifier
key-UP events (on focus changes, when the event tap briefly stalls, during fast
tapping). Modifier-only chords like the default ``<ctrl>+<alt>`` are the most
exposed. Before the self-heal, a dropped release left ``_pressed`` stuck holding
the chord and ``_chord_down`` stuck True forever, so the recorder never stopped
and no further hotkey press could reach the stop branch — the mic stayed on with
no way to shut it off.

These tests drive the REAL key-event path (``_feed_press``/``_feed_release``),
unlike test_hotkey_handsfree.py which drives ``_chord_edge`` directly and so
never exercised this layer.
"""

import unittest

from pynput import keyboard

import spuk.hotkey as H
from spuk.hotkey import HotkeyListener, _is_modifier

CTRL = keyboard.Key.ctrl
ALT = keyboard.Key.alt
LETTER_L = keyboard.KeyCode.from_char("l")


def make(key_combo="<ctrl>+<alt>", mode="push_to_talk", handsfree=True, double=0.4):
    events: list[str] = []
    hl = HotkeyListener(
        key_combo=key_combo,
        mode=mode,
        on_start=lambda: events.append("start"),
        on_stop=lambda: events.append("stop"),
        on_cancel=lambda: events.append("cancel"),
        handsfree=handsfree,
        double_tap_seconds=double,
    )
    return hl, events


class ModifierDetection(unittest.TestCase):
    def test_modifiers_are_detected(self):
        self.assertTrue(_is_modifier(CTRL))
        self.assertTrue(_is_modifier(ALT))
        self.assertTrue(_is_modifier(keyboard.Key.shift))
        self.assertTrue(_is_modifier(keyboard.Key.cmd))

    def test_letters_are_not_modifiers(self):
        self.assertFalse(_is_modifier(LETTER_L))


class DroppedReleaseSelfHeal(unittest.TestCase):
    def setUp(self):
        self._clock = [0.0]
        self._orig = H.time.monotonic
        H.time.monotonic = lambda: self._clock[0]

    def tearDown(self):
        H.time.monotonic = self._orig

    def _t(self, value):
        self._clock[0] = value

    def test_dropped_release_no_longer_wedges_recording(self):
        """The exact reproduction: chord down, both key-ups dropped, then the user
        presses the chord again to stop. It must actually stop."""
        hl, ev = make()
        # Chord pressed and held; macOS never delivers the key-ups.
        self._t(0.0)
        hl._feed_press(CTRL)
        hl._feed_press(ALT)
        self.assertTrue(hl._recording, "phantom hold should be recording")
        self.assertTrue(hl._chord_down)

        # User presses Ctrl+Alt again to stop (key-downs are reliable), then
        # releases normally after a clear hold.
        self._t(2.0)
        hl._feed_press(CTRL)
        hl._feed_press(ALT)
        self._t(2.6)  # held 0.6s > 0.4 cutoff -> a real hold -> stop+transcribe
        hl._feed_release(ALT)
        hl._feed_release(CTRL)

        self.assertFalse(hl._recording, "re-press must be able to stop the recording")
        self.assertFalse(hl._chord_down)
        self.assertEqual(hl._pressed, set())
        self.assertIn("stop", ev)

    def test_letter_autorepeat_is_still_ignored(self):
        """Non-modifier keys DO auto-repeat; a repeated key-down for a held letter
        must NOT be treated as a missed release (no spurious re-trigger)."""
        hl, ev = make(key_combo="<ctrl>+l")
        self._t(0.0)
        hl._feed_press(CTRL)
        hl._feed_press(LETTER_L)  # chord completes -> one start
        self._t(0.1)
        hl._feed_press(LETTER_L)  # auto-repeat of the held letter -> ignored
        self._t(0.2)
        hl._feed_press(LETTER_L)  # still held
        self.assertEqual(ev.count("start"), 1, "letter auto-repeat must not re-fire the chord")

    def test_reset_state_clears_a_wedged_chord(self):
        """The escape hatch the UI calls: forcibly clear stuck key state."""
        hl, _ev = make()
        self._t(0.0)
        hl._feed_press(CTRL)
        hl._feed_press(ALT)
        self.assertTrue(hl._chord_down)
        self.assertTrue(hl._recording)

        hl.reset_state()

        self.assertFalse(hl._chord_down)
        self.assertFalse(hl._recording)
        self.assertFalse(hl._latched)
        self.assertEqual(hl._pressed, set())


if __name__ == "__main__":
    unittest.main()
