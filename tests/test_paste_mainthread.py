"""Regression: macOS keyboard injection must run on the main thread.

pynput's ``Controller`` (both construction and key-send) queries the current
keyboard layout through HIToolbox's Text Input Source Manager, which asserts it
runs on the main thread (``dispatch_assert_queue``). Spuk synthesizes the paste
keystroke from the hotkey-listener thread and from the UI's "Hold to talk" worker
thread, so the injector MUST marshal that pynput work through the installed
main-thread runner. Running it on a background thread is what killed the app with
SIGTRAP after every dictation.

These tests fake ``pynput.keyboard`` (via ``sys.modules``) so they never touch a
real macOS API, and record which thread each pynput call lands on.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import types

import spuk.paste as paste


def _install_fake_pynput(monkeypatch, record):
    """Replace ``pynput.keyboard`` with a fake that records the calling thread."""

    class FakeController:
        def __init__(self):
            record.append(("construct", threading.get_ident()))

        def press(self, k):
            record.append(("press", threading.get_ident()))

        def release(self, k):
            record.append(("release", threading.get_ident()))

        def type(self, text):
            record.append(("type", text, threading.get_ident()))

    class FakeHotKey:
        @staticmethod
        def parse(combo):
            return ["mod", "key"]  # placeholder keys; order/content irrelevant here

    fake = types.ModuleType("pynput.keyboard")
    fake.Controller = FakeController
    fake.HotKey = FakeHotKey
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake)


class _FakeMainThread:
    """A stand-in main thread that runs submitted callables and blocks the caller."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self.ident: int | None = None
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        while self.ident is None:  # wait until it knows its own ident
            time.sleep(0.001)

    def _loop(self):
        self.ident = threading.get_ident()
        while True:
            job = self._q.get()
            if job is None:
                return
            fn, box, done = job
            try:
                box["value"] = fn()
            except BaseException as exc:  # noqa: BLE001 - surfaced to caller
                box["error"] = exc
            finally:
                done.set()

    def run(self, fn):
        box: dict = {}
        done = threading.Event()
        self._q.put((fn, box, done))
        done.wait()
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def stop(self):
        self._q.put(None)
        self._t.join()


def test_injector_runs_all_pynput_work_on_the_runner_thread(monkeypatch):
    """The injector must do its pynput work on the runner (main) thread, not the caller."""
    record: list = []
    _install_fake_pynput(monkeypatch, record)
    main = _FakeMainThread()
    monkeypatch.setattr(paste, "_main_thread_runner", main.run, raising=False)

    inject = paste._build_pynput_injector("<cmd>+v")
    # Building the injector must NOT construct a Controller yet — that has to be
    # deferred onto the main thread.
    assert record == [], "Controller was built before the main-thread runner ran"

    caller: dict = {}

    def work():
        caller["ident"] = threading.get_ident()
        inject()

    t = threading.Thread(target=work)
    t.start()
    t.join()
    main.stop()

    assert record, "injector did no pynput work"
    assert caller["ident"] != main.ident, "test bug: worker ran on the main thread"
    off_main = [e for e in record if e[-1] != main.ident]
    assert not off_main, f"pynput work ran off the main thread: {off_main}"


def test_typer_runs_all_pynput_work_on_the_runner_thread(monkeypatch):
    record: list = []
    _install_fake_pynput(monkeypatch, record)
    main = _FakeMainThread()
    monkeypatch.setattr(paste, "_main_thread_runner", main.run, raising=False)

    typer = paste._build_pynput_typer()
    assert record == [], "Controller was built before the main-thread runner ran"

    caller: dict = {}

    def work():
        caller["ident"] = threading.get_ident()
        typer("hä llo")

    t = threading.Thread(target=work)
    t.start()
    t.join()
    main.stop()

    assert ("type", "hä llo", main.ident) in record
    off_main = [e for e in record if e[-1] != main.ident]
    assert not off_main, f"pynput work ran off the main thread: {off_main}"


def test_no_runner_runs_inline(monkeypatch):
    """Windows/Linux/headless: with no runner installed, injection runs inline (unchanged)."""
    record: list = []
    _install_fake_pynput(monkeypatch, record)
    monkeypatch.setattr(paste, "_main_thread_runner", None, raising=False)

    caller_ident = threading.get_ident()
    inject = paste._build_pynput_injector("<cmd>+v")
    inject()

    assert record, "injector did no pynput work"
    assert all(e[-1] == caller_ident for e in record), record


def test_set_main_thread_runner_roundtrip():
    sentinel = lambda fn: fn()  # noqa: E731
    paste.set_main_thread_runner(sentinel)
    assert paste._main_thread_runner is sentinel
    paste.set_main_thread_runner(None)
    assert paste._main_thread_runner is None
