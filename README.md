# Spuk 👻

**Talk, and your words appear.** Spuk is a tiny app that types for you: hold a key,
say what you want to write, let go — and the text drops straight into whatever you
were typing in (an email, a message, a document, anywhere).

No subscription. No internet needed after setup. Your voice never leaves your
computer. It's free, forever.

Works on **Mac**, **Windows**, and **Linux**, in **almost any language** — the built-in
speech model understands around 100, so you can dictate in whatever you speak.

---

## ✨ What you get

- 🆓 **Free** — no account, no subscription, no hidden costs.
- 🔒 **Private** — everything happens on your own computer. Nothing is uploaded.
- 🌍 **Almost any language** — around 100 supported (English, German, Polish, Spanish, French, Ukrainian, and many more). Add the ones you speak and switch any time; accents and special characters (ä ö ü ß, ą ę ł ó ż, …) just work.
- 🎤 **Just hold a key and talk** — no buttons to find, no windows to open.
- 💻 **Mac, Windows, and Linux** — same app, your choice.

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

#### 1. Download & install

- On the Releases page, click **`Spuk-macos.dmg`** to download it.
- Open the downloaded `.dmg`. A window appears with the **Spuk** ghost on the left
  and your **Applications** folder on the right.
- **Drag Spuk onto Applications** — just like installing any other Mac app. Then
  eject the disk (the little ⏏ next to "Spuk" in Finder's sidebar).

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

### 🐧 On Linux

Spuk ships as normal native packages — no AppImage, no Flatpak.

#### 1. Install

Download the file for your distro from the **[Releases page](https://github.com/1mp3ctz/spuk/releases)**, then:

- **Debian / Ubuntu / Mint:** `sudo apt install ./spuk_*_amd64.deb`
- **Fedora / openSUSE / RHEL:** `sudo dnf install ./spuk-*.x86_64.rpm`
- **Arch / Manjaro:** build the `PKGBUILD` in `packaging/aur/` with `makepkg -si`.
- **Any other distro:** grab `spuk-*-linux-x86_64.tar.gz`, extract it, and run `sudo ./install.sh`.

#### 2. One-time setup (important — read this!)

So Spuk can hear your hotkey and type for you, your user must be in the **`input`**
group. The installer offers to add you, but to be sure, run:

```
sudo usermod -aG input "$USER"
```

Then **log out and back in** — group changes only apply to a fresh login.

Spuk also needs a tiny clipboard helper to drop text in. The `.deb`/`.rpm` pull one
in automatically; on other distros install **`wl-clipboard`** (Wayland) or **`xclip`**
(X11). Wayland users can optionally add **`ydotool`** for a second paste path.

> ✅ **Works on both X11 and Wayland.** Spuk reads the keyboard at the system level,
> so the hold-to-talk key works no matter which display server your distro uses.

#### 3. Talk! 🎤

1. Click into any text box.
2. **Hold `Ctrl` + `Alt`**.
3. **Speak** while holding them.
4. **Let go** — your words appear.

The first run downloads the speech model (~480 MB, internet needed once); fully
offline and free afterwards, exactly like on Mac and Windows.

---

## 🎛️ How to use it

- **Dictate (hold):** click into any text field, **hold the hotkey, speak, release.**
  - Mac: **`Control` + `Option`** · Windows: **`Strg` + `Alt`**
- **Dictate hands-free (no holding):** **double-tap** the hotkey to start recording,
  let go and talk as long as you like, then **press it once more** to stop and drop
  the text in. Great for longer dictation when you don't want to hold the keys down.
- **Switch language:** press **`Ctrl` + `Shift` + `L`** to cycle through the languages
  you've added, or pick one from the hover bar. The current language shows on the pill.
- **Add a language:** click the **⚙ gear** on the pill (or the menu-bar ghost →
  **Settings…**) to open Settings, then use **"Add a language…"** to pick from the
  ~100 the speech model supports. Your chosen languages appear as quick-switch buttons
  on the pill, and your picks are remembered between restarts.
- **The hover bar:** move your mouse over the little pill at the bottom of the screen.
  It expands to show **your languages, hold-to-talk, and the shortcuts**, plus the
  **⚙ gear** for Settings (languages & microphone).
- **Check for updates:** open **Settings** (⚙ gear or menu-bar ghost → **Settings…**)
  and click **"Check for updates"**. If a newer version exists, the installed app can
  **download and install it for you in one click** — it replaces itself and restarts
  automatically, no re-downloading by hand. (When you run Spuk from source it just opens
  the download page instead.)
- **Quit Spuk:** click the little **ghost icon in the menu bar** (top-right of the
  screen on Mac, system tray on Windows) and choose **Quit Spuk** — or use **Quit Spuk**
  in Settings. Either fully closes the app (pill included).

---

## 🛟 Troubleshooting

**No pill / nothing appears on screen.**
On Mac, make sure you opened it via **right-click → Open** the first time, and that
you granted the three permissions below. Try holding the hotkey and speaking — the
pill is small and sits at the bottom-center.

**I hold the keys and talk, but no text appears.**
- **Mac:** the most common cause is a missing permission. Re-check **System Settings →
  Privacy & Security** and make sure **Spuk** is ON for all three:
  - **Input Monitoring** — this is the one people miss; without it Spuk never *hears*
    the hold-to-talk keys, so nothing happens at all.
  - **Accessibility** — needed to paste the text once it's transcribed.
  - **Microphone** — needed to hear your voice.
- **You must fully quit and reopen Spuk after changing any of these.** macOS only
  applies a permission grant to a *freshly started* program — re-clicking the popup
  or leaving Spuk running does nothing. Quit it from the **menu-bar ghost icon →
  Quit Spuk**, then open it again.
- **Windows:** check the microphone permission (see install step 3). Make sure your
  cursor is actually clicked into a text box.
- Hold the keys for a **full second or two** while speaking — very short taps are
  ignored on purpose.

**Mac: I installed a new version and now the hotkey is dead, even though Spuk still
shows as ON in the permission lists.**
A rebuilt/updated Spuk is a *different* program to macOS, so the old "ON" switch is
pointing at the previous copy and no longer counts. Clear the stale entries and
re-grant fresh:
1. Open **Terminal** and run:
   ```
   tccutil reset Accessibility dev.kotowski.spuk
   tccutil reset ListenEvent  dev.kotowski.spuk
   ```
2. Open Spuk again and approve the **Accessibility** and **Input Monitoring** prompts.
3. Quit Spuk (menu-bar ghost → **Quit Spuk**) and reopen it once more.

**The microphone isn't picking up my voice.**
Open **Settings** (the **⚙ gear** on the pill, or the menu-bar ghost → **Settings…**)
and check the **Microphone** picker — the wrong input device (e.g. a disconnected
headset) may be selected. Pick your real microphone.

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

**Linux: I hold the keys and talk, but nothing happens.**
Almost always the `input` group. Run `groups` — if `input` isn't listed, run
`sudo usermod -aG input "$USER"` and then **log out and back in** (a reboot also
works). Spuk reads the keyboard from `/dev/input`, which needs that group.

**Linux: the text is transcribed (I see it in the log) but doesn't paste.**
Install a clipboard helper — `wl-clipboard` on Wayland, or `xclip`/`xsel` on X11 —
so Spuk can set the clipboard. On Wayland, installing `ydotool` (and starting
`ydotoold`) also gives Spuk a reliable way to send the paste keystroke.

**Linux: "could not load the Qt platform plugin xcb".**
A system Qt library is missing. On Debian/Ubuntu:
`sudo apt install libxcb-cursor0 libxkbcommon0 libegl1`. The `.deb`/`.rpm` declare
these as dependencies, so a normal package install pulls them in for you.

---

## 📄 License

Spuk's own code is **open source under the [MIT License](LICENSE)** — you're free to
use, copy, modify, share, and even sell it, as long as the copyright notice stays.

Spuk bundles other open-source libraries (Whisper/CTranslate2, Qt/PySide6, and
others). They keep their own licenses — see **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**.
A few are LGPL (Qt, pynput, FFmpeg); that's fully fine while Spuk stays open source.
If you later want to ship a *closed-source* commercial version, read the LGPL note in
that file first.

---

Spuk is an independent, personal open-source project. It is **not affiliated with,
endorsed by, or sponsored by** any other dictation or voice-software company. All
product names and trademarks mentioned anywhere are the property of their respective
owners.
