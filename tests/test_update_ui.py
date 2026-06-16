"""Offscreen smoke for the in-app self-update progress UI (no network, no threads)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QProgressDialog  # noqa: E402

from spuk.config import load_config  # noqa: E402
from spuk.core import SpukCore  # noqa: E402
from spuk.ui_bar import CoreSignals  # noqa: E402
from spuk.ui_window import SpukWindow  # noqa: E402


def _window():
    app = QApplication.instance() or QApplication([])
    cfg = load_config()
    return app, SpukWindow(cfg, SpukCore(cfg), CoreSignals())


def test_progress_slot_updates_dialog():
    _app, win = _window()
    win._update_dialog = QProgressDialog("Downloading update…", "Cancel", 0, 0, win)
    win._on_self_update_progress(50 * 1048576, 100 * 1048576)
    assert win._update_dialog.maximum() == 100 * 1048576
    assert win._update_dialog.value() == 50 * 1048576
    assert "50 / 100 MB" in win._update_dialog.labelText()


def test_done_success_quits_and_closes_dialog():
    _app, win = _window()
    win._update_dialog = QProgressDialog("Downloading update…", "Cancel", 0, 100, win)
    quit_called = []
    win.set_quit(lambda: quit_called.append(True))
    win._on_self_update_done(True, "")
    assert quit_called == [True]
    assert win._update_dialog is None  # dialog closed/cleared


def test_cancel_resets_button_without_error_dialog():
    _app, win = _window()
    win._update_dialog = QProgressDialog("Downloading update…", "Cancel", 0, 100, win)
    # Empty message = user cancelled: should NOT try to quit, just reset.
    win.set_quit(lambda: (_ for _ in ()).throw(AssertionError("must not quit on cancel")))
    win._on_self_update_done(False, "")
    assert win._update_dialog is None
    assert win._update_btn.isEnabled()
    assert win._update_btn.text() == "Check for updates"
