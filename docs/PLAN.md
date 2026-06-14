# Spuk — Phased Plan

A decision resolved up front: **prototype in Python first, then port to Swift.**
You're Python-strong and new to Swift. Straight-to-Swift means learning
AVAudioEngine, NSPasteboard, CGEvent, the TCC dance, bundling, and codesigning
*simultaneously* — while not yet knowing whether `small`'s German accuracy is good
enough. Python-first validates the product in an afternoon; the Swift port then
becomes a mechanical translation of a working design (every box has a clean 1:1
native equivalent), not a research project.

## Phase 0 — Repo, scaffold, env, permissions ✅

- **Goal:** runnable, dependency-resolved skeleton + macOS permissions granted.
- **Deliverables:** `1mp3ctz/spuk` private repo; `uv` env pinned to Python 3.11
  (copy mode for exFAT); `pyproject.toml`, `config.toml`, `docs/`, `src/spuk/`,
  `scripts/check_env.py`.
- **Verify:** `uv run python scripts/check_env.py` passes (imports, mic, clipboard).
- **Teaches:** macOS TCC and that the *terminal* holds the permissions; reverse-DNS
  bundle ids; why exFAT breaks Python venvs (symlinks → use copy mode).

## Phase 1 — Minimal end-to-end loop ✅

- **Goal:** hold hotkey → speak → release → German text pastes into the focused field.
- **Deliverables:** `src/spuk/{config,audio,transcriber,paste,postprocess,hotkey,core}.py`;
  faster-whisper `small`; push-to-talk.
- **Verify:** focus a Claude box, hold `Ctrl+Alt+Space`, say "Schöne Grüße über die
  Brücke", release — correct text appears, umlauts intact, prior clipboard restored.
- **Teaches:** keystroke injection vs clipboard paste and *why clipboard wins for
  German*; the push-to-talk state machine.

## Phase 2 — Quality, latency, robustness

- **Goal:** make it feel good; survive mic edge cases.
- **Deliverables:** latency logging (audio-end→text→paste); model A/B
  (faster-whisper vs MLX `small`); toggle mode; handle no-input / device-switch /
  empty transcript; faithful NSPasteboard save/restore; refine VAD.
- **Verify:** median latency < ~1.5 s for short utterances; pulling AirPods
  mid-session doesn't crash; silence yields no paste.
- **Teaches:** audio device lifecycle, sample-rate mismatch, VAD, cold vs warm inference.

## Phase 3 — Native Swift/SwiftUI menu-bar app

- **Goal:** a real `Spuk.app` in the menu bar that owns its own permissions, no terminal.
- **Deliverables:** SwiftUI `MenuBarExtra`; `RegisterEventHotKey`; `AVAudioEngine`
  tap → `AVAudioConverter` to 16 kHz mono; `whisper.cpp` (Metal) via a C bridge /
  XCFramework; `NSPasteboard` save/paste/restore; Info.plist usage strings; ad-hoc
  codesign + run.
- **Verify:** launch the `.app`; grant mic + accessibility to *Spuk* specifically;
  full loop works with the terminal closed.
- **Teaches:** SwiftUI `MenuBarExtra`, AVAudioEngine taps, bridging C into Swift,
  Info.plist usage descriptions, codesigning + Gatekeeper.

## Phase 4 — Optional Claude post-proc, custom vocab, settings

- **Goal:** polish + the gated smart features.
- **Deliverables:** wire `ClaudePostProcessor` (double-gated, capped, logged);
  custom vocabulary / `initial_prompt` biasing for names/jargon; SwiftUI settings
  (model, hotkey, mode, post-proc toggle with money warning); launch-at-login.
- **Verify:** post-proc stays off unless *both* flags set; every paid call logs
  `[PAID API CALL]`; daily cap fails closed; custom vocab fixes a known hard word.
- **Teaches:** Keychain in Swift, `SMAppService` launch-at-login, safe opt-in design
  for paid features.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Accessibility/Input-Monitoring not granted → paste silently does nothing | High | High | clear log on no-effect; document exact System Settings path; Phase 3 app guides to the pane |
| Latency too high on fanless M3 (thermal throttle) | Medium | Medium | default `small` int8; warm at startup; log latency; don't run Ollama models concurrently |
| Mic edge cases (sample rate, device switch, no input) | Medium | High | capture at 16 kHz mono; wrap stream in try/except; abort on empty/short buffer |
| exFAT venv breakage (no symlinks) | High if mishandled | High | `UV_LINK_MODE=copy` venv (verified working); model cache via `HF_HOME` on the drive |
| Python 3.14 wheel incompatibility | High | High | pin `uv venv --python 3.11`; never call bare `python3` (=3.14); always `uv run` |
| Clipboard clobbering | High | Medium | save/restore around paste; non-text items can't round-trip in Phase 1 (logged) |
| Hotkey conflict | Medium | Medium | default to an unlikely combo; configurable; log on registration failure |
| Model cold-start (first transcription slow) | High (once/launch) | Low | warm with a 0.5 s silent buffer at startup |
| Ad-hoc signing re-prompts permissions each rebuild (Phase 3) | Medium | Low | use a stable free "Apple Development" cert |
| Accidental paid API spend | Low (by design) | High | off by default, double-flag, daily cap, `[PAID API CALL]` logging, key from Keychain |
