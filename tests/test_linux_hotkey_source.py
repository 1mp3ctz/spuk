"""The Linux evdev source must drive the SAME chord FSM as the pynput path.

We don't import the real ``evdev`` (it can't build on macOS); instead we feed
synthetic categorized key events straight into
``LinuxHotkeySource._handle_key_event`` with a tiny fake ``ecodes`` and assert
the wrapped, real :class:`HotkeyListener` produces the right start/stop events.

This is the Linux mirror of ``test_hotkey_handsfree.py`` (which drives
``_chord_edge`` directly): here we drive one layer lower, through the evdev →
canonical-key translation and the shared ``_feed_press`` / ``_feed_release``.
"""

import unittest
from unittest import mock

import spuk.hotkey as hotkey_mod
from spuk.hotkey import HotkeyListener
from spuk.linux_input import LinuxHotkeySource


# --- fakes modelling the bits of evdev the source touches ------------------

# evdev scancodes (input-event-codes.h). Real evdev exposes these on ecodes too;
# we only need a handful for the chord <ctrl>+<alt> and the letter L.
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_LEFTALT = 56
KEY_L = 38
KEY_F1 = 59


class FakeEcodes:
    """Minimal stand-in for ``evdev.ecodes`` used by ``_handle_key_event``."""

    EV_KEY = 1
    KEY = {
        KEY_LEFTCTRL: "KEY_LEFTCTRL",
        KEY_RIGHTCTRL: "KEY_RIGHTCTRL",
        KEY_LEFTALT: "KEY_LEFTALT",
        KEY_L: "KEY_L",
        KEY_F1: "KEY_F1",
    }


class FakeKeyEvent:
    """Stand-in for ``evdev.categorize(event)`` (a KeyEvent).

    Mirrors the real attributes the source reads: ``scancode``, ``keystate`` and
    the class-level ``key_down`` (1) / ``key_up`` (0) constants.
    """

    key_up = 0
    key_down = 1
    key_hold = 2

    def __init__(self, scancode: int, keystate: int) -> None:
        self.scancode = scancode
        self.keystate = keystate


def _build():
    events: list[str] = []
    listener = HotkeyListener(
        key_combo="<ctrl>+<alt>",
        mode="push_to_talk",
        on_start=lambda: events.append("start"),
        on_stop=lambda: events.append("stop"),
        on_cancel=lambda: events.append("cancel"),
        handsfree=True,
        double_tap_seconds=0.4,
    )
    source = LinuxHotkeySource(listener)
    return source, listener, events


def _down(source, scancode):
    source._handle_key_event(FakeKeyEvent(scancode, FakeKeyEvent.key_down), FakeEcodes)


def _up(source, scancode):
    source._handle_key_event(FakeKeyEvent(scancode, FakeKeyEvent.key_up), FakeEcodes)


class _Clock:
    """Controllable stand-in for ``time.monotonic`` (the FSM's hold timer).

    The chord FSM uses wall-clock time to tell a real hold (>= double_tap_seconds)
    from a quick tap. Feeding events through the evdev path calls the FSM with the
    *real* clock, so we patch it to advance deterministically — mirroring how
    ``test_hotkey_handsfree.py`` passes explicit timestamps to ``_chord_edge``.
    """

    def __init__(self) -> None:
        self.t = 0.0

    def advance(self, dt: float) -> None:
        self.t += dt

    def __call__(self) -> float:
        return self.t


class EvdevDrivesChordFSM(unittest.TestCase):
    def test_holding_ctrl_alt_starts_recording_release_stops(self):
        source, _listener, ev = _build()
        clock = _Clock()
        with mock.patch.object(hotkey_mod.time, "monotonic", clock):
            _down(source, KEY_LEFTCTRL)   # partial chord — nothing yet
            self.assertEqual(ev, [])
            _down(source, KEY_LEFTALT)    # chord complete → push-to-talk starts
            self.assertEqual(ev, ["start"])
            clock.advance(0.6)            # held 0.6s (> 0.4 cutoff) → a real hold
            _up(source, KEY_LEFTALT)      # chord broken → stop + transcribe
            self.assertEqual(ev, ["start", "stop"])
            _up(source, KEY_LEFTCTRL)
            self.assertEqual(ev, ["start", "stop"])

    def test_right_ctrl_satisfies_same_chord(self):
        # Right Ctrl must canonicalise to the same modifier as left Ctrl.
        source, _listener, ev = _build()
        clock = _Clock()
        with mock.patch.object(hotkey_mod.time, "monotonic", clock):
            _down(source, KEY_RIGHTCTRL)
            _down(source, KEY_LEFTALT)
            self.assertEqual(ev, ["start"])
            clock.advance(0.6)
            _up(source, KEY_RIGHTCTRL)
            self.assertEqual(ev, ["start", "stop"])

    def test_autorepeat_does_not_retrigger(self):
        # keystate == key_hold (2) is autorepeat for a held key; it must be
        # ignored so a held chord doesn't fire repeatedly.
        source, _listener, ev = _build()
        _down(source, KEY_LEFTCTRL)
        _down(source, KEY_LEFTALT)
        source._handle_key_event(FakeKeyEvent(KEY_LEFTALT, FakeKeyEvent.key_hold), FakeEcodes)
        source._handle_key_event(FakeKeyEvent(KEY_LEFTCTRL, FakeKeyEvent.key_hold), FakeEcodes)
        self.assertEqual(ev, ["start"])  # still just one start

    def test_unrelated_keys_are_ignored(self):
        source, listener, ev = _build()
        _down(source, KEY_F1)
        self.assertEqual(ev, [])
        self.assertEqual(listener._pressed, set())  # F1 not tracked


class EvdevDrivesTapHotkey(unittest.TestCase):
    def test_tap_combo_fires_once_then_rearms(self):
        # A "tap" hotkey (used for language cycling) fires its callback once per
        # activation and re-arms after release. We model a Ctrl+L tap (the keys
        # our fake ecodes covers); the same path serves the configured cycle key.
        fired = {"n": 0}
        listener = HotkeyListener(
            key_combo="<ctrl>+<alt>",
            mode="push_to_talk",
            on_start=lambda: None,
            on_stop=lambda: None,
            taps={"<ctrl>+l": lambda: fired.__setitem__("n", fired["n"] + 1)},
        )
        source = LinuxHotkeySource(listener)
        _down(source, KEY_LEFTCTRL)
        _down(source, KEY_L)          # Ctrl+L satisfied → fires once
        self.assertEqual(fired["n"], 1)
        _down(source, KEY_L)          # still held, must not re-fire
        self.assertEqual(fired["n"], 1)
        _up(source, KEY_L)
        _up(source, KEY_LEFTCTRL)
        _down(source, KEY_LEFTCTRL)
        _down(source, KEY_L)          # re-armed → fires again
        self.assertEqual(fired["n"], 2)


if __name__ == "__main__":
    unittest.main()
