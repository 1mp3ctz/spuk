"""SpukCore.force_stop is the UI's guaranteed 'stop the mic now' escape hatch.

It must (1) clear any wedged hotkey state on the listener and (2) stop the
recorder, even when the hotkey FSM has desynced (e.g. a dropped modifier
release). It must be a no-op when nothing is recording.
"""

from __future__ import annotations

import numpy as np
from pynput import keyboard

from spuk.config import load_config
from spuk.core import SpukCore


class _FakeRecorder:
    """Stands in for the real Recorder; returns empty audio so _on_stop short-
    circuits before transcription (duration < min_seconds)."""

    def __init__(self):
        self.device = None
        self.is_recording = True
        self.stops = 0

    def stop(self):
        self.stops += 1
        self.is_recording = False
        return np.zeros(0, dtype=np.float32)


def _core():
    cfg = load_config()
    core = SpukCore(cfg)
    core._recorder = _FakeRecorder()
    core._listener = core.make_listener()  # built, but pynput not started
    return core


def test_force_stop_resets_listener_and_stops_recorder():
    core = _core()
    # Wedge the FSM the way a dropped modifier release would.
    core._listener._feed_press(keyboard.Key.ctrl)
    core._listener._feed_press(keyboard.Key.alt)
    assert core._listener._chord_down is True

    core.force_stop()

    assert core._recorder.stops == 1
    assert core._listener._chord_down is False
    assert core._listener._pressed == set()


def test_force_stop_is_noop_when_not_recording():
    core = _core()
    core._recorder.is_recording = False

    core.force_stop()  # must not raise

    assert core._recorder.stops == 0


def test_is_recording_reflects_recorder():
    core = _core()
    assert core.is_recording is True
    core._recorder.is_recording = False
    assert core.is_recording is False
