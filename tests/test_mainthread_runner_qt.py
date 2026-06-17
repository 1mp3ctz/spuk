"""Integration test for the real Qt main-thread runner (PySide6).

The pure-Python paste tests fake the runner; this one drives the actual
``_MainThreadRunner`` with a live QApplication to prove that work submitted from a
worker thread really executes on the GUI/main thread — the property that stops the
macOS SIGTRAP when injecting the paste keystroke. Runs headless via the offscreen
Qt platform.
"""

from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from spuk.ui_bar import _MainThreadRunner  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_runner_executes_on_the_gui_thread_and_returns_value():
    app = _app()
    runner = _MainThreadRunner()
    main_ident = threading.get_ident()
    out: dict = {}

    def worker():
        out["thread"] = threading.get_ident()
        out["result"] = runner.run(lambda: (threading.get_ident(), 42))

    t = threading.Thread(target=worker)
    t.start()
    deadline = time.time() + 5.0
    while t.is_alive() and time.time() < deadline:
        app.processEvents()  # deliver the queued submit to the main thread
        time.sleep(0.005)
    t.join(timeout=1.0)

    assert not t.is_alive(), "runner.run did not return — main-thread dispatch stalled"
    assert out["thread"] != main_ident, "test bug: worker ran on the main thread"
    ran_on, value = out["result"]
    assert ran_on == main_ident, "callable did not run on the GUI/main thread"
    assert value == 42, "runner did not propagate the return value"


def test_runner_propagates_exceptions_to_caller():
    app = _app()
    runner = _MainThreadRunner()
    out: dict = {}

    def boom():
        raise ValueError("kaboom")

    def worker():
        try:
            runner.run(boom)
        except Exception as exc:  # noqa: BLE001
            out["error"] = exc

    t = threading.Thread(target=worker)
    t.start()
    deadline = time.time() + 5.0
    while t.is_alive() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    t.join(timeout=1.0)

    assert isinstance(out.get("error"), ValueError)
    assert str(out["error"]) == "kaboom"


def test_runner_runs_inline_when_called_on_main_thread():
    _app()
    runner = _MainThreadRunner()
    # Called directly on the main thread: must run inline (no event loop needed),
    # which is what guards against deadlocking on done.wait().
    ran_on = runner.run(lambda: threading.get_ident())
    assert ran_on == threading.get_ident()
