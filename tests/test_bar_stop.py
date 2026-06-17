"""The floating pill is a guaranteed, hotkey-independent way to stop recording.

Clicking the pill while a recording is active (e.g. a hands-free latch) stops it,
so the user is never stranded with the mic on when the global hotkey misbehaves.
Clicking it when idle opens Settings as before.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from spuk.config import load_config  # noqa: E402
from spuk.core import SpukCore  # noqa: E402
from spuk.ui_bar import CoreSignals, SpukBar  # noqa: E402


def _bar():
    QApplication.instance() or QApplication([])
    cfg = load_config()
    return SpukBar(cfg, SpukCore(cfg), CoreSignals())


def test_click_while_recording_stops():
    bar = _bar()
    calls = {"stop": 0, "settings": 0}
    bar._stop_recording = lambda: calls.__setitem__("stop", calls["stop"] + 1)
    bar._open_settings = lambda: calls.__setitem__("settings", calls["settings"] + 1)

    bar._on_recording(True)  # a recording is now active
    bar._on_pill_clicked()

    assert calls == {"stop": 1, "settings": 0}


def test_click_while_idle_opens_settings():
    bar = _bar()
    calls = {"stop": 0, "settings": 0}
    bar._stop_recording = lambda: calls.__setitem__("stop", calls["stop"] + 1)
    bar._open_settings = lambda: calls.__setitem__("settings", calls["settings"] + 1)

    bar._on_recording(False)  # idle
    bar._on_pill_clicked()

    assert calls == {"stop": 0, "settings": 1}
