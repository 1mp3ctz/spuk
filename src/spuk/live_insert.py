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
        """Replace provisional text with ``text``. Erases previous via Backspace."""
        if self._provisional:
            self._backspace(len(self._provisional))
        self._type(text)
        self._provisional = text

    def commit(self) -> None:
        """Mark current provisional text as permanent. No keystrokes sent."""
        self._provisional = ""

    def cancel(self) -> None:
        """Erase provisional text and clear tracking."""
        if self._provisional:
            self._backspace(len(self._provisional))
        self._provisional = ""
