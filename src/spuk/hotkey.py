"""Global hotkey handling (push-to-talk, toggle, plus tap actions).

pynput's built-in GlobalHotKeys only fires when a chord *activates* — it gives no
release event, which push-to-talk needs. So we run a raw keyboard Listener and
track the set of currently-pressed keys against the parsed hotkeys, canonicalising
left/right modifier variants. This needs the "Input Monitoring" permission
(macOS) / runs with no special permission on Windows.

The same listener also handles "tap" hotkeys — combos that fire a callback once
per activation (used for cycling the dictation language).
"""

from __future__ import annotations

import logging
from typing import Callable

from pynput import keyboard

log = logging.getLogger("spuk.hotkey")


class HotkeyListener:
    """Watches a primary hotkey (push-to-talk / toggle) and optional tap hotkeys."""

    def __init__(
        self,
        key_combo: str,
        mode: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        taps: dict[str, Callable[[], None]] | None = None,
    ) -> None:
        self._expected = set(keyboard.HotKey.parse(key_combo))
        self._mode = mode
        self._on_start = on_start
        self._on_stop = on_stop

        # Tap hotkeys: parsed-combo -> (key-set, callback, already-fired flag).
        self._taps = [
            {"keys": set(keyboard.HotKey.parse(combo)), "cb": cb, "fired": False}
            for combo, cb in (taps or {}).items()
        ]

        self._pressed: set = set()
        self._active = False  # combo currently satisfied (ptt) / recording (toggle)
        self._chord_fired = False
        self._listener: keyboard.Listener | None = None

    def _canonical(self, key):
        assert self._listener is not None
        return self._listener.canonical(key)

    def _satisfied(self, expected: set) -> bool:
        return expected.issubset(self._pressed)

    def _on_press(self, key) -> None:
        self._pressed.add(self._canonical(key))

        # Tap hotkeys first (fire once per activation).
        for tap in self._taps:
            if self._satisfied(tap["keys"]):
                if not tap["fired"]:
                    tap["fired"] = True
                    tap["cb"]()

        if not self._satisfied(self._expected):
            return
        if self._mode == "push_to_talk":
            if not self._active:
                self._active = True
                self._on_start()
        else:  # toggle
            if not self._chord_fired:
                self._chord_fired = True
                self._active = not self._active
                (self._on_start if self._active else self._on_stop)()

    def _on_release(self, key) -> None:
        self._pressed.discard(self._canonical(key))

        for tap in self._taps:
            if not self._satisfied(tap["keys"]):
                tap["fired"] = False

        if self._mode == "push_to_talk":
            if self._active and not self._satisfied(self._expected):
                self._active = False
                self._on_stop()
        else:  # toggle: re-arm once the chord is fully released
            if not self._satisfied(self._expected):
                self._chord_fired = False

    def run(self) -> None:
        """Block, listening for hotkeys until the listener is stopped."""
        with keyboard.Listener(on_press=self._on_press, on_release=self._on_release) as listener:
            self._listener = listener
            listener.join()

    def start(self) -> keyboard.Listener:
        """Start listening on a background thread; returns the listener (non-blocking)."""
        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener = listener
        listener.start()
        return listener
