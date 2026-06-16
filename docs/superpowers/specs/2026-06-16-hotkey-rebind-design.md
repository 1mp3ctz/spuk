# Design: User-configurable hotkeys (live capture + live rebind)

**Date:** 2026-06-16
**Status:** Approved (brainstorming) → ready for implementation plan
**Branch:** `feat/configurable-hotkeys` (stacked on `feat/linux-support`)

## Problem

Today every hotkey lives in `config.toml` (`[hotkey] mode / key / cycle_language /
handsfree / double_tap_seconds`) and can only be changed by editing that file. Spuk
is built for non-technical family on macOS, Windows, and Linux. They should be able
to **choose all the keys themselves** from the Settings window by pressing the keys
they want — no file editing.

## Goal

From the Settings window, let the user rebind:

1. **Talk key** — the push-to-talk / toggle combo (`hotkey.key`).
2. **Cycle-language key** — `hotkey.cycle_language`.
3. **Mode** — hold-to-talk (`push_to_talk`) vs press-to-toggle (`toggle`).
4. **Hands-free** — the double-tap-to-record switch (`push_to_talk` only).

Changes apply **live** (no app restart), **persist** across restarts, and are
guarded so a non-technical user cannot lock themselves out.

### Non-goals (YAGNI)

- A UI for `double_tap_seconds` (a timing, not a key — stays `config.toml`-only).
- Per-app hotkey profiles.
- Multiple alternative combos bound to the same action.

## Decisions (from brainstorming)

| Question | Decision |
|----------|----------|
| Scope | All of: talk key, cycle key, mode, hands-free. The keys are the priority. |
| Capture UX | **Live capture** — click "Change", press the keys, it records them. |
| Guardrails | Reject combos that clearly misfire; always-visible "Reset to default"; warn (not block) on the German AltGr=Ctrl+Alt caveat. |
| Capture mechanism | **Approach A** — capture through the same input backend that does the real global listening (pynput on Mac/Win, evdev on Linux), so captured keys == listened-for keys on every platform. |
| Apply timing | Live rebind (stop + restart the listener); also persisted for next launch. |

## Architecture

The single interchange format for a combo is the canonical pynput string
(`"<ctrl>+<alt>"`, `"<ctrl>+<shift>+l"`). `hotkey.py` already parses it via
`keyboard.HotKey.parse`, and `linux_input.py` already maps whatever combo the FSM
is configured with — so reusing this format means no new translation layer.

### 1. Persistence — overlay hotkey from `settings.json`

Mirror the existing `_overlay_user_languages` pattern in `config.py`:

- New `_overlay_user_hotkey(h: dict)` reads from `settings.json`:
  `hotkey_key`, `hotkey_cycle_language`, `hotkey_mode`, `hotkey_handsfree`
  (namespaced to avoid clashing with the language keys).
- Validate each (ignore invalid/missing → fall back to bundled default), then
  overlay onto `raw["hotkey"]` before constructing the frozen `HotkeyConfig`.
- `config.toml` remains the factory default and documented manual escape hatch.

`settings_store.py` is unchanged structurally (already a generic dict store);
new keys are just written through `update_user_settings(...)`.

### 2. Capture — backend capability (Approach A)

Extend the input-backend seam (`input_backend.py` + the pynput path in `hotkey.py`
and the evdev path in `linux_input.py`):

- New capability `capture_combo(on_done, on_cancel, timeout=8.0)` returning the
  canonical combo string for the next combo the user presses.
- **Semantics:** accumulate the set of keys held; finalize the combo on the first
  key *release*. Holding Ctrl+Alt then releasing → `"<ctrl>+<alt>"`. This handles
  modifier-only and modifier+key uniformly.
- **pynput impl (Mac/Win):** a temporary `keyboard.Listener`; canonicalize keys the
  same way the live listener does; format to the canonical string.
- **evdev impl (Linux):** reuse `linux_input.py`'s evdev read loop + its existing
  keycode→canonical mapping; format identically. Needs the `input` group (already
  required for Spuk to function).
- **Pause coordination:** while a capture session is active, the backend suspends
  normal dispatch to the chord FSM, so pressing the combo *sets* it rather than
  starting a recording. The session restores normal dispatch on finish/cancel/timeout.

### 3. Normalization + validation — new `hotkey_format.py`

Small, pure, fully unit-testable module:

- `keys_to_combo_string(keys) -> str` — canonical, modifier-ordered string so
  `Alt+Ctrl` and `Ctrl+Alt` normalize identically.
- `combo_to_label(combo) -> str` — friendly display, e.g. `"Ctrl + Alt"`,
  `"Ctrl + Shift + L"` (OS-aware: `⌘`/Option on macOS labels if cheap, else plain).
- `validate_combo(combo, *, mode, other_combo=None) -> (ok: bool, message: str|None)`:
  - reject empty;
  - reject a **bare printable key** with no modifier (would type while dictating);
  - allow modifier-only (e.g. Ctrl+Alt), modifier+key, and lone function/special
    keys (F1–F12, etc.);
  - reject when it equals `other_combo` (talk == cycle collision);
  - **warn (allow)** when combo is exactly Ctrl+Alt: AltGr on German/Austrian
    keyboards reports as Ctrl+Alt (already a known README caveat).

### 4. Live rebind — `core.py`

- `core.start_capture(on_done, on_cancel)` — delegates to the backend capture
  session with the live listener paused.
- `core.rebind_hotkeys(*, key=None, cycle_language=None, mode=None, handsfree=None)`:
  - build a **new** frozen `HotkeyConfig` (immutability — never mutate the existing);
  - persist the changed fields to `settings.json`;
  - stop the running `HotkeyListener`, start a fresh one via the input backend with
    the new combos/mode/handsfree;
  - on failure to start, **roll back** to the previous config + log + report.
- `core.reset_hotkeys()` — clear the `hotkey_*` keys from `settings.json` and rebind
  to the bundled `config.toml` defaults.

### 5. Settings UI — `ui_window.py`

A new "Hotkeys" section:

- **Talk key** row: current combo label + `[Change]`. Clicking enters
  `⌨ Press your keys…  [Cancel]`; on capture → validate → apply or show inline error.
- **Cycle-language key** row: same control.
- **Mode**: hold-to-talk vs press-to-toggle selector. In toggle mode the hands-free
  checkbox is disabled (hands-free is `push_to_talk`-only).
- **Hands-free** checkbox: "Double-tap to record hands-free."
- **Reset hotkeys to default** button — always visible.

Capture runs off the UI thread (backend listener thread); results return via the
existing thread-safe core→UI Qt signal bridge. Inline validation messages appear in
the row. After any successful rebind, the floating pill's shortcut labels refresh.

### 6. Pill hint refresh — `ui_bar.py`

The pill shows the hold-to-talk key and shortcuts; after a rebind, update those
labels (via an `on_hotkey_change` callback / the existing signal bridge).

## Data flow (rebind)

```
[Change] → core.start_capture()           (live listener paused)
        → backend capture session
        → user presses keys → canonical string
        → Qt signal → UI
        → validate_combo()
             invalid → inline warning, no change, listener resumes
             valid   → core.rebind_hotkeys(...)
                        → new frozen HotkeyConfig
                        → persist settings.json
                        → swap HotkeyListener
                        → UI shows new combo + pill refreshes
```

## Error handling / recovery

- Invalid combo → inline message; nothing changes; listener resumes.
- Capture timeout (~8s, no keys) → cancel cleanly; listener restored.
- Linux capture without `input`-group access → reuse the existing actionable
  permission message; capture unavailable but the app keeps running.
- Rebind that fails to start a listener → roll back to the previous combo, log, tell
  the user.
- Always-visible **Reset to default**; `config.toml` documented in the README as the
  manual escape hatch.

## Testing

Pure-logic units (run on macOS, no evdev needed):

- `hotkey_format`: normalization/ordering, `combo_to_label`, and a table-driven
  `validate_combo` (bare letter rejected; modifier-only ok; F-key ok; empty rejected;
  talk==cycle rejected; Ctrl+Alt warns-but-allows).
- `config._overlay_user_hotkey`: `settings.json` beats `config.toml`; invalid saved
  combo is ignored; partial overlays keep other defaults.
- `core.rebind_hotkeys` / `reset_hotkeys`: builds a new immutable config and persists
  the right keys (backend mocked); rollback on listener-start failure.

Not unit-testable on the dev Mac: the actual pynput/evdev key *capture* (event loop /
hardware). Covered by manual test + the Linux hardware pass. Existing 52 tests stay
green; new logic targets 80%+.

## Files touched

- `src/spuk/config.py` — `_overlay_user_hotkey`, wire into `load_config`.
- `src/spuk/hotkey_format.py` — **new**: normalize/label/validate.
- `src/spuk/input_backend.py` — capture capability on the seam.
- `src/spuk/hotkey.py` — pynput capture path; expose pause/resume of dispatch.
- `src/spuk/linux_input.py` — evdev capture path (reuse mapping).
- `src/spuk/core.py` — `start_capture`, `rebind_hotkeys`, `reset_hotkeys`.
- `src/spuk/ui_window.py` — Hotkeys settings section.
- `src/spuk/ui_bar.py` — refresh shortcut labels after rebind.
- `tests/` — new units for `hotkey_format`, overlay, rebind.
- `README.md` — short "change your hotkeys in Settings" note + escape hatch.
