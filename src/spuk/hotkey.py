"""Global hotkey handling (push-to-talk, toggle, hands-free double-tap, plus taps).

pynput's built-in GlobalHotKeys only fires when a chord *activates* — it gives no
release event, which push-to-talk needs. So we run a raw keyboard Listener and
track the set of currently-pressed keys against the parsed hotkeys, canonicalising
left/right modifier variants. This needs the "Input Monitoring" permission
(macOS) / runs with no special permission on Windows.

The chord drives a small state machine (see `_chord_edge`):

* **Hold** the chord and speak, release to transcribe — classic push-to-talk.
* **Double-tap** the chord to start recording hands-free (let go and keep
  talking); **press once more** to stop + transcribe. (push_to_talk mode only.)
* **toggle** mode: a single press starts, the next press stops.

The same listener also handles "tap" hotkeys — combos that fire a callback once
per activation (used for cycling the dictation language).
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from pynput import keyboard

log = logging.getLogger("spuk.hotkey")


def _noop() -> None:
    pass


class HotkeyListener:
    """Watches a primary hotkey (push-to-talk / toggle) and optional tap hotkeys."""

    def __init__(
        self,
        key_combo: str,
        mode: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_cancel: Callable[[], None] | None = None,
        taps: dict[str, Callable[[], None]] | None = None,
        handsfree: bool = True,
        double_tap_seconds: float = 0.4,
    ) -> None:
        self._expected = set(keyboard.HotKey.parse(key_combo))
        self._mode = mode
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_cancel = on_cancel or _noop
        # Hands-free double-tap only makes sense for push-to-talk (toggle already
        # latches on a single press).
        self._handsfree = handsfree and mode == "push_to_talk"
        self._double = double_tap_seconds

        # Tap hotkeys: parsed-combo -> (key-set, callback, already-fired flag).
        self._taps = [
            {"keys": set(keyboard.HotKey.parse(combo)), "cb": cb, "fired": False}
            for combo, cb in (taps or {}).items()
        ]

        self._pressed: set = set()
        self._listener: keyboard.Listener | None = None

        # --- chord state machine -----------------------------------------
        self._chord_down = False        # is the chord currently fully held?
        self._recording = False         # are we capturing audio right now?
        self._latched = False           # hands-free recording (chord not held)
        self._toggle_on = False         # toggle-mode recording state
        self._press_time = 0.0          # when the current chord press began
        self._last_tap_time = float("-inf")  # when the previous quick tap ended
        self._pending_double = False    # current press completes a double-tap
        self._ignore_release = False    # swallow the release that stopped hands-free

    # --- backend-agnostic key feed ---------------------------------------
    #
    # `_feed_press` / `_feed_release` take an ALREADY-CANONICAL key (a
    # `pynput.keyboard.Key`/`KeyCode`, matching what `keyboard.HotKey.parse`
    # produces) and drive the chord/tap state. Both the pynput path
    # (`_on_press`/`_on_release`, which canonicalise via the listener) and the
    # Linux evdev path (which canonicalises via keycode→Key mapping) call these,
    # so the FSM stays the single source of truth — no duplicated chord logic.

    def _satisfied(self, expected: set) -> bool:
        return expected.issubset(self._pressed)

    def _fire_taps(self) -> None:
        for tap in self._taps:
            if self._satisfied(tap["keys"]):
                if not tap["fired"]:
                    tap["fired"] = True
                    tap["cb"]()

    def _rearm_taps(self) -> None:
        for tap in self._taps:
            if not self._satisfied(tap["keys"]):
                tap["fired"] = False

    def _feed_press(self, key) -> None:
        """Register a canonical key going down and advance the chord/tap state."""
        self._pressed.add(key)
        self._fire_taps()
        if self._satisfied(self._expected) and not self._chord_down:
            self._chord_down = True
            self._chord_edge(down=True, t=time.monotonic())

    def _feed_release(self, key) -> None:
        """Register a canonical key going up and advance the chord/tap state."""
        self._pressed.discard(key)
        self._rearm_taps()
        if self._chord_down and not self._satisfied(self._expected):
            self._chord_down = False
            self._chord_edge(down=False, t=time.monotonic())

    # --- pynput plumbing -------------------------------------------------

    def _canonical(self, key):
        assert self._listener is not None
        return self._listener.canonical(key)

    def _on_press(self, key) -> None:
        self._feed_press(self._canonical(key))

    def _on_release(self, key) -> None:
        self._feed_release(self._canonical(key))

    # --- the actual behaviour (driven purely by chord up/down edges) -----

    def _chord_edge(self, down: bool, t: float) -> None:
        """Handle the chord becoming fully pressed (down) or released (up).

        Kept free of pynput specifics so it can be unit-tested by feeding edges
        and timestamps directly.
        """
        if self._mode == "toggle":
            if down:
                self._toggle_on = not self._toggle_on
                (self._on_start if self._toggle_on else self._on_stop)()
            return

        # push_to_talk (with optional hands-free double-tap)
        if down:
            self._press_down(t)
        else:
            self._press_up(t)

    def _press_down(self, t: float) -> None:
        if self._latched:
            # Hands-free is running: this press stops it and transcribes.
            self._latched = False
            self._recording = False
            self._ignore_release = True
            self._on_stop()
            return
        # Begin capturing immediately (keeps hold-to-talk latency low). Whether
        # this turns out to be a hold, a discarded tap, or the start of a
        # hands-free latch is decided on release.
        self._pending_double = self._handsfree and (t - self._last_tap_time) <= self._double
        self._recording = True
        self._press_time = t
        self._on_start()

    def _press_up(self, t: float) -> None:
        if self._ignore_release:
            self._ignore_release = False
            return
        if not self._recording:
            return
        held = t - self._press_time
        if held >= self._double:
            # A real hold → push-to-talk: stop and transcribe.
            self._recording = False
            self._last_tap_time = float("-inf")
            self._pending_double = False
            self._on_stop()
            return
        # A quick tap.
        if self._pending_double:
            # Second tap of a double-tap → latch hands-free; keep recording.
            self._latched = True
            self._pending_double = False
            self._last_tap_time = float("-inf")
            return
        # First tap → discard this tiny clip and wait for a possible second tap.
        self._recording = False
        self._pending_double = False
        self._last_tap_time = t
        self._on_cancel()

    # --- lifecycle -------------------------------------------------------

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
