"""Smoke-test the wiring layer without real Qt or OS frameworks."""


def test_live_inserter_update_calls_type_fn():
    """LiveInserter correctly delegates type/backspace (wiring sanity)."""
    from spuk.live_insert import LiveInserter

    typed = []
    backed = []
    ins = LiveInserter(type_fn=typed.append, backspace_fn=backed.append)
    ins.update("hello")
    ins.update("hello world")
    assert typed == ["hello", " world"]  # only the new suffix is typed
    assert backed == []                  # "hello" is a common prefix — nothing erased


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
