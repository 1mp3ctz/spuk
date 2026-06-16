"""Offscreen smoke for the 'Paste with' dropdown, incl. the new 'Type it out' option."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from spuk.config import load_config  # noqa: E402
from spuk.core import SpukCore  # noqa: E402
from spuk.ui_bar import CoreSignals  # noqa: E402
from spuk.ui_window import SpukWindow  # noqa: E402


def _window():
    app = QApplication.instance() or QApplication([])
    cfg = load_config()
    return app, SpukWindow(cfg, SpukCore(cfg), CoreSignals())


def test_paste_dropdown_has_three_options_with_type():
    _app, win = _window()
    data = [win._paste.itemData(i) for i in range(win._paste.count())]
    assert data == ["", "<ctrl>+<shift>+v", "type"]


def test_paste_index_for_maps_each_value():
    _app, win = _window()
    assert win._paste_index_for("") == 0
    assert win._paste_index_for("<ctrl>+<shift>+v") == 1
    assert win._paste_index_for("type") == 2
    assert win._paste_index_for(None) == 0          # None -> default
    assert win._paste_index_for("nonsense") == 0    # unknown -> default
