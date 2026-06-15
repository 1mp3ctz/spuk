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
            self._stream = sd.InputStream(
                samplerate=self._cfg.samplerate,
                channels=self._cfg.channels,
                dtype="float32",
                device=self.device,
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:  # no input device, device busy, etc.
            log.error("Could not open microphone: %s", exc)
            self._stream = None
            raise

    def stop(self) -> np.ndarray:
        """Stop recording and return the captured mono audio (may be empty)."""
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None

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
