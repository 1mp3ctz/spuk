"""Offscreen PySide6 tests for the macOS PermissionsDialog."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

import spuk.permissions as permissions  # noqa: E402
import spuk.ui_permissions as ui_permissions  # noqa: E402
import spuk.updates as updates  # noqa: E402
from spuk import __version__  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _all(values):
    return {"input_monitoring": values, "accessibility": values}


def test_dialog_shows_status_icon_per_permission(monkeypatch):
    _app()
    monkeypatch.setattr(
        permissions,
        "permission_status",
        lambda: {"input_monitoring": False, "accessibility": None},
    )
    dlg = ui_permissions.PermissionsDialog()
    assert dlg._icons["input_monitoring"].text() == "✕"
    assert dlg._icons["accessibility"].text() == "?"
    assert "microphone" not in dlg._icons  # mic row removed


def test_open_button_opens_the_matching_pane(monkeypatch):
    _app()
    monkeypatch.setattr(permissions, "permission_status", lambda: _all(True))
    opened = []
    monkeypatch.setattr(permissions, "open_privacy_pane", lambda name: opened.append(name) or True)
    dlg = ui_permissions.PermissionsDialog()
    dlg._open_buttons["input_monitoring"].click()
    assert opened == ["input_monitoring"]


def test_recheck_refreshes_icons(monkeypatch):
    _app()
    state = {"value": _all(False)}
    monkeypatch.setattr(permissions, "permission_status", lambda: state["value"])
    dlg = ui_permissions.PermissionsDialog()
    assert dlg._icons["input_monitoring"].text() == "✕"
    state["value"] = _all(True)
    dlg.refresh()
    assert dlg._icons["input_monitoring"].text() == "✓"


def test_dont_show_again_persists_and_clears_version(monkeypatch):
    _app()
    monkeypatch.setattr(permissions, "permission_status", lambda: _all(True))
    saved: dict = {}
    monkeypatch.setattr(ui_permissions, "update_user_settings", lambda **kw: saved.update(kw))
    dlg = ui_permissions.PermissionsDialog()
    dlg._dont.setChecked(True)
    assert saved.get("perm_popup_dismissed_version") == __version__
    dlg._dont.setChecked(False)
    assert saved.get("perm_popup_dismissed_version") == ""


def test_quit_and_reopen_relaunches_then_quits(monkeypatch):
    _app()
    monkeypatch.setattr(permissions, "permission_status", lambda: _all(True))
    monkeypatch.setattr(updates, "relaunch_macos_app", lambda: True)
    quit_calls = []
    dlg = ui_permissions.PermissionsDialog(on_quit=lambda: quit_calls.append(1))
    dlg._quit_reopen()
    assert quit_calls == [1]


def test_quit_and_reopen_does_not_quit_when_relaunch_unavailable(monkeypatch):
    _app()
    monkeypatch.setattr(permissions, "permission_status", lambda: _all(True))
    monkeypatch.setattr(updates, "relaunch_macos_app", lambda: False)
    quit_calls = []
    dlg = ui_permissions.PermissionsDialog(on_quit=lambda: quit_calls.append(1))
    dlg._quit_reopen()
    assert quit_calls == []
