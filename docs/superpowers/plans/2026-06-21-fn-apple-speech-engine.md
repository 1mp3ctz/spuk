# Fn → Apple Live-Streaming Dictation Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second dictation mode: while Fn is held, Apple's on-device `SFSpeechRecognizer` streams partial results directly into the focused field in real time. Release Fn to finalize. Ctrl+Option → Whisper is unchanged.

**Architecture:**
Extend the existing `MacFlagsTap` (already running one CGEventTap for dual-⌘) to also fire `on_fn_press`/`on_fn_release` from the same tap. A new `AppleSpeechEngine` wraps `SFSpeechRecognizer` + `AVAudioEngine`. A new `LiveInserter` manages provisional text: on each partial result it backtracks the previous provisional text and types the new one; on final, it clears tracking.

**Tech Stack:** Python 3.11, pyobjc-framework-Speech, pyobjc-framework-AVFoundation, pynput (existing), PySide6 (existing)

## Global Constraints

- macOS ONLY — every new module must guard with `platform.system() == "Darwin"` or a `sys_platform` pyproject marker; Windows/Linux import must be safe (no lazy-import crash on import)
- All OS calls (SFSpeechRecognizer, AVAudioEngine, Quartz tap) behind injectable seams — tests run with zero real framework calls
- Immutable config dataclasses (frozen=True); use `dataclasses.replace()` for updates
- No hardcoded secrets; no new network calls
- `pytest -q` must stay green (≥161 passing); `ruff check src/ tests/` must pass
- Version bump: `1.1.1` → `1.2.0` in `pyproject.toml`, `src/spuk/__init__.py`, and `packaging/spuk.spec`
- All commits must use the noreply GitHub email (`git config user.email`)
- Working directory: `/Volumes/2TB/Claude/Spuk.worktrees/apple-speech-engine`
- SDD ledger: `.superpowers/sdd/progress.md` — append each completed task

---

## File Map

**New files:**
- `src/spuk/fn_gesture.py` — pure Fn press/release logic + wiring helper
- `src/spuk/live_insert.py` — provisional-text backspace/type manager
- `src/spuk/apple_speech.py` — `AppleSpeechEngine` wrapping SFSpeechRecognizer
- `tests/test_fn_detection.py` — unit tests for Fn edge logic
- `tests/test_live_insert.py` — unit tests for LiveInserter
- `tests/test_apple_speech.py` — unit tests for AppleSpeechEngine

**Modified files:**
- `src/spuk/mac_flags_tap.py` — add `FN_BIT`, `fn_edge()`, Fn callbacks to `MacFlagsTap`
- `src/spuk/paste.py` — add `live_type(text)` and `live_backspace(count)` public functions
- `src/spuk/config.py` — add `AppleSpeechConfig`, `apple_speech` field on `Config`
- `config.toml` — add `[apple_speech]` section
- `src/spuk/permissions.py` — add Speech Recognition authorization helpers + pane key
- `src/spuk/ui_permissions.py` — add Speech Recognition row
- `src/spuk/tray.py` — add "Apple Dictation (Fn)" checkbox toggle
- `src/spuk/ui_bar.py` — wire Fn gesture → Apple engine → live insert on launch/quit
- `pyproject.toml` — add pyobjc-framework-Speech + pyobjc-framework-AVFoundation deps; bump version
- `src/spuk/__init__.py` — bump `__version__` to `"1.2.0"`
- `packaging/spuk.spec` — add Speech/AVFoundation hidden imports; bump Info.plist version

---

### Task 1: Fn detection logic in MacFlagsTap

**Files:**
- Modify: `src/spuk/mac_flags_tap.py`
- Create: `tests/test_fn_detection.py`

**Interfaces:**
- Produces: `FN_BIT = 0x00800000`, `fn_edge(flags: int, fn_down: bool) -> tuple[bool, bool, bool]` (press, release, new_fn_down), and `MacFlagsTap.__init__` now accepts two new optional kwargs: `on_fn_press: Callable[[], None] | None = None` and `on_fn_release: Callable[[], None] | None = None`
- Backward compatible: existing `MacFlagsTap(on_dual_cmd=...)` calls keep working unchanged

**Background:** The existing CGEventTap fires on every `kCGEventFlagsChanged` event and reads the full device-specific modifier flags word. `FN_BIT = 0x00800000` is already listed in `OTHER_MODS` (to block dual-⌘ while Fn is held) but never read separately. We add a second edge detector that fires when the Fn bit transitions, without any changes to the existing dual-⌘ path.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fn_detection.py
from spuk.mac_flags_tap import FN_BIT, fn_edge, MacFlagsTap

CMD_L = 0x00000008
CMD_R = 0x00000010


def test_fn_edge_press():
    """Bit goes 0 → 1: press fires, not release."""
    press, release, new_down = fn_edge(FN_BIT, fn_down=False)
    assert press is True
    assert release is False
    assert new_down is True


def test_fn_edge_release():
    """Bit goes 1 → 0: release fires, not press."""
    press, release, new_down = fn_edge(0, fn_down=True)
    assert press is False
    assert release is True
    assert new_down is False


def test_fn_edge_held():
    """Bit stays 1: nothing fires."""
    press, release, new_down = fn_edge(FN_BIT, fn_down=True)
    assert press is False
    assert release is False
    assert new_down is True


def test_fn_edge_not_pressed():
    """Bit stays 0: nothing fires."""
    press, release, new_down = fn_edge(0, fn_down=False)
    assert press is False
    assert release is False
    assert new_down is False


def test_fn_callbacks_fired_from_handle_flags():
    press_calls = []
    release_calls = []

    tap = MacFlagsTap(
        on_dual_cmd=lambda: None,
        on_fn_press=lambda: press_calls.append(1),
        on_fn_release=lambda: release_calls.append(1),
    )
    tap._handle_flags(FN_BIT)   # press
    tap._handle_flags(FN_BIT)   # still held — no duplicate
    tap._handle_flags(0)         # release

    assert press_calls == [1]
    assert release_calls == [1]


def test_fn_and_dual_cmd_independent():
    """Fn press does not fire dual-⌘ callback and vice versa."""
    fn_fired = []
    cmd_fired = []

    tap = MacFlagsTap(
        on_dual_cmd=lambda: cmd_fired.append(1),
        on_fn_press=lambda: fn_fired.append(1),
    )
    tap._handle_flags(FN_BIT)       # only fn
    tap._handle_flags(0)
    tap._handle_flags(CMD_L | CMD_R) # only dual-⌘ (no Fn)

    assert fn_fired == [1]
    assert cmd_fired == [1]


def test_no_fn_callbacks_when_omitted():
    """MacFlagsTap with no fn callbacks stays backward-compatible."""
    tap = MacFlagsTap(on_dual_cmd=lambda: None)
    tap._handle_flags(FN_BIT)  # must not raise
    tap._handle_flags(0)
```

- [ ] **Step 2: Run to verify all fail**

```bash
cd /Volumes/2TB/Claude/Spuk.worktrees/apple-speech-engine
uv run pytest tests/test_fn_detection.py -v
```
Expected: ERRORS/FAILURES (FN_BIT and fn_edge don't exist yet)

- [ ] **Step 3: Add FN_BIT and fn_edge to mac_flags_tap.py**

After the existing `CMD_R = 0x00000010` line add:
```python
FN_BIT = 0x00800000  # kCGEventFlagMaskSecondaryFn
```

After the `dual_cmd_edge` function add:
```python
def fn_edge(flags: int, fn_down: bool) -> tuple[bool, bool, bool]:
    """Pure Fn press/release edge detector. Returns (press, release, new_fn_down)."""
    now_down = bool(flags & FN_BIT)
    if now_down and not fn_down:
        return True, False, True
    if not now_down and fn_down:
        return False, True, False
    return False, False, now_down
```

- [ ] **Step 4: Extend MacFlagsTap.__init__ and _handle_flags**

Change `__init__` signature to:
```python
def __init__(
    self,
    on_dual_cmd: Callable[[], None],
    on_fn_press: Callable[[], None] | None = None,
    on_fn_release: Callable[[], None] | None = None,
) -> None:
    self._cb = on_dual_cmd
    self._on_fn_press = on_fn_press
    self._on_fn_release = on_fn_release
    self._armed = False
    self._fn_down = False
    self._tap = None
    self._runloop_source = None
    self._runloop = None
    self._thread: threading.Thread | None = None
```

Extend `_handle_flags` to call fn callbacks after the existing dual-⌘ block:
```python
def _handle_flags(self, flags: int) -> None:
    # dual-⌘ (unchanged)
    active = both_cmd_only(flags)
    fire, self._armed = dual_cmd_edge(active, self._armed)
    if fire:
        try:
            self._cb()
        except Exception as exc:
            log.error("dual-⌘ handler failed: %s", exc)

    # Fn press / release
    press, release, self._fn_down = fn_edge(flags, self._fn_down)
    if press and self._on_fn_press is not None:
        try:
            self._on_fn_press()
        except Exception as exc:
            log.error("fn-press handler failed: %s", exc)
    if release and self._on_fn_release is not None:
        try:
            self._on_fn_release()
        except Exception as exc:
            log.error("fn-release handler failed: %s", exc)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_fn_detection.py tests/test_dual_cmd_logic.py -v
```
Expected: all pass

- [ ] **Step 6: Full suite green**

```bash
uv run pytest -q && uv run ruff check src/ tests/
```
Expected: ≥161 passed, 0 errors

- [ ] **Step 7: Commit**

```bash
git add src/spuk/mac_flags_tap.py tests/test_fn_detection.py
git commit -m "feat: add Fn press/release detection to MacFlagsTap"
```

---

### Task 2: Live text inserter

**Files:**
- Modify: `src/spuk/paste.py` (add `live_type` and `live_backspace`)
- Create: `src/spuk/live_insert.py`
- Create: `tests/test_live_insert.py`

**Interfaces:**
- `paste.live_type(text: str) -> None` — type text as keystrokes via pynput (already main-thread-safe)
- `paste.live_backspace(count: int) -> None` — press Backspace `count` times; no-op if count ≤ 0; uses `_run_on_main` so it's main-thread-safe
- `LiveInserter(type_fn=None, backspace_fn=None)` — None defaults lazily import from paste
- `live_insert.update(text: str)` — erase previous provisional via backspace, type new text
- `live_insert.commit()` — clear provisional tracking (text is now permanent)
- `live_insert.cancel()` — erase provisional text and clear tracking

**Background:** Apple speech fires partial results rapidly. Each update must erase the previous provisional text (N backspaces) then type the new text. We count provisional characters by Python `len()` (code points), which equals the number of pynput backspace strokes needed. On macOS, pynput typing must run on the main thread — `paste._run_on_main` handles this already via `_build_pynput_typer`. `live_backspace` uses the same `_run_on_main` wrapper.

- [ ] **Step 1: Write failing tests for live_insert and paste helpers**

```python
# tests/test_live_insert.py
from spuk.live_insert import LiveInserter


def make_inserter():
    typed = []
    backed = []

    def type_fn(text):
        typed.append(text)

    def bs_fn(n):
        backed.append(n)

    return LiveInserter(type_fn=type_fn, backspace_fn=bs_fn), typed, backed


def test_first_update_types_without_backspace():
    ins, typed, backed = make_inserter()
    ins.update("hello")
    assert backed == []
    assert typed == ["hello"]


def test_second_update_erases_previous():
    ins, typed, backed = make_inserter()
    ins.update("hell")
    ins.update("hello world")
    assert backed == [4]          # erased "hell" (4 chars)
    assert typed == ["hell", "hello world"]


def test_update_empty_text_erases_provisional():
    ins, typed, backed = make_inserter()
    ins.update("abc")
    ins.update("")
    assert backed == [3]
    assert typed == ["abc", ""]


def test_commit_clears_provisional():
    ins, typed, backed = make_inserter()
    ins.update("hi")
    ins.commit()
    ins.update("new")   # no backspace — committed text is not provisional
    assert backed == []
    assert typed == ["hi", "new"]


def test_cancel_erases_provisional_text():
    ins, typed, backed = make_inserter()
    ins.update("draft")
    ins.cancel()
    assert backed == [5]
    assert typed == ["draft"]


def test_cancel_when_nothing_provisional_is_noop():
    ins, typed, backed = make_inserter()
    ins.cancel()
    assert backed == []
    assert typed == []


def test_unicode_len_counts_code_points():
    """len("über") = 4 code points → 4 backspaces."""
    ins, typed, backed = make_inserter()
    ins.update("über")
    ins.update("überall")
    assert backed == [4]
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_live_insert.py -v
```
Expected: ERRORS (module not found)

- [ ] **Step 3: Add live_type and live_backspace to paste.py**

Add at the end of `paste.py`:
```python
# --- live streaming dictation helpers (no clipboard touch) ------------------

_bs_state: dict = {}


def live_type(text: str) -> None:
    """Type ``text`` as keystrokes (live dictation; no clipboard)."""
    _type_text(text)


def live_backspace(count: int) -> None:
    """Press Backspace ``count`` times to erase provisional live-dictation text."""
    if count <= 0:
        return

    def do() -> None:
        from pynput.keyboard import Controller, Key

        ctrl = _bs_state.get("kb")
        if ctrl is None:
            _bs_state["kb"] = ctrl = Controller()
        for _ in range(count):
            ctrl.press(Key.backspace)
            ctrl.release(Key.backspace)

    _run_on_main(do)
```

- [ ] **Step 4: Create src/spuk/live_insert.py**

```python
"""Provisional-text manager for live streaming dictation.

Tracks the text that has been typed but not yet confirmed (a partial result from
SFSpeechRecognizer). On each update, erases the previous provisional text via
Backspace, then types the new text. On commit the tracking is cleared (the final
text is now permanent). On cancel the provisional text is erased and tracking cleared.

All type/backspace calls go through injectable functions (default: paste.live_type
and paste.live_backspace) so tests run with zero real pynput calls.
"""

from __future__ import annotations

from typing import Callable


class LiveInserter:
    def __init__(
        self,
        type_fn: Callable[[str], None] | None = None,
        backspace_fn: Callable[[int], None] | None = None,
    ) -> None:
        self._type_fn = type_fn
        self._backspace_fn = backspace_fn
        self._provisional = ""

    def _type(self, text: str) -> None:
        if self._type_fn is not None:
            self._type_fn(text)
        else:
            from .paste import live_type
            live_type(text)

    def _backspace(self, count: int) -> None:
        if self._backspace_fn is not None:
            self._backspace_fn(count)
        else:
            from .paste import live_backspace
            live_backspace(count)

    def update(self, text: str) -> None:
        """Replace provisional text with ``text``. Erases previous via Backspace."""
        if self._provisional:
            self._backspace(len(self._provisional))
        self._type(text)
        self._provisional = text

    def commit(self) -> None:
        """Mark current provisional text as permanent. No keystrokes sent."""
        self._provisional = ""

    def cancel(self) -> None:
        """Erase provisional text and clear tracking."""
        if self._provisional:
            self._backspace(len(self._provisional))
        self._provisional = ""
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_live_insert.py -v
```
Expected: all pass

- [ ] **Step 6: Full suite green**

```bash
uv run pytest -q && uv run ruff check src/ tests/
```
Expected: ≥161 passed, 0 errors

- [ ] **Step 7: Commit**

```bash
git add src/spuk/paste.py src/spuk/live_insert.py tests/test_live_insert.py
git commit -m "feat: add LiveInserter and paste.live_type/live_backspace for streaming dictation"
```

---

### Task 3: Apple Speech engine

**Files:**
- Create: `src/spuk/apple_speech.py`
- Create: `tests/test_apple_speech.py`

**Interfaces:**
- `speech_auth_status(status_fn=None) -> str` — returns one of `"authorized"`, `"denied"`, `"restricted"`, `"not_determined"` using `SFSpeechRecognizer.authorizationStatus()` (class method, int enum 0–3). Injectable via `status_fn()`
- `request_speech_authorization(callback: Callable[[str], None], request_fn=None) -> None` — calls `SFSpeechRecognizer.requestAuthorization_(block)` async. Converts int status to the same string codes. Injectable via `request_fn(callback)`
- `AppleSpeechEngine(on_partial, on_final, on_error, *, recognizer=None, audio_engine=None)` — main class
  - `is_available() -> bool` — True if `SFSpeechRecognizer.isSupportedLocale_(locale)` (injectable via `recognizer`)
  - `start() -> bool` — set up AVAudioEngine + recognition request + task; return True on success
  - `stop() -> None` — cancel task, stop audio engine, remove tap

**Background:** `SFSpeechRecognizer` is in the `Speech` framework (pyobjc-framework-Speech). `AVAudioEngine` is in `AVFoundation`. Both are macOS-only. The recognizer fires `on_partial` for each interim result (result.isFinal() == False) and `on_final` when done. The `on_partial`/`on_final` callbacks receive a plain `str` (the transcript). `on_error` receives a `str` error description. All three fire from Apple's internal GCD queue — callers must marshal to the main thread if needed (done in ui_bar.py via Qt signals).

The engine uses `requiresOnDeviceRecognition = True` so no network traffic occurs.

**Injectable seam pattern for tests:** Pass fake objects that expose the same method names. The test creates a fake recognizer that immediately calls the result handler with a fake partial + final.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_apple_speech.py
import sys
import types

import pytest

from spuk.apple_speech import speech_auth_status, AppleSpeechEngine


# --- speech_auth_status -------------------------------------------------------


def test_auth_status_authorized():
    assert speech_auth_status(status_fn=lambda: 3) == "authorized"


def test_auth_status_denied():
    assert speech_auth_status(status_fn=lambda: 1) == "denied"


def test_auth_status_restricted():
    assert speech_auth_status(status_fn=lambda: 2) == "restricted"


def test_auth_status_not_determined():
    assert speech_auth_status(status_fn=lambda: 0) == "not_determined"


# --- AppleSpeechEngine --------------------------------------------------------


def _make_fake_recognizer(partial_text="hello", final_text="hello world"):
    """Returns a fake recognizer class + recorded calls."""
    calls = {"start": 0, "stop": 0, "task_started": False}
    handler_ref = [None]

    class FakeTask:
        def cancel(self):
            calls["stop"] += 1

    class FakeRecognizer:
        def __init__(self):
            self._on_device = False

        def setRequiresOnDeviceRecognition_(self, v):
            self._on_device = v

        def recognitionTaskWithRequest_resultHandler_(self, request, handler):
            calls["task_started"] = True
            handler_ref[0] = handler
            return FakeTask()

    return FakeRecognizer(), handler_ref, calls


def _make_fake_audio_engine(ok=True):
    calls = {"started": False, "stopped": False, "tap_installed": False, "tap_removed": False}
    tap_ref = [None]

    class FakeBusFormat:
        pass

    class FakeInputNode:
        def outputFormatForBus_(self, bus):
            return FakeBusFormat()

        def installTapOnBus_bufferSize_format_block_(self, bus, size, fmt, block):
            calls["tap_installed"] = True
            tap_ref[0] = block

        def removeTapOnBus_(self, bus):
            calls["tap_removed"] = True

    class FakeAudioEngine:
        def __init__(self):
            self._node = FakeInputNode()

        def inputNode(self):
            return self._node

        def startAndReturnError_(self, err):
            calls["started"] = True
            return ok

        def stop(self):
            calls["stopped"] = True

    return FakeAudioEngine(), calls


def test_engine_start_fires_on_partial_and_on_final():
    partials = []
    finals = []
    errors = []

    fake_recognizer, handler_ref, rec_calls = _make_fake_recognizer()
    fake_audio, audio_calls = _make_fake_audio_engine()

    engine = AppleSpeechEngine(
        on_partial=partials.append,
        on_final=finals.append,
        on_error=errors.append,
        recognizer=fake_recognizer,
        audio_engine=fake_audio,
    )
    assert engine.start() is True
    assert rec_calls["task_started"] is True
    assert audio_calls["started"] is True

    # Simulate partial result
    class FakeResult:
        def __init__(self, text, final):
            self._text = text
            self._final = final

        def bestTranscription(self):
            class T:
                pass
            t = T()
            t.formattedString = lambda: self._text
            return t

        def isFinal(self):
            return self._final

    handler_ref[0](FakeResult("hello", False), None)
    assert partials == ["hello"]
    assert finals == []

    handler_ref[0](FakeResult("hello world", True), None)
    assert finals == ["hello world"]
    assert errors == []


def test_engine_stop_cancels_task_and_stops_audio():
    fake_recognizer, handler_ref, rec_calls = _make_fake_recognizer()
    fake_audio, audio_calls = _make_fake_audio_engine()

    engine = AppleSpeechEngine(
        on_partial=lambda t: None,
        on_final=lambda t: None,
        on_error=lambda e: None,
        recognizer=fake_recognizer,
        audio_engine=fake_audio,
    )
    engine.start()
    engine.stop()

    assert rec_calls["stop"] == 1
    assert audio_calls["stopped"] is True
    assert audio_calls["tap_removed"] is True


def test_engine_error_in_handler_calls_on_error():
    errors = []
    fake_recognizer, handler_ref, _ = _make_fake_recognizer()
    fake_audio, _ = _make_fake_audio_engine()

    engine = AppleSpeechEngine(
        on_partial=lambda t: None,
        on_final=lambda t: None,
        on_error=errors.append,
        recognizer=fake_recognizer,
        audio_engine=fake_audio,
    )
    engine.start()

    class FakeNSError:
        def localizedDescription(self):
            return "mic busy"

    handler_ref[0](None, FakeNSError())
    assert errors == ["mic busy"]


def test_engine_start_fails_when_audio_engine_fails():
    fake_recognizer, _, _ = _make_fake_recognizer()
    fake_audio, _ = _make_fake_audio_engine(ok=False)

    engine = AppleSpeechEngine(
        on_partial=lambda t: None,
        on_final=lambda t: None,
        on_error=lambda e: None,
        recognizer=fake_recognizer,
        audio_engine=fake_audio,
    )
    assert engine.start() is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_apple_speech.py -v
```
Expected: ERRORS (module not found)

- [ ] **Step 3: Create src/spuk/apple_speech.py**

```python
"""Apple on-device speech recognition engine for live streaming dictation.

Uses SFSpeechRecognizer (Speech framework) with requiresOnDeviceRecognition=True
so all processing is local and free. AVAudioEngine taps the microphone and feeds
PCM buffers to the recognition request. Partial results fire on_partial; the
final result fires on_final.

THREADING: callbacks fire on Apple's internal GCD queue. Callers (ui_bar.py)
must marshal to the Qt main thread via signals before touching the UI or pynput.

All OS objects (recognizer, audio_engine) are injectable for testing.
"""

from __future__ import annotations

import logging
import platform
from typing import Callable

log = logging.getLogger("spuk.apple_speech")

_STATUS_MAP = {0: "not_determined", 1: "denied", 2: "restricted", 3: "authorized"}


def speech_auth_status(status_fn: Callable[[], int] | None = None) -> str:
    """Return current Speech Recognition authorization as a string.

    Uses ``SFSpeechRecognizer.authorizationStatus()`` (class method, int enum).
    Injectable via ``status_fn`` for tests.
    """
    if status_fn is not None:
        return _STATUS_MAP.get(status_fn(), "not_determined")
    if platform.system() != "Darwin":
        return "authorized"
    try:
        from Speech import SFSpeechRecognizer
        return _STATUS_MAP.get(int(SFSpeechRecognizer.authorizationStatus()), "not_determined")
    except Exception as exc:
        log.debug("Could not read speech auth status: %s", exc)
        return "not_determined"


def request_speech_authorization(
    callback: Callable[[str], None],
    request_fn: Callable[[Callable[[int], None]], None] | None = None,
) -> None:
    """Trigger the macOS Speech Recognition prompt (async).

    ``callback`` receives one of the _STATUS_MAP strings when the user responds.
    Injectable via ``request_fn`` for tests.
    """
    def _wrap(status_int: int) -> None:
        callback(_STATUS_MAP.get(int(status_int), "not_determined"))

    if request_fn is not None:
        request_fn(_wrap)
        return
    if platform.system() != "Darwin":
        callback("authorized")
        return
    try:
        from Speech import SFSpeechRecognizer
        SFSpeechRecognizer.requestAuthorization_(_wrap)
    except Exception as exc:
        log.warning("Could not request speech authorization: %s", exc)
        callback("not_determined")


class AppleSpeechEngine:
    """Live streaming dictation via SFSpeechRecognizer.

    ``recognizer`` and ``audio_engine`` are real framework objects in production
    and fakes in tests. Pass None to have the constructor build real ones
    (macOS only, lazy import).
    """

    def __init__(
        self,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
        on_error: Callable[[str], None],
        *,
        recognizer: object | None = None,
        audio_engine: object | None = None,
    ) -> None:
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error
        self._recognizer = recognizer
        self._audio_engine = audio_engine
        self._task: object | None = None
        self._request: object | None = None

    def _build_real_objects(self) -> bool:
        """Build SFSpeechRecognizer + AVAudioEngine. Returns False on failure."""
        try:
            from Speech import SFSpeechRecognizer
            from AVFoundation import AVAudioEngine
            import Foundation

            locale = Foundation.NSLocale.localeWithLocaleIdentifier_("en-US")
            rec = SFSpeechRecognizer.alloc().initWithLocale_(locale)
            if rec is None:
                log.warning("SFSpeechRecognizer unavailable for en-US locale.")
                return False
            rec.setRequiresOnDeviceRecognition_(True)
            self._recognizer = rec
            self._audio_engine = AVAudioEngine.alloc().init()
            return True
        except Exception as exc:
            log.warning("Could not build Apple speech objects: %s", exc)
            return False

    def _build_request(self) -> object | None:
        """Create and configure the audio buffer recognition request."""
        try:
            from Speech import SFSpeechAudioBufferRecognitionRequest
            req = SFSpeechAudioBufferRecognitionRequest.alloc().init()
            req.setShouldReportPartialResults_(True)
            return req
        except Exception as exc:
            log.warning("Could not create recognition request: %s", exc)
            return None

    def start(self) -> bool:
        """Start live recognition. Returns True on success."""
        if platform.system() != "Darwin" and self._recognizer is None:
            log.debug("Apple speech: not on Darwin, no injected recognizer — skipping.")
            return False

        if self._recognizer is None or self._audio_engine is None:
            if not self._build_real_objects():
                return False

        recognizer = self._recognizer
        audio_engine = self._audio_engine

        # Build recognition request
        try:
            from Speech import SFSpeechAudioBufferRecognitionRequest
            request = SFSpeechAudioBufferRecognitionRequest.alloc().init()
            request.setShouldReportPartialResults_(True)
        except Exception:
            # In tests, we skip the real framework import
            request = None

        self._request = request

        # Install mic tap
        try:
            input_node = audio_engine.inputNode()
            fmt = input_node.outputFormatForBus_(0)

            def feed_buffer(buffer, when):
                if self._request is not None:
                    try:
                        self._request.appendAudioPCMBuffer_(buffer)
                    except Exception:
                        pass

            input_node.installTapOnBus_bufferSize_format_block_(0, 1024, fmt, feed_buffer)
        except Exception as exc:
            log.warning("Could not install audio tap: %s", exc)
            return False

        # Start audio engine
        try:
            ok = audio_engine.startAndReturnError_(None)
            if not ok:
                log.warning("AVAudioEngine.start failed.")
                try:
                    audio_engine.inputNode().removeTapOnBus_(0)
                except Exception:
                    pass
                return False
        except Exception as exc:
            log.warning("Could not start AVAudioEngine: %s", exc)
            return False

        # Start recognition task
        def _result_handler(result, error):
            if error is not None:
                try:
                    self._on_error(error.localizedDescription())
                except Exception as e:
                    log.debug("on_error raised: %s", e)
            if result is not None:
                try:
                    text = result.bestTranscription().formattedString()
                    if result.isFinal():
                        self._on_final(text)
                    else:
                        self._on_partial(text)
                except Exception as e:
                    log.debug("result handler raised: %s", e)

        try:
            self._task = recognizer.recognitionTaskWithRequest_resultHandler_(
                self._request if self._request is not None else object(),
                _result_handler,
            )
        except Exception as exc:
            log.warning("Could not start recognition task: %s", exc)
            return False

        return True

    def stop(self) -> None:
        """Stop live recognition and tear down audio."""
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception as exc:
                log.debug("task cancel error: %s", exc)
            self._task = None

        if self._audio_engine is not None:
            try:
                self._audio_engine.inputNode().removeTapOnBus_(0)
            except Exception:
                pass
            try:
                self._audio_engine.stop()
            except Exception as exc:
                log.debug("audio engine stop error: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_apple_speech.py -v
```
Expected: all pass

- [ ] **Step 5: Full suite green**

```bash
uv run pytest -q && uv run ruff check src/ tests/
```
Expected: ≥161 passed, 0 errors

- [ ] **Step 6: Commit**

```bash
git add src/spuk/apple_speech.py tests/test_apple_speech.py
git commit -m "feat: add AppleSpeechEngine with SFSpeechRecognizer streaming (injectable seams)"
```

---

### Task 4: Config + permissions

**Files:**
- Modify: `src/spuk/config.py`
- Modify: `config.toml`
- Modify: `src/spuk/permissions.py`
- Modify: `src/spuk/ui_permissions.py`

**Interfaces:**
- `AppleSpeechConfig(frozen=True, enabled: bool = True)` — new dataclass
- `Config.apple_speech: AppleSpeechConfig` — new field; optional TOML section (defaults apply when `[apple_speech]` absent)
- `permissions.speech_recognition_authorized() -> bool | None` — calls `speech_auth_status()`; True="authorized", False="denied"/"restricted", None="not_determined"
- `permissions.PRIVACY_PANES["speech_recognition"]` — added entry: `"x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition"`
- `ui_permissions.py` — adds a "Speech Recognition" row that appears when `speech_recognition_authorized() is False`; "Enable" opens the privacy pane

**Background:** The `[apple_speech]` section in config.toml mirrors the `[screenshot]` pattern: optional section, `ScreenshotConfig(**raw.get("screenshot", {}))` → `AppleSpeechConfig(**raw.get("apple_speech", {}))`. The Speech Recognition pane deep-link uses the same `open_privacy_pane()` helper.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_apple_speech_config.py
from spuk.config import load_config, AppleSpeechConfig


def test_apple_speech_config_defaults_when_section_absent(tmp_path):
    """Load a config.toml that has no [apple_speech] section — defaults apply."""
    cfg_text = (tmp_path / "base.toml").read_text() if False else ""
    # Build minimal valid config with NO [apple_speech] section
    minimal = tmp_path / "config.toml"
    minimal.write_text(
        "[transcribe]\n"
        'engine = "faster-whisper"\nmodel = "small"\ndefault_language = "en"\n'
        'languages = ["en"]\ndevice = "cpu"\ncompute_type = "int8"\n'
        "vad_filter = true\nbeam_size = 1\n\n"
        "[hotkey]\nmode = \"push_to_talk\"\nkey = \"<ctrl>+<alt>\"\n"
        "cycle_language = \"<ctrl>+<shift>+l\"\n\n"
        "[audio]\nsamplerate = 16000\nchannels = 1\nmin_seconds = 0.3\n\n"
        "[post_process]\nenabled = false\ni_understand_this_costs_money = false\n"
        'provider = "claude"\nmax_calls_per_day = 50\n'
    )
    cfg = load_config(minimal)
    assert cfg.apple_speech.enabled is True


def test_apple_speech_config_honours_toml(tmp_path):
    minimal = tmp_path / "config.toml"
    minimal.write_text(
        "[transcribe]\n"
        'engine = "faster-whisper"\nmodel = "small"\ndefault_language = "en"\n'
        'languages = ["en"]\ndevice = "cpu"\ncompute_type = "int8"\n'
        "vad_filter = true\nbeam_size = 1\n\n"
        "[hotkey]\nmode = \"push_to_talk\"\nkey = \"<ctrl>+<alt>\"\n"
        "cycle_language = \"<ctrl>+<shift>+l\"\n\n"
        "[audio]\nsamplerate = 16000\nchannels = 1\nmin_seconds = 0.3\n\n"
        "[post_process]\nenabled = false\ni_understand_this_costs_money = false\n"
        'provider = "claude"\nmax_calls_per_day = 50\n\n'
        "[apple_speech]\nenabled = false\n"
    )
    cfg = load_config(minimal)
    assert cfg.apple_speech.enabled is False


def test_speech_recognition_authorized_uses_status():
    from spuk import permissions
    # monkeypatch via injected speech_auth_status
    import spuk.apple_speech as asp

    original = asp.speech_auth_status

    asp.speech_auth_status = lambda: "authorized"
    assert permissions.speech_recognition_authorized() is True

    asp.speech_auth_status = lambda: "denied"
    assert permissions.speech_recognition_authorized() is False

    asp.speech_auth_status = lambda: "not_determined"
    assert permissions.speech_recognition_authorized() is None

    asp.speech_auth_status = original
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_apple_speech_config.py -v
```
Expected: ERRORS (AppleSpeechConfig / apple_speech field don't exist yet)

- [ ] **Step 3: Add AppleSpeechConfig and apple_speech field to config.py**

After `ScreenshotConfig`:
```python
@dataclass(frozen=True)
class AppleSpeechConfig:
    enabled: bool = True
```

In `Config`:
```python
@dataclass(frozen=True)
class Config:
    transcribe: TranscribeConfig
    hotkey: HotkeyConfig
    audio: AudioConfig
    post_process: PostProcessConfig
    screenshot: ScreenshotConfig
    apple_speech: AppleSpeechConfig
```

In `load_config`, after the `screenshot = ScreenshotConfig(**s)` line:
```python
apple_speech = AppleSpeechConfig(**raw.get("apple_speech", {}))
```

And in the `return Config(...)` call add `apple_speech=apple_speech`.

- [ ] **Step 4: Add [apple_speech] section to config.toml**

Append at the end of `config.toml`:
```toml
[apple_speech]
# macOS only. Hold the Fn (Globe) key to dictate with Apple's on-device engine.
# Words appear live as you speak; release Fn to finalise. Fully local — no network.
# Note: set System Settings → Keyboard → "Press Globe key to: Do Nothing" so macOS
# doesn't open its own dictation popup when you press Fn.
enabled = true
```

- [ ] **Step 5: Add permission helpers to permissions.py**

Add `"speech_recognition"` to `PRIVACY_PANES`:
```python
"speech_recognition": "x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition",
```

Add at the end of `permissions.py` (before the Linux section is fine, after the screen_recording helpers):
```python
def speech_recognition_authorized() -> bool | None:
    """Whether Speech Recognition is authorized for this process.

    Returns True="authorized", False="denied"/"restricted", None="not_determined".
    """
    from .apple_speech import speech_auth_status
    status = speech_auth_status()
    if status == "authorized":
        return True
    if status in ("denied", "restricted"):
        return False
    return None  # not_determined — user hasn't been asked yet
```

- [ ] **Step 6: Add Speech Recognition row to ui_permissions.py**

Read `src/spuk/ui_permissions.py` first to understand the row pattern (each permission row has a label, status check, and enable button). Mirror the Screen Recording row pattern:

Find where the Screen Recording row is added and add a Speech Recognition row immediately after it using the same structure:
- Label: `"Speech Recognition"` 
- Status check: `permissions.speech_recognition_authorized() is False`
- Enable: `lambda: permissions.open_privacy_pane("speech_recognition")`
- Show condition: same as Screen Recording (only when `False`, not when `None`)

- [ ] **Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/test_apple_speech_config.py -v
```
Expected: all pass

- [ ] **Step 8: Full suite green**

```bash
uv run pytest -q && uv run ruff check src/ tests/
```
Expected: ≥161 passed, 0 errors

- [ ] **Step 9: Commit**

```bash
git add src/spuk/config.py config.toml src/spuk/permissions.py src/spuk/ui_permissions.py tests/test_apple_speech_config.py
git commit -m "feat: add AppleSpeechConfig, speech_recognition_authorized(), privacy pane + UI row"
```

---

### Task 5: UI wiring + build metadata

**Files:**
- Modify: `src/spuk/ui_bar.py`
- Modify: `src/spuk/tray.py`
- Modify: `pyproject.toml`
- Modify: `src/spuk/__init__.py`
- Modify: `packaging/spuk.spec`

**Interfaces consumed from earlier tasks:**
- `MacFlagsTap(on_dual_cmd=..., on_fn_press=..., on_fn_release=...)` — Task 1
- `LiveInserter(type_fn=None, backspace_fn=None)` — Task 2
- `AppleSpeechEngine(on_partial, on_final, on_error)` — Task 3
- `config.apple_speech.enabled: bool` — Task 4

**Background (threading):**
`AppleSpeechEngine` callbacks (`on_partial`, `on_final`, `on_error`) fire on Apple's internal GCD queue — a non-Qt thread. To update the UI and call `live_insert.update()` safely, add Qt signals `live_partial = Signal(str)` and `live_final = Signal(str)` to `CoreSignals`. Connect them to slots on the main thread. `live_insert.update()` calls `paste.live_type` which already uses `_run_on_main`, so it's safe to call from the Qt main thread.

The Fn gesture starts/stops the Apple engine. Because `_handle_flags` fires from the CGEventTap daemon thread (same as pynput), and `AppleSpeechEngine.start()` / `.stop()` involve setting up `AVAudioEngine`, marshal the start/stop through Qt signals too (`live_start = Signal()`, `live_stop = Signal()`).

**Tray toggle ("Apple Dictation (Fn)"):** mirrors the existing Screenshot toggle in `tray.py`. Toggling saves `apple_speech_enabled` to settings.json; the tap is started/stopped accordingly.

**Version bump:** `1.1.1` → `1.2.0` in three places.

- [ ] **Step 1: Write a failing integration smoke test**

```python
# tests/test_apple_speech_wiring.py
"""Smoke-test the wiring layer without real Qt or OS frameworks."""
import platform
import pytest


def test_live_inserter_update_calls_type_fn():
    """LiveInserter correctly delegates type/backspace (wiring sanity)."""
    from spuk.live_insert import LiveInserter

    typed = []
    backed = []
    ins = LiveInserter(type_fn=typed.append, backspace_fn=backed.append)
    ins.update("hello")
    ins.update("hello world")
    assert typed == ["hello", "hello world"]
    assert backed == [5]  # erased "hello"


def test_apple_speech_engine_partial_and_final_via_fake():
    """End-to-end: fake recognizer + fake audio → on_partial + on_final fire."""
    from spuk.apple_speech import AppleSpeechEngine

    partials = []
    finals = []

    handler_ref = [None]

    class FakeTask:
        def cancel(self):
            pass

    class FakeRecognizer:
        def setRequiresOnDeviceRecognition_(self, v):
            pass
        def recognitionTaskWithRequest_resultHandler_(self, req, h):
            handler_ref[0] = h
            return FakeTask()

    class FakeInputNode:
        def outputFormatForBus_(self, bus):
            return None
        def installTapOnBus_bufferSize_format_block_(self, *a):
            pass
        def removeTapOnBus_(self, bus):
            pass

    class FakeAudioEngine:
        def inputNode(self):
            return FakeInputNode()
        def startAndReturnError_(self, e):
            return True
        def stop(self):
            pass

    engine = AppleSpeechEngine(
        on_partial=partials.append,
        on_final=finals.append,
        on_error=lambda e: None,
        recognizer=FakeRecognizer(),
        audio_engine=FakeAudioEngine(),
    )
    assert engine.start()

    class R:
        def __init__(self, t, f):
            self._t = t
            self._f = f
        def bestTranscription(self):
            class T:
                pass
            x = T()
            x.formattedString = lambda: self._t
            return x
        def isFinal(self):
            return self._f

    handler_ref[0](R("hi", False), None)
    handler_ref[0](R("hi there", True), None)

    assert partials == ["hi"]
    assert finals == ["hi there"]
```

- [ ] **Step 2: Run to verify the smoke test passes already (it uses only prior-task code)**

```bash
uv run pytest tests/test_apple_speech_wiring.py -v
```
Expected: all pass (no new code needed for this test — it uses Tasks 2 & 3)

- [ ] **Step 3: Bump version to 1.2.0**

In `src/spuk/__init__.py`:
```python
__version__ = "1.2.0"
```

In `pyproject.toml`, change `version = "1.1.1"` to `version = "1.2.0"`.

In `packaging/spuk.spec`, change both `CFBundleShortVersionString` and `CFBundleVersion` to `"1.2.0"`.

- [ ] **Step 4: Add pyobjc-framework-Speech and pyobjc-framework-AVFoundation to pyproject.toml**

In the `dependencies` list, after the `pyobjc-framework-Cocoa` line add:
```toml
"pyobjc-framework-Speech>=10,<12; sys_platform == 'darwin'",
"pyobjc-framework-AVFoundation>=10,<12; sys_platform == 'darwin'",
```

- [ ] **Step 5: Add Speech and AVFoundation to spuk.spec hidden imports**

In `packaging/spuk.spec`, in the macOS `hiddenimports` block:
```python
if sys.platform == "darwin":
    hiddenimports += ["Quartz", "AppKit", "Foundation", "Speech", "AVFoundation"]
```

Also add to `info_plist` in the `BUNDLE` call:
```python
"NSSpeechRecognitionUsageDescription": "Spuk uses on-device speech recognition when you hold the Fn key. Audio never leaves your Mac.",
```

- [ ] **Step 6: Wire Fn gesture in ui_bar.py**

Read `src/spuk/ui_bar.py` fully, then make the following targeted changes:

**6a. Add two new signals to `CoreSignals`:**
```python
live_partial = Signal(str)   # partial Apple speech result
live_final = Signal(str)     # final Apple speech result
live_start = Signal()        # Fn pressed: start Apple engine
live_stop = Signal()         # Fn released: stop Apple engine
```

**6b. In `SpukBar.__init__` (or a new `_wire_apple_speech` method called from there), add:**
```python
from .live_insert import LiveInserter
from .apple_speech import AppleSpeechEngine

self._live_insert = LiveInserter()  # uses paste.live_type/live_backspace defaults
self._apple_engine: AppleSpeechEngine | None = None
self._apple_tap = None  # the MacFlagsTap (may already exist for screenshot)
```

**6c. Connect signals to slots in `_wire_core()`:**
```python
self._sig.live_partial.connect(self._on_live_partial)
self._sig.live_final.connect(self._on_live_final)
self._sig.live_start.connect(self._on_fn_press)
self._sig.live_stop.connect(self._on_fn_release)
```

**6d. Add slot methods:**
```python
def _on_live_partial(self, text: str) -> None:
    self._live_insert.update(text)

def _on_live_final(self, text: str) -> None:
    self._live_insert.commit()

def _on_fn_press(self) -> None:
    if not self._cfg.apple_speech.enabled:
        return
    engine = AppleSpeechEngine(
        on_partial=lambda t: self._sig.live_partial.emit(t),
        on_final=lambda t: self._sig.live_final.emit(t),
        on_error=lambda e: log.warning("Apple speech error: %s", e),
    )
    if engine.start():
        self._apple_engine = engine
    else:
        self._live_insert.cancel()

def _on_fn_release(self) -> None:
    if self._apple_engine is not None:
        self._apple_engine.stop()
        self._apple_engine = None
        self._live_insert.commit()
```

**6e. In `run_bar()` (where screenshot tap is started), also start the Fn tap:**

Read how `_start_screenshot(config)` returns the tap. The screenshot gesture already creates `MacFlagsTap(on_dual_cmd=run_capture_async)`. For the Fn gesture, we need to ADD `on_fn_press`/`on_fn_release` to that SAME tap, not create a second tap. 

Modify `screenshot_gesture.py`'s `start_if_enabled` to accept optional Fn callbacks:
```python
def start_if_enabled(
    config,
    on_fn_press: Callable[[], None] | None = None,
    on_fn_release: Callable[[], None] | None = None,
) -> MacFlagsTap | None:
    if platform.system() != "Darwin":
        return None
    screenshot_enabled = getattr(config.screenshot, "enabled", False)
    fn_enabled = getattr(config, "apple_speech", None) and config.apple_speech.enabled
    if not screenshot_enabled and not fn_enabled:
        return None
    ...
    tap_kwargs = {}
    if screenshot_enabled:
        ...  # existing on_dual_cmd setup
    if on_fn_press is not None:
        tap_kwargs["on_fn_press"] = on_fn_press
    if on_fn_release is not None:
        tap_kwargs["on_fn_release"] = on_fn_release
    return MacFlagsTap(on_dual_cmd=run_capture_async if screenshot_enabled else lambda: None,
                       **tap_kwargs).start()
```

Then in `ui_bar.py`'s `run_bar()`, pass Fn callbacks:
```python
tap = _start_screenshot(
    config,
    on_fn_press=lambda: signals.live_start.emit(),
    on_fn_release=lambda: signals.live_stop.emit(),
)
```

- [ ] **Step 7: Add "Apple Dictation (Fn)" toggle to tray.py**

Read `src/spuk/tray.py` fully. Mirror the `toggle_screenshot()` pattern:
- Add a checkbox menu item "Apple Dictation (Fn)" 
- `is_apple_speech_enabled(item)` returns `_apple_enabled[0]` (intent, not tap liveness)
- `toggle_apple_speech()` uses `dataclasses.replace(config, apple_speech=dataclasses.replace(config.apple_speech, enabled=...))` and saves via `update_user_settings(apple_speech_enabled=...)`

In `settings_store.py`, ensure `update_user_settings` can save/load `apple_speech_enabled`.

- [ ] **Step 8: Run full suite**

```bash
uv run pytest -q && uv run ruff check src/ tests/
```
Expected: ≥168 passed, 0 errors

- [ ] **Step 9: Commit**

```bash
git add src/spuk/ui_bar.py src/spuk/tray.py src/spuk/screenshot_gesture.py \
        src/spuk/__init__.py pyproject.toml packaging/spuk.spec \
        tests/test_apple_speech_wiring.py
git commit -m "feat: wire Fn → AppleSpeechEngine → LiveInserter; bump to v1.2.0"
```

---

## Post-Task Notes

### User setup required
After installing, the user must:
1. **System Settings → Keyboard → Press Globe key to: Do Nothing** — prevents macOS's own dictation popup competing for the Fn key
2. **System Settings → Privacy → Speech Recognition** — grant Spuk access when prompted on first Fn press

### Build command (after all tasks)
```bash
cd /Volumes/2TB/Claude/Spuk.worktrees/apple-speech-engine
uv run pyinstaller packaging/spuk.spec --noconfirm
```
Then sign and install as before (using the spuk-codesign identity).
