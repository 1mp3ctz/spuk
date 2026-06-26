"""mac_tap_heal patches pynput's darwin tap so it re-enables after a disable.

We test the pure ``_apply_patch`` against a fake ListenerMixin + fake Quartz, so
no real pynput/macOS is needed. This is the recovery that keeps the global hotkey
alive after macOS disables the tap (sleep/wake, timeout, synthetic-input burst).
"""

import spuk.mac_tap_heal as heal
from spuk.mac_tap_heal import _TAP_DISABLED, _apply_patch


class _FakeQuartz:
    def __init__(self) -> None:
        self.enables: list[tuple] = []

    def CGEventTapEnable(self, tap, on) -> None:
        self.enables.append((tap, on))


def _fresh_mixin():
    class FakeMixin:
        def _create_event_tap(self):
            return "THE_TAP"

        def _handler(self, proxy, event_type, event, refcon):
            return ("orig", event_type)

    return FakeMixin


def test_patch_stores_tap_and_reenables_on_disable():
    q = _FakeQuartz()
    mixin = _fresh_mixin()
    assert _apply_patch(mixin, q) is True

    inst = mixin()
    # creating the tap now records the handle on the instance
    assert inst._create_event_tap() == "THE_TAP"
    assert inst._spuk_tap == "THE_TAP"

    # each disable type re-enables the stored tap and short-circuits
    for dt in _TAP_DISABLED:
        q.enables.clear()
        assert inst._handler(None, dt, "evt", None) == "evt"
        assert q.enables == [("THE_TAP", True)]

    # a normal event delegates to the original handler, untouched
    assert inst._handler(None, 7, "evt", None) == ("orig", 7)


def test_patch_is_idempotent():
    q = _FakeQuartz()
    mixin = _fresh_mixin()
    assert _apply_patch(mixin, q) is True
    assert _apply_patch(mixin, q) is False  # already patched


def test_patch_skips_class_without_expected_internals():
    class NotPynput:
        pass

    assert _apply_patch(NotPynput, _FakeQuartz()) is False


def test_install_never_raises_off_darwin(monkeypatch):
    monkeypatch.setattr(heal.platform, "system", lambda: "Linux")
    heal.install_pynput_tap_healing()  # must be a silent no-op
