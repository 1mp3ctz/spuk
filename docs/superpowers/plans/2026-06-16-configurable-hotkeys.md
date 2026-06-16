# Configurable Hotkeys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user rebind all hotkeys (talk key, language-cycle key, hold/toggle mode, hands-free) from the Settings window by pressing the keys they want, applied live and persisted, on macOS/Windows/Linux.

**Architecture:** Capture goes through the existing input-backend chokepoint — both pynput (Mac/Win) and evdev (Linux) feed canonical keys into `HotkeyListener._feed_press`/`_feed_release`, so a capture mode there is backend-agnostic and what you press equals what Spuk listens for. `core` takes ownership of the backend handle so it can stop+restart it on rebind. User values overlay `config.toml` via `settings.json`, mirroring how languages already persist.

**Tech Stack:** Python 3.11, pynput, python-evdev (Linux only), PySide6/Qt, pytest (run via `uv run --with pytest`), ruff.

**Spec:** `docs/superpowers/specs/2026-06-16-hotkey-rebind-design.md`

**Branch:** `feat/configurable-hotkeys` (already checked out, stacked on `feat/linux-support`).

**Conventions:** Run tests with `UV_LINK_MODE=copy uv run --with pytest pytest -q` and lint with `uv run --with ruff ruff check src/ tests/` (pytest/ruff are not project deps; `--with` is ephemeral). Immutable config dataclasses — never mutate a frozen `HotkeyConfig`, build a new one. Commit after each task.

---

### Task 1: `hotkey_format.py` — format / label / validate combos (pure, TDD)

**Files:**
- Create: `src/spuk/hotkey_format.py`
- Test: `tests/test_hotkey_format.py`

The canonical combo string is the pynput parse format `hotkey.py` already uses: modifiers `<ctrl> <alt> <shift> <cmd>`, special keys `<f8> <space>`, printable keys as the bare lowercased char (`l`). Joined with `+`, modifiers first in a fixed order.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hotkey_format.py
import pytest
from pynput.keyboard import Key, KeyCode

from spuk.hotkey_format import keys_to_combo_string, combo_to_label, validate_combo


def test_keys_to_combo_string_modifier_only():
    assert keys_to_combo_string({Key.ctrl, Key.alt}) == "<ctrl>+<alt>"


def test_keys_to_combo_string_orders_modifiers_consistently():
    # order of input set must not matter; output order is fixed (cmd,ctrl,alt,shift)
    assert keys_to_combo_string({Key.alt, Key.ctrl}) == "<ctrl>+<alt>"
    assert keys_to_combo_string({Key.shift, Key.ctrl}) == "<ctrl>+<shift>"


def test_keys_to_combo_string_with_letter():
    assert keys_to_combo_string([Key.ctrl, Key.shift, KeyCode.from_char("L")]) == "<ctrl>+<shift>+l"


def test_keys_to_combo_string_special_key():
    assert keys_to_combo_string({Key.f8}) == "<f8>"


def test_combo_to_label_is_friendly():
    assert combo_to_label("<ctrl>+<alt>") == "Ctrl + Alt"
    assert combo_to_label("<ctrl>+<shift>+l") == "Ctrl + Shift + L"


@pytest.mark.parametrize(
    "combo, ok",
    [
        ("<ctrl>+<alt>", True),       # modifier-only is fine (it's the default)
        ("<ctrl>+<shift>+l", True),   # modifier + letter
        ("<f8>", True),               # lone special/function key is fine
        ("l", False),                 # bare printable letter would type
        ("", False),                  # empty
    ],
)
def test_validate_combo_basic(combo, ok):
    result_ok, _msg = validate_combo(combo, mode="push_to_talk")
    assert result_ok is ok


def test_validate_combo_rejects_collision_with_other():
    ok, msg = validate_combo("<ctrl>+<alt>", mode="push_to_talk", other_combo="<ctrl>+<alt>")
    assert ok is False
    assert "already" in msg.lower()


def test_validate_combo_warns_on_altgr_but_allows():
    ok, msg = validate_combo("<ctrl>+<alt>", mode="push_to_talk")
    assert ok is True
    assert msg is not None and "altgr" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_hotkey_format.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'spuk.hotkey_format'`.

- [ ] **Step 3: Write the implementation**

```python
# src/spuk/hotkey_format.py
"""Pure helpers for hotkey combos: format pressed keys, label, validate.

The canonical combo string is the pynput parse format that hotkey.py parses via
keyboard.HotKey.parse and linux_input.py maps: modifiers as <ctrl>/<alt>/<shift>/
<cmd>, special keys as <name> (e.g. <f8>), printable keys as the bare lowercased
character. Joined with '+', modifiers first in a fixed order so two presses of the
same chord normalise identically.
"""
from __future__ import annotations

import platform

_MOD_ORDER = ("cmd", "ctrl", "alt", "shift")
_MOD_TOKENS = {m: f"<{m}>" for m in _MOD_ORDER}
_MOD_TOKEN_SET = set(_MOD_TOKENS.values())

# Friendly labels. On macOS show the familiar glyphs; elsewhere plain words.
_MAC = platform.system() == "Darwin"
_LABELS = {
    "<ctrl>": "⌃ Ctrl" if _MAC else "Ctrl",
    "<alt>": "⌥ Option" if _MAC else "Alt",
    "<shift>": "⇧ Shift" if _MAC else "Shift",
    "<cmd>": "⌘ Cmd" if _MAC else "Win",
}


def keys_to_combo_string(keys) -> str:
    """Build a canonical '<ctrl>+<alt>+l' string from pynput Key/KeyCode objects."""
    from pynput.keyboard import Key, KeyCode

    mods: list[str] = []
    others: list[str] = []
    for k in keys:
        if isinstance(k, Key):
            name = k.name  # 'ctrl','alt','shift','cmd','f8','space',...
            if name in _MOD_ORDER:
                if name not in mods:
                    mods.append(name)
            else:
                tok = f"<{name}>"
                if tok not in others:
                    others.append(tok)
        elif isinstance(k, KeyCode) and getattr(k, "char", None):
            tok = k.char.lower()
            if tok not in others:
                others.append(tok)
    ordered = [_MOD_TOKENS[m] for m in _MOD_ORDER if m in mods]
    return "+".join(ordered + others)


def _tokens(combo: str) -> list[str]:
    return [t for t in combo.split("+") if t]


def combo_to_label(combo: str) -> str:
    """'<ctrl>+<shift>+l' -> 'Ctrl + Shift + L' (OS-aware modifier names)."""
    out = []
    for t in _tokens(combo):
        if t in _LABELS:
            out.append(_LABELS[t])
        elif t.startswith("<") and t.endswith(">"):
            out.append(t[1:-1].upper())  # <f8> -> F8
        else:
            out.append(t.upper())        # l -> L
    return " + ".join(out)


def validate_combo(combo: str, *, mode: str = "push_to_talk", other_combo: str | None = None):
    """Return (ok: bool, message: str | None).

    message is an error when ok is False, or a non-blocking warning when ok is True.
    """
    tokens = _tokens(combo)
    if not tokens:
        return False, "Press at least one key."

    mods = [t for t in tokens if t in _MOD_TOKEN_SET]
    non_mods = [t for t in tokens if t not in _MOD_TOKEN_SET]
    printable = [t for t in non_mods if not t.startswith("<")]
    specials = [t for t in non_mods if t.startswith("<")]

    # A bare printable key with no modifier and no special would fire while typing.
    if not mods and printable and not specials:
        return False, "Add a modifier (like Ctrl or Alt) — a plain key would fire while you type."

    if other_combo and tokens == _tokens(other_combo):
        return False, "That combo is already used by the other shortcut."

    if set(tokens) == {"<ctrl>", "<alt>"}:
        return True, "Heads-up: on German/Austrian keyboards AltGr sends Ctrl+Alt, which can trigger Spuk."

    return True, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_hotkey_format.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/hotkey_format.py tests/test_hotkey_format.py
git commit -m "feat(hotkey): pure combo format/label/validate helpers"
```

---

### Task 2: Overlay saved hotkeys onto config (`config.py`, TDD)

**Files:**
- Modify: `src/spuk/config.py` (add `_overlay_user_hotkey`, call it in `load_config`)
- Test: `tests/test_config_hotkey_overlay.py`

Mirror `_overlay_user_languages`. settings.json keys: `hotkey_key`, `hotkey_cycle_language`, `hotkey_mode`, `hotkey_handsfree`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config_hotkey_overlay.py
from spuk.config import _overlay_user_hotkey


def test_overlay_applies_saved_values(monkeypatch):
    import spuk.config as cfg
    monkeypatch.setattr(cfg, "load_user_settings", lambda: {
        "hotkey_key": "<ctrl>+<shift>+<space>",
        "hotkey_cycle_language": "<ctrl>+<alt>+c",
        "hotkey_mode": "toggle",
        "hotkey_handsfree": False,
    }, raising=False)
    h = {"key": "<ctrl>+<alt>", "cycle_language": "<ctrl>+<shift>+l",
         "mode": "push_to_talk", "handsfree": True, "double_tap_seconds": 0.4}
    _overlay_user_hotkey(h)
    assert h["key"] == "<ctrl>+<shift>+<space>"
    assert h["cycle_language"] == "<ctrl>+<alt>+c"
    assert h["mode"] == "toggle"
    assert h["handsfree"] is False


def test_overlay_ignores_missing_and_invalid(monkeypatch):
    import spuk.config as cfg
    monkeypatch.setattr(cfg, "load_user_settings", lambda: {
        "hotkey_key": "",            # blank -> ignored
        "hotkey_mode": "nonsense",   # invalid -> ignored
    }, raising=False)
    h = {"key": "<ctrl>+<alt>", "cycle_language": "<ctrl>+<shift>+l",
         "mode": "push_to_talk", "handsfree": True, "double_tap_seconds": 0.4}
    _overlay_user_hotkey(h)
    assert h["key"] == "<ctrl>+<alt>"   # unchanged
    assert h["mode"] == "push_to_talk"  # unchanged
```

- [ ] **Step 2: Run to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_config_hotkey_overlay.py -q`
Expected: FAIL with `ImportError: cannot import name '_overlay_user_hotkey'`.

- [ ] **Step 3: Implement in `config.py`**

Add this function next to `_overlay_user_languages` (note: tests monkeypatch `load_user_settings` on the `spuk.config` module, so import it at module scope is fine, but to match the existing lazy style import inside the function — the test patches with `raising=False` so either works; use a module-scope-friendly local import):

```python
def _overlay_user_hotkey(h: dict) -> None:
    """Overlay the user's saved hotkey choices (settings.json) onto the defaults.

    Mutates ``h`` in place. Ignores missing/blank/invalid values so a partial or
    absent settings.json simply leaves the bundled config.toml defaults in place.
    """
    from .settings_store import load_user_settings

    user = load_user_settings()

    key = user.get("hotkey_key")
    if isinstance(key, str) and key.strip():
        h["key"] = key

    cycle = user.get("hotkey_cycle_language")
    if isinstance(cycle, str) and cycle.strip():
        h["cycle_language"] = cycle

    mode = user.get("hotkey_mode")
    if mode in ("push_to_talk", "toggle"):
        h["mode"] = mode

    handsfree = user.get("hotkey_handsfree")
    if isinstance(handsfree, bool):
        h["handsfree"] = handsfree
```

Then in `load_config`, change the hotkey construction from `hotkey = HotkeyConfig(**raw["hotkey"])` to overlay first:

```python
        h = dict(raw["hotkey"])
        _overlay_user_hotkey(h)
        hotkey = HotkeyConfig(**h)
```

- [ ] **Step 4: Run to verify pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_config_hotkey_overlay.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spuk/config.py tests/test_config_hotkey_overlay.py
git commit -m "feat(hotkey): overlay saved hotkeys from settings.json onto config"
```

---

### Task 3: Capture mode in `HotkeyListener` (`hotkey.py`, TDD)

**Files:**
- Modify: `src/spuk/hotkey.py` (add capture state + intercept in `_feed_press`/`_feed_release`)
- Test: `tests/test_hotkey_capture.py`

**Read `src/spuk/hotkey.py` first.** It now has `_feed_press(key)` / `_feed_release(key)` (canonical keys; both the pynput path and Linux path call them). Capture intercepts at the TOP of those two methods: while capturing, accumulate the held set, track the max set seen, and finalize on the first release — then call `on_done(combo_string)` and leave capture mode. Normal FSM dispatch must NOT run while capturing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hotkey_capture.py
from pynput.keyboard import Key

from spuk.hotkey import HotkeyListener


def _listener(on_start=None, on_stop=None):
    return HotkeyListener(
        key_combo="<ctrl>+<alt>", mode="push_to_talk",
        on_start=on_start or (lambda: None),
        on_stop=on_stop or (lambda: None),
    )


def test_capture_returns_combo_on_first_release():
    got = []
    lis = _listener()
    lis.begin_capture(on_done=got.append)
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    lis._feed_release(Key.alt)
    assert got == ["<ctrl>+<alt>"]


def test_capture_suppresses_the_fsm():
    started = []
    lis = _listener(on_start=lambda: started.append(1))
    lis.begin_capture(on_done=lambda _c: None)
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    # Holding the chord during capture must NOT start a recording.
    assert started == []


def test_capture_can_be_cancelled():
    got = []
    lis = _listener()
    lis.begin_capture(on_done=got.append)
    lis.cancel_capture()
    lis._feed_press(Key.ctrl)
    lis._feed_release(Key.ctrl)
    assert got == []


def test_after_capture_fsm_works_again():
    started = []
    lis = _listener(on_start=lambda: started.append(1))
    lis.begin_capture(on_done=lambda _c: None)
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    lis._feed_release(Key.alt)   # capture done here
    # Now a real chord press should start recording.
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    assert started == [1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_hotkey_capture.py -q`
Expected: FAIL with `AttributeError: 'HotkeyListener' object has no attribute 'begin_capture'`.

- [ ] **Step 3: Implement capture in `hotkey.py`**

In `HotkeyListener.__init__`, add capture state (near the other instance fields):

```python
        # --- combo capture (Settings "press your keys") -------------------
        self._capturing = False
        self._capture_on_done = None
        self._capture_max: set = set()
        self._capture_down: set = set()
```

Add these methods to the class:

```python
    def begin_capture(self, on_done) -> None:
        """Capture the next combo the user presses instead of driving the FSM.

        ``on_done`` is called once, with the canonical combo string, on the first
        key release. Runs on the listener thread — marshal to the UI thread.
        """
        self._capture_on_done = on_done
        self._capture_max = set()
        self._capture_down = set()
        self._capturing = True

    def cancel_capture(self) -> None:
        self._capturing = False
        self._capture_on_done = None

    def _capture_press(self, key) -> None:
        self._capture_down.add(key)
        # Track the largest simultaneously-held set (so Ctrl+Alt captures both).
        if len(self._capture_down) >= len(self._capture_max):
            self._capture_max = set(self._capture_down)

    def _capture_release(self, key) -> None:
        from .hotkey_format import keys_to_combo_string

        combo = keys_to_combo_string(self._capture_max)
        on_done = self._capture_on_done
        self._capturing = False
        self._capture_on_done = None
        self._capture_down = set()
        self._capture_max = set()
        if on_done and combo:
            on_done(combo)
```

Then at the TOP of `_feed_press` add:

```python
        if self._capturing:
            self._capture_press(key)
            return
```

And at the TOP of `_feed_release` add:

```python
        if self._capturing:
            self._capture_release(key)
            return
```

- [ ] **Step 4: Run to verify pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_hotkey_capture.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spuk/hotkey.py tests/test_hotkey_capture.py
git commit -m "feat(hotkey): capture mode at the _feed_* chokepoint (backend-agnostic)"
```

---

### Task 4: Core ownership + rebind/reset/capture (`core.py`, TDD)

**Files:**
- Modify: `src/spuk/core.py`
- Test: `tests/test_core_rebind.py`

`core` must own the running backend handle so it can swap it on rebind. Add a pure helper to build an updated frozen `HotkeyConfig`, plus `start_input`/`stop_input`/`rebind_hotkeys`/`reset_hotkeys`/`start_capture`/`cancel_capture`. Use `dataclasses.replace` for immutability.

- [ ] **Step 1: Write the failing tests**

These avoid constructing the heavy `SpukCore` by testing the pure config helper and by faking the transcriber/recorder.

```python
# tests/test_core_rebind.py
import dataclasses

from spuk.config import HotkeyConfig
from spuk.core import with_hotkey, hotkey_settings


def _hk():
    return HotkeyConfig(mode="push_to_talk", key="<ctrl>+<alt>",
                        cycle_language="<ctrl>+<shift>+l", handsfree=True, double_tap_seconds=0.4)


def test_with_hotkey_builds_new_immutable_config():
    hk = _hk()
    new = with_hotkey(hk, key="<ctrl>+<shift>+<space>", mode="toggle")
    assert new.key == "<ctrl>+<shift>+<space>"
    assert new.mode == "toggle"
    assert new.cycle_language == hk.cycle_language  # untouched
    assert hk.key == "<ctrl>+<alt>"                 # original NOT mutated


def test_hotkey_settings_maps_only_changed_fields():
    assert hotkey_settings(key="<ctrl>+<alt>+x") == {"hotkey_key": "<ctrl>+<alt>+x"}
    out = hotkey_settings(mode="toggle", handsfree=False)
    assert out == {"hotkey_mode": "toggle", "hotkey_handsfree": False}
```

- [ ] **Step 2: Run to verify fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_core_rebind.py -q`
Expected: FAIL with `ImportError: cannot import name 'with_hotkey'`.

- [ ] **Step 3: Implement in `core.py`**

Add module-level pure helpers (top of file, after imports) — note `import dataclasses`:

```python
import dataclasses


def with_hotkey(hk, *, key=None, cycle_language=None, mode=None, handsfree=None):
    """Return a NEW HotkeyConfig with the given fields changed (immutability)."""
    changes = {}
    if key is not None:
        changes["key"] = key
    if cycle_language is not None:
        changes["cycle_language"] = cycle_language
    if mode is not None:
        changes["mode"] = mode
    if handsfree is not None:
        changes["handsfree"] = handsfree
    return dataclasses.replace(hk, **changes)


def hotkey_settings(*, key=None, cycle_language=None, mode=None, handsfree=None) -> dict:
    """Map changed hotkey fields to their settings.json keys (skip unset)."""
    out = {}
    if key is not None:
        out["hotkey_key"] = key
    if cycle_language is not None:
        out["hotkey_cycle_language"] = cycle_language
    if mode is not None:
        out["hotkey_mode"] = mode
    if handsfree is not None:
        out["hotkey_handsfree"] = handsfree
    return out
```

In `SpukCore.__init__`, add a handle + observer:

```python
        self._backend = None   # started handle (owns .stop())
        self._listener = None  # the HotkeyListener FSM (has begin_capture)
        self.on_hotkey_change: Callable[[], None] | None = None
        self.on_combo_captured: Callable[[str], None] | None = None
```

Replace the UI-driven start with core-owned lifecycle. Add:

```python
    def start_input(self):
        """Start the hotkey backend; keep BOTH the FSM listener and the stop handle.

        pynput's ``HotkeyListener.start()`` returns the underlying pynput Listener,
        while ``LinuxHotkeySource.start()`` returns itself — both have ``.stop()``,
        but only the HotkeyListener has ``begin_capture``. So we hold the FSM
        listener explicitly for capture, separate from the started stop-handle.
        """
        from .input_backend import make_input_backend

        self._listener = self.make_listener()
        self._backend = make_input_backend(self._listener).start()
        return self._backend

    def stop_input(self) -> None:
        if self._backend is not None:
            try:
                self._backend.stop()
            except Exception:  # noqa: BLE001
                pass
            self._backend = None

    def rebind_hotkeys(self, *, key=None, cycle_language=None, mode=None, handsfree=None) -> None:
        """Apply new hotkey settings live: persist, then restart the listener."""
        previous = self._cfg.hotkey
        new_hotkey = with_hotkey(previous, key=key, cycle_language=cycle_language,
                                 mode=mode, handsfree=handsfree)
        self._cfg = dataclasses.replace(self._cfg, hotkey=new_hotkey)

        from .settings_store import update_user_settings
        update_user_settings(**hotkey_settings(key=key, cycle_language=cycle_language,
                                               mode=mode, handsfree=handsfree))

        try:
            self.stop_input()
            self.start_input()
        except Exception as exc:  # noqa: BLE001 - roll back so the user isn't stuck
            log.error("Rebind failed (%s); rolling back.", exc)
            self._cfg = dataclasses.replace(self._cfg, hotkey=previous)
            self.stop_input()
            self.start_input()
            raise
        log.info("Hotkeys rebound: key=%s cycle=%s mode=%s handsfree=%s",
                 new_hotkey.key, new_hotkey.cycle_language, new_hotkey.mode, new_hotkey.handsfree)
        if self.on_hotkey_change:
            self.on_hotkey_change()

    def reset_hotkeys(self) -> None:
        """Clear saved hotkey overrides and rebind to the bundled config.toml."""
        from .settings_store import load_user_settings, save_user_settings
        data = load_user_settings()
        for k in ("hotkey_key", "hotkey_cycle_language", "hotkey_mode", "hotkey_handsfree"):
            data.pop(k, None)
        save_user_settings(data)
        from .config import load_config
        defaults = load_config().hotkey
        self.rebind_hotkeys(key=defaults.key, cycle_language=defaults.cycle_language,
                            mode=defaults.mode, handsfree=defaults.handsfree)

    @property
    def hotkey(self):
        return self._cfg.hotkey

    def start_capture(self, on_done) -> bool:
        """Capture the next combo via the running FSM listener.

        Returns False if input isn't started. ``on_done`` fires on the listener
        thread with the canonical combo string.
        """
        if self._listener is None:
            return False
        self._listener.begin_capture(on_done)
        return True

    def cancel_capture(self) -> None:
        if self._listener is not None:
            self._listener.cancel_capture()
```

> Note: `make_input_backend()` already builds a fresh `HotkeyListener` from `self._cfg.hotkey` each call (see `make_listener`), so `start_input()` after a config change picks up the new combo automatically.

- [ ] **Step 4: Run to verify pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest tests/test_core_rebind.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spuk/core.py tests/test_core_rebind.py
git commit -m "feat(hotkey): core owns backend handle + rebind/reset/capture"
```

---

### Task 5: Route backend lifecycle + capture signals through core (`ui_bar.py`, `tray.py`)

**Files:**
- Modify: `src/spuk/ui_bar.py` (run_bar: use `core.start_input()`/`core.stop_input()`; add signals + wire observers)
- Modify: `src/spuk/tray.py` (same lifecycle change — read it first; it also starts the backend)

No new unit test (Qt/event-loop integration; covered by the manual checklist in Task 9). Keep existing tests green.

- [ ] **Step 1: Extend `CoreSignals` in `ui_bar.py`**

Add two signals to `class CoreSignals` (after `ready = Signal()`):

```python
    combo_captured = Signal(str)   # a Settings capture finished
    hotkey_changed = Signal()      # bindings changed -> refresh labels
```

- [ ] **Step 2: Wire the new observers + core-owned lifecycle in `run_bar`**

In `run_bar`, after the existing `core.on_transcript = signals.transcript.emit` line, add:

```python
    core.on_combo_captured = signals.combo_captured.emit
    core.on_hotkey_change = signals.hotkey_changed.emit
```

Replace `listener = core.make_input_backend().start()` with:

```python
    core.start_input()
```

In `quit_app`, replace the `listener.stop()` block with `core.stop_input()`:

```python
        try:
            core.stop_input()
        except Exception:  # noqa: BLE001
            pass
        app.quit()
        logging.shutdown()
        os._exit(0)
```

- [ ] **Step 3: Mirror the lifecycle change in `tray.py`**

Read `src/spuk/tray.py`. Wherever it does `core.make_input_backend().start()` and later `.stop()`, change to `core.start_input()` and `core.stop_input()` so the tray path also lets core own the handle (rebind works in `--tray` mode too).

- [ ] **Step 4: Verify imports + existing tests**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q` (all existing tests still pass)
Run: `uv run python -c "import spuk.ui_bar, spuk.core; print('ok')"`
Expected: PASS / `ok`.

- [ ] **Step 5: Commit**

```bash
git add src/spuk/ui_bar.py src/spuk/tray.py
git commit -m "refactor(hotkey): core owns the input backend; add capture/hotkey signals"
```

---

### Task 6: Hotkeys section in Settings (`ui_window.py`)

**Files:**
- Modify: `src/spuk/ui_window.py`

Replace the static shortcut label (lines ~106-109) with a live "Hotkeys" section: talk-key row + cycle-key row (each with a `[Change]` button that enters capture), a hold/toggle selector, a hands-free checkbox, and a "Reset hotkeys to default" button. Validation messages show inline. Capture results arrive via `signals.combo_captured`.

No unit test (Qt). Manual checklist in Task 9.

- [ ] **Step 1: Replace the static shortcut block**

Remove these lines in `_build_ui` (the informational shortcut label):

```python
        # Shortcut (informational).
        combo = "⌃ Ctrl    ⌥ Option" if _is_mac() else "Ctrl    Alt"
        key = QLabel(f"{combo}        Hold & speak")
        key.setObjectName("key")
        c.addWidget(key)
```

Replace with a Hotkeys section builder call:

```python
        # --- Hotkeys ---
        c.addWidget(_section("Hotkeys"))
        c.addWidget(self._build_hotkeys())
```

- [ ] **Step 2: Add the Hotkeys widget builder + handlers**

Add these imports at the top of `ui_window.py` (extend the existing PySide6 import block):

```python
from PySide6.QtWidgets import QCheckBox, QComboBox  # QComboBox already imported; add QCheckBox
from .hotkey_format import combo_to_label, validate_combo
```

Add methods to `SpukWindow`:

```python
    def _build_hotkeys(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        hk = self._core.hotkey
        self._talk_btn = self._combo_row(v, "Talk", hk.key, self._capture_talk)
        self._cycle_btn = self._combo_row(v, "Switch language", hk.cycle_language, self._capture_cycle)

        # Mode selector.
        self._mode = QComboBox()
        self._mode.setObjectName("mic")  # reuse styling
        self._mode.addItem("Hold to talk", "push_to_talk")
        self._mode.addItem("Press to toggle", "toggle")
        self._mode.setCurrentIndex(0 if hk.mode == "push_to_talk" else 1)
        self._mode.currentIndexChanged.connect(self._mode_changed)
        v.addWidget(self._mode)

        # Hands-free (push_to_talk only).
        self._handsfree = QCheckBox("Double-tap to record hands-free")
        self._handsfree.setChecked(hk.handsfree)
        self._handsfree.setEnabled(hk.mode == "push_to_talk")
        self._handsfree.stateChanged.connect(self._handsfree_changed)
        v.addWidget(self._handsfree)

        # Inline status / validation message.
        self._hk_msg = QLabel("")
        self._hk_msg.setObjectName("section")
        self._hk_msg.setWordWrap(True)
        v.addWidget(self._hk_msg)

        reset = QPushButton("Reset hotkeys to default")
        reset.setObjectName("update")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self._reset_hotkeys)
        v.addWidget(reset)
        return box

    def _combo_row(self, parent_layout, label: str, combo: str, on_change) -> QPushButton:
        row = QHBoxLayout()
        name = QLabel(label)
        name.setObjectName("priv")
        btn = QPushButton(combo_to_label(combo))
        btn.setObjectName("update")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(on_change)
        row.addWidget(name, 1)
        row.addWidget(btn)
        parent_layout.addLayout(row)
        return btn

    # --- capture flow ---
    def _capture_talk(self) -> None:
        self._start_capture(self._talk_btn, which="talk")

    def _capture_cycle(self) -> None:
        self._start_capture(self._cycle_btn, which="cycle")

    def _start_capture(self, btn, which: str) -> None:
        self._capturing_which = which
        btn.setText("⌨ Press your keys…")
        self._hk_msg.setText("")
        started = self._core.start_capture(self._core.on_combo_captured)
        if not started:
            btn.setText(combo_to_label(self._core.hotkey.key if which == "talk"
                                       else self._core.hotkey.cycle_language))
            self._hk_msg.setText("Hotkey backend not ready — try again in a moment.")

    def _on_combo_captured(self, combo: str) -> None:
        which = getattr(self, "_capturing_which", None)
        if which is None:
            return
        self._capturing_which = None
        hk = self._core.hotkey
        other = hk.cycle_language if which == "talk" else hk.key
        ok, msg = validate_combo(combo, mode=hk.mode, other_combo=other)
        if not ok:
            self._hk_msg.setText("⚠ " + msg)
            # restore the button label
            (self._talk_btn if which == "talk" else self._cycle_btn).setText(
                combo_to_label(hk.key if which == "talk" else hk.cycle_language))
            return
        if msg:
            self._hk_msg.setText(msg)  # non-blocking warning
        if which == "talk":
            self._core.rebind_hotkeys(key=combo)
        else:
            self._core.rebind_hotkeys(cycle_language=combo)
        self._refresh_hotkey_labels()

    def _mode_changed(self, _i: int) -> None:
        mode = self._mode.currentData()
        self._handsfree.setEnabled(mode == "push_to_talk")
        self._core.rebind_hotkeys(mode=mode)

    def _handsfree_changed(self, _state: int) -> None:
        self._core.rebind_hotkeys(handsfree=self._handsfree.isChecked())

    def _reset_hotkeys(self) -> None:
        self._core.reset_hotkeys()
        self._refresh_hotkey_labels()
        self._hk_msg.setText("Reset to defaults.")

    def _refresh_hotkey_labels(self) -> None:
        hk = self._core.hotkey
        self._talk_btn.setText(combo_to_label(hk.key))
        self._cycle_btn.setText(combo_to_label(hk.cycle_language))
        self._mode.setCurrentIndex(0 if hk.mode == "push_to_talk" else 1)
        self._handsfree.setChecked(hk.handsfree)
```

- [ ] **Step 3: Wire `combo_captured` in `_wire`**

In `SpukWindow._wire`, add:

```python
        signals.combo_captured.connect(self._on_combo_captured)
        signals.hotkey_changed.connect(self._refresh_hotkey_labels)
```

- [ ] **Step 4: Verify import + launch (manual)**

Run: `uv run python -c "import spuk.ui_window; print('ok')"`
Expected: `ok`. (Full UI behaviour verified in Task 9.)

- [ ] **Step 5: Commit**

```bash
git add src/spuk/ui_window.py
git commit -m "feat(hotkey): Hotkeys section in Settings with live capture + reset"
```

---

### Task 7: Refresh the pill's shortcut hint after rebind (`ui_bar.py`)

**Files:**
- Modify: `src/spuk/ui_bar.py`

The pill's `_hint` label (lines ~143-144) hardcodes `Ctrl+Alt`. Make it derive from `core.hotkey.key` and refresh on `hotkey_changed`.

- [ ] **Step 1: Build the hint from config**

Replace:

```python
        mod = "⌃⌥" if _is_mac() else "Ctrl+Alt"
        self._hint = QLabel(f"Hold {mod} to dictate · ⚙ for languages & settings")
```

with:

```python
        from .hotkey_format import combo_to_label
        self._hint = QLabel(self._hint_text())
```

Add a helper + a refresh slot to `SpukBar`:

```python
    def _hint_text(self) -> str:
        from .hotkey_format import combo_to_label
        verb = "Hold" if self._core.hotkey.mode == "push_to_talk" else "Press"
        return f"{verb} {combo_to_label(self._core.hotkey.key)} to dictate · ⚙ for settings"

    def _on_hotkey_changed(self) -> None:
        self._hint.setText(self._hint_text())
        self._dictate.setText("Hold to talk" if self._core.hotkey.mode == "push_to_talk" else "Tap to toggle")
```

- [ ] **Step 2: Connect the signal in `_wire_core`**

Add:

```python
        self._sig.hotkey_changed.connect(self._on_hotkey_changed)
```

- [ ] **Step 3: Verify import + tests**

Run: `uv run python -c "import spuk.ui_bar; print('ok')"` → `ok`
Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q` → all pass

- [ ] **Step 4: Commit**

```bash
git add src/spuk/ui_bar.py
git commit -m "feat(hotkey): pill hint reflects the current hotkey live"
```

---

### Task 8: Docs — README + config.toml note

**Files:**
- Modify: `README.md` (add a short "Change your hotkeys" note under How to use it)
- Modify: `config.toml` (note that the keys are now editable in Settings)

- [ ] **Step 1: README note**

Under "## 🎛️ How to use it", add a bullet after the "Switch language" bullet:

```markdown
- **Change your keys:** open **Settings** (⚙) → **Hotkeys**, click **Change** next to
  "Talk" or "Switch language", and **press the keys you want**. Pick hold-to-talk or
  press-to-toggle, and there's always a **Reset to default** if you want the originals
  back. Your choices are remembered. (You can still edit `config.toml` by hand.)
```

- [ ] **Step 2: config.toml comment**

Above the `[hotkey]` section, add:

```toml
# These can also be changed in the app: Settings (⚙) → Hotkeys → Change.
# Saved choices in settings.json override the values here.
```

- [ ] **Step 3: Commit**

```bash
git add README.md config.toml
git commit -m "docs: document changing hotkeys from Settings"
```

---

### Task 9: Full verification

- [ ] **Step 1: Full test suite + lint**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q`
Expected: all pass (52 existing + new from Tasks 1-4).
Run: `uv run --with ruff ruff check src/ tests/`
Expected: All checks passed!

- [ ] **Step 2: Manual smoke test (macOS dev box)**

Run: `UV_LINK_MODE=copy uv run python -m spuk`
- Open Settings (⚙) → Hotkeys.
- Click **Change** on Talk → press **Ctrl+Shift+Space** → label updates; the pill hint updates; dictation now triggers on the new combo.
- Try a bare letter → inline ⚠ warning, no change.
- Switch mode to **Press to toggle** → hands-free greys out; one press starts, next stops.
- **Reset hotkeys to default** → back to Ctrl+Alt.
- Quit and relaunch → the last-set combo persists (settings.json).

- [ ] **Step 3: Linux note**

The evdev capture path uses the same `_feed_*` chokepoint, so it is exercised by the same UI — but like the rest of the Linux backend it can only be confirmed on real Linux hardware (X11 + Wayland). Add it to the Linux hardware test checklist; do not claim it verified on macOS.

- [ ] **Step 4: Final commit (if anything pending) + push**

```bash
git status
git push -u origin feat/configurable-hotkeys
```

---

## Self-review notes

- **Spec coverage:** scope (talk/cycle/mode/handsfree) → Tasks 4/6; live capture → Tasks 3/6; guardrails + reset → Tasks 1/6; persistence overlay → Task 2; live rebind → Task 4; pill refresh → Task 7; testing → Tasks 1-4 + 9. All covered.
- **Type consistency:** `with_hotkey`/`hotkey_settings`/`rebind_hotkeys`/`reset_hotkeys`/`start_capture`/`cancel_capture`/`begin_capture`/`cancel_capture`/`keys_to_combo_string`/`combo_to_label`/`validate_combo` names are used identically across tasks.
- **Out of scope (unchanged):** `double_tap_seconds` UI, per-app profiles.
