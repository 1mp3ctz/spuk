"""Optional text post-processing.

The core loop calls ``processor.process(text)`` unconditionally, but the DEFAULT
processor is a no-op. Post-processing can therefore never be "accidentally on".

The Claude processor is PAID and gated behind TWO latches plus a hard daily cap.
The developer has been API-drained before — these guards are non-negotiable:
  1. post_process.enabled must be true
  2. post_process.i_understand_this_costs_money must be true
  3. the API key comes from the environment/Keychain, never hardcoded
  4. every call logs a [PAID API CALL] line
  5. a daily call cap fails closed
"""

from __future__ import annotations

import logging
from typing import Protocol

from .config import PostProcessConfig

log = logging.getLogger("spuk.postprocess")


class PostProcessor(Protocol):
    def process(self, text: str) -> str:
        ...


class NullPostProcessor:
    """Default. Returns text unchanged — zero cost, zero network."""

    def process(self, text: str) -> str:
        return text


class ClaudePostProcessor:
    """OPT-IN, PAID. Cleans punctuation/formatting via the Anthropic API.

    Not wired into Phase 1 by default — kept as the documented extension point so
    Phase 4 can enable it without reshaping the core loop. Constructing this
    without both safety flags set raises immediately.
    """

    def __init__(self, cfg: PostProcessConfig) -> None:
        if not (cfg.enabled and cfg.i_understand_this_costs_money):
            raise RuntimeError(
                "ClaudePostProcessor requires post_process.enabled AND "
                "post_process.i_understand_this_costs_money to both be true."
            )
        self._cfg = cfg
        self._calls_today = 0
        # Real implementation (Phase 4): read ANTHROPIC_API_KEY from env/Keychain,
        # construct the client here, and fail if missing.
        raise NotImplementedError(
            "ClaudePostProcessor is a Phase 4 feature and is intentionally not "
            "implemented yet. The core dictation loop never needs it."
        )

    def process(self, text: str) -> str:  # pragma: no cover - Phase 4
        if self._calls_today >= self._cfg.max_calls_per_day:
            log.warning("Daily post-process cap reached — returning text unchanged.")
            return text
        self._calls_today += 1
        log.info("[PAID API CALL] provider=%s input_chars=%d", self._cfg.provider, len(text))
        # ... Anthropic Messages API call would go here ...
        return text


def build_post_processor(cfg: PostProcessConfig) -> PostProcessor:
    """Return the no-op processor unless post-processing is explicitly enabled."""
    if not cfg.enabled:
        return NullPostProcessor()
    return ClaudePostProcessor(cfg)
