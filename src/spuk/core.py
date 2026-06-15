"""Spuk core engine: hotkey -> mic capture -> local Whisper -> paste.

`SpukCore` owns the dictation loop and the runtime language state. It is UI-
agnostic: the headless runner and the system-tray app both drive the same core.
Each piece lives in its own module so this file stays small:
    hotkey.py      global push-to-talk / toggle + tap hotkeys
    audio.py       microphone capture
    transcriber.py local Whisper (swappable engine)
    postprocess.py optional, OFF-by-default text cleanup
    paste.py       clipboard + paste insertion (Cmd+V / Ctrl+V per OS)
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .audio import Recorder
from .config import Config
from .hotkey import HotkeyListener
from .paste import paste_text
from .postprocess import build_post_processor
from .transcriber import build_transcriber

log = logging.getLogger("spuk")


class SpukCore:
    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._recorder = Recorder(config.audio)
        self._transcriber = build_transcriber(config.transcribe)
        self._post = build_post_processor(config.post_process)

        # The user's curated set of languages (mutable at runtime) and the active
        # one. Seeded from config (which already overlays the user's saved choices).
        self._languages: list[str] = list(config.transcribe.languages)
        self._language = config.transcribe.default_language

        # Apply a previously-saved microphone choice, if any.
        from .settings_store import load_user_settings

        saved = load_user_settings()
        if "device" in saved:
            try:
                self._recorder.device = saved["device"]
            except Exception:  # noqa: BLE001
                pass

        # Optional observers so a UI can react. These fire from the hotkey
        # listener thread — a Qt UI must marshal them onto the main thread.
        self.on_language_change: Callable[[str], None] | None = None
        self.on_languages_change: Callable[[tuple[str, ...]], None] | None = None
        self.on_recording_change: Callable[[bool], None] | None = None
        self.on_transcript: Callable[[str], None] | None = None

    # --- language state ---------------------------------------------------

    @property
    def language(self) -> str:
        return self._language

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(self._languages)

    def set_language(self, lang: str) -> None:
        if lang not in self._languages:
            log.warning("Ignoring unknown language %r", lang)
            return
        self._language = lang
        log.info("Language → %s", lang)
        self._persist()
        if self.on_language_change:
            self.on_language_change(lang)

    def add_language(self, code: str) -> None:
        """Add a language to the curated set (and make it active)."""
        from .languages import is_supported

        if not is_supported(code):
            log.warning("Ignoring unsupported language %r", code)
            return
        if code not in self._languages:
            self._languages.append(code)
            log.info("Added language %s (now: %s)", code, ", ".join(self._languages))
            self._persist()
            if self.on_languages_change:
                self.on_languages_change(tuple(self._languages))
        self.set_language(code)

    def remove_language(self, code: str) -> None:
        """Remove a language from the curated set. Keeps at least one."""
        if code not in self._languages:
            return
        if len(self._languages) <= 1:
            log.warning("Refusing to remove the last language (%s).", code)
            return
        self._languages.remove(code)
        log.info("Removed language %s (now: %s)", code, ", ".join(self._languages))
        if self._language == code:
            self._language = self._languages[0]
            if self.on_language_change:
                self.on_language_change(self._language)
        self._persist()
        if self.on_languages_change:
            self.on_languages_change(tuple(self._languages))

    def set_input_device(self, device: int | str | None) -> None:
        """Choose the microphone (sounddevice index or name; None = system default)."""
        self._recorder.device = device
        log.info("Microphone → %s", device if device is not None else "system default")
        self._persist()

    def cycle_language(self) -> None:
        langs = self._languages
        if self._language not in langs:
            self._language = langs[0]
        nxt = langs[(langs.index(self._language) + 1) % len(langs)]
        self.set_language(nxt)

    def _persist(self) -> None:
        """Save the user's current languages / active language / microphone."""
        from .settings_store import update_user_settings

        update_user_settings(
            languages=list(self._languages),
            default_language=self._language,
            device=self._recorder.device,
        )

    # --- lifecycle --------------------------------------------------------

    def warm(self) -> None:
        warm = getattr(self._transcriber, "warm", None)
        if callable(warm):
            warm(self._cfg.audio.samplerate, self._language)

    def make_listener(self) -> HotkeyListener:
        return HotkeyListener(
            key_combo=self._cfg.hotkey.key,
            mode=self._cfg.hotkey.mode,
            on_start=self._on_start,
            on_stop=self._on_stop,
            taps={self._cfg.hotkey.cycle_language: self.cycle_language},
        )

    def run_headless(self) -> None:
        log.info(
            "Spuk ready. Mode=%s  Hotkey=%s  Cycle=%s  Language=%s",
            self._cfg.hotkey.mode, self._cfg.hotkey.key,
            self._cfg.hotkey.cycle_language, self._language,
        )
        log.info("Hold the hotkey and speak; release to transcribe & paste. Ctrl-C to quit.")
        try:
            self.make_listener().run()  # blocks until Ctrl-C
        except KeyboardInterrupt:
            log.info("Shutting down.")

    # --- recording (used by the hotkey and the UI button) -----------------

    def begin_recording(self) -> None:
        """Public entry to start recording (UI button or hotkey)."""
        self._on_start()

    def finish_recording(self) -> None:
        """Public entry to stop + transcribe + paste. Blocks ~1s — call off the UI thread."""
        self._on_stop()

    # --- hotkey callbacks -------------------------------------------------

    def _on_start(self) -> None:
        try:
            self._recorder.start()
            log.info("● recording… (%s)", self._language)
            if self.on_recording_change:
                self.on_recording_change(True)
        except Exception:
            log.error("Recording failed to start — check microphone permission.")

    def _on_stop(self) -> None:
        audio = self._recorder.stop()
        if self.on_recording_change:
            self.on_recording_change(False)
        duration = len(audio) / self._cfg.audio.samplerate if len(audio) else 0.0
        if duration < self._cfg.audio.min_seconds:
            log.info("… too short (%.2fs) — ignoring.", duration)
            return

        log.info("… transcribing %.2fs of audio (%s)", duration, self._language)
        t0 = time.perf_counter()
        try:
            text = self._transcriber.transcribe(audio, self._cfg.audio.samplerate, self._language)
        except Exception as exc:
            log.error("Transcription failed: %s", exc)
            return
        elapsed = time.perf_counter() - t0

        if not text:
            log.info("Empty transcript — nothing to paste.")
            return

        text = self._post.process(text)
        log.info("→ (%.2fs) %s", elapsed, text)
        paste_text(text)
        if self.on_transcript:
            self.on_transcript(text)
