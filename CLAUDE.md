# CLAUDE.md

Conventions for Claude Code in this repo. See [AGENTS.md](AGENTS.md) for the full
rules — this is the short version.

## What Spuk is

Private, **local, free** press-to-talk dictation for **macOS, Windows, and Linux**.
Hotkey → mic → local Whisper (faster-whisper) → paste into the focused field.
Languages: any of the ~100 the multilingual Whisper model supports — English, German,
and Polish ship as the starter set, and users add more from Settings (⚙); switchable
live. Runs as a cross-platform tray app; built for the author and family.

## Hard constraints (do not violate)

- Core loop stays 100% local and free — no required network calls.
- Cross-platform: one codebase runs on macOS + Windows + Linux. Isolate platform
  bits behind `input_backend.py` (pynput on macOS/Windows, evdev/uinput on Linux).
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
  hotkey.py        global hotkey FSM: hold (push-to-talk), double-tap hands-free, toggle (backend-agnostic)
  paste.py         clipboard save → set → paste shortcut → restore (per-OS injector)
  input_backend.py picks the input backend by OS: pynput (macOS/Windows) vs evdev (Linux)
  linux_input.py   Linux only — evdev keyboard read + uinput paste injection (X11 + Wayland)
  postprocess.py   optional, OFF-by-default text cleanup (gated)
  core.py          SpukCore engine + runtime language state (UI-agnostic)
  updates.py       manual "Check for updates" — compares the GitHub release tag (user-triggered only)
  ui_bar.py        floating pill UI (PySide6); ui_window.py = Settings window
  tray.py          alternate system-tray UI (pystray; --tray)
  __main__.py      entry point (floating pill by default, --tray / --headless)
scripts/check_env.py     Phase 0 sanity check
packaging/               PyInstaller spec + build_macos.sh / build_windows.ps1 / build_linux.sh (+ linux/, aur/)
docs/                    ARCHITECTURE.md, PLAN.md
```

Current status: **Phases 1–4 complete in code; Linux (Phase 5) added** — Mac +
Windows + Linux, en/de/pl. Linux uses an evdev/uinput input backend (works on X11
+ Wayland) and ships as .deb/.rpm/tarball + AUR. Pending: live verification on real
Linux hardware — the macOS dev box can't run evdev or build the packages, so the
Linux build happens in CI. The native-Swift plan is superseded by the cross-platform Python app.
