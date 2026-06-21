# Apple On-Device Speech (Hybrid Engine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Apple's on-device Speech engine as a new transcriber behind the existing `build_transcriber` factory, with per-language routing — en/de (and any locale Apple supports on-device) go to Apple's Neural-Engine recognizer; Polish and anything Apple can't do offline fall back to faster-whisper. macOS only; Windows/Linux behaviour is untouched.

**Architecture:** Spuk's core loop is already engine-agnostic — `core._on_stop()` hands a float32 numpy buffer to `Transcriber.transcribe(audio, samplerate, language)` and pastes the result. We add an `AppleSpeechTranscriber` that writes the buffer to a temp WAV and feeds it to `SFSpeechRecognizer` (file-based `SFSpeechURLRecognitionRequest`, `requiresOnDeviceRecognition = True`), plus a `HybridTranscriber` that routes by language using Apple's *own* `supportsOnDeviceRecognition` flag and falls back to Whisper on any miss/empty/error. The real Speech call sits behind an injectable seam so all routing/fallback logic is unit-tested with fakes; the on-device call itself is verified by an opt-in integration test. The hotkey, audio, paste, language, and UI layers do not change.

**Tech Stack:** Python 3.11 (`>=3.11,<3.13`), pyobjc-framework-Speech (macOS only), faster-whisper (unchanged fallback), numpy, stdlib `wave`, pytest (via `uv run --with pytest`), ruff.

## Global Constraints

- **Local & free, no network.** Apple on-device recognition only (`requiresOnDeviceRecognition = True`). Never use Apple's server path. This is non-negotiable — it is Spuk's entire identity. Verbatim from `config.toml`: "Everything here is local and free."
- **macOS only.** All new framework imports are lazy and guarded by `platform.system() == "Darwin"`. Importing `spuk.apple_speech` on Windows/Linux must not import any pyobjc framework, and `build_transcriber` with `engine="apple"` on non-macOS must silently degrade to faster-whisper.
- **Python floor:** `requires-python = ">=3.11,<3.13"`. Do not raise it.
- **Immutable config:** `TranscribeConfig` is a frozen dataclass — never mutate; build a new one.
- **Thermal rule:** the fallback Whisper model must stay **lazily loaded** — never warm/load it just because the hybrid engine is selected. It loads only when a fallback locale (e.g. pl) is actually used. (Target hardware is a fanless M3 Air; avoiding the Whisper CPU load is half the point of this feature.)
- **Test command:** `UV_LINK_MODE=copy uv run --with pytest pytest -q`
- **Lint command:** `uv run --with ruff ruff check src/ tests/`
- **Commit after every task.** Conventional commits (`feat:`, `test:`, `chore:`).

**Branch:** `feat/apple-speech-engine`, created from the scrubbed `origin/main` (do NOT branch from a stale local clone — see repo history notes; GitHub-noreply commits only).

---

### Task 1: Declare the macOS Speech dependency + an availability probe

**Files:**
- Modify: `pyproject.toml` (dependencies table)
- Create: `src/spuk/apple_speech.py`
- Test: `tests/test_apple_speech_available.py`

**Interfaces:**
- Produces: `apple_speech.available() -> bool` — True only on macOS with the Speech framework importable. Used by `build_transcriber` (Task 6) to decide whether to route to Apple at all.

- [ ] **Step 1: Add the dependency** (macOS-gated, mirroring the existing `evdev; sys_platform == 'linux'` marker)

In `pyproject.toml`, inside `dependencies`, add after the `evdev` line:

```toml
    # macOS only: Apple's on-device Speech engine (SFSpeechRecognizer). The marker
    # keeps it off Windows/Linux, where it cannot install. pyobjc-core/Cocoa come
    # in transitively; pin the framework wrapper. Import name is 'Speech'.
    "pyobjc-framework-Speech>=10,<12; sys_platform == 'darwin'",
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_apple_speech_available.py
import platform

from spuk import apple_speech


def test_available_is_bool():
    assert isinstance(apple_speech.available(), bool)


def test_available_false_off_macos(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert apple_speech.available() is False
```

- [ ] **Step 3: Run it to verify it fails**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_available.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'spuk.apple_speech'`.

- [ ] **Step 4: Write the minimal module**

```python
# src/spuk/apple_speech.py
"""Apple on-device Speech engine (macOS only).

Writes Spuk's captured audio to a temp WAV and recognises it with
``SFSpeechRecognizer`` using ``requiresOnDeviceRecognition = True`` — the same
on-device engine behind macOS Dictation, running on the Neural Engine. No audio
leaves the machine. All framework imports are lazy and macOS-guarded so importing
this module on Windows/Linux is safe.
"""

from __future__ import annotations

import logging
import platform

log = logging.getLogger("spuk.apple_speech")


def available() -> bool:
    """True only on macOS with the Speech framework importable."""
    if platform.system() != "Darwin":
        return False
    try:
        import Speech  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - framework missing / load failure
        log.debug("Apple Speech unavailable: %s", exc)
        return False
    return True
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_available.py`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/spuk/apple_speech.py tests/test_apple_speech_available.py
git commit -m "feat(apple): add macOS Speech dependency + availability probe"
```

---

### Task 2: WAV writer for the captured buffer (pure, TDD)

**Files:**
- Modify: `src/spuk/apple_speech.py`
- Test: `tests/test_apple_speech_wav.py`

**Interfaces:**
- Produces: `apple_speech.write_wav(audio: np.ndarray, samplerate: int, path: str) -> None` — writes mono 16-bit PCM WAV from float32 [-1, 1]. Consumed by `AppleSpeechTranscriber.transcribe` (Task 3).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_apple_speech_wav.py
import wave

import numpy as np

from spuk.apple_speech import write_wav


def test_write_wav_roundtrips_rate_and_frames(tmp_path):
    audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    out = tmp_path / "x.wav"
    write_wav(audio, 16000, str(out))
    with wave.open(str(out), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2          # 16-bit
        assert w.getnframes() == 5


def test_write_wav_clips_out_of_range(tmp_path):
    audio = np.array([2.0, -2.0], dtype=np.float32)  # must clamp, not wrap
    out = tmp_path / "c.wav"
    write_wav(audio, 16000, str(out))
    with wave.open(str(out), "rb") as w:
        frames = np.frombuffer(w.readframes(2), dtype=np.int16)
    assert frames[0] == 32767 and frames[1] == -32768


def test_write_wav_handles_empty(tmp_path):
    out = tmp_path / "e.wav"
    write_wav(np.zeros(0, dtype=np.float32), 16000, str(out))
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_wav.py`
Expected: FAIL with `ImportError: cannot import name 'write_wav'`.

- [ ] **Step 3: Implement `write_wav`**

Add to `src/spuk/apple_speech.py`:

```python
import wave

import numpy as np


def write_wav(audio: np.ndarray, samplerate: int, path: str) -> None:
    """Write mono 16-bit PCM WAV from float32 [-1, 1] (clamped)."""
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm.tobytes())
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_wav.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/apple_speech.py tests/test_apple_speech_wav.py
git commit -m "feat(apple): add 16-bit PCM WAV writer for captured audio"
```

---

### Task 3: Locale mapping + `AppleSpeechTranscriber` over an injectable seam (TDD)

**Files:**
- Modify: `src/spuk/apple_speech.py`
- Test: `tests/test_apple_speech_transcriber.py`

**Interfaces:**
- Produces:
  - `apple_speech.whisper_to_locale(lang: str) -> str` — `"en" -> "en-US"`, `"de" -> "de-DE"`, `"pl" -> "pl-PL"`, otherwise `f"{lang}"`.
  - `class AppleSpeechTranscriber` with `__init__(self, recognize_file: Callable[[str, str], str] | None = None)`, `transcribe(self, audio, samplerate, language) -> str`, `warm(self, samplerate, language) -> None`. Implements the `Transcriber` protocol from `transcriber.py`.
- Consumes: `write_wav` (Task 2). The `recognize_file(wav_path, locale) -> str` seam defaults to the real `_sfspeech_recognize_file` (Task 4) but is injected as a fake in tests.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_apple_speech_transcriber.py
import numpy as np

from spuk.apple_speech import AppleSpeechTranscriber, whisper_to_locale


def test_whisper_to_locale_known_codes():
    assert whisper_to_locale("en") == "en-US"
    assert whisper_to_locale("de") == "de-DE"
    assert whisper_to_locale("pl") == "pl-PL"


def test_transcribe_passes_wav_and_locale_to_seam(tmp_path):
    seen = {}

    def fake_recognize(path, locale):
        seen["path"] = path
        seen["locale"] = locale
        return "hello world"

    t = AppleSpeechTranscriber(recognize_file=fake_recognize)
    out = t.transcribe(np.array([0.1, -0.1], dtype=np.float32), 16000, "en")
    assert out == "hello world"
    assert seen["locale"] == "en-US"
    assert seen["path"].endswith(".wav")


def test_transcribe_returns_empty_string_on_seam_error():
    def boom(path, locale):
        raise RuntimeError("recognizer exploded")

    t = AppleSpeechTranscriber(recognize_file=boom)
    # Must NOT raise — empty string signals the hybrid layer to fall back.
    assert t.transcribe(np.zeros(4, dtype=np.float32), 16000, "en") == ""
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_transcriber.py`
Expected: FAIL with `ImportError: cannot import name 'AppleSpeechTranscriber'`.

- [ ] **Step 3: Implement the mapping + transcriber**

Add to `src/spuk/apple_speech.py`:

```python
import os
import tempfile
from typing import Callable

_LOCALE_MAP = {"en": "en-US", "de": "de-DE", "pl": "pl-PL"}


def whisper_to_locale(lang: str) -> str:
    """Map a Whisper language code to a BCP-47 locale for SFSpeechRecognizer."""
    return _LOCALE_MAP.get(lang, lang)


class AppleSpeechTranscriber:
    """On-device Apple Speech engine. Implements the Transcriber protocol.

    The real recognition call is injected so the file/locale plumbing is unit
    tested with a fake; production passes the real ``_sfspeech_recognize_file``.
    Returns "" on any failure so the hybrid layer can fall back to Whisper.
    """

    def __init__(self, recognize_file: Callable[[str, str], str] | None = None) -> None:
        self._recognize = recognize_file or _sfspeech_recognize_file

    def transcribe(self, audio: "np.ndarray", samplerate: int, language: str) -> str:
        locale = whisper_to_locale(language)
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="spuk-")
        os.close(fd)
        try:
            write_wav(audio, samplerate, path)
            return (self._recognize(path, locale) or "").strip()
        except Exception as exc:  # noqa: BLE001 - never crash the dictation loop
            log.warning("Apple Speech recognition failed: %s", exc)
            return ""
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def warm(self, samplerate: int, language: str) -> None:
        """Pre-create the recognizer cheaply. Deliberately does NOT touch Whisper."""
        try:
            _prewarm_recognizer(whisper_to_locale(language))
        except Exception as exc:  # noqa: BLE001
            log.debug("Apple Speech warm skipped: %s", exc)
```

Add temporary stubs so the module imports (the real bodies land in Task 4):

```python
def _sfspeech_recognize_file(path: str, locale: str) -> str:  # noqa: D401
    raise NotImplementedError  # replaced in Task 4


def _prewarm_recognizer(locale: str) -> None:
    return None  # replaced in Task 4
```

Add `import numpy as np` is already present from Task 2; the `"np.ndarray"` annotation is a string so no runtime import is forced.

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_transcriber.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/apple_speech.py tests/test_apple_speech_transcriber.py
git commit -m "feat(apple): AppleSpeechTranscriber over an injectable recognize seam"
```

---

### Task 4: The real `SFSpeechRecognizer` call + on-device routing probe (macOS integration)

**Files:**
- Modify: `src/spuk/apple_speech.py`
- Test: `tests/test_apple_speech_ondevice.py` (opt-in integration; skipped by default)

**Interfaces:**
- Produces:
  - `apple_speech.supports_on_device(lang: str) -> bool` — asks Apple whether the mapped locale recognises on-device. Drives Task 6's routing.
  - real `_sfspeech_recognize_file(path, locale) -> str` and `_prewarm_recognizer(locale)`.

This task wraps Apple APIs that can't run on CI's non-macOS runners, so its automated test is **opt-in** (gated on `SPUK_SPEECH_INTEGRATION=1` and a recorded fixture). The routing/fallback logic that depends on it is fully unit-tested in Task 6 with fakes.

- [ ] **Step 1: Replace the stubs with the real implementation**

In `src/spuk/apple_speech.py`, replace the Task 3 stubs:

```python
import threading

# SFSpeechRecognizerAuthorizationStatus: 0 notDetermined, 1 denied, 2 restricted,
# 3 authorized. Recognition only works at 3.
_AUTH_AUTHORIZED = 3


def _recognizer_for(locale: str):
    """Build an SFSpeechRecognizer for ``locale`` (or None if unsupported)."""
    from Foundation import NSLocale
    from Speech import SFSpeechRecognizer

    rec = SFSpeechRecognizer.alloc().initWithLocale_(NSLocale.localeWithLocaleIdentifier_(locale))
    return rec  # None when the locale isn't supported at all


def supports_on_device(lang: str) -> bool:
    """Whether Apple can recognise this locale fully on-device (no network)."""
    if not available():
        return False
    try:
        rec = _recognizer_for(whisper_to_locale(lang))
        return bool(rec and rec.supportsOnDeviceRecognition())
    except Exception as exc:  # noqa: BLE001
        log.debug("supports_on_device(%s) check failed: %s", lang, exc)
        return False


def _prewarm_recognizer(locale: str) -> None:
    """Construct the recognizer once so the first real utterance isn't cold."""
    _recognizer_for(locale)


def _sfspeech_recognize_file(path: str, locale: str) -> str:
    """Recognise a WAV file fully on-device via SFSpeechRecognizer (blocking).

    Uses a file-based request (no AVAudioPCMBuffer marshaling) and blocks the
    caller until the final result, signalled through a threading.Event from
    Speech's own completion queue. Raises on auth-missing or recognizer error so
    the transcriber's try/except converts it to "" and the hybrid falls back.
    """
    from Foundation import NSURL
    from Speech import SFSpeechRecognizer, SFSpeechURLRecognitionRequest

    if SFSpeechRecognizer.authorizationStatus() != _AUTH_AUTHORIZED:
        raise PermissionError("Speech Recognition not authorized")

    rec = _recognizer_for(locale)
    if rec is None or not rec.isAvailable():
        raise RuntimeError(f"recognizer unavailable for {locale}")

    request = SFSpeechURLRecognitionRequest.alloc().initWithURL_(
        NSURL.fileURLWithPath_(path)
    )
    request.setRequiresOnDeviceRecognition_(True)  # LOCAL ONLY — never the server

    done = threading.Event()
    box: dict[str, object] = {"text": "", "error": None}

    def handler(result, error) -> None:
        if error is not None:
            box["error"] = error
            done.set()
            return
        if result is not None:
            box["text"] = result.bestTranscription().formattedString()
            if result.isFinal():
                done.set()

    rec.recognitionTaskWithRequest_resultHandler_(request, handler)
    if not done.wait(timeout=15.0):
        raise TimeoutError("Apple Speech recognition timed out")
    if box["error"] is not None:
        raise RuntimeError(str(box["error"]))
    return str(box["text"])
```

- [ ] **Step 2: Write the opt-in integration test**

```python
# tests/test_apple_speech_ondevice.py
import os
import wave

import numpy as np
import pytest

from spuk import apple_speech

pytestmark = pytest.mark.skipif(
    os.environ.get("SPUK_SPEECH_INTEGRATION") != "1" or not apple_speech.available(),
    reason="on-device Apple Speech integration test (set SPUK_SPEECH_INTEGRATION=1 on macOS)",
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "hello_en.wav")


def _load_wav_float32(path):
    with wave.open(path, "rb") as w:
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return (frames.astype(np.float32) / 32768.0), w.getframerate()


def test_supports_on_device_english():
    assert apple_speech.supports_on_device("en") is True


def test_recognizes_known_phrase():
    audio, rate = _load_wav_float32(FIXTURE)
    out = apple_speech.AppleSpeechTranscriber().transcribe(audio, rate, "en")
    assert "hello" in out.lower()
```

- [ ] **Step 3: Record the fixture (one-time, manual, on macOS)**

Record yourself saying "hello world" with Spuk's mic path and save it as a 16 kHz mono WAV at `tests/fixtures/hello_en.wav`. Quick capture:

```bash
mkdir -p tests/fixtures
UV_LINK_MODE=copy uv run python -c "import sounddevice as sd, numpy as np, wave; \
r=sd.rec(int(2.5*16000),samplerate=16000,channels=1,dtype='float32'); print('say: hello world'); sd.wait(); \
p=(np.clip(r[:,0],-1,1)*32767).astype('int16'); \
w=wave.open('tests/fixtures/hello_en.wav','wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(p.tobytes()); w.close()"
```

- [ ] **Step 4: Run the integration test on-device**

Run: `SPUK_SPEECH_INTEGRATION=1 UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_ondevice.py`
Expected: PASS (grant the Speech Recognition prompt on first run; see Task 5). The default suite run (without the env var) SKIPS this file — confirm with `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_apple_speech_ondevice.py` → 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/spuk/apple_speech.py tests/test_apple_speech_ondevice.py tests/fixtures/hello_en.wav
git commit -m "feat(apple): real on-device SFSpeechRecognizer call + on-device routing probe"
```

---

### Task 5: Speech Recognition permission helper + UI (TDD with mocked Speech)

**Files:**
- Modify: `src/spuk/permissions.py`
- Test: `tests/test_permissions_speech.py`
- Modify: `src/spuk/ui_permissions.py` (add a Speech Recognition row) — mirror the existing Input Monitoring / Accessibility rows
- Test: extend `tests/test_permissions_ui.py` (or add `tests/test_permissions_ui_speech.py`)

**Interfaces:**
- Produces:
  - `permissions.speech_recognition_trusted() -> bool | None` (True authorized, False denied/restricted, None unknown/unavailable, True off-macOS).
  - `permissions.request_speech_recognition() -> None` (raises the system prompt; grant applies after relaunch).
  - New `PRIVACY_PANES["speech_recognition"]` deep link.

- [ ] **Step 1: Write the failing test** (inject a fake `Speech` module, mirroring `tests/test_permissions_macos.py`)

```python
# tests/test_permissions_speech.py
import sys
import types

import spuk.permissions as perms


def _install_fake_speech(monkeypatch, status):
    mod = types.ModuleType("Speech")

    class SFSpeechRecognizer:
        @staticmethod
        def authorizationStatus():
            return status

    mod.SFSpeechRecognizer = SFSpeechRecognizer
    monkeypatch.setitem(sys.modules, "Speech", mod)


def test_speech_trusted_true_when_authorized(monkeypatch):
    monkeypatch.setattr(perms.platform, "system", lambda: "Darwin")
    _install_fake_speech(monkeypatch, 3)  # authorized
    assert perms.speech_recognition_trusted() is True


def test_speech_trusted_false_when_denied(monkeypatch):
    monkeypatch.setattr(perms.platform, "system", lambda: "Darwin")
    _install_fake_speech(monkeypatch, 1)  # denied
    assert perms.speech_recognition_trusted() is False


def test_speech_trusted_true_off_macos(monkeypatch):
    monkeypatch.setattr(perms.platform, "system", lambda: "Linux")
    assert perms.speech_recognition_trusted() is True


def test_speech_pane_registered():
    assert "speech_recognition" in perms.PRIVACY_PANES
```

- [ ] **Step 2: Run it to verify it fails**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_permissions_speech.py`
Expected: FAIL with `AttributeError: module 'spuk.permissions' has no attribute 'speech_recognition_trusted'`.

- [ ] **Step 3: Implement the helper**

In `src/spuk/permissions.py`, add the pane to `PRIVACY_PANES`:

```python
    "speech_recognition": "x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition",
```

Add the functions (place near `accessibility_trusted`):

```python
_SPEECH_AUTHORIZED = 3  # SFSpeechRecognizerAuthorizationStatus.authorized


def speech_recognition_trusted() -> bool | None:
    """Whether this process may use Speech Recognition. None when unknown."""
    if platform.system() != "Darwin":
        return True
    try:
        from Speech import SFSpeechRecognizer

        return SFSpeechRecognizer.authorizationStatus() == _SPEECH_AUTHORIZED
    except Exception as exc:  # noqa: BLE001 - framework missing / not built in
        log.debug("Could not check Speech Recognition trust: %s", exc)
        return None


def request_speech_recognition() -> None:
    """Raise the macOS Speech Recognition prompt. Grant applies after relaunch."""
    if platform.system() != "Darwin":
        return
    try:
        from Speech import SFSpeechRecognizer

        SFSpeechRecognizer.requestAuthorization_(lambda _status: None)
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not request Speech Recognition: %s", exc)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_permissions_speech.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Add the UI row + request on first use**

In `src/spuk/ui_permissions.py`, add a "Speech Recognition" row (label: "Speech Recognition — so dictation can use Apple's on-device engine"), wired to `open_privacy_pane("speech_recognition")`, shown only when `speech_recognition_trusted() is False`. Follow the exact construction of the Input Monitoring row already there. Extend the UI test to assert the row appears when the status is False and is hidden when True. Run:

`UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_permissions_ui.py tests/test_permissions_speech.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/spuk/permissions.py src/spuk/ui_permissions.py tests/test_permissions_speech.py tests/test_permissions_ui.py
git commit -m "feat(perms): add Speech Recognition trust check, prompt, pane, and UI row"
```

---

### Task 6: `HybridTranscriber` + `build_transcriber` routing (pure, TDD)

**Files:**
- Modify: `src/spuk/transcriber.py`
- Test: `tests/test_hybrid_transcriber.py`

**Interfaces:**
- Consumes: `apple_speech.available`, `apple_speech.AppleSpeechTranscriber`, `apple_speech.supports_on_device` (Tasks 1, 3, 4); `FasterWhisperTranscriber` (existing).
- Produces:
  - `class HybridTranscriber` with `__init__(self, primary, fallback, supports: Callable[[str], bool])`, `transcribe(...) -> str`, `warm(...) -> None`.
  - Updated `build_transcriber(cfg)` handling `cfg.engine == "apple"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hybrid_transcriber.py
import numpy as np

from spuk.transcriber import HybridTranscriber


class _Stub:
    def __init__(self, text, *, boom=False):
        self.text = text
        self.boom = boom
        self.calls = 0

    def transcribe(self, audio, samplerate, language):
        self.calls += 1
        if self.boom:
            raise RuntimeError("engine error")
        return self.text


AUDIO = np.zeros(4, dtype=np.float32)


def test_routes_supported_language_to_primary():
    primary, fallback = _Stub("apple"), _Stub("whisper")
    h = HybridTranscriber(primary, fallback, supports=lambda l: l in {"en", "de"})
    assert h.transcribe(AUDIO, 16000, "en") == "apple"
    assert fallback.calls == 0


def test_routes_unsupported_language_to_fallback():
    primary, fallback = _Stub("apple"), _Stub("whisper")
    h = HybridTranscriber(primary, fallback, supports=lambda l: l in {"en", "de"})
    assert h.transcribe(AUDIO, 16000, "pl") == "whisper"
    assert primary.calls == 0


def test_falls_back_when_primary_returns_empty():
    primary, fallback = _Stub(""), _Stub("whisper")
    h = HybridTranscriber(primary, fallback, supports=lambda l: True)
    assert h.transcribe(AUDIO, 16000, "en") == "whisper"


def test_falls_back_when_primary_raises():
    primary, fallback = _Stub("apple", boom=True), _Stub("whisper")
    h = HybridTranscriber(primary, fallback, supports=lambda l: True)
    assert h.transcribe(AUDIO, 16000, "en") == "whisper"


def test_warm_does_not_touch_fallback():
    # Thermal rule: warming must NOT load Whisper. The fallback's warm (if any)
    # must not be called by HybridTranscriber.warm.
    warmed = {"primary": False, "fallback": False}

    class P(_Stub):
        def warm(self, samplerate, language):
            warmed["primary"] = True

    class F(_Stub):
        def warm(self, samplerate, language):
            warmed["fallback"] = True

    h = HybridTranscriber(P("a"), F("w"), supports=lambda l: True)
    h.warm(16000, "en")
    assert warmed["primary"] is True
    assert warmed["fallback"] is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_hybrid_transcriber.py`
Expected: FAIL with `ImportError: cannot import name 'HybridTranscriber'`.

- [ ] **Step 3: Implement the hybrid + factory**

In `src/spuk/transcriber.py`, add the class and update the factory:

```python
from typing import Callable


class HybridTranscriber:
    """Route each utterance to ``primary`` when ``supports(language)`` is true,
    else to ``fallback``. Falls back on empty result or any primary error so a
    bad recognition never drops the user's words."""

    def __init__(self, primary, fallback, supports: Callable[[str], bool]) -> None:
        self._primary = primary
        self._fallback = fallback
        self._supports = supports

    def transcribe(self, audio, samplerate: int, language: str) -> str:
        if self._supports(language):
            try:
                text = self._primary.transcribe(audio, samplerate, language)
                if text:
                    return text
                log.info("Primary engine empty for %s — falling back.", language)
            except Exception as exc:  # noqa: BLE001
                log.warning("Primary engine failed (%s) — falling back.", exc)
        return self._fallback.transcribe(audio, samplerate, language)

    def warm(self, samplerate: int, language: str) -> None:
        # Warm ONLY the primary. The fallback (Whisper) stays lazily unloaded so
        # selecting the hybrid engine costs no Whisper model load / heat.
        warm = getattr(self._primary, "warm", None)
        if callable(warm):
            warm(samplerate, language)
```

Replace `build_transcriber`:

```python
def build_transcriber(cfg: TranscribeConfig) -> Transcriber:
    """Factory: pick an engine implementation from config.

    'apple' = Apple on-device Speech for locales it supports on-device, with
    faster-whisper as the fallback for everything else. On non-macOS (or when the
    Speech framework is unavailable) 'apple' degrades to faster-whisper so a
    shared config.toml is safe everywhere.
    """
    whisper = FasterWhisperTranscriber(cfg)  # lazy: loads only when actually used
    if cfg.engine == "faster-whisper":
        return whisper
    if cfg.engine == "apple":
        from . import apple_speech

        if not apple_speech.available():
            log.warning("engine 'apple' selected but Apple Speech is unavailable here "
                        "— using faster-whisper.")
            return whisper
        return HybridTranscriber(
            apple_speech.AppleSpeechTranscriber(),
            whisper,
            apple_speech.supports_on_device,
        )
    raise NotImplementedError(
        f"engine {cfg.engine!r} not implemented. Supported: 'apple', 'faster-whisper'."
    )
```

- [ ] **Step 4: Run them to verify they pass**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_hybrid_transcriber.py`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spuk/transcriber.py tests/test_hybrid_transcriber.py
git commit -m "feat(engine): HybridTranscriber + 'apple' engine routing with Whisper fallback"
```

---

### Task 7: Request Speech permission at startup + make `apple` the macOS default

**Files:**
- Modify: `config.toml`
- Modify: `src/spuk/__main__.py`
- Test: `tests/test_config_engine.py`

**Interfaces:**
- Consumes: `permissions.speech_recognition_trusted`, `permissions.request_speech_recognition` (Task 5); `load_config` (existing).

- [ ] **Step 1: Write the failing test** (engine value loads through config)

```python
# tests/test_config_engine.py
import tomllib
from pathlib import Path

from spuk.config import load_config


def test_engine_value_loads(tmp_path):
    # The bundled config selects the apple engine; loader must surface it verbatim.
    cfg = load_config(Path("config.toml"))
    assert cfg.transcribe.engine in {"apple", "faster-whisper"}


def test_bundled_config_default_is_apple():
    raw = tomllib.loads(Path("config.toml").read_text())
    assert raw["transcribe"]["engine"] == "apple"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q tests/test_config_engine.py`
Expected: FAIL on `test_bundled_config_default_is_apple` (engine is still `faster-whisper`).

- [ ] **Step 3: Flip the default + document it**

In `config.toml`, change the engine line and its comment:

```toml
engine           = "apple"           # apple = macOS on-device Speech (Neural Engine; en/de) with
                                     # faster-whisper fallback (pl + non-macOS). Set "faster-whisper"
                                     # to force Whisper everywhere.
```

- [ ] **Step 4: Request the Speech prompt at startup (macOS, only when missing)**

In `src/spuk/__main__.py`, after `ensure_permissions(prompt=True)` and after `config = load_config()`, add:

```python
    # If the on-device Apple engine is selected, make sure Speech Recognition is
    # granted — silent when already trusted, raises the system prompt once when
    # missing (the grant applies after the next relaunch, like the other perms).
    if config.transcribe.engine == "apple":
        from .permissions import request_speech_recognition, speech_recognition_trusted

        if speech_recognition_trusted() is False:
            request_speech_recognition()
```

- [ ] **Step 5: Run the full suite + lint**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q`
Expected: PASS (all green; the on-device integration file shows as skipped).
Run: `uv run --with ruff ruff check src/ tests/`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add config.toml src/spuk/__main__.py tests/test_config_engine.py
git commit -m "feat(engine): default macOS to the apple on-device engine + request Speech at startup"
```

---

### Task 8: Packaging — bundle Speech, add Info.plist usage string, verify a built app

**Files:**
- Modify: the PyInstaller spec / build config under `packaging/` (the `.spec` or build script that defines hidden imports and the macOS `Info.plist`)
- Modify: `docs/RELEASE.md` (note the new permission + dependency)

**Interfaces:** none (build-time only).

- [ ] **Step 1: Add the Info.plist usage string**

In the macOS app's `Info.plist` block (in the PyInstaller `.spec` `info_plist`/`BUNDLE` section under `packaging/`), add:

```xml
<key>NSSpeechRecognitionUsageDescription</key>
<string>Spuk uses on-device speech recognition to turn your dictation into text. No audio leaves your Mac.</string>
```

- [ ] **Step 2: Ensure the Speech framework is bundled**

In the same `.spec`, add `Speech` and `Foundation` to `hiddenimports` (pyobjc framework wrappers are imported lazily, so PyInstaller won't see them statically):

```python
hiddenimports += ["Speech", "Foundation"]
```

- [ ] **Step 3: Build and smoke-test the app**

Build with the project's existing macOS build path (see `docs/RELEASE.md` / `packaging/`). Then:
- Launch the built `Spuk.app`.
- Confirm the Speech Recognition prompt appears on first run; grant it; relaunch.
- Dictate an English phrase → it pastes (served by Apple on-device).
- Switch the active language to Polish in the tray and dictate → it still pastes (Whisper fallback loads on first Polish use).

Record the result in `docs/RELEASE.md` under a new "Apple on-device engine" note (dependency added, new permission, fallback behaviour).

- [ ] **Step 4: Commit**

```bash
git add packaging docs/RELEASE.md
git commit -m "chore(packaging): bundle Speech framework + Info.plist usage string for on-device engine"
```

---

### Task 9: Docs — README + ARCHITECTURE reflect the hybrid engine

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:** none.

- [ ] **Step 1: Update the engine description**

In `README.md`, update the "Powered by on-device Whisper" framing to: macOS uses Apple's on-device Speech engine (Neural Engine) for supported languages with on-device Whisper as the fallback and as the engine on Windows/Linux — still no cloud, still free. In `docs/ARCHITECTURE.md`, document the `Transcriber` protocol, `HybridTranscriber` routing (via `supports_on_device`), the lazy-Whisper thermal rule, and the file-based `SFSpeechRecognizer` path.

- [ ] **Step 2: Verify the suite once more + commit**

Run: `UV_LINK_MODE=copy uv run --with pytest pytest -q`
Expected: PASS.

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs: describe the macOS on-device Apple Speech engine + Whisper fallback"
```

---

## Self-Review

**Spec coverage:**
- "Use the Mac's native dictation engine, fast & reliable" → Tasks 3–4 (file-based on-device `SFSpeechRecognizer`), Task 7 (default-on).
- "Hybrid: Apple en/de, Whisper for pl/unsupported; Windows/Linux Whisper as today" → Task 6 (routing via Apple's own `supportsOnDeviceRecognition`), Task 6 factory degrade off-macOS, Global Constraints.
- "Local & free, no cloud" → `requiresOnDeviceRecognition = True` (Task 4), Global Constraints, telemetry already disabled in `__main__`.
- "Keep Spuk's hotkey/paste/languages/UI" → core/hotkey/paste/audio untouched; only `transcriber.py` + `build_transcriber` + a startup permission line change.
- "Thermal: don't load Whisper unnecessarily" → Task 6 lazy fallback + `warm()` warms only Apple; Task 6 test `test_warm_does_not_touch_fallback`.
- New permission → Task 5 (+ UI), Task 7 (startup request), Task 8 (Info.plist).

**Placeholder scan:** none — every code step is concrete. The one non-CI path (real Apple call, Task 4) is an explicit, env-gated integration test with a recorded fixture and a manual build check (Task 8), not a TODO.

**Type consistency:** `transcribe(audio, samplerate, language) -> str` matches the `Transcriber` protocol throughout; `supports_on_device(lang) -> bool` is the same callable passed as `HybridTranscriber(..., supports=...)`; `recognize_file(path, locale) -> str` is consistent between Task 3 (seam) and Task 4 (real `_sfspeech_recognize_file`); `speech_recognition_trusted` / `request_speech_recognition` names match across Tasks 5 and 7.
