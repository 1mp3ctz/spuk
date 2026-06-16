# Packaging Spuk for macOS, Windows, and Linux

Spuk is one Python codebase packaged into a native-feeling app on each OS with
[PyInstaller](https://pyinstaller.org/). There is **no cross-compilation**: build
the macOS app on a Mac, the Windows app on a PC, and the Linux packages on Linux.

## Build

**macOS** (on a Mac):
```bash
bash packaging/build_macos.sh        # -> dist/Spuk.app
```

**Windows** (on a PC with Python 3.11 + uv):
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1   # -> dist\Spuk\Spuk.exe
```

**Linux** (x86_64, on a Linux box — see "Linux build" below):
```bash
bash packaging/build_linux.sh        # -> dist/spuk_<ver>_amd64.deb, .rpm, tarball
```

All three bundle a default, user-editable `config.toml` beside the app. The Whisper
model (~480 MB for `small`) is **not** bundled — it downloads on first launch to
the OS user cache (`~/.cache/huggingface` / `%USERPROFILE%\.cache\huggingface`),
so the first run needs internet and shows "Warming model…". Every run after is
fully offline and free.

## Linux build (x86_64)

Run on a **Linux x86_64** host (PyInstaller can't cross-build from macOS/Windows):

```bash
bash packaging/build_linux.sh
```

**Required tooling on the build host:**
- Python 3.11 + [uv](https://docs.astral.sh/uv/) (the repo pins 3.11; `evdev`
  installs only on Linux via the `sys_platform == 'linux'` marker).
- [`fpm`](https://github.com/jordansissel/fpm) — a Ruby gem that emits the `.deb`
  and `.rpm`: `gem install --no-document fpm` (needs **ruby**).
- `rpm` / `rpmbuild` on PATH so fpm can write the `.rpm`
  (`apt install rpm` on Debian/Ubuntu, `dnf install rpm-build` on Fedora). If
  it's missing the script still builds the `.deb` and tarball and **skips** the
  `.rpm` with a warning.

**Artifacts** (under `dist/`, version parsed from `pyproject.toml`):
- `spuk_<ver>_amd64.deb` — Debian/Ubuntu
- `spuk-<ver>.x86_64.rpm` — Fedora/RHEL/openSUSE
- `spuk-<ver>-linux-x86_64.tar.gz` — portable bundle with `install.sh` / `uninstall.sh`

**Install layout (FHS), identical across all three:**

| Path | Contents |
|------|----------|
| `/opt/spuk/` | the PyInstaller onedir bundle (`Spuk` + libs) |
| `/usr/bin/spuk` | symlink → `/opt/spuk/Spuk` |
| `/usr/share/applications/spuk.desktop` | menu entry |
| `/usr/share/icons/hicolor/<size>/apps/spuk.png` | icons (16–512px) |

**Install commands:**
```bash
sudo apt install ./spuk_<ver>_amd64.deb        # Debian/Ubuntu
sudo dnf install ./spuk-<ver>.x86_64.rpm       # Fedora/RHEL
# Portable:
tar xzf spuk-<ver>-linux-x86_64.tar.gz && cd spuk-<ver>-linux-x86_64 && sudo ./install.sh
```

**Arch / Manjaro:** see `packaging/aur/PKGBUILD` (repackages the release tarball;
bump `pkgver` to match `pyproject.toml`, then `updpkgsums`).

**One-time setup the package tells the user about:** Spuk reads `/dev/input` for
the global hotkey and writes `/dev/uinput` to inject paste, so the user must be in
the **`input` group** (`sudo usermod -aG input $USER`, then log out/in). The
`.deb`/`.rpm` `postinst` offers to add the installing user automatically. A
clipboard tool (`wl-clipboard` on Wayland, `xclip`/`xsel` on X11) is required;
`ydotool` is an optional Wayland paste fallback.

> **No AppImage / Flatpak.** Their sandboxes block reading `/dev/input` and the
> `uinput` paste injection Spuk depends on, so they can't deliver a working global
> hotkey. We ship FHS packages instead. **x86_64 only** for now.

## Installing for non-technical family (the honest friction)

These builds are **unsigned**. The OS will warn the first time:

- **macOS Gatekeeper:** right-click the app → **Open** → **Open** (once). After
  that it launches normally. They also grant **Microphone**, **Accessibility**,
  and **Input Monitoring** to *Spuk* in System Settings → Privacy & Security.
- **Windows SmartScreen:** **More info** → **Run anyway** (once). No extra
  permission grants are needed for the hotkey/paste on Windows.
- **Linux:** no OS signing prompt, but the hotkey needs the **`input` group**
  (the `postinst` offers to add the installing user) and a one-time log out/in.
  See "Linux build" above.

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
