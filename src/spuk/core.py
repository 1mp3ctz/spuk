"""Spuk core: wires hotkey -> mic capture -> local Whisper -> paste.

This is the whole Phase 1 dictation loop. Each piece lives in its own module so
this file stays small and readable:
    hotkey.py      global push-to-talk / toggle
    audio.py       microphone capture
    transcriber.py local Whisper (swappable engine)
    postprocess.py optional, OFF-by-default text cleanup
    paste.py       clipboard + Cmd+V insertion
"""

from __future__ import annotations

import logging
import time

from .audio import Recorder
from .config import Config, load_config
from .hotkey import HotkeyListener
from .paste import paste_text
from .postprocess import build_post_processor
from .transcriber import build_transcriber

log = logging.getLogger("spuk")


class Spuk:
    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._recorder = Recorder(config.audio)
        self._transcriber = build_transcriber(config.transcribe)
        self._post = build_post_processor(config.post_process)

    def start(self) -> None:
        # Warm the model so the first real utterance isn't slow.
        warm = getattr(self._transcriber, "warm", None)
        if callable(warm):
            warm(self._cfg.audio.samplerate)

        mode = self._cfg.hotkey.mode
        key = self._cfg.hotkey.key
        log.info("Spuk ready. Mode=%s  Hotkey=%s", mode, key)
        log.info("Hold the hotkey (push-to-talk) and speak; release to transcribe & paste.")

        listener = HotkeyListener(
            key_combo=key,
            mode=mode,
            on_start=self._on_start,
            on_stop=self._on_stop,
        )
        try:
            listener.run()  # blocks until Ctrl-C
        except KeyboardInterrupt:
            log.info("Shutting down.")

    # --- hotkey callbacks -------------------------------------------------

    def _on_start(self) -> None:
        try:
            self._recorder.start()
            log.info("● recording…")
        except Exception:
            log.error("Recording failed to start — check microphone permission for your terminal.")

    def _on_stop(self) -> None:
        audio = self._recorder.stop()
        duration = len(audio) / self._cfg.audio.samplerate if len(audio) else 0.0
        if duration < self._cfg.audio.min_seconds:
            log.info("… too short (%.2fs) — ignoring.", duration)
            return

        log.info("… transcribing %.2fs of audio", duration)
        t0 = time.perf_counter()
        text = self._transcriber.transcribe(audio, self._cfg.audio.samplerate)
        elapsed = time.perf_counter() - t0

        if not text:
            log.info("Empty transcript — nothing to paste.")
            return

        text = self._post.process(text)
        log.info("→ (%.2fs) %s", elapsed, text)
        paste_text(text)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    config = load_config()
    Spuk(config).start()
