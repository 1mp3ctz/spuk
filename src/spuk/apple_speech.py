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
        request: object | None = None,
    ) -> None:
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error
        self._recognizer = recognizer
        self._audio_engine = audio_engine
        self._request_in = request
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
            # requiresOnDeviceRecognition is a property of the REQUEST, not the
            # recognizer — it is set in start(). The recognizer only exposes the
            # read-only supportsOnDeviceRecognition.
            try:
                if not rec.supportsOnDeviceRecognition():
                    log.warning(
                        "On-device recognition unavailable for en-US — enable macOS "
                        "Dictation (System Settings → Keyboard) to install the model."
                    )
            except Exception:
                pass
            self._recognizer = rec
            self._audio_engine = AVAudioEngine.alloc().init()
            return True
        except Exception as exc:
            log.warning("Could not build Apple speech objects: %s", exc)
            return False

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

        # Build + configure the recognition request. requiresOnDeviceRecognition
        # lives on SFSpeechRecognitionRequest (NOT the recognizer) and keeps all
        # audio on-device. Injectable via the ``request`` constructor arg for tests.
        request = self._request_in
        if request is None:
            try:
                from Speech import SFSpeechAudioBufferRecognitionRequest
                request = SFSpeechAudioBufferRecognitionRequest.alloc().init()
            except Exception:
                request = None  # non-Darwin / no framework
        if request is not None:
            try:
                request.setShouldReportPartialResults_(True)
                request.setRequiresOnDeviceRecognition_(True)
            except Exception as exc:
                log.warning("Could not configure recognition request: %s", exc)

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
