# Spuk 👻

**Talk, and your words appear.** Spuk is a tiny app that types for you: hold a key,
say what you want to write, let go — and the text drops straight into whatever you
were typing in (an email, a message, a document, anywhere).

No subscription. No internet needed after setup. Your voice never leaves your
computer. It's free, forever.

Works on **Mac** and **Windows**, in **English, German, and Polish**.

---

## ✨ What you get

- 🆓 **Free** — no account, no subscription, no hidden costs.
- 🔒 **Private** — everything happens on your own computer. Nothing is uploaded.
- 🌍 **Three languages** — English, German (with ä ö ü ß), Polish (with ą ę ł ó ż) — switch any time.
- 🎤 **Just hold a key and talk** — no buttons to find, no windows to open.
- 💻 **Mac and Windows** — same app, your choice.

There's a small floating pill at the bottom of your screen that shows when Spuk is
listening. Hover it with your mouse to see the language buttons and shortcuts.

---

## ⬇️ Download & Install

> 💡 You only do this **once**. After it's set up, you just talk.

Go to the **[Releases page](https://github.com/1mp3ctz/spuk/releases)** and open
the newest release at the top. Under **"Assets"** you'll see the downloads. Pick
the one for your computer below and follow the steps.

---

### 🍎 On a Mac

#### 1. Download

- On the Releases page, click **`Spuk-macos.zip`** to download it.
- It lands in your **Downloads** folder. Double-click the `.zip` — it unzips into
  an app called **Spuk** (with a little ghost icon).
- Drag **Spuk** into your **Applications** folder. *(Recommended, but not required.)*

#### 2. Open it the first time (important — read this!)

Because Spuk is a small personal project and not sold in the App Store, your Mac
will be cautious the **first** time. This is normal. Here's the exact way around it:

1. **Don't** double-click it the normal way the first time.
2. **Right-click** (or hold **Control** and click) the **Spuk** icon.
3. In the little menu, click **Open**.
4. A box pops up saying it's from an unidentified developer. Click **Open** again.

That's it — from now on you can open Spuk normally by double-clicking.

> 😟 **If it says "Spuk is damaged and can't be opened"** — don't worry, it isn't
> damaged. See the [Troubleshooting](#-troubleshooting) section near the bottom for
> the one-line fix.

#### 3. Give it permission to hear you and type for you

The first time it runs, your Mac will ask for permission. Spuk needs three, all in
the same place. Open **System Settings → Privacy & Security**, and turn **Spuk ON**
in each of these:

- **Microphone** — so it can hear you. ✅
- **Accessibility** — so it can type the text for you. ✅
- **Input Monitoring** — so the hold-to-talk key works. ✅

> If you don't see Spuk in one of these lists, try Spuk once (hold the keys and
> talk) and it will appear so you can switch it on. You may need to quit and reopen
> Spuk after granting these.

#### 4. Wait about a minute the very first time ⏳

The first time only, Spuk quietly downloads its "ears" — the part that understands
speech (about 480 MB). **You need internet for this one time.** While it downloads,
the pill may say it's **getting ready / warming up**. This is normal — give it up
to a minute. After this, Spuk works **completely offline, forever**.

#### 5. Talk! 🎤

1. Click into any text box (an email, Notes, a chat, anywhere you'd type).
2. **Hold down `Control` + `Option`** (the ⌃ and ⌥ keys, next to the space bar).
3. **Speak** clearly while holding them.
4. **Let go.** A moment later, your words appear right where the cursor was.

---

### 🪟 On Windows

#### 1. Download

- On the Releases page, click **`Spuk-windows.zip`** to download it.
- Find it in your **Downloads** folder. **Right-click** it → **Extract All…** →
  **Extract**. *(Important: actually extract it — don't run it from inside the zip.)*
- You now have a **Spuk** folder. Inside is **`Spuk.exe`** (the ghost icon). That's
  the app. You can move the whole **Spuk** folder to your Desktop and right-click
  `Spuk.exe` → **Send to → Desktop (create shortcut)** for easy access.

#### 2. Open it the first time (important — read this!)

Because Spuk is a small personal project, Windows will show a blue warning box the
**first** time. This is normal and safe. Here's exactly what to click:

1. Double-click **`Spuk.exe`**.
2. A blue box appears: **"Windows protected your PC."**
3. Click the small **"More info"** link in that box.
4. A **"Run anyway"** button appears. Click it.

That's it — Windows only asks this the first time.

#### 3. Give it permission to hear you

The first time, Windows may ask to let Spuk use your **microphone** — click **Yes** /
**Allow**. If it didn't ask, or if dictation isn't picking up your voice, go to
**Settings → Privacy & security → Microphone** and make sure microphone access is
**On**, and that desktop apps are allowed to use it.

> On Windows that's the **only** permission needed — no extra steps for typing.

#### 4. Wait about a minute the very first time ⏳

Just like on Mac: the first run downloads the speech model (about 480 MB) and may
show **getting ready / warming up**. **Internet needed once.** After that, Spuk is
**fully offline and free**.

#### 5. Talk! 🎤

1. Click into any text box.
2. **Hold down `Strg` + `Alt`** (Control + Alt).
3. **Speak** while holding them.
4. **Let go** — your words appear.

> ⚠️ **German / Austrian keyboards:** the **AltGr** key (right of the space bar) is
> read by Windows as `Strg+Alt` — the same combo Spuk listens for. So pressing
> **AltGr** to type `@`, `€`, `{` etc. can make Spuk think you want to dictate. If
> this gets in your way, see [Troubleshooting](#-troubleshooting) — you can change
> the hold-to-talk keys in one line.

---

## 🎛️ How to use it

- **Dictate:** click into any text field, **hold the hotkey, speak, release.**
  - Mac: **`Control` + `Option`** · Windows: **`Strg` + `Alt`**
- **Switch language:** press **`Ctrl` + `Shift` + `L`** to cycle
  **English → German → Polish**. (You can also pick a language from the hover bar.)
  The current language shows on the pill.
- **The hover bar:** move your mouse over the little pill at the bottom of the screen.
  It expands to show **language buttons, hold-to-talk, your microphone choice, and the
  shortcuts**.

---

## 🛟 Troubleshooting

**No pill / nothing appears on screen.**
On Mac, make sure you opened it via **right-click → Open** the first time, and that
you granted the three permissions below. Try holding the hotkey and speaking — the
pill is small and sits at the bottom-center.

**I hold the keys and talk, but no text appears.**
- **Mac:** the most common cause is a missing permission. Re-check **System Settings →
  Privacy & Security** and make sure **Spuk** is ON for **Accessibility** *and*
  **Input Monitoring** *and* **Microphone**. Quit and reopen Spuk after changing these.
- **Windows:** check the microphone permission (see install step 3). Make sure your
  cursor is actually clicked into a text box.
- Hold the keys for a **full second or two** while speaking — very short taps are
  ignored on purpose.

**The microphone isn't picking up my voice.**
Hover the pill and check the **microphone picker** — the wrong input device (e.g. a
disconnected headset) may be selected. Pick your real microphone.

**Mac says "Spuk is damaged and can't be opened."**
It's not damaged — this is the unsigned-app warning in disguise. The simple fix:
1. Open the **Terminal** app (press `Cmd+Space`, type *Terminal*, press Enter).
2. Type this and press Enter (drag the Spuk app onto the window to fill in the path
   if you're unsure):
   ```
   xattr -dr com.apple.quarantine /Applications/Spuk.app
   ```
3. Now open Spuk normally.

**Windows: the blue "Windows protected your PC" box has no "Run anyway".**
Click the **"More info"** link first — the **Run anyway** button only appears after that.

**The first launch is taking a while / seems stuck.**
On the very first run it's downloading the speech model (~480 MB). Give it up to a
minute on a normal connection, and make sure you're online **for this first run only**.

**AltGr on a German/Austrian keyboard keeps triggering Spuk.**
Windows reports **AltGr** as `Strg+Alt`. Easiest fix: require an extra key so AltGr
alone won't trigger it. Open the `config.toml` file next to the app, find `[hotkey]`,
and change:
```
key = "<ctrl>+<alt>"          ->   key = "<ctrl>+<alt>+<space>"
```
Save and restart Spuk — now you hold **Strg+Alt+Space** to dictate, and typing
`@`/`€` is no longer affected.

---

<details>
<summary><b>🧑‍💻 Build from source / for developers</b> (normal users can ignore this)</summary>

Spuk is one Python codebase. It needs [`uv`](https://docs.astral.sh/uv/) and
**Python 3.11** (the speech engine's CTranslate2 wheels don't reliably target
3.13/3.14 yet).

```bash
# macOS — UV_LINK_MODE=copy is required only on an exFAT external drive,
# which can't hold the symlinks uv would otherwise create.
UV_LINK_MODE=copy uv venv --python 3.11 .venv
UV_LINK_MODE=copy uv sync
uv run python -m spuk            # floating bar (Wispr-Flow style); default
#   --tray       menu-bar/system-tray icon instead of the bar
#   --headless   no UI, terminal only (good for debugging)
```

```powershell
# Windows
uv venv --python 3.11 .venv
uv sync
uv run python -m spuk
```

**Build native apps locally** (must build on each target OS — no cross-compiling):

```bash
bash packaging/build_macos.sh                                          # -> dist/Spuk.app
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1   # -> dist\Spuk\Spuk.exe
```

> ⚠️ **Building the `.app` on macOS must target an internal disk.** exFAT volumes
> can't store the framework symlinks PySide6/Qt bundles need. Build to an internal
> path, then copy the result back if your repo lives on an external exFAT drive.

Downloadable releases for both platforms are produced automatically by **GitHub
Actions** on macOS and Windows runners — see `.github/workflows/release.yml` and
[docs/RELEASE.md](docs/RELEASE.md).

Config lives in [`config.toml`](config.toml): model, languages, default language,
hotkeys, push-to-talk vs toggle.

</details>

---

## 📝 Notes & limitations (the honest bit)

- **Spuk is a personal project**, made to share with family — not a polished
  commercial product.
- **The app is unsigned.** That's why Mac and Windows show a one-time warning on
  first launch (the steps above get you past it safely). Removing the warnings would
  require a paid Apple Developer account and a Windows code-signing certificate; the
  app works fully without them — it's purely about the first-run prompt.
- **First launch needs internet once** to download the speech model (~480 MB).
  Everything after that is offline and free.
- Accuracy depends on your microphone and how clearly you speak. The default model
  (`small`) is a good balance of speed and accuracy on ordinary computers.

---

## 📄 License

Spuk's own code is **open source under the [MIT License](LICENSE)** — you're free to
use, copy, modify, share, and even sell it, as long as the copyright notice stays.

Spuk bundles other open-source libraries (Whisper/CTranslate2, Qt/PySide6, and
others). They keep their own licenses — see **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**.
A few are LGPL (Qt, pynput, FFmpeg); that's fully fine while Spuk stays open source.
If you later want to ship a *closed-source* commercial version, read the LGPL note in
that file first.
