from spuk.fn_dictation import FnDictationController


class FakeEngine:
    def __init__(self, start_ok=True):
        self._start_ok = start_ok
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1
        return self._start_ok

    def stop(self):
        self.stopped += 1


class FakeInsert:
    def __init__(self):
        self.events = []

    def update(self, text):
        self.events.append(("update", text))

    def commit(self):
        self.events.append(("commit",))

    def cancel(self):
        self.events.append(("cancel",))


def make(engines):
    """Build a controller whose factory hands out ``engines`` in order."""
    li = FakeInsert()
    it = iter(engines)
    return FnDictationController(li, lambda: next(it)), li


def test_press_starts_engine():
    e = FakeEngine()
    ctrl, _li = make([e])
    ctrl.on_press()
    assert e.started == 1
    assert ctrl.running is True


def test_release_stops_engine_and_commits():
    e = FakeEngine()
    ctrl, li = make([e])
    ctrl.on_press()
    ctrl.on_release()
    assert e.stopped == 1
    assert ctrl.running is False
    assert ("commit",) in li.events


def test_double_press_stops_first_engine_no_leak():
    """Critical: a 2nd press before release must stop the first engine, not leak it."""
    e1, e2 = FakeEngine(), FakeEngine()
    ctrl, _li = make([e1, e2])
    ctrl.on_press()
    ctrl.on_press()  # second press without an intervening release
    assert e1.stopped == 1  # first engine was torn down (mic released)
    assert e2.started == 1
    assert ctrl.running is True  # now owns the second engine
    ctrl.on_release()
    assert e2.stopped == 1


def test_failed_start_cancels_inserter_and_not_running():
    e = FakeEngine(start_ok=False)
    ctrl, li = make([e])
    ctrl.on_press()
    assert ctrl.running is False
    assert ("cancel",) in li.events


def test_partial_updates_inserter():
    ctrl, li = make([])
    ctrl.on_partial("hello")
    assert li.events == [("update", "hello")]


def test_final_commits_inserter():
    ctrl, li = make([])
    ctrl.on_final("done")
    assert li.events == [("commit",)]


def test_stop_when_running_stops_engine():
    """Toggle-off / quit while live must stop the mic immediately."""
    e = FakeEngine()
    ctrl, _li = make([e])
    ctrl.on_press()
    ctrl.stop()
    assert e.stopped == 1
    assert ctrl.running is False


def test_stop_when_idle_is_safe_noop():
    ctrl, _li = make([])
    ctrl.stop()  # must not raise
    assert ctrl.running is False
