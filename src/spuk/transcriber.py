"""Transcription engines.

The rest of the app depends only on the ``Transcriber`` protocol — a single
method that turns audio (float32 mono numpy array) into text. This is what makes
the Whisper runtime swappable: faster-whisper today, MLX or whisper.cpp later,
without touching the core loop.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

from .config import TranscribeConfig

log = logging.getLogger("spuk.transcriber")


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray, samplerate: int) -> str:
        """Return the transcribed text for ``audio`` (mono float32 in [-1, 1])."""
        ...


class FasterWhisperTranscriber:
    """faster-whisper (CTranslate2) engine. CPU + int8 is the fast path on Apple Silicon.

    The model is loaded lazily on first use and then warmed, so the first real
    utterance isn't paying the cold-start cost.
    """

    def __init__(self, cfg: TranscribeConfig) -> None:
        self._cfg = cfg
        self._model = None  # loaded lazily — importing faster_whisper is slow

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel  # local import keeps startup snappy

        log.info("Loading Whisper model %r (device=%s, compute_type=%s)…",
                 self._cfg.model, self._cfg.device, self._cfg.compute_type)
        self._model = WhisperModel(
            self._cfg.model,
            device=self._cfg.device,
            compute_type=self._cfg.compute_type,
        )

    def warm(self, samplerate: int) -> None:
        """Run one tiny inference so the first real utterance is fast."""
        self._ensure_loaded()
        silence = np.zeros(int(0.5 * samplerate), dtype=np.float32)
        self.transcribe(silence, samplerate)
        log.info("Model warm — ready.")

    def transcribe(self, audio: np.ndarray, samplerate: int) -> str:
        self._ensure_loaded()
        assert self._model is not None

        # faster-whisper expects 16kHz mono float32. We capture at 16kHz, so no
        # resampling needed; if a caller passes another rate, that's a bug to fix
        # at the audio boundary, not silently here.
        if samplerate != 16000:
            raise ValueError(f"Expected 16kHz audio, got {samplerate}Hz")

        language = self._cfg.language or None  # "" -> auto-detect
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            beam_size=self._cfg.beam_size,
            vad_filter=self._cfg.vad_filter,
        )
        return " ".join(seg.text for seg in segments).strip()


def build_transcriber(cfg: TranscribeConfig) -> Transcriber:
    """Factory: pick an engine implementation from config."""
    if cfg.engine == "faster-whisper":
        return FasterWhisperTranscriber(cfg)
    # MLX and whisper.cpp engines are Phase 2/3 — fail loudly rather than guess.
    raise NotImplementedError(
        f"engine {cfg.engine!r} not implemented yet. Phase 1 ships 'faster-whisper'."
    )
