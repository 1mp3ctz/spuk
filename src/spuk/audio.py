"""Microphone capture via sounddevice (PortAudio).

We record raw float32 frames into a list while the hotkey is held, then
concatenate into one mono array. Capturing directly at 16kHz mono means no
resampling step before Whisper.
"""

from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

from .config import AudioConfig

log = logging.getLogger("spuk.audio")


class Recorder:
    """Push-to-talk recorder. Call start() on key-down, stop() on key-up."""

    def __init__(self, cfg: AudioConfig) -> None:
        self._cfg = cfg
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        # None = system default input. A sounddevice index or name selects a mic.
        self.device: int | str | None = None

    def start(self) -> None:
        if self._stream is not None:
            return  # already recording — ignore repeat key-down (auto-repeat)
        self._frames = []

        def callback(indata, _frames, _time, status):
            if status:
                log.warning("audio status: %s", status)
            # Copy: indata is a reusable buffer owned by PortAudio.
            self._frames.append(indata.copy())

        try:
            self._open(self.device, callback)
        except Exception as exc:  # no input device, device busy, stale index, etc.
            # A saved device INDEX can go stale (an unplugged USB / disconnected
            # AirPods mic), which otherwise fails silently — no recording AND no
            # macOS mic prompt, because the mic is never actually engaged. Fall back
            # to the system default so dictation keeps working, and forget the bad
            # device so we don't keep retrying it.
            if self.device is not None:
                log.warning("Mic %r unavailable (%s) — using the default input.", self.device, exc)
                self.device = None
                self._open(None, callback)  # genuine no-mic error still propagates
            else:
                log.error("Could not open microphone: %s", exc)
                raise

    def _open(self, device, callback) -> None:
        """Open + start an input stream on ``device`` (None = system default)."""
        stream = sd.InputStream(
            samplerate=self._cfg.samplerate,
            channels=self._cfg.channels,
            dtype="float32",
            device=device,
            callback=callback,
        )
        stream.start()
        self._stream = stream  # only set once the stream is actually running

    def stop(self) -> np.ndarray:
        """Stop recording and return the captured mono audio (may be empty)."""
        stream = self._stream
        if stream is None:
            return np.zeros(0, dtype=np.float32)
        # Clear the handle BEFORE tearing the stream down. PortAudio can raise from
        # stop()/close() after a sleep/wake or a mic-device change; if that left
        # self._stream set, start()'s `if self._stream is not None: return` guard
        # would silently no-op every later recording — hotkey, Fn, and the
        # Hold-to-talk button all route through here — until the app restarted.
        # Resetting first makes a failed teardown fully recoverable.
        self._stream = None
        try:
            stream.stop()
            stream.close()
        except Exception as exc:  # noqa: BLE001 - best-effort teardown; never wedge
            log.warning("Audio stream teardown failed (ignored, recorder reset): %s", exc)

        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._frames, axis=0)
        # Flatten to mono 1-D regardless of channel count.
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)

    @property
    def is_recording(self) -> bool:
        return self._stream is not None
