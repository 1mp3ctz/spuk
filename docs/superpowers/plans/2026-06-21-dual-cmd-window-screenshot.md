# Dual-⌘ Window Screenshot → Clipboard + Paste Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On macOS, pressing **both Command keys at once** (left ⌘ + right ⌘, and no other modifiers) captures the **frontmost window**, puts the PNG on the clipboard, and auto-pastes it into the focused field — fully local, no cloud upload.

**Architecture:** Spuk's existing pynput/`canonical()` pipeline collapses left-⌘ and right-⌘ into a single `Key.cmd`, so it physically cannot see "both ⌘" (same lossy-modifier limitation documented for the Fn key in issue #17). We therefore add a dedicated, **listen-only macOS `CGEventTap` on `kCGEventFlagsChanged`** that reads the *live* device-specific command-flag bits (left `0x8`, right `0x10`) and fires on a clean rising edge. Reading flag *state* (not counting up/down edges) means a dropped event just re-syncs — it can't wedge. The capture uses `screencapture -l<windowID>` against the frontmost app's front window (via `NSWorkspace` + `CGWindowListCopyWindowInfo`), writes the PNG to `NSPasteboard`, and reuses Spuk's existing paste injector (`paste.py`) to send ⌘V. All bit logic, window-picking, and orchestration are pure and unit-tested; the CGEventTap, screencapture, and pasteboard calls sit behind injectable seams verified by an opt-in integration check. The dictation hotkey FSM, recorder, and transcriber are untouched.

**Tech Stack:** Python 3.11 (`>=3.11,<3.13`), pyobjc-framework-Quartz + pyobjc-framework-Cocoa (macOS only), `screencapture` (macOS built-in), pynput (existing paste injector), pytest (via `uv run --with pytest`), ruff.

## Global Constraints

- **Fully local, no upload.** The image goes to the clipboard and is pasted into the focused field. Nothing is uploaded anywhere — Spuk stays "private, local & free." (The original "upload" wording was clarified by the owner to mean "copy it so I can paste it," e.g. into a terminal/chat.)
- **macOS only.** The gesture, the tap, and the capture are macOS-only. All pyobjc/Quartz imports are lazy and guarded by `platform.system() == "Darwin"`. The feature is simply absent on Windows/Linux (no error, no menu item).
- **Independent of the dictation FSM.** This must not touch `HotkeyListener`'s chord/recording state. It is a separate listen-only tap with its own callback. Do not route it through `_feed_press`/`_feed_release`.
- **Robust by construction.** Detection reads the current flag bits, so a dropped flagsChanged event self-corrects on the next one — no "stuck" gesture. (Same property issue #17 wants for Fn; this plan builds the shared tap infrastructure that unblocks #17.)
- **Trigger precision:** fire only when **both** command bits are set and **no other** modifier (ctrl/alt/shift/fn) is held — so ⌘⇧, ⌘⌥, etc. never trigger it. Caps-lock is ignored (don't block on it).
- **Python floor:** `requires-python = ">=3.11,<3.13"`. Immutable frozen config dataclasses.
- **Test command:** `UV_LINK_MODE=copy uv run --with pytest pytest -q`
- **Lint command:** `uv run --with ruff ruff check src/ tests/`
- **Commit after every task.** Conventional commits.

**Branch:** `feat/dual-cmd-screenshot`, created from the scrubbed `origin/main` (GitHub-noreply commits only).

---

### Task 1: Declare the macOS Quartz/Cocoa dependencies

**Files:**
- Modify: `pyproject.toml` (dependencies table)

**Interfaces:** none (dependency declaration only). pyobjc is already present transitively but is **not declared**, so the tap/capture/pasteboard imports must not rely on luck.

- [ ] **Step 1: Add the dependencies** (macOS-gated, after the `evdev` marker)

```toml
    # macOS only: the dual-Command screenshot gesture needs a Quartz CGEventTap
    # (flagsChanged) and Cocoa (NSWorkspace/NSPasteboard/CGWindowList). Import
    # names are 'Quartz' and 'AppKit'/'Foundation'.
    "pyobjc-framework-Quartz>=10,<12; sys_platform == 'darwin'",
    "pyobjc-framework-Cocoa>=10,<12; sys_platform == 'darwin'",
```

- [ ] **Step 2: Verify they resolve**

Run: `UV_LINK_MODE=copy uv run python -c "import Quartz, AppKit, Foundation; print('ok')"`
Expected: prints `ok` (on macOS).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: declare macOS Quartz/Cocoa deps for the screenshot gesture"
```

---

### Task 2: Pure dual-⌘ flag logic (TDD)

**Files:**
- Create: `src/spuk/mac_flags_tap.py`
- Test: `tests/test_dual_cmd_logic.py`

**Interfaces:**
- Produces:
  - `mac_flags_tap.both_cmd_only(flags: int) -> bool` — True iff both device command bits are set and no other modifier bit is.
  - `mac_flags_tap.dual_cmd_edge(active: bool, armed: bool) -> tuple[bool, bool]` — returns `(fire, new_armed)`; fires once on the rising edge, re-arms on release.
  - Mask constants `CMD_L`, `CMD_R`, `OTHER_MODS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dual_cmd_logic.py
from spuk.mac_flags_tap import CMD_L, CMD_R, both_cmd_only, dual_cmd_edge

CTRL_L = 0x00000001
SHIFT_L = 0x00000002
ALT_L = 0x00000020
FN = 0x00800000
CAPS = 0x00010000


def test_both_cmd_true_when_only_both_commands():
    assert both_cmd_only(CMD_L | CMD_R) is True


def test_one_command_is_not_enough():
    assert both_cmd_only(CMD_L) is False
    assert both_cmd_only(CMD_R) is False
    assert both_cmd_only(0) is False


def test_other_modifier_blocks_the_gesture():
    assert both_cmd_only(CMD_L | CMD_R | SHIFT_L) is False
    assert both_cmd_only(CMD_L | CMD_R | CTRL_L) is False
    assert both_cmd_only(CMD_L | CMD_R | ALT_L) is False
    assert both_cmd_only(CMD_L | CMD_R | FN) is False


def test_caps_lock_is_ignored():
    assert both_cmd_only(CMD_L | CMD_R | CAPS) is True


def test_edge_fires_once_on_rising_then_rearms():
    # not held -> held: fire
    fire, armed = dual_cmd_edge(active=True, armed=False)
    assert fire is True and armed is True
    # still held: no repeat
    fire, armed = dual_cmd_edge(active=True, armed=armed)
    assert fire is False and armed is True
    # released: re-arm, no fire
    fire, armed = dual_cmd_edge(active=False, armed=armed)
    assert fire is False and armed is False
    # held again: fire again
    fire, armed = dual_cmd_edge(active=True, armed=armed)
    assert fire is True and armed is True
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_dual_cmd_logic.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'spuk.mac_flags_tap'`.

- [ ] **Step 3: Implement the pure logic**

```python
# src/spuk/mac_flags_tap.py
"""macOS dual-Command gesture: a listen-only flagsChanged CGEventTap.

Spuk's pynput pipeline canonicalises left/right ⌘ into one Key.cmd, so it can't
see "both ⌘". This reads the LIVE device-specific modifier bits from each
flagsChanged event instead. Reading state (not counting edges) means a dropped
event self-corrects on the next one — the gesture cannot wedge.

Device-dependent modifier masks (Apple, IOKit/hidsystem/IOLLEvent.h NX_*):
    left ctrl 0x1  left shift 0x2  right shift 0x4  left cmd 0x8
    right cmd 0x10 left alt 0x20  right alt 0x40   right ctrl 0x2000
    fn/secondary 0x800000 (kCGEventFlagMaskSecondaryFn)
Caps-lock (0x10000) is intentionally NOT in OTHER_MODS — it must not block.
"""

from __future__ import annotations

import logging

log = logging.getLogger("spuk.mac_flags_tap")

CMD_L = 0x00000008
CMD_R = 0x00000010
OTHER_MODS = (
    0x00000001  # left ctrl
    | 0x00000002  # left shift
    | 0x00000004  # right shift
    | 0x00000020  # left alt
    | 0x00000040  # right alt
    | 0x00002000  # right ctrl
    | 0x00800000  # fn / secondary
)


def both_cmd_only(flags: int) -> bool:
    """True iff both ⌘ are held and no other modifier (caps-lock ignored)."""
    return bool(flags & CMD_L) and bool(flags & CMD_R) and not (flags & OTHER_MODS)


def dual_cmd_edge(active: bool, armed: bool) -> tuple[bool, bool]:
    """Edge detector. Returns (fire, new_armed): fire once on the rising edge."""
    if active and not armed:
        return True, True
    if not active:
        return False, False
    return False, True
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_dual_cmd_logic.py`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/mac_flags_tap.py tests/test_dual_cmd_logic.py
git commit -m "feat(gesture): pure dual-Command flag detection + edge logic"
```

---

### Task 3: `MacFlagsTap` — stateful handler (TDD) + real CGEventTap runner (integration)

**Files:**
- Modify: `src/spuk/mac_flags_tap.py`
- Test: `tests/test_mac_flags_tap.py`

**Interfaces:**
- Produces: `class MacFlagsTap` with `__init__(self, on_dual_cmd: Callable[[], None])`, `_handle_flags(self, flags: int) -> None` (unit-tested seam the real tap callback calls), `start(self) -> "MacFlagsTap"`, `stop(self) -> None`.
- Consumes: `both_cmd_only`, `dual_cmd_edge` (Task 2).

- [ ] **Step 1: Write the failing tests** (drive the real handler seam — no tap needed)

```python
# tests/test_mac_flags_tap.py
from spuk.mac_flags_tap import CMD_L, CMD_R, MacFlagsTap

SHIFT_L = 0x00000002


def test_handle_flags_fires_callback_once_per_press():
    calls = []
    tap = MacFlagsTap(on_dual_cmd=lambda: calls.append(1))
    tap._handle_flags(CMD_L)              # one cmd: nothing
    tap._handle_flags(CMD_L | CMD_R)      # both: FIRE
    tap._handle_flags(CMD_L | CMD_R)      # still both: no repeat
    tap._handle_flags(0)                  # released: re-arm
    tap._handle_flags(CMD_L | CMD_R)      # both again: FIRE
    assert calls == [1, 1]


def test_handle_flags_other_modifier_does_not_fire():
    calls = []
    tap = MacFlagsTap(on_dual_cmd=lambda: calls.append(1))
    tap._handle_flags(CMD_L | CMD_R | SHIFT_L)  # ⌘⌘⇧ — blocked
    assert calls == []


def test_callback_exception_does_not_propagate():
    def boom():
        raise RuntimeError("handler blew up")

    tap = MacFlagsTap(on_dual_cmd=boom)
    # A misbehaving callback must never kill the tap thread.
    tap._handle_flags(CMD_L | CMD_R)  # should not raise
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_mac_flags_tap.py`
Expected: FAIL with `ImportError: cannot import name 'MacFlagsTap'`.

- [ ] **Step 3: Implement the handler + real tap**

Add to `src/spuk/mac_flags_tap.py`:

```python
import platform
import threading
from typing import Callable


class MacFlagsTap:
    """Listen-only flagsChanged tap that fires ``on_dual_cmd`` on both-⌘.

    The stateful edge logic lives in ``_handle_flags`` (unit-tested directly).
    ``start`` installs a real CGEventTap on a background CFRunLoop; the tap's C
    callback only extracts the flags and calls ``_handle_flags`` — so all behaviour
    is testable without a real tap.
    """

    def __init__(self, on_dual_cmd: Callable[[], None]) -> None:
        self._cb = on_dual_cmd
        self._armed = False
        self._tap = None
        self._runloop_source = None
        self._runloop = None
        self._thread: threading.Thread | None = None

    def _handle_flags(self, flags: int) -> None:
        active = both_cmd_only(flags)
        fire, self._armed = dual_cmd_edge(active, self._armed)
        if fire:
            try:
                self._cb()
            except Exception as exc:  # noqa: BLE001 - never kill the tap thread
                log.error("dual-⌘ handler failed: %s", exc)

    def start(self) -> "MacFlagsTap":
        if platform.system() != "Darwin":
            return self
        self._thread = threading.Thread(target=self._run, name="spuk-flags-tap", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        import Quartz

        def callback(proxy, type_, event, refcon):
            try:
                self._handle_flags(int(Quartz.CGEventGetFlags(event)))
            except Exception as exc:  # noqa: BLE001
                log.debug("flags callback error: %s", exc)
            return event  # listen-only: pass the event through unchanged

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged),
            callback,
            None,
        )
        if not self._tap:
            log.warning("Could not create flags event tap (Input Monitoring needed?).")
            return
        self._runloop_source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._runloop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._runloop, self._runloop_source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        Quartz.CFRunLoopRun()

    def stop(self) -> None:
        if platform.system() != "Darwin":
            return
        try:
            import Quartz

            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, False)
            if self._runloop is not None:
                Quartz.CFRunLoopStop(self._runloop)
        except Exception as exc:  # noqa: BLE001
            log.debug("flags tap stop error: %s", exc)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_mac_flags_tap.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/mac_flags_tap.py tests/test_mac_flags_tap.py
git commit -m "feat(gesture): MacFlagsTap stateful handler + listen-only CGEventTap runner"
```

---

### Task 4: Frontmost-window picker + capture command (TDD)

**Files:**
- Create: `src/spuk/screenshot.py`
- Test: `tests/test_screenshot_capture.py`

**Interfaces:**
- Produces:
  - `screenshot.pick_window(window_infos: list[dict], pid: int) -> int | None` — choose the frontmost (layer 0) window owned by `pid`, largest by area; None if none.
  - `screenshot.capture_window_to_png(window_id: int, path: str, *, runner=subprocess.run) -> None` — shells `screencapture -x -o -l<id> <path>`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_screenshot_capture.py
from spuk.screenshot import capture_window_to_png, pick_window


def _win(pid, layer, number, w, h):
    return {
        "kCGWindowOwnerPID": pid,
        "kCGWindowLayer": layer,
        "kCGWindowNumber": number,
        "kCGWindowBounds": {"Width": w, "Height": h},
    }


def test_pick_window_returns_layer0_window_for_pid():
    infos = [
        _win(99, 0, 11, 800, 600),   # another app
        _win(42, 0, 22, 1200, 800),  # our app, main window
        _win(42, 25, 33, 50, 20),    # our app, a menu/overlay (layer != 0)
    ]
    assert pick_window(infos, 42) == 22


def test_pick_window_prefers_largest_layer0():
    infos = [
        _win(42, 0, 1, 400, 300),
        _win(42, 0, 2, 1600, 1000),  # biggest -> the real window
    ]
    assert pick_window(infos, 42) == 2


def test_pick_window_none_when_no_match():
    assert pick_window([_win(99, 0, 1, 800, 600)], 42) is None


def test_capture_window_builds_expected_screencapture_argv(tmp_path):
    seen = {}

    def fake_runner(argv, check):
        seen["argv"] = argv
        seen["check"] = check

    out = str(tmp_path / "shot.png")
    capture_window_to_png(123, out, runner=fake_runner)
    assert seen["argv"] == ["screencapture", "-x", "-o", "-l", "123", out]
    assert seen["check"] is True
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_screenshot_capture.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'spuk.screenshot'`.

- [ ] **Step 3: Implement the picker + capture**

```python
# src/spuk/screenshot.py
"""Capture the frontmost window to a PNG and put it on the clipboard (macOS).

Pure helpers (pick_window) and the screencapture argv are unit-tested; the Cocoa
calls (NSWorkspace, CGWindowListCopyWindowInfo, NSPasteboard) sit behind thin
wrappers exercised by the opt-in integration check and the live app.
"""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger("spuk.screenshot")


def pick_window(window_infos: list[dict], pid: int) -> int | None:
    """Pick the frontmost on-screen window (layer 0) owned by ``pid``.

    Among that owner's layer-0 windows, choose the largest by area — the real
    document window rather than a small panel. Returns its window number, or None.
    """
    candidates = [
        w
        for w in window_infos
        if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0
    ]
    if not candidates:
        return None

    def area(w: dict) -> float:
        b = w.get("kCGWindowBounds") or {}
        return float(b.get("Width", 0)) * float(b.get("Height", 0))

    best = max(candidates, key=area)
    number = best.get("kCGWindowNumber")
    return int(number) if number is not None else None


def capture_window_to_png(window_id: int, path: str, *, runner=subprocess.run) -> None:
    """Capture exactly ``window_id`` to ``path``: no sound (-x), no shadow (-o)."""
    runner(["screencapture", "-x", "-o", "-l", str(window_id), path], check=True)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_screenshot_capture.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/screenshot.py tests/test_screenshot_capture.py
git commit -m "feat(screenshot): frontmost-window picker + screencapture command"
```

---

### Task 5: Clipboard write, orchestrator, and a public paste-shortcut sender (TDD)

**Files:**
- Modify: `src/spuk/screenshot.py`
- Modify: `src/spuk/paste.py` (expose a public `send_paste_shortcut`)
- Test: `tests/test_screenshot_flow.py`
- Test: `tests/test_paste_send_shortcut.py`

**Interfaces:**
- Produces:
  - `paste.send_paste_shortcut() -> None` — public wrapper over the existing private `_send_paste_shortcut`, so the screenshot flow can send ⌘V (through the same main-thread-safe injector dictation uses).
  - `screenshot.front_window_png() -> str | None` — capture the frontmost window to a temp PNG, return the path (or None).
  - `screenshot.copy_image_to_clipboard(path: str) -> None` — write the PNG to `NSPasteboard`.
  - `screenshot.shoot_and_paste(*, capture=front_window_png, copy=copy_image_to_clipboard, paste=...) -> bool` — capture → clipboard → ⌘V; no-op (False) when capture fails.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_screenshot_flow.py
from spuk import screenshot


def test_shoot_and_paste_runs_capture_copy_paste_in_order(tmp_path):
    order = []
    png = str(tmp_path / "s.png")

    def capture():
        order.append("capture")
        return png

    def copy(path):
        assert path == png
        order.append("copy")

    def paste():
        order.append("paste")

    ok = screenshot.shoot_and_paste(capture=capture, copy=copy, paste=paste)
    assert ok is True
    assert order == ["capture", "copy", "paste"]


def test_shoot_and_paste_noops_when_capture_returns_none():
    calls = []
    ok = screenshot.shoot_and_paste(
        capture=lambda: None,
        copy=lambda p: calls.append("copy"),
        paste=lambda: calls.append("paste"),
    )
    assert ok is False
    assert calls == []  # nothing copied, nothing pasted
```

```python
# tests/test_paste_send_shortcut.py
import spuk.paste as paste


def test_send_paste_shortcut_invokes_injector(monkeypatch):
    fired = []
    monkeypatch.setattr(paste, "_get_injector", lambda: (lambda: fired.append(1)))
    paste.send_paste_shortcut()
    assert fired == [1]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_screenshot_flow.py tests/test_paste_send_shortcut.py`
Expected: FAIL (`AttributeError: ... 'shoot_and_paste'` and `... 'send_paste_shortcut'`).

- [ ] **Step 3: Expose the public paste sender**

In `src/spuk/paste.py`, add right after `_send_paste_shortcut`:

```python
def send_paste_shortcut() -> None:
    """Public: send the configured paste shortcut now (same injector as dictation).

    Used by the screenshot gesture to paste the captured image. Goes through the
    same main-thread-safe pynput injector, so it's umlaut/main-thread correct.
    """
    _send_paste_shortcut()
```

- [ ] **Step 4: Implement the orchestrator + clipboard write**

Add to `src/spuk/screenshot.py`:

```python
import os
import tempfile


def front_window_png() -> str | None:
    """Capture the frontmost app's front window to a temp PNG; return path or None."""
    try:
        from AppKit import NSWorkspace
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception as exc:  # noqa: BLE001 - non-macOS / framework missing
        log.debug("screenshot frameworks unavailable: %s", exc)
        return None

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    pid = app.processIdentifier()
    infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    window_id = pick_window(list(infos), pid)
    if window_id is None:
        log.info("No capturable front window for pid %s.", pid)
        return None

    fd, path = tempfile.mkstemp(suffix=".png", prefix="spuk-shot-")
    os.close(fd)
    try:
        capture_window_to_png(window_id, path)
    except Exception as exc:  # noqa: BLE001
        log.error("screencapture failed: %s", exc)
        return None
    return path


def copy_image_to_clipboard(path: str) -> None:
    """Write the PNG at ``path`` to the general pasteboard as image data."""
    from AppKit import NSPasteboard, NSPasteboardTypePNG
    from Foundation import NSData

    data = NSData.dataWithContentsOfFile_(path)
    if data is None:
        raise FileNotFoundError(path)
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setData_forType_(data, NSPasteboardTypePNG)


def shoot_and_paste(*, capture=front_window_png, copy=copy_image_to_clipboard, paste=None) -> bool:
    """Capture the front window → clipboard → paste it into the focused field.

    Returns False (and does nothing further) when capture fails. The image is left
    on the clipboard on purpose, so the user can paste it again. We deliberately do
    NOT restore the previous clipboard — "copy it right away" is the feature.
    """
    if paste is None:
        from .paste import send_paste_shortcut

        paste = send_paste_shortcut
    path = capture()
    if not path:
        return False
    try:
        copy(path)
        paste()
        return True
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
```

- [ ] **Step 5: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_screenshot_flow.py tests/test_paste_send_shortcut.py`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/spuk/screenshot.py src/spuk/paste.py tests/test_screenshot_flow.py tests/test_paste_send_shortcut.py
git commit -m "feat(screenshot): clipboard write + capture→copy→paste orchestrator"
```

---

### Task 6: Screen Recording permission helper (TDD with mocked Quartz)

**Files:**
- Modify: `src/spuk/permissions.py`
- Test: `tests/test_permissions_screen_recording.py`

**Interfaces:**
- Produces:
  - `permissions.screen_recording_trusted() -> bool | None` (True granted, False missing, None unknown/unavailable, True off-macOS).
  - `permissions.request_screen_recording() -> None`.
  - New `PRIVACY_PANES["screen_recording"]` deep link.

- [ ] **Step 1: Write the failing tests** (inject a fake `Quartz` module)

```python
# tests/test_permissions_screen_recording.py
import sys
import types

import spuk.permissions as perms


def _fake_quartz(monkeypatch, granted):
    mod = types.ModuleType("Quartz")
    mod.CGPreflightScreenCaptureAccess = lambda: granted
    mod.CGRequestScreenCaptureAccess = lambda: True
    monkeypatch.setitem(sys.modules, "Quartz", mod)


def test_screen_recording_trusted_true(monkeypatch):
    monkeypatch.setattr(perms.platform, "system", lambda: "Darwin")
    _fake_quartz(monkeypatch, True)
    assert perms.screen_recording_trusted() is True


def test_screen_recording_trusted_false(monkeypatch):
    monkeypatch.setattr(perms.platform, "system", lambda: "Darwin")
    _fake_quartz(monkeypatch, False)
    assert perms.screen_recording_trusted() is False


def test_screen_recording_trusted_true_off_macos(monkeypatch):
    monkeypatch.setattr(perms.platform, "system", lambda: "Linux")
    assert perms.screen_recording_trusted() is True


def test_screen_recording_pane_registered():
    assert "screen_recording" in perms.PRIVACY_PANES
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_permissions_screen_recording.py`
Expected: FAIL (`AttributeError: ... 'screen_recording_trusted'`).

- [ ] **Step 3: Implement the helper**

In `src/spuk/permissions.py`, add the pane:

```python
    "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
```

Add the functions:

```python
def screen_recording_trusted() -> bool | None:
    """Whether this process may capture window contents (Screen Recording)."""
    if platform.system() != "Darwin":
        return True
    try:
        from Quartz import CGPreflightScreenCaptureAccess

        return bool(CGPreflightScreenCaptureAccess())
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not check Screen Recording trust: %s", exc)
        return None


def request_screen_recording() -> None:
    """Raise the macOS Screen Recording prompt. Grant applies after relaunch."""
    if platform.system() != "Darwin":
        return
    try:
        from Quartz import CGRequestScreenCaptureAccess

        CGRequestScreenCaptureAccess()
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not request Screen Recording: %s", exc)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_permissions_screen_recording.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/permissions.py tests/test_permissions_screen_recording.py
git commit -m "feat(perms): Screen Recording trust check, prompt, and privacy pane"
```

---

### Task 7: Config `[screenshot]` section (TDD)

**Files:**
- Modify: `config.toml`
- Modify: `src/spuk/config.py`
- Test: `tests/test_config_screenshot.py`

**Interfaces:**
- Produces: `ScreenshotConfig(enabled: bool, gesture: str)` frozen dataclass on `Config.screenshot`. Defaulted so an older `config.toml` without the section still loads.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config_screenshot.py
from pathlib import Path

from spuk.config import load_config


def test_screenshot_config_loads_from_bundled_toml():
    cfg = load_config(Path("config.toml"))
    assert cfg.screenshot.enabled is True
    assert cfg.screenshot.gesture == "dual_cmd"


def test_screenshot_defaults_when_section_absent(tmp_path):
    # A config.toml predating the feature must still load (defaults applied).
    src = Path("config.toml").read_text()
    trimmed = src.split("[screenshot]")[0]  # drop the screenshot section
    p = tmp_path / "old.toml"
    p.write_text(trimmed)
    cfg = load_config(p)
    assert cfg.screenshot.enabled is True
    assert cfg.screenshot.gesture == "dual_cmd"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_config_screenshot.py`
Expected: FAIL (`AttributeError: 'Config' object has no attribute 'screenshot'`).

- [ ] **Step 3: Add the config section + dataclass**

In `config.toml`, append:

```toml
[screenshot]
# macOS only. Press BOTH Command keys (left + right, nothing else) to screenshot
# the window you're in, copy it to the clipboard, and paste it into the focused
# field. Fully local — nothing is uploaded.
enabled = true
gesture = "dual_cmd"   # reserved for future trigger choices
```

In `src/spuk/config.py`, add the dataclass (near the others):

```python
@dataclass(frozen=True)
class ScreenshotConfig:
    enabled: bool = True
    gesture: str = "dual_cmd"
```

Add the field to `Config`:

```python
@dataclass(frozen=True)
class Config:
    transcribe: TranscribeConfig
    hotkey: HotkeyConfig
    audio: AudioConfig
    post_process: PostProcessConfig
    screenshot: ScreenshotConfig
```

In `load_config`, build it with defaults when the section is absent (inside the existing `try`):

```python
        screenshot = ScreenshotConfig(**raw.get("screenshot", {}))
```

and pass it to the `Config(...)` constructor:

```python
    return Config(transcribe=transcribe, hotkey=hotkey, audio=audio,
                  post_process=post_process, screenshot=screenshot)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_config_screenshot.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite (guard the new Config field)**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q`
Expected: PASS — if any test constructs `Config(...)` directly, update it to pass `screenshot=ScreenshotConfig()`.

- [ ] **Step 6: Commit**

```bash
git add config.toml src/spuk/config.py tests/test_config_screenshot.py
git commit -m "feat(config): add [screenshot] section with safe defaults"
```

---

### Task 8: Wire the gesture into the app + a tray toggle (integration)

**Files:**
- Create: `src/spuk/screenshot_gesture.py` (start/stop wiring used by both UIs)
- Modify: `src/spuk/tray.py` (start on launch + a menu checkbox)
- Modify: `src/spuk/ui_bar.py` (start on launch for the default floating-bar app)
- Modify: `src/spuk/settings_store.py` is not required (reuses generic keys) — persist via `update_user_settings(screenshot_enabled=...)`
- Test: `tests/test_screenshot_gesture_wiring.py`

**Interfaces:**
- Produces: `screenshot_gesture.start_if_enabled(config) -> MacFlagsTap | None` — returns a started tap (macOS + enabled + Screen Recording grantable), else None. `screenshot_gesture.run_capture_async() -> None` — runs `shoot_and_paste` on a worker thread (capture/clipboard are blocking; the ⌘V injection marshals to the main thread inside `paste.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_screenshot_gesture_wiring.py
import types

import spuk.screenshot_gesture as sg
from spuk.config import ScreenshotConfig


def _cfg(enabled):
    return types.SimpleNamespace(screenshot=ScreenshotConfig(enabled=enabled))


def test_start_if_enabled_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(sg.platform, "system", lambda: "Darwin")
    assert sg.start_if_enabled(_cfg(False)) is None


def test_start_if_enabled_returns_none_off_macos(monkeypatch):
    monkeypatch.setattr(sg.platform, "system", lambda: "Linux")
    assert sg.start_if_enabled(_cfg(True)) is None


def test_start_if_enabled_starts_tap_when_enabled_on_macos(monkeypatch):
    started = {"v": False}

    class FakeTap:
        def __init__(self, on_dual_cmd):
            self.cb = on_dual_cmd

        def start(self):
            started["v"] = True
            return self

    monkeypatch.setattr(sg.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(sg, "MacFlagsTap", FakeTap)
    monkeypatch.setattr(sg, "request_screen_recording", lambda: None)
    monkeypatch.setattr(sg, "screen_recording_trusted", lambda: True)
    tap = sg.start_if_enabled(_cfg(True))
    assert started["v"] is True
    assert isinstance(tap, FakeTap)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_screenshot_gesture_wiring.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'spuk.screenshot_gesture'`.

- [ ] **Step 3: Implement the wiring module**

```python
# src/spuk/screenshot_gesture.py
"""Start/stop the dual-⌘ screenshot gesture for the tray and floating-bar apps.

macOS-only. Owns nothing about capture mechanics (see screenshot.py) — it just
connects the MacFlagsTap to an off-thread shoot_and_paste, and asks for the
Screen Recording permission the first time it's enabled.
"""

from __future__ import annotations

import logging
import platform
import threading

from .mac_flags_tap import MacFlagsTap
from .permissions import request_screen_recording, screen_recording_trusted

log = logging.getLogger("spuk.screenshot_gesture")


def run_capture_async() -> None:
    """Run capture→clipboard→paste off the tap thread (it blocks on screencapture)."""
    from .screenshot import shoot_and_paste

    def work() -> None:
        try:
            shoot_and_paste()
        except Exception as exc:  # noqa: BLE001
            log.error("screenshot gesture failed: %s", exc)

    threading.Thread(target=work, name="spuk-shoot", daemon=True).start()


def start_if_enabled(config) -> MacFlagsTap | None:
    """Start the dual-⌘ tap when on macOS and enabled. Returns the tap or None."""
    if platform.system() != "Darwin":
        return None
    if not getattr(config.screenshot, "enabled", False):
        return None
    # Nudge the Screen Recording grant; capture yields a blank image without it.
    if screen_recording_trusted() is False:
        request_screen_recording()
    log.info("Dual-⌘ screenshot gesture armed (press both Command keys).")
    return MacFlagsTap(on_dual_cmd=run_capture_async).start()
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_screenshot_gesture_wiring.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Wire into both UIs + a tray toggle**

- In `src/spuk/ui_bar.py` `run_bar(...)`, after the core/listener start, call `tap = start_if_enabled(config)` and `tap and tap.stop()` on shutdown (store it next to the other handles the bar already cleans up).
- In `src/spuk/tray.py` `run_tray(...)`, do the same, and add a menu checkbox "Screenshot on ⌘ + ⌘" bound to the current `screenshot_enabled` state: toggling it persists via `update_user_settings(screenshot_enabled=<bool>)` and starts/stops the tap live (mirror how the tray already toggles other options). Overlay the saved value in `config.py` `load_config` like the other user settings (add an `_overlay_user_screenshot(s)` reading `screenshot_enabled`).

Manually verify (macOS, built or `uv run python -m spuk --tray`): press both ⌘ over a Safari window → the window image lands on the clipboard and pastes into a focused TextEdit/Notes/Claude-Code field. Toggle the menu item off → pressing both ⌘ does nothing.

- [ ] **Step 6: Run full suite + lint, then commit**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q`
Expected: PASS.
Run: `uv run --with ruff ruff check src/ tests/`
Expected: clean.

```bash
git add src/spuk/screenshot_gesture.py src/spuk/tray.py src/spuk/ui_bar.py src/spuk/config.py tests/test_screenshot_gesture_wiring.py
git commit -m "feat(screenshot): wire dual-⌘ gesture into tray + bar with a live toggle"
```

---

### Task 9: Permissions UI row, packaging plist, docs + manual verification

**Files:**
- Modify: `src/spuk/ui_permissions.py` (Screen Recording row)
- Test: extend `tests/test_permissions_ui.py`
- Modify: packaging macOS `Info.plist` block (under `packaging/`)
- Modify: `README.md`, `docs/ARCHITECTURE.md`

**Interfaces:** none.

- [ ] **Step 1: Add the Screen Recording row** (shown only when the gesture is enabled AND `screen_recording_trusted() is False`), wired to `open_privacy_pane("screen_recording")`, mirroring the Input Monitoring row. Extend `tests/test_permissions_ui.py` to assert it shows when untrusted and hides when trusted. Run:

`UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_permissions_ui.py`
Expected: PASS.

- [ ] **Step 2: Add the Info.plist usage string** in the packaging `.spec`:

```xml
<key>NSScreenCaptureUsageDescription</key>
<string>Spuk captures the window you choose (press both Command keys) so you can paste it. The image stays on your Mac.</string>
```

- [ ] **Step 3: Docs.** In `README.md` add a "Window screenshot (macOS)" feature note: press both ⌘ to copy + paste the current window, fully local, requires Screen Recording. In `docs/ARCHITECTURE.md` document the listen-only flags tap (and that it's the shared base that unblocks issue #17's Fn support), the window picker, and the local-only guarantee.

- [ ] **Step 4: Final verification + commit**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q`
Expected: PASS.

```bash
git add src/spuk/ui_permissions.py tests/test_permissions_ui.py packaging README.md docs/ARCHITECTURE.md
git commit -m "feat(screenshot): Screen Recording UI row, Info.plist string, docs"
```

---

## Self-Review

**Spec coverage:**
- "Press both Command keys" → Task 2 (`both_cmd_only` requires both bits, no others), Task 3 (`MacFlagsTap`).
- "Screenshot the window you're in right now" → Task 4 (`pick_window` = frontmost app's layer-0 window) + Task 5 (`front_window_png`).
- "Copy it right away" → Task 5 (`copy_image_to_clipboard`, clipboard left intact on purpose).
- "Paste into the focused field, e.g. terminal" → Task 5 (`shoot_and_paste` sends ⌘V via the existing injector). (Honesty note for the owner: a plain text-only terminal can't render a pasted image, but image-capable targets — Claude Code's TUI, chat fields, editors, Slack, Preview — will.)
- "No cloud upload" → Global Constraints; no network code anywhere in the feature.
- macOS-only + can't-wedge robustness → Global Constraints, Task 2/3 state-read design.
- Permission → Task 6 (helper), Task 8 (request on enable), Task 9 (UI row + plist).
- Doesn't disturb dictation → separate module, separate tap, no `_feed_press` involvement (Global Constraints).

**Placeholder scan:** none — every code step is concrete. The only non-CI paths (real CGEventTap, screencapture, NSPasteboard) are behind seams whose logic is unit-tested, plus an explicit manual macOS verification in Tasks 8–9.

**Type consistency:** `pick_window(window_infos, pid) -> int | None` feeds `capture_window_to_png(window_id, path)` consistently; `shoot_and_paste(capture, copy, paste)` matches the injected fakes in `test_screenshot_flow.py` and the production defaults `front_window_png` / `copy_image_to_clipboard` / `send_paste_shortcut`; `MacFlagsTap(on_dual_cmd=...)` / `.start()` / `.stop()` names match across Tasks 3 and 8; `screen_recording_trusted` / `request_screen_recording` match across Tasks 6 and 8.
