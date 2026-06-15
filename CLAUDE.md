# CLAUDE.md

Conventions for Claude Code in this repo. See [AGENTS.md](AGENTS.md) for the full
rules — this is the short version.

## What Spuk is

Private, **local, free** press-to-talk dictation for **macOS and Windows**.
Hotkey → mic → local Whisper (faster-whisper) → paste into the focused field.
Languages: any of the ~100 the multilingual Whisper model supports — English, German,
and Polish ship as the starter set, and users add more from Settings (⚙); switchable
live. Runs as a cross-platform tray app; built for the author and family.

## Hard constraints (do not violate)

- Core loop stays 100% local and free — no required network calls.
- Cross-platform: one codebase runs on macOS + Windows. Isolate platform bits.
- Claude post-processing is optional, OFF by default, double-gated, capped, and
  logged. Never weaken the guards in `src/spuk/postprocess.py`. Never hardcode keys.
- Use multilingual Whisper models; keep Unicode-safe clipboard paste as default.

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
  hotkey.py        global hotkey FSM: hold (push-to-talk), double-tap hands-free, toggle (pynput)
  paste.py         clipboard save → set → Cmd+V → restore
  postprocess.py   optional, OFF-by-default text cleanup (gated)
  core.py          SpukCore engine + runtime language state (UI-agnostic)
  updates.py       manual "Check for updates" — compares the GitHub release tag (user-triggered only)
  ui_bar.py        floating pill UI (PySide6); ui_window.py = Settings window
  tray.py          alternate system-tray UI (pystray; --tray)
  __main__.py      entry point (floating pill by default, --tray / --headless)
scripts/check_env.py     Phase 0 sanity check
packaging/               PyInstaller spec + build_macos.sh / build_windows.ps1
docs/                    ARCHITECTURE.md, PLAN.md
```

Current status: **Phase 1 + cross-platform (1.5) complete in code** (Mac+Win tray
app, en/de/pl). Next: live verification on hardware, then Phase 2 (latency,
robustness). The native-Swift plan is superseded by the cross-platform Python app.
