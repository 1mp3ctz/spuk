# Spuk 👻

> *Spuk* — German for "haunting". A voice that makes text appear in your field out of nowhere.

A private, **fully local, free** dictation tool for macOS on Apple Silicon — a
stripped-down clone of Wispr Flow. Hold a global hotkey, speak (German or
English), release, and the transcription is pasted into whatever text field is
focused. No subscription, no per-use API cost, no audio leaves your Mac.

- **Transcription:** Whisper model via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) — *not* the slow PyTorch `openai/whisper` runtime.
- **Default model:** multilingual `small`, `int8`, language forced to German.
- **Insertion:** clipboard + synthetic `Cmd+V` (umlaut-safe; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).
- **Optional:** Claude post-processing — **off by default, paid, double-gated.**

This is also a learning project (native macOS Swift is the Phase 3 target), so
the code is kept clean, small, and documented.

## Requirements

- macOS on Apple Silicon (built/tested on an M3 Air, 16 GB).
- [`uv`](https://docs.astral.sh/uv/) and Homebrew **Python 3.11** (the system 3.14 lacks ctranslate2 wheels).

## Setup

```bash
cd "/Volumes/2TB/Claude/Spuk"

# Create the env on Python 3.11 (copy mode so it works on the exFAT drive)
UV_LINK_MODE=copy uv venv --python 3.11 .venv
UV_LINK_MODE=copy uv sync

# Verify the environment (imports, mic, clipboard)
uv run python scripts/check_env.py
```

### Grant macOS permissions (one time)

The Python prototype inherits permissions from **the terminal app you run it in**
(Terminal / iTerm / VS Code). In **System Settings → Privacy & Security**, add
your terminal to:

| Pane | Why |
|------|-----|
| **Microphone** | record your voice |
| **Accessibility** | send the synthetic `Cmd+V` into other apps |
| **Input Monitoring** | detect the global hotkey while another app is focused |

> The Microphone prompt appears automatically on first run; Accessibility and
> Input Monitoring you toggle on manually. A proper `.app` with its own scoped
> permissions is the Phase 3 goal.

## Run

```bash
uv run python -m spuk
```

Focus any text field, **hold `Ctrl+Alt+Space`**, speak a German sentence, release.
The first run downloads the `small` model (~480 MB) into `models/`.

Configure the model, hotkey, and mode in [`config.toml`](config.toml).

## Phases

| Phase | What |
|-------|------|
| 0 | Repo + scaffold + env + permissions ✅ |
| 1 | Minimal end-to-end loop: hotkey → record → local Whisper → paste ✅ (Python) |
| 2 | Quality: model tuning, latency, push-to-talk vs toggle, robustness |
| 3 | Native Swift/SwiftUI menu-bar app with proper permissions UX |
| 4 | Optional Claude post-processing, custom vocabulary, settings |

Full plan: [docs/PLAN.md](docs/PLAN.md). Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

Private/personal. Not for redistribution.
