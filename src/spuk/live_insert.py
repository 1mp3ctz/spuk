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

    def update(self, text: str) -> None:
        """Replace provisional text with ``text``, touching only what changed.

        Streaming partials usually just grow ("hi" → "hi there"), so we keep the
        common prefix and only backspace/retype the divergent tail. Fewer
        keystrokes means less flicker and far less fighting with the focused
        field's autocorrect than erasing and retyping the whole line each time.
        """
        prev = self._provisional
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

    def commit(self) -> None:
        """Mark current provisional text as permanent. No keystrokes sent."""
        self._provisional = ""

    def cancel(self) -> None:
        """Erase provisional text and clear tracking."""
        if self._provisional:
            self._backspace(len(self._provisional))
        self._provisional = ""
