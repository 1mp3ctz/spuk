"""Global hotkey handling (push-to-talk and toggle).

pynput's built-in GlobalHotKeys only fires when a chord *activates* — it gives no
release event, which push-to-talk needs. So we run a raw keyboard Listener and
track the set of currently-pressed keys against the parsed hotkey, canonicalising
left/right modifier variants. This needs macOS "Input Monitoring" permission for
the host app (the terminal in Phase 1).
"""

from __future__ import annotations

import logging
from typing import Callable

from pynput import keyboard

log = logging.getLogger("spuk.hotkey")


class HotkeyListener:
    """Watches a hotkey combo and drives push-to-talk or toggle callbacks.

    push_to_talk: on_activate fires when the combo goes down, on_release when it
    is let go. toggle: on_activate alternates a single start/stop callback.
    """

    def __init__(
        self,
        key_combo: str,
        mode: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ) -> None:
        self._expected = set(keyboard.HotKey.parse(key_combo))
        self._mode = mode
        self._on_start = on_start
        self._on_stop = on_stop

        self._pressed: set = set()
        self._active = False  # combo currently satisfied (ptt) / recording (toggle)
        self._listener: keyboard.Listener | None = None

    def _canonical(self, key):
        assert self._listener is not None
        return self._listener.canonical(key)

    def _combo_satisfied(self) -> bool:
        return self._expected.issubset(self._pressed)

    def _on_press(self, key) -> None:
        self._pressed.add(self._canonical(key))
        if not self._combo_satisfied():
            return
        if self._mode == "push_to_talk":
            if not self._active:
                self._active = True
                self._on_start()
        else:  # toggle
            # Fire once per chord activation (ignore key auto-repeat).
            if not getattr(self, "_chord_fired", False):
                self._chord_fired = True
                self._active = not self._active
                (self._on_start if self._active else self._on_stop)()

    def _on_release(self, key) -> None:
        self._pressed.discard(self._canonical(key))
        if self._mode == "push_to_talk":
            if self._active and not self._combo_satisfied():
                self._active = False
                self._on_stop()
        else:  # toggle: re-arm once the chord is fully released
            if not self._combo_satisfied():
                self._chord_fired = False

    def run(self) -> None:
        """Block, listening for the hotkey until the listener is stopped."""
        with keyboard.Listener(on_press=self._on_press, on_release=self._on_release) as listener:
            self._listener = listener
            listener.join()
