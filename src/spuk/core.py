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

import dataclasses
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


def with_hotkey(hk, *, key=None, cycle_language=None, mode=None, handsfree=None, paste_key=None):
    """Return a NEW HotkeyConfig with the given fields changed (immutability)."""
    changes = {}
    if key is not None:
        changes["key"] = key
    if cycle_language is not None:
        changes["cycle_language"] = cycle_language
    if mode is not None:
        changes["mode"] = mode
    if handsfree is not None:
        changes["handsfree"] = handsfree
    if paste_key is not None:
        changes["paste_key"] = paste_key
    return dataclasses.replace(hk, **changes)


def hotkey_settings(*, key=None, cycle_language=None, mode=None, handsfree=None, paste_key=None) -> dict:
    """Map changed hotkey fields to their settings.json keys (skip unset)."""
    out = {}
    if key is not None:
        out["hotkey_key"] = key
    if cycle_language is not None:
        out["hotkey_cycle_language"] = cycle_language
    if mode is not None:
        out["hotkey_mode"] = mode
    if handsfree is not None:
        out["hotkey_handsfree"] = handsfree
    if paste_key is not None:
        out["paste_key"] = paste_key
    return out


class SpukCore:
    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._recorder = Recorder(config.audio)
        self._transcriber = build_transcriber(config.transcribe)
        self._post = build_post_processor(config.post_process)

        # Apply the configured paste shortcut (OS default unless the user picked a
        # terminal-friendly one like Ctrl+Shift+V for VS Code / Cursor terminals).
        from .paste import set_paste_shortcut as _apply_paste

        _apply_paste(config.hotkey.paste_key or None)

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
        self.on_hotkey_change: Callable[[], None] | None = None
        self.on_combo_captured: Callable[[str], None] | None = None

        # Input backend handles: the FSM listener (has begin_capture) and the
        # started stop-handle. Owned here so rebind can swap them live.
        self._listener = None
        self._backend = None

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
            on_cancel=self._on_cancel,
            taps={self._cfg.hotkey.cycle_language: self.cycle_language},
            handsfree=self._cfg.hotkey.handsfree,
            double_tap_seconds=self._cfg.hotkey.double_tap_seconds,
        )

    def make_input_backend(self):
        """The platform-selected hotkey backend driving the FSM above.

        pynput on macOS/Windows, evdev on Linux — both expose ``run()`` (block)
        and ``start()`` (background, returns a handle with ``stop()``). The UIs
        and the headless loop drive this, not pynput directly.
        """
        from .input_backend import make_input_backend

        return make_input_backend(self.make_listener())

    # --- hotkey lifecycle + live rebind -----------------------------------

    @property
    def hotkey(self):
        return self._cfg.hotkey

    def start_input(self):
        """Start the hotkey backend; keep BOTH the FSM listener and the stop handle.

        pynput's ``HotkeyListener.start()`` returns the underlying pynput Listener,
        while ``LinuxHotkeySource.start()`` returns itself — both have ``.stop()``,
        but only the HotkeyListener has ``begin_capture``. So we hold the FSM
        listener explicitly for capture, separate from the started stop-handle.
        """
        from .input_backend import make_input_backend

        self._listener = self.make_listener()
        self._backend = make_input_backend(self._listener).start()
        return self._backend

    def stop_input(self) -> None:
        if self._backend is not None:
            try:
                self._backend.stop()
            except Exception:  # noqa: BLE001
                pass
            self._backend = None

    def rebind_hotkeys(self, *, key=None, cycle_language=None, mode=None, handsfree=None) -> None:
        """Apply new hotkey settings live, IN PLACE (no listener restart).

        Stopping and recreating the pynput CGEventTap mid-run to apply a new
        hotkey crashes on macOS (SIGTRAP). Instead the running listener keeps its
        reader thread(s) alive and we just re-point the combos it matches.
        """
        previous = self._cfg.hotkey
        new_hotkey = with_hotkey(previous, key=key, cycle_language=cycle_language,
                                 mode=mode, handsfree=handsfree)
        self._cfg = dataclasses.replace(self._cfg, hotkey=new_hotkey)

        from .settings_store import update_user_settings

        update_user_settings(**hotkey_settings(key=key, cycle_language=cycle_language,
                                               mode=mode, handsfree=handsfree))

        try:
            if self._listener is not None:
                self._listener.update_bindings(
                    key_combo=new_hotkey.key,
                    mode=new_hotkey.mode,
                    taps={new_hotkey.cycle_language: self.cycle_language},
                    handsfree=new_hotkey.handsfree,
                    double_tap_seconds=new_hotkey.double_tap_seconds,
                )
        except Exception as exc:  # noqa: BLE001 - revert so the user isn't stuck
            log.error("Rebind failed (%s); reverting.", exc)
            self._cfg = dataclasses.replace(self._cfg, hotkey=previous)
            raise
        log.info("Hotkeys rebound: key=%s cycle=%s mode=%s handsfree=%s",
                 new_hotkey.key, new_hotkey.cycle_language, new_hotkey.mode, new_hotkey.handsfree)
        if self.on_hotkey_change:
            self.on_hotkey_change()

    def reset_hotkeys(self) -> None:
        """Clear saved hotkey overrides and rebind to the bundled config.toml."""
        from .settings_store import load_user_settings, save_user_settings

        data = load_user_settings()
        for k in ("hotkey_key", "hotkey_cycle_language", "hotkey_mode", "hotkey_handsfree", "paste_key"):
            data.pop(k, None)
        save_user_settings(data)

        from .config import load_config

        defaults = load_config().hotkey
        self.rebind_hotkeys(key=defaults.key, cycle_language=defaults.cycle_language,
                            mode=defaults.mode, handsfree=defaults.handsfree)
        self.set_paste_shortcut(defaults.paste_key)

    def set_paste_shortcut(self, combo: str) -> None:
        """Set the shortcut Spuk SENDS to paste (not a listened hotkey).

        ``combo`` is a canonical combo string ("<ctrl>+<shift>+v" for terminals) or
        "" for the OS default. Persisted and applied immediately — no listener
        restart, since this only changes what Spuk injects after transcribing.
        """
        from .paste import set_paste_shortcut as _apply_paste
        from .settings_store import update_user_settings

        self._cfg = dataclasses.replace(self._cfg, hotkey=with_hotkey(self._cfg.hotkey, paste_key=combo))
        update_user_settings(**hotkey_settings(paste_key=combo))
        _apply_paste(combo or None)
        log.info("Paste shortcut → %s", combo or "(OS default)")
        if self.on_hotkey_change:
            self.on_hotkey_change()

    def start_capture(self, on_done) -> bool:
        """Capture the next combo via the running FSM listener.

        Returns False if input isn't started. ``on_done`` fires on the listener
        thread with the canonical combo string.
        """
        if self._listener is None:
            return False
        self._listener.begin_capture(on_done)
        return True

    def cancel_capture(self) -> None:
        if self._listener is not None:
            self._listener.cancel_capture()

    def run_headless(self) -> None:
        log.info(
            "Spuk ready. Mode=%s  Hotkey=%s  Cycle=%s  Language=%s",
            self._cfg.hotkey.mode, self._cfg.hotkey.key,
            self._cfg.hotkey.cycle_language, self._language,
        )
        log.info("Hold the hotkey and speak; release to transcribe & paste. Ctrl-C to quit.")
        try:
            self.make_input_backend().run()  # blocks until Ctrl-C
        except KeyboardInterrupt:
            log.info("Shutting down.")

    # --- recording (used by the hotkey and the UI button) -----------------

    def begin_recording(self) -> None:
        """Public entry to start recording (UI button or hotkey)."""
        self._on_start()

    def finish_recording(self) -> None:
        """Public entry to stop + transcribe + paste. Blocks ~1s — call off the UI thread."""
        self._on_stop()

    @property
    def is_recording(self) -> bool:
        return self._recorder.is_recording

    def force_stop(self) -> None:
        """Guaranteed 'stop the mic now' for the UI (menu bar / clicking the pill).

        First clears any wedged hotkey state — macOS can drop a modifier key-up and
        leave the chord stuck 'down', which would otherwise keep the recorder
        running with no way to stop it from the keyboard. Then stops + transcribes +
        pastes whatever was captured, exactly like releasing the hotkey. A no-op
        when nothing is recording. Blocks ~1s on transcription — call off the UI
        thread.
        """
        if self._listener is not None:
            self._listener.reset_state()
        if self._recorder.is_recording:
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

    def _on_cancel(self) -> None:
        """Discard the in-progress recording without transcribing.

        Used for the first of a double-tap: that tiny clip is a gesture, not
        speech, so we drop it instead of running it through Whisper.
        """
        self._recorder.stop()
        if self.on_recording_change:
            self.on_recording_change(False)

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
