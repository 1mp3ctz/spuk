"""State-machine tests for the hotkey: hold-to-talk, double-tap hands-free, toggle.

Drives `_chord_edge(down, t)` directly with synthetic timestamps so the logic is
tested without pynput, audio, or real timing.
"""

import unittest

from spuk.hotkey import HotkeyListener


def make(mode="push_to_talk", handsfree=True, double=0.4):
    events: list[str] = []
    listener = HotkeyListener(
        key_combo="<ctrl>+<alt>",
        mode=mode,
        on_start=lambda: events.append("start"),
        on_stop=lambda: events.append("stop"),
        on_cancel=lambda: events.append("cancel"),
        handsfree=handsfree,
        double_tap_seconds=double,
    )
    return listener, events


class PushToTalk(unittest.TestCase):
    def test_hold_records_then_transcribes(self):
        hl, ev = make()
        hl._chord_edge(True, 0.0)
        hl._chord_edge(False, 0.6)  # held 0.6s (> 0.4 cutoff) → a real hold
        self.assertEqual(ev, ["start", "stop"])

    def test_single_quick_tap_is_discarded(self):
        hl, ev = make()
        hl._chord_edge(True, 0.0)
        hl._chord_edge(False, 0.1)
        self.assertEqual(ev, ["start", "cancel"])
        self.assertFalse(hl._recording)


class HandsFree(unittest.TestCase):
    def test_double_tap_latches_then_press_stops(self):
        hl, ev = make()
        hl._chord_edge(True, 0.0)
        hl._chord_edge(False, 0.1)            # first tap (discarded)
        hl._chord_edge(True, 0.3)
        hl._chord_edge(False, 0.4)            # second tap → latch hands-free
        self.assertTrue(hl._latched)
        self.assertTrue(hl._recording)
        # ...user speaks freely, then a single press stops + transcribes.
        hl._chord_edge(True, 3.0)
        hl._chord_edge(False, 3.05)           # release of the stop-press is ignored
        self.assertEqual(ev, ["start", "cancel", "start", "stop"])
        self.assertFalse(hl._latched)
        self.assertFalse(hl._recording)

    def test_two_slow_taps_do_not_latch(self):
        hl, ev = make()
        hl._chord_edge(True, 0.0)
        hl._chord_edge(False, 0.1)
        hl._chord_edge(True, 1.0)             # gap 0.9s > 0.4 → not a double-tap
        hl._chord_edge(False, 1.1)
        self.assertFalse(hl._latched)
        self.assertEqual(ev, ["start", "cancel", "start", "cancel"])

    def test_handsfree_disabled_only_holds_work(self):
        hl, ev = make(handsfree=False)
        hl._chord_edge(True, 0.0)
        hl._chord_edge(False, 0.1)
        hl._chord_edge(True, 0.3)
        hl._chord_edge(False, 0.4)
        self.assertFalse(hl._latched)
        self.assertEqual(ev, ["start", "cancel", "start", "cancel"])


class Toggle(unittest.TestCase):
    def test_press_starts_next_press_stops(self):
        hl, ev = make(mode="toggle")
        hl._chord_edge(True, 0.0)             # start
        hl._chord_edge(False, 0.1)            # release: no-op
        hl._chord_edge(True, 1.0)             # stop
        hl._chord_edge(False, 1.1)
        self.assertEqual(ev, ["start", "stop"])

    def test_handsfree_forced_off_in_toggle(self):
        hl, _ = make(mode="toggle")
        self.assertFalse(hl._handsfree)


if __name__ == "__main__":
    unittest.main()
