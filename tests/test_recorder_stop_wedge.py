"""A failing stream teardown must never wedge the recorder.

macOS PortAudio can raise from ``stream.stop()`` / ``stream.close()`` after a
sleep/wake or a mic-device change. The old ``stop()`` set ``self._stream = None``
only AFTER stop()+close(), so a raised exception left a dead, non-None stream in
place. ``start()`` begins with ``if self._stream is not None: return`` — so every
later recording (the hotkey, Fn, AND the Hold-to-talk mouse button all funnel
through this one Recorder) silently no-oped until the app was restarted. That is
the "speaking just stops working until I quit Spuk" bug.
"""

from __future__ import annotations

import spuk.audio as audio
from spuk.config import load_config


class _RaisingStream:
    """A stream whose teardown raises, like PortAudio after sleep/wake."""

    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        raise RuntimeError("PortAudioError: cannot stop a dead stream")

    def close(self) -> None:
        raise RuntimeError("PortAudioError: cannot close a dead stream")


def _recorder() -> audio.Recorder:
    return audio.Recorder(load_config().audio)


def test_stop_that_raises_does_not_wedge_future_recordings(monkeypatch):
    streams: list[_RaisingStream] = []

    def fake_inputstream(*, device, **kw):
        s = _RaisingStream()
        streams.append(s)
        return s

    monkeypatch.setattr(audio.sd, "InputStream", fake_inputstream)
    rec = _recorder()

    rec.start()
    assert rec.is_recording

    # The underlying stop()/close() raise — but stop() must swallow that and
    # still reset state, never propagate a wedge.
    rec.stop()
    assert not rec.is_recording  # state reset despite the raise

    # The crucial assertion: a new recording must actually open a NEW stream,
    # not get swallowed by the `if self._stream is not None: return` guard.
    rec.start()
    assert rec.is_recording
    assert len(streams) == 2


def test_stop_returns_captured_audio_even_if_teardown_raises(monkeypatch):
    import numpy as np

    def fake_inputstream(*, device, **kw):
        return _RaisingStream()

    monkeypatch.setattr(audio.sd, "InputStream", fake_inputstream)
    rec = _recorder()
    rec.start()
    # Simulate captured frames as the PortAudio callback would have appended.
    rec._frames = [np.ones(800, dtype=np.float32)]
    out = rec.stop()
    assert out.shape == (800,)
    assert not rec.is_recording
