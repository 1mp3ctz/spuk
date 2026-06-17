"""Recorder falls back to the default mic when a saved device index is stale.

A persisted sounddevice INDEX can become invalid (an unplugged USB mic, AirPods
disconnecting), which previously failed silently: no recording and — worse — no
macOS microphone prompt, because the device is never actually engaged. The
recorder now retries on the system default so dictation keeps working.
"""

from __future__ import annotations

import pytest

import spuk.audio as audio
from spuk.config import load_config


class _FakeStream:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


def _recorder() -> audio.Recorder:
    return audio.Recorder(load_config().audio)


def test_falls_back_to_default_when_saved_device_fails(monkeypatch):
    opened = []

    def fake_inputstream(*, device, **kw):
        opened.append(device)
        if device is not None:
            raise RuntimeError("invalid device 1")
        return _FakeStream()

    monkeypatch.setattr(audio.sd, "InputStream", fake_inputstream)
    rec = _recorder()
    rec.device = 1  # stale index (e.g. a mic that's been unplugged)
    rec.start()
    assert opened == [1, None]  # tried the saved device, then the default
    assert rec.device is None  # forgot the bad device so it won't retry it
    assert rec.is_recording


def test_default_device_failure_still_propagates(monkeypatch):
    def fake_inputstream(*, device, **kw):
        raise RuntimeError("no input device at all")

    monkeypatch.setattr(audio.sd, "InputStream", fake_inputstream)
    rec = _recorder()
    rec.device = None
    with pytest.raises(RuntimeError):
        rec.start()
    assert not rec.is_recording


def test_no_fallback_when_saved_device_works(monkeypatch):
    opened = []

    def fake_inputstream(*, device, **kw):
        opened.append(device)
        return _FakeStream()

    monkeypatch.setattr(audio.sd, "InputStream", fake_inputstream)
    rec = _recorder()
    rec.device = 0
    rec.start()
    assert opened == [0]  # used the saved device, no fallback
    assert rec.device == 0
    assert rec.is_recording
