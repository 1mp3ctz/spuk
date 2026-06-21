# Spuk — Architecture

## App name

**`Spuk`** — German for "haunting/ghost": a voice that appears in your text field
out of nowhere. Short, two syllables, types fast, lowercase-friendly. No collision
with existing macOS/voice/Swift tooling or a PyPI package named `spuk`. Eventual
bundle id: `dev.1mp3ctz.spuk` (reverse-DNS convention; you don't need to own the
domain for a local/ad-hoc build, but pick one you *could* own).

## The loop

```
                          ┌──────────────────────────────────────────────┐
                          │                  SPUK (core loop)             │
  ╔════════════╗  hotkey  │  ┌──────────┐   raw f32 PCM   ┌────────────┐  │
  ║  Global    ║─────────▶│  │   Mic    │────────────────▶│  Whisper   │  │
  ║  Hotkey    ║  down/up │  │ Capture  │  16kHz mono     │  (LOCAL)   │  │
  ╚════════════╝          │  └──────────┘  numpy array    └─────┬──────┘  │
        │ press-to-talk   │   sounddevice            faster-whisper        │
        ▼                 │                                     │ text     │
  user speaks             │                          ┌──────────▼───────┐  │
                          │      (dotted = optional) │   post-process?  │  │ ← OFF by default
                          │        ┌───────────────┐ │  NullPostProc.   │  │
                          │        │  Claude API   │·│  (no-op)         │  │
                          │        │  (PAID,gated) │ └────────┬─────────┘  │
                          │        └───────────────┘          │ text       │
                          │                          ┌────────▼─────────┐  │
                          │                          │  Text Insertion  │  │
                          │                          │ save clip → set → │  │
                          │                          │ Cmd+V → restore  │  │
                          │                          └────────┬─────────┘  │
                          └───────────────────────────────────┼────────────┘
                                                               ▼
                                                 focused text field (Claude, etc.)
```

## Box → Python lib → eventual Swift-native equivalent

| Box | Python (prototype) | Swift-native (Phase 3) | Why it changes |
|-----|--------------------|------------------------|----------------|
| Global hotkey | `pynput` | Carbon `RegisterEventHotKey` | event-driven, lower latency, less TCC surface |
| Mic capture | `sounddevice` (PortAudio) | `AVAudioEngine` + `installTap` | native device-switch / sample-rate handling |
| Resample/format | (capture at 16k) | `AVAudioConverter` | correct + free |
| Whisper | `faster-whisper` (CTranslate2) | `whisper.cpp` (Metal) | removes Python runtime from the shipped app |
| Post-process (opt.) | `anthropic` SDK (gated) | `URLSession` (gated) | same gating, native HTTP |
| Text insertion | `pyperclip` + `pynput` Cmd+V | `NSPasteboard` + `CGEvent` | NSPasteboard is the real API |

## Runtime + model choice (German on M3/16 GB)

Realistic ballpark latency for a ~5 s utterance (audio-end → text-ready; cold
start excluded). **Estimates — Phase 2 replaces them with real numbers.**

| Model | Runtime | Size (quant) | ~5 s latency | German | Verdict |
|-------|---------|--------------|--------------|--------|---------|
| tiny | faster-whisper int8 | ~75 MB | ~0.3–0.6 s | poor (drops umlauts) | no |
| base | faster-whisper int8 | ~140 MB | ~0.5–0.9 s | mediocre | fallback |
| **small** | **faster-whisper int8** | **~480 MB** | **~0.9–1.6 s** | **good — sweet spot** | **DEFAULT** |
| small | MLX 4-bit | ~480 MB | ~0.7–1.2 s | good | Phase 2 A/B |
| large-v3-turbo | faster-whisper int8 | ~1.6 GB | ~1.8–3.5 s | excellent | quality tier |
| large-v3-turbo | MLX 4-bit | ~1.6 GB | ~1.3–2.5 s | excellent | best native later |

Why CPU+int8 and not GPU for faster-whisper: CTranslate2 has no Metal backend on
Apple Silicon; int8 on CPU is the fast path and avoids pinning a big GPU model on
a fanless Air. The transcriber is a swappable interface, so MLX / whisper.cpp drop
in later without touching the core loop.

## Why clipboard-paste, not per-character keystrokes

Synthetic per-character key events pass through the active keyboard layout and
dead-key state machine. On a German layout, `ä ö ü ß` and dead keys (`^ ´ \``) get
re-interpreted, dropped, or combined with the next character. Clipboard + `Cmd+V`
inserts the **exact** string in one atomic, layout-independent action — umlaut-safe.
The only cost is clobbering the clipboard, mitigated by save/restore (text-only in
Phase 1; full NSPasteboard fidelity is a Phase 2 upgrade).

## macOS permissions (TCC)

macOS gates capabilities behind TCC (Transparency, Consent & Control):

| Permission | Needed for | Prototype holder | Swift app |
|-----------|-----------|------------------|-----------|
| Microphone | capture audio | the terminal app | `NSMicrophoneUsageDescription`, prompt on first `AVAudioEngine` start |
| Accessibility | post `Cmd+V` into other apps | the terminal app | Spuk.app in the Accessibility list; can't request programmatically |
| Input Monitoring | global hotkey while unfocused | the terminal app | `RegisterEventHotKey` minimises this; `NSEvent` global monitor needs it |

**Teaching point:** in the prototype every permission is held by the *host terminal*,
not by Spuk. That's leaky (anything in that terminal now has mic + accessibility) —
one of the real reasons to do the native Phase 3 port, where a `.app` owns its own
scoped permissions.

**Self-distribution (no App Store):** build locally and ad-hoc codesign
(`codesign --force --deep --sign - Spuk.app`). Runs on your own Mac; **not**
distributable to others without notarization. Ad-hoc identity is unstable across
rebuilds → TCC may re-prompt; a free "Apple Development" cert keeps TCC stable.
**Do not sandbox** — a sandboxed app can't post `CGEvent`s into other apps, which
would kill the core feature.

## Window screenshot (macOS-only)

Press both ⌘ keys simultaneously to capture the frontmost window and paste it as an image.

### `mac_flags_tap` — listen-only Quartz event tap

`MacFlagsTap` (`screenshot.py`) opens a **listen-only** `CGEventTap` on the `flagsChanged` event (modifier state changes). It is passive — it never intercepts or swallows events — which means it requires no Accessibility permission and cannot block other keyboard input. The tap calls `on_dual_cmd` when both ⌘ bits are set and no other modifiers are held.

This is the shared foundation that also unblocks Fn-key hotkey support (issue #17): a dedicated `flagsChanged` tap reading the `kCGEventFlagMaskSecondaryFn` bit is the same pattern, macOS-only, and fits cleanly into this seam.

### Window picker + capture

`pick_window` reads `CGWindowListCopyWindowInfo` to find the frontmost app's layer-0 window, then `capture_window_to_png` runs `screencapture -l <window_id>` to write a PNG to a temp file. Both calls stay local — no network involved.

### Clipboard + paste

`copy_image_to_clipboard` writes the PNG bytes onto `NSPasteboard` via `AppKit`. `send_paste_shortcut` sends ⌘V via the existing CGEvent injector. The image stays on the Mac; nothing is uploaded.

### Permission

Capturing another app's window pixels requires **Screen Recording** (TCC key `kTCCServiceScreenCapture`). Spuk requests it lazily when the screenshot gesture is first triggered (`request_screen_recording`). The permissions helper dialog shows a row for it only when it is not yet granted (`screen_recording_trusted() is False`).

## Optional Claude post-processing

One interface, off by default, can never silently spend money:

- `post_process.enabled` defaults to `false`.
- Enabling also requires `i_understand_this_costs_money = true` (second latch).
- Key from env/Keychain, never hardcoded.
- Every call logs `[PAID API CALL] …`.
- Hard `max_calls_per_day` cap that fails closed.
- The core loop always calls `processor.process(text)`, but the default is a no-op
  (`NullPostProcessor`), so post-processing is never "accidentally on".
