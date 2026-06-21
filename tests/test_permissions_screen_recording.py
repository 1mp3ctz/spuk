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
