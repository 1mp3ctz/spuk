# Packaging Spuk for macOS and Windows

Spuk is one Python codebase packaged into a native-feeling tray app on each OS
with [PyInstaller](https://pyinstaller.org/). There is **no cross-compilation**:
build the macOS app on a Mac and the Windows app on a PC.

## Build

**macOS** (on a Mac):
```bash
bash packaging/build_macos.sh        # -> dist/Spuk.app
```

**Windows** (on a PC with Python 3.11 + uv):
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1   # -> dist\Spuk\Spuk.exe
```

Both bundle a default, user-editable `config.toml` beside the app. The Whisper
model (~480 MB for `small`) is **not** bundled — it downloads on first launch to
the OS user cache (`~/.cache/huggingface` / `%USERPROFILE%\.cache\huggingface`),
so the first run needs internet and shows "Warming model…". Every run after is
fully offline and free.

## Installing for non-technical family (the honest friction)

These builds are **unsigned**. The OS will warn the first time:

- **macOS Gatekeeper:** right-click the app → **Open** → **Open** (once). After
  that it launches normally. They also grant **Microphone**, **Accessibility**,
  and **Input Monitoring** to *Spuk* in System Settings → Privacy & Security.
- **Windows SmartScreen:** **More info** → **Run anyway** (once). No extra
  permission grants are needed for the hotkey/paste on Windows.

To remove the warnings entirely (a smoother experience for relatives):
- macOS: a paid **Apple Developer** account ($99/yr) → sign + notarize.
- Windows: a code-signing certificate (~$100+/yr) or build reputation over time.

Both cost money, so they're **opt-in decisions for the project owner** — the app
works fully without them; it's purely about removing the first-run warning.

## Known packaging caveats

- PyInstaller + ctranslate2/av/faster-whisper bundles large native libraries; the
  `spuk.spec` collects them explicitly. If a packaged build can't import one,
  add it to the `collect_all` list in `spuk.spec`.
- Test the packaged app on a **clean** machine (no dev tools) to catch missing
  bundled libraries — this is exactly the step that needs a real Windows box.
