"""Regression tests at the REAL key-tracking layer (_feed_press/_feed_release).

The other hotkey tests drive ``_chord_edge()`` directly, which never exercises
the dropped-modifier-release self-heal — exactly where macOS desyncs happen
(macOS reliably delivers modifier key-DOWNs but routinely drops their key-UPs).
These drive the real layer with pynput ``Key`` objects, reproducing the "stuck
mic" class of bug for a modifier-only chord (<ctrl>+<alt>).

The bug: in toggle mode, a dropped key-UP left a stale modifier in ``_pressed``;
on the next press the self-heal discarded only the re-pressed key, so the stale
one re-satisfied the chord and fired a PHANTOM edge on every key-down. Toggling
became unpredictable and the recording could never be reliably stopped.
"""

import unittest

from pynput import keyboard

from spuk.hotkey import HotkeyListener

CTRL = keyboard.Key.ctrl
ALT = keyboard.Key.alt


def make(mode="toggle", handsfree=True, double=0.4):
    ev: list[str] = []
    rec = {"on": False}

    def start() -> None:
        ev.append("start")
        rec["on"] = True

    def stop() -> None:
        ev.append("stop")
        rec["on"] = False

    hl = HotkeyListener(
        key_combo="<ctrl>+<alt>",
        mode=mode,
        on_start=start,
        on_stop=stop,
        on_cancel=lambda: ev.append("cancel"),
        handsfree=handsfree,
        double_tap_seconds=double,
    )
    return hl, ev, rec


def tap_chord_dropped_ups(hl) -> None:
    """Press ctrl then alt and DROP both key-UPs (the macOS failure mode)."""
    hl._feed_press(CTRL)
    hl._feed_press(ALT)
    # both releases dropped by the OS — intentionally not fed


class ToggleDroppedRelease(unittest.TestCase):
    def test_each_tap_toggles_exactly_once(self):
        hl, ev, rec = make(mode="toggle")
        tap_chord_dropped_ups(hl)            # tap 1 -> START
        self.assertEqual(ev, ["start"])
        self.assertTrue(rec["on"])
        tap_chord_dropped_ups(hl)            # tap 2 -> STOP (bug fired start,stop,start)
        self.assertEqual(ev, ["start", "stop"])
        self.assertFalse(rec["on"])          # mic OFF — the user CAN stop

    def test_many_taps_never_leave_mic_stuck(self):
        hl, ev, rec = make(mode="toggle")
        for _ in range(6):                   # 6 taps -> must end OFF
            tap_chord_dropped_ups(hl)
        self.assertFalse(rec["on"])
        self.assertEqual(ev, ["start", "stop"] * 3)  # exactly one edge per tap

    def test_happy_path_all_releases_delivered(self):
        hl, ev, rec = make(mode="toggle")
        for _ in range(2):
            hl._feed_press(CTRL)
            hl._feed_press(ALT)
            hl._feed_release(ALT)
            hl._feed_release(CTRL)
        self.assertEqual(ev, ["start", "stop"])
        self.assertFalse(rec["on"])


class HandsfreeUnwedgePreserved(unittest.TestCase):
    """Preserve the v1.0.9 fix: a hands-free latch wedged by a dropped release
    must still be stoppable by pressing the chord again."""

    def test_rebuild_chord_stops_wedged_latch(self):
        hl, ev, rec = make(mode="push_to_talk", handsfree=True)
        # A wedged hands-free latch: recording, chord believed "down", and both
        # modifiers stale-held because their key-UPs were dropped.
        hl._latched = True
        rec["on"] = True
        hl._chord_down = True
        hl._pressed = {CTRL, ALT}
        # User presses the chord again to stop it.
        hl._feed_press(CTRL)
        hl._feed_press(ALT)
        self.assertIn("stop", ev)
        self.assertFalse(rec["on"])          # mic released
        self.assertFalse(hl._latched)


if __name__ == "__main__":
    unittest.main()
