"""Provisional-text manager for live streaming dictation.

Tracks the text that has been typed but not yet confirmed (a partial result from
SFSpeechRecognizer). On each update, erases the previous provisional text via
Backspace, then types the new text. On commit the tracking is cleared (the final
text is now permanent). On cancel the provisional text is erased and tracking cleared.

All type/backspace calls go through injectable functions (default: paste.live_type
and paste.live_backspace) so tests run with zero real pynput calls.
"""

from __future__ import annotations

from typing import Callable


class LiveInserter:
    def __init__(
        self,
        type_fn: Callable[[str], None] | None = None,
        backspace_fn: Callable[[int], None] | None = None,
    ) -> None:
        self._type_fn = type_fn
        self._backspace_fn = backspace_fn
        self._provisional = ""

    def _type(self, text: str) -> None:
        if self._type_fn is not None:
            self._type_fn(text)
        else:
            from .paste import live_type
            live_type(text)

    def _backspace(self, count: int) -> None:
        if self._backspace_fn is not None:
            self._backspace_fn(count)
        else:
            from .paste import live_backspace
            live_backspace(count)

    # Streaming partials normally grow ("hi" → "hi there") or correct their tail
    # ("their" → "there"), sharing most of their prefix with the previous partial.
    # When a new partial shares less than this fraction of the previous provisional
    # text, it is a NEW utterance, not a correction: Apple's recognizer resets its
    # running transcript after a ~1s pause and restarts from the next phrase (a
    # known SFSpeechRecognizer behavior). Backspacing to "match" it would erase
    # everything already dictated, so we keep the prior text and append instead.
    _RESET_PREFIX_FRACTION = 0.5

    def update(self, text: str) -> None:
        """Render a streaming partial, touching only what changed.

        Growth and tail corrections keep the common prefix and only
        backspace/retype the divergent tail — fewer keystrokes, less flicker, less
        fighting with the focused field's autocorrect.

        A partial that shares almost nothing with the previous one is treated as a
        new utterance (see ``_RESET_PREFIX_FRACTION``): the prior text is committed
        in place and the new phrase appended after it, rather than backspacing the
        whole line away.
        """
        prev = self._provisional
        if prev and self._is_reset(prev, text):
            needs_space = self._commit_current()
            if text:
                if needs_space and not text[:1].isspace():
                    self._type(" ")
                self._type(text)
            self._provisional = text
            return

        common = 0
        for a, b in zip(prev, text):
            if a != b:
                break
            common += 1
        erase = len(prev) - common
        if erase > 0:
            self._backspace(erase)
        suffix = text[common:]
        if suffix:
            self._type(suffix)
        self._provisional = text

    def _is_reset(self, prev: str, text: str) -> bool:
        """True if ``text`` is a fresh utterance rather than a growth/correction of
        ``prev``. An empty partial is Apple signalling a boundary (keep prior text).
        Compared case-insensitively so a capitalisation/punctuation rewrite
        ("hello world" → "Hello world.") stays a correction, not a reset."""
        if not text:
            return True
        if text[: len(prev)].lower() == prev.lower():
            return False  # pure growth (or identical)
        if prev[: len(text)].lower() == text.lower():
            return False  # pure truncation/shrink of the same utterance
        common = 0
        for a, b in zip(prev.lower(), text.lower()):
            if a != b:
                break
            common += 1
        return common < self._RESET_PREFIX_FRACTION * len(prev)

    def _commit_current(self) -> bool:
        """Lock the current provisional text as permanent (no keystrokes). Returns
        True if a following appended segment needs a leading space separator."""
        needs_space = bool(self._provisional) and not self._provisional[-1].isspace()
        self._provisional = ""
        return needs_space

    def commit(self) -> None:
        """Mark current provisional text as permanent. No keystrokes sent."""
        self._commit_current()

    def cancel(self) -> None:
        """Erase provisional text and clear tracking."""
        if self._provisional:
            self._backspace(len(self._provisional))
        self._provisional = ""
