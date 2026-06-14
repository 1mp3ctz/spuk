# CLAUDE.md

Conventions for Claude Code in this repo. See [AGENTS.md](AGENTS.md) for the full
rules — this is the short version.

## What Spuk is

Private, **local, free** macOS dictation (Wispr Flow clone). Hotkey → mic →
local Whisper (faster-whisper) → paste into the focused field. German-first.

## Hard constraints (do not violate)

- Core loop stays 100% local and free — no required network calls.
- Claude post-processing is optional, OFF by default, double-gated, capped, and
  logged. Never weaken the guards in `src/spuk/postprocess.py`. Never hardcode keys.
- Use multilingual Whisper models; keep umlaut-safe clipboard paste as default.

## Run it

```bash
UV_LINK_MODE=copy uv sync
uv run python -m spuk
```

Python **3.11** via `uv` only (system 3.14 lacks ctranslate2 wheels). Repo is on an
exFAT drive → venv must be created in copy mode (`UV_LINK_MODE=copy`).

## Layout

```
config.toml              runtime config (model, hotkey, language)
src/spuk/
  config.py        load + validate config
  audio.py         mic capture (sounddevice)
  transcriber.py   swappable Whisper engine (faster-whisper now)
  hotkey.py        global push-to-talk / toggle (pynput)
  paste.py         clipboard save → set → Cmd+V → restore
  postprocess.py   optional, OFF-by-default text cleanup (gated)
  core.py          wires the loop together
scripts/check_env.py     Phase 0 sanity check
docs/                    ARCHITECTURE.md, PLAN.md
```

Current status: **Phase 1 complete** (Python prototype). Next: Phase 2 (latency,
robustness), then the native Swift menu-bar app (Phase 3).
