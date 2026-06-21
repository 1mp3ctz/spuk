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
        # NB: a real SFSpeechRecognizer has NO setRequiresOnDeviceRecognition_ —
        # that property lives on the request. The fake mirrors that.
        def recognitionTaskWithRequest_resultHandler_(self, request, handler):
            calls["task_started"] = True
            handler_ref[0] = handler
            return FakeTask()

    return FakeRecognizer(), handler_ref, calls


def _make_fake_request():
    """Fake SFSpeechAudioBufferRecognitionRequest recording its configuration."""
    calls = {"partial_results": None, "on_device": None}

    class FakeRequest:
        def setShouldReportPartialResults_(self, v):
            calls["partial_results"] = v

        def setRequiresOnDeviceRecognition_(self, v):
            calls["on_device"] = v

        def appendAudioPCMBuffer_(self, buf):
            pass

    return FakeRequest(), calls


def test_on_device_flag_is_set_on_the_request_not_the_recognizer():
    """Regression: requiresOnDeviceRecognition is a property of the REQUEST
    (SFSpeechRecognitionRequest), not SFSpeechRecognizer. Setting it on the
    recognizer raised AttributeError and the engine never started."""
    fake_recognizer, _handler, _ = _make_fake_recognizer()
    fake_audio, _ = _make_fake_audio_engine()
    fake_request, req_calls = _make_fake_request()

    engine = AppleSpeechEngine(
        on_partial=lambda t: None,
        on_final=lambda t: None,
        on_error=lambda e: None,
        recognizer=fake_recognizer,
        audio_engine=fake_audio,
        request=fake_request,
    )
    assert engine.start() is True
    assert req_calls["partial_results"] is True
    assert req_calls["on_device"] is True


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
