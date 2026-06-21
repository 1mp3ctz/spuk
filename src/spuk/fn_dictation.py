"""Fn live-dictation lifecycle controller.

Owns the single live ``AppleSpeechEngine`` for the Fn (hold-to-dictate) gesture so
the microphone can always be stopped exactly once. ``ui_bar`` drives this from Qt
main-thread slots; the engine and live-inserter calls therefore happen on the main
thread (where pynput injection is required anyway).

Why a controller and not raw state on the widget: a second Fn-press edge arriving
before the release must NOT overwrite a live engine reference — that would leak its
AVAudioEngine mic tap and leave the mic hot with no owner to stop it. Centralising
start/stop here means press always tears down any existing engine first, and the
same teardown path serves Fn-release, the menu-bar toggle-off, and app quit.

The engine and live inserter are injected, so this is fully unit-testable with
fakes (no Qt, no AVFoundation).
"""

from __future__ import annotations

from typing import Callable


class FnDictationController:
    def __init__(
        self,
        live_insert,
        engine_factory: Callable[[], object],
    ) -> None:
        self._live_insert = live_insert
        self._engine_factory = engine_factory
        self._engine: object | None = None

    @property
    def running(self) -> bool:
        return self._engine is not None

    def on_press(self) -> None:
        """Start a fresh engine, first stopping any still-running one (no leak)."""
        if self._engine is not None:
            self.stop()
        engine = self._engine_factory()
        if engine.start():
            self._engine = engine
        else:
            self._live_insert.cancel()

    def on_release(self) -> None:
        self.stop()

    def on_partial(self, text: str) -> None:
        self._live_insert.update(text)

    def on_final(self, text: str) -> None:
        self._live_insert.commit()

    def stop(self) -> None:
        """Stop the engine if running and finalise provisional text. Idempotent."""
        if self._engine is not None:
            self._engine.stop()
            self._engine = None
        self._live_insert.commit()
