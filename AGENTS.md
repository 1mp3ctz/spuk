# AGENTS.md — conventions for AI agents & contributors

Spuk is a private, local, free macOS dictation tool. Read this before changing code.

## Golden rules

1. **Local-first and free.** The core loop (record → transcribe → paste) must run
   100% on-device with zero network calls. Never add a required cloud dependency.
2. **Never spend money silently.** The only paid path is Claude post-processing,
   which is OFF by default and gated behind two flags + a daily cap (see
   `src/spuk/postprocess.py`). Do not weaken these guards. Do not hardcode API keys.
3. **Multi-language, cross-platform.** Supported languages are English (default),
   German, Polish — use multilingual Whisper models (never the `.en` variants),
   switchable at runtime. Keep Unicode-safe clipboard paste as the default
   insertion method (umlauts ä ö ü, Polish ą ę ł ó ż) — never per-character
   keystroke injection. Code must run on **both macOS and Windows** from one
   codebase (platform-specific bits isolated, e.g. the paste modifier in `paste.py`).

## Environment

- **Python 3.11 only** (system `python3` is 3.14 and lacks ctranslate2 wheels).
- The repo lives on an **exFAT** drive → always create the venv in copy mode:
  `UV_LINK_MODE=copy uv venv --python 3.11 .venv`. Never call bare `python3`; use
  `uv run`.

## Build / run

```bash
UV_LINK_MODE=copy uv sync
uv run python scripts/check_env.py     # sanity check
uv run python -m spuk                  # run the dictation loop
```

## Code conventions

- Small, focused modules (one responsibility each). Keep `core.py` thin — it only wires.
- Immutable config (`config.py` uses frozen dataclasses). Validate at boundaries.
- The Whisper engine is swappable behind the `Transcriber` protocol; add new engines
  in `transcriber.py` via `build_transcriber`, don't branch in the core loop.
- Handle mic / permission / empty-transcript failures explicitly and log clearly.

## Don't touch without discussion

- The post-processing safety gates in `postprocess.py`.
- The clipboard save/restore logic in `paste.py` (it protects the user's clipboard).
- `requires-python` pin in `pyproject.toml`.
