# Spuk 👻

> *Spuk* — German for "haunting". A voice that makes text appear in your field out of nowhere.

A private, **fully local and free** dictation tool — a stripped-down clone of
Wispr Flow. Hold a global hotkey, speak, release, and the transcription is pasted
into whatever text field is focused. No subscription, no per-use API cost, no
audio leaves the machine.

Built to be shared with family — runs as a simple **tray app on both macOS and
Windows** from one codebase.

- **Languages:** English (default), German, Polish — switch live from the tray menu or with `Ctrl+Alt+L`.
- **Transcription:** Whisper model via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) — runs on CPU, cross-platform, *not* the slow PyTorch `openai/whisper` runtime. Default model: `small`, int8.
- **Insertion:** clipboard + synthetic paste (`Cmd+V` on macOS, `Ctrl+V` on Windows) — Unicode-safe, so umlauts (ä ö ü) and Polish letters (ą ę ł ó ż) come through intact.
- **Optional:** Claude post-processing — **off by default, paid, double-gated.**

## Requirements (to run from source / build)

- macOS (Apple Silicon or Intel) **or** Windows 10/11.
- [`uv`](https://docs.astral.sh/uv/) and **Python 3.11** (the engine's wheels don't yet target 3.13/3.14).

## Run from source

```bash
# macOS (note: copy mode is needed only on the exFAT external drive)
UV_LINK_MODE=copy uv venv --python 3.11 .venv
UV_LINK_MODE=copy uv sync
uv run python scripts/check_env.py     # verify imports, mic, clipboard
uv run python -m spuk                   # floating bar (Wispr-Flow style)
#   --tray      menu-bar/system-tray icon instead of the bar
#   --headless  no UI, terminal only (good for debugging)
```

```powershell
# Windows
uv venv --python 3.11 .venv
uv sync
uv run python -m spuk
```

Focus any text field, **hold `Ctrl+Option`** (Mac) / **`Strg+Alt`** (Windows),
speak, release. First run downloads the `small` model (~480 MB). Cycle language
with **`Ctrl+Shift+L`**.

### macOS permissions (one time)

The source build inherits permissions from the **terminal app** you run it in; a
packaged `Spuk.app` owns its own. In **System Settings → Privacy & Security**, grant
**Microphone**, **Accessibility** (for the synthetic paste), and **Input Monitoring**
(for the global hotkey). Windows needs none of these for the hotkey/paste.

## Build native apps for family

```bash
bash packaging/build_macos.sh                                    # -> dist/Spuk.app
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1   # -> dist\Spuk\Spuk.exe
```

See [packaging/README.md](packaging/README.md) — including the honest first-run
install steps for unsigned apps (Gatekeeper / SmartScreen) and the optional paid
signing that removes the warnings.

## Configuration

Edit [`config.toml`](config.toml): model, languages (`["en","de","pl"]`), default
language, hotkeys, push-to-talk vs toggle.

## Phases

| Phase | What |
|-------|------|
| 0 | Repo + scaffold + env + permissions plan ✅ |
| 1 | Minimal end-to-end loop: hotkey → record → local Whisper → paste ✅ |
| 1.5 | Cross-platform (Mac + Win), en/de/pl, tray UI, packaging ✅ (code) |
| 2 | Quality: latency, model tuning, robustness |
| 3 | Distribution polish: tested Windows build, signed installs (optional) |
| 4 | Optional Claude post-processing, custom vocabulary, settings |

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Plan: [docs/PLAN.md](docs/PLAN.md).

## License

Private/personal, for the author and family. Not for redistribution.
