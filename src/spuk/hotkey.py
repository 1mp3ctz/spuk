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


# Modifier keys never auto-repeat at the OS level, so a key-DOWN for one we still
# believe is held can only mean its key-UP was dropped (common on macOS when focus
# shifts or the event tap briefly stalls). We use that to self-heal a desynced
# chord. Non-modifier keys DO auto-repeat, so they are deliberately excluded — a
# repeated letter key-down is auto-repeat, not a missed release.
_MODIFIER_KEYS = frozenset(
    k
    for name in (
        "ctrl", "ctrl_l", "ctrl_r",
        "alt", "alt_l", "alt_r", "alt_gr",
        "shift", "shift_l", "shift_r",
        "cmd", "cmd_l", "cmd_r",
    )
    if (k := getattr(keyboard.Key, name, None)) is not None
)


def _is_modifier(key) -> bool:
    """True if ``key`` is a modifier (which never auto-repeats its key-down)."""
    return key in _MODIFIER_KEYS


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

        # --- combo capture (Settings "press your keys") ------------------
        self._capturing = False
        self._capture_on_done: Callable[[str], None] | None = None
        self._capture_max: set = set()
        self._capture_down: set = set()

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
        if self._capturing:
            self._capture_press(key)
            return
        # Self-heal a dropped key-UP. A modifier can't auto-repeat its key-DOWN
        # without an intervening release, so a DOWN for one we still believe is held
        # means macOS dropped its release and our state is stale (common on focus
        # changes / event-tap stalls).
        if key in self._pressed and _is_modifier(key):
            if self._chord_down:
                # We thought the chord was fully held, but this re-press proves at
                # least one release was dropped — so the WHOLE chord is suspect, not
                # just this key (the other expected modifiers may be just as stale).
                # Tear the chord down and forget the other expected keys so it can
                # only re-fire once the user genuinely re-presses the full chord —
                # exactly ONE clean edge. Discarding only the re-pressed key (the
                # old behaviour) let a stale sibling modifier re-satisfy the chord
                # and fire a PHANTOM edge on every key-down, which made toggle mode
                # flip unpredictably and left the mic stuck on with no way to stop.
                self._chord_down = False
                self._pressed -= self._expected
            else:
                # Chord wasn't held; just drop this one stale hold.
                self._pressed.discard(key)
        self._pressed.add(key)
        self._fire_taps()
        if self._satisfied(self._expected) and not self._chord_down:
            self._chord_down = True
            self._chord_edge(down=True, t=time.monotonic())

    def _feed_release(self, key) -> None:
        """Register a canonical key going up and advance the chord/tap state."""
        if self._capturing:
            self._capture_release(key)
            return
        self._pressed.discard(key)
        self._rearm_taps()
        if self._chord_down and not self._satisfied(self._expected):
            self._chord_down = False
            self._chord_edge(down=False, t=time.monotonic())

    # --- combo capture ---------------------------------------------------
    #
    # While capturing, key edges feed a collector instead of the chord FSM, so
    # pressing the combo in Settings *sets* it rather than starting a recording.
    # This works for every backend because both pynput and evdev funnel through
    # `_feed_press`/`_feed_release`.

    def begin_capture(self, on_done: Callable[[str], None]) -> None:
        """Capture the next combo the user presses instead of driving the FSM.

        ``on_done`` is called once, with the canonical combo string, on the first
        key release. Fires on the listener thread — marshal to the UI thread.
        """
        self._capture_on_done = on_done
        self._capture_max = set()
        self._capture_down = set()
        self._capturing = True

    def cancel_capture(self) -> None:
        self._capturing = False
        self._capture_on_done = None

    def _capture_press(self, key) -> None:
        self._capture_down.add(key)
        # Track the largest simultaneously-held set (so Ctrl+Alt captures both).
        if len(self._capture_down) >= len(self._capture_max):
            self._capture_max = set(self._capture_down)

    def _capture_release(self, key) -> None:
        from .hotkey_format import keys_to_combo_string

        combo = keys_to_combo_string(self._capture_max)
        on_done = self._capture_on_done
        self._capturing = False
        self._capture_on_done = None
        self._capture_down = set()
        self._capture_max = set()
        if on_done and combo:
            on_done(combo)

    # --- live re-binding -------------------------------------------------

    def update_bindings(self, *, key_combo, mode, taps, handsfree, double_tap_seconds) -> None:
        """Re-point what the listener matches, in place — NO listener restart.

        Tearing down and recreating the pynput CGEventTap (or the evdev reader
        threads) to apply a new hotkey crashes on macOS. Instead the running
        listener keeps feeding key edges and we just swap the combos it matches
        against. Each field is reassigned to a fresh object (atomic in CPython)
        and transient chord/tap state is reset, so the new binding starts clean
        even though this is called from the UI thread while the listener thread
        may be reading.
        """
        self._expected = set(keyboard.HotKey.parse(key_combo))
        self._mode = mode
        self._handsfree = handsfree and mode == "push_to_talk"
        self._double = double_tap_seconds
        self._taps = [
            {"keys": set(keyboard.HotKey.parse(combo)), "cb": cb, "fired": False}
            for combo, cb in (taps or {}).items()
        ]
        self.reset_state()

    def reset_state(self) -> None:
        """Forget all transient key/chord state, returning to a clean slate.

        Clears the pressed-key set and every chord/tap latch (but NOT the bindings
        themselves). The UI calls this as an escape hatch to un-wedge a listener
        whose chord got stuck "down" after macOS dropped a modifier release. Field
        reassignment is atomic in CPython, so it's safe to call from the UI thread
        while the listener thread may be reading.
        """
        self._pressed = set()
        self._chord_down = False
        self._recording = False
        self._latched = False
        self._toggle_on = False
        self._pending_double = False
        self._ignore_release = False
        self._last_tap_time = float("-inf")
        for tap in self._taps:
            tap["fired"] = False

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
