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
