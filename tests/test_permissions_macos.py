"""Tests for the macOS permissions helpers (pure logic; no real pyobjc / TCC)."""

from __future__ import annotations

import pathlib
import subprocess

import spuk.permissions as permissions
import spuk.updates as updates

ALL_OK = {"input_monitoring": True, "accessibility": True}


# --- should_show_permissions ----------------------------------------------


def test_hidden_when_all_granted():
    assert (
        permissions.should_show_permissions(
            statuses=ALL_OK, dismissed_version=None, current_version="1.0.6"
        )
        is False
    )


def test_show_when_a_permission_is_missing():
    statuses = {**ALL_OK, "input_monitoring": False}
    assert (
        permissions.should_show_permissions(
            statuses=statuses, dismissed_version=None, current_version="1.0.6"
        )
        is True
    )


def test_unknown_status_is_not_treated_as_missing():
    statuses = {"input_monitoring": None, "accessibility": None}
    assert (
        permissions.should_show_permissions(
            statuses=statuses, dismissed_version=None, current_version="1.0.6"
        )
        is False
    )


def test_dismissed_this_version_suppresses_even_if_missing():
    statuses = {**ALL_OK, "accessibility": False}
    assert (
        permissions.should_show_permissions(
            statuses=statuses, dismissed_version="1.0.6", current_version="1.0.6"
        )
        is False
    )


def test_dismissed_old_version_does_not_suppress_a_missing_grant():
    statuses = {**ALL_OK, "input_monitoring": False}
    assert (
        permissions.should_show_permissions(
            statuses=statuses, dismissed_version="1.0.5", current_version="1.0.6"
        )
        is True
    )


# --- deep links + status ----------------------------------------------------


def test_privacy_panes_target_the_correct_anchors():
    # Microphone is intentionally absent (granted via macOS's own prompt on first record).
    assert set(permissions.PRIVACY_PANES) == {"input_monitoring", "accessibility", "screen_recording"}
    assert permissions.PRIVACY_PANES["input_monitoring"].endswith("Privacy_ListenEvent")
    assert permissions.PRIVACY_PANES["accessibility"].endswith("Privacy_Accessibility")
    assert permissions.PRIVACY_PANES["screen_recording"].endswith("Privacy_ScreenCapture")


def test_open_privacy_pane_runs_open_with_the_url(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd))
    assert permissions.open_privacy_pane("input_monitoring") is True
    assert calls == [["open", permissions.PRIVACY_PANES["input_monitoring"]]]


def test_open_privacy_pane_rejects_unknown_name(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd))
    assert permissions.open_privacy_pane("microphone") is False  # removed → now unknown
    assert permissions.open_privacy_pane("bogus") is False
    assert calls == []


def test_permission_status_aggregates_the_checks(monkeypatch):
    monkeypatch.setattr(permissions, "input_monitoring_trusted", lambda: False)
    monkeypatch.setattr(permissions, "accessibility_trusted", lambda prompt=False: None)
    assert permissions.permission_status() == {
        "input_monitoring": False,
        "accessibility": None,
    }


# --- relaunch helper --------------------------------------------------------


def test_relaunch_macos_app_stages_helper_that_reopens_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(updates.sys, "platform", "darwin")
    fake_app = tmp_path / "Spuk.app"
    fake_app.mkdir()
    monkeypatch.setattr(updates, "_installed_macos_app", lambda: fake_app)
    popen_calls = []
    monkeypatch.setattr(updates.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))

    assert updates.relaunch_macos_app() is True
    assert popen_calls, "no detached relaunch helper spawned"
    cmd = popen_calls[0][0][0]  # the Popen argv
    assert cmd[0] == "/bin/sh"
    helper_script = pathlib.Path(cmd[1]).read_text()
    assert f'open "{fake_app}"' in helper_script


def test_relaunch_macos_app_false_when_not_packaged(monkeypatch):
    monkeypatch.setattr(updates.sys, "platform", "darwin")
    monkeypatch.setattr(updates, "_installed_macos_app", lambda: None)
    assert updates.relaunch_macos_app() is False


def test_relaunch_macos_app_false_off_darwin(monkeypatch):
    monkeypatch.setattr(updates.sys, "platform", "linux")
    assert updates.relaunch_macos_app() is False
