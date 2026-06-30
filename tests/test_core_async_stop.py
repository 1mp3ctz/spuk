"""The global hotkey must never block its callback thread on transcription.

On macOS pynput's keyboard Listener runs its tap callback on the listener
thread's CFRunLoop. SpukCore's hotkey ``on_stop`` is called straight from that
callback, so if it runs the (1-3s) Whisper transcription inline it stalls the
event-tap. macOS then disables the tap with ``kCGEventTapDisabledByTimeout`` and
the global push-to-talk hotkey dies — and any key-UP during the stall is dropped,
wedging the chord FSM with the mic stuck on. The UI button / pill / menu-bar stop
paths already offload to a worker thread; the hotkey path must too.

These tests pin the contract: with async dispatch enabled (the GUI path), a stop
returns immediately and transcribes+pastes on a *different* thread, while the
recording-stopped signal still fires right away so the pill un-sticks. With it
disabled (headless), the old inline behaviour is preserved.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from spuk.config import load_config
from spuk.core import SpukCore


class _FakeRecorder:
    def __init__(self, audio: np.ndarray) -> None:
        self.device = None
        self.is_recording = True
        self._audio = audio
        self.stops = 0

    def stop(self) -> np.ndarray:
        self.stops += 1
        self.is_recording = False
        return self._audio


class _BlockingTranscriber:
    """Records which thread it ran on and blocks until the test releases it."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.thread_ident: int | None = None
        self.calls = 0

    def transcribe(self, audio, samplerate, language) -> str:  # noqa: ANN001
        self.calls += 1
        self.thread_ident = threading.get_ident()
        self.started.set()
        # Block so the test can prove the *caller* didn't wait for us.
        if not self.release.wait(timeout=3.0):
            raise AssertionError("transcription was never released")
        return "hello world"


def _make_core(transcriber, monkeypatch):
    cfg = load_config()
    core = SpukCore(cfg)
    # One second of non-silent audio so _on_stop clears the min-duration guard.
    audio = np.ones(cfg.audio.samplerate, dtype=np.float32)
    core._recorder = _FakeRecorder(audio)
    core._transcriber = transcriber
    pastes: list[str] = []
    monkeypatch.setattr("spuk.core.paste_text", lambda text: pastes.append(text))
    return core, pastes


def test_hotkey_stop_does_not_block_caller_on_transcription(monkeypatch):
    tr = _BlockingTranscriber()
    core, pastes = _make_core(tr, monkeypatch)
    rec_changes: list[bool] = []
    core.on_recording_change = rec_changes.append
    core._async_stop = True  # what start_input() turns on for the GUI hotkey path

    caller_ident = threading.get_ident()
    t0 = time.perf_counter()
    core._on_stop()  # simulates the hotkey release firing on the event-tap thread
    elapsed = time.perf_counter() - t0

    # Transcription began (on a worker) but the caller returned without waiting.
    assert tr.started.wait(1.0), "transcription did not start on a worker thread"
    assert elapsed < 0.5, f"hotkey stop blocked the caller for {elapsed:.2f}s"
    assert tr.thread_ident is not None and tr.thread_ident != caller_ident, (
        "transcription ran on the caller (event-tap) thread"
    )
    # The pill must un-stick the moment recording stops, not after transcription.
    assert rec_changes == [False]
    assert pastes == [], "paste happened before transcription was released"

    tr.release.set()  # let the worker finish
    deadline = time.perf_counter() + 3.0
    while not pastes and time.perf_counter() < deadline:
        time.sleep(0.01)
    assert pastes == ["hello world"]


def test_headless_stop_still_transcribes_inline(monkeypatch):
    """With async dispatch off (headless), _on_stop keeps its old inline behaviour:
    transcription + paste are done by the time it returns."""

    class _Immediate:
        def transcribe(self, audio, samplerate, language):  # noqa: ANN001
            return "inline text"

    core, pastes = _make_core(_Immediate(), monkeypatch)
    assert getattr(core, "_async_stop", False) is False  # default

    core._on_stop()

    assert pastes == ["inline text"]  # completed synchronously, no worker needed
