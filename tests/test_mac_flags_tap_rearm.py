"""The Fn/dual-⌘ tap must re-arm itself after macOS disables it.

macOS disables a CGEventTap (kCGEventTapDisabledByTimeout /
kCGEventTapDisabledByUserInput, and across sleep/wake). The tap callback receives
those as special event *types*; the owner must call CGEventTapEnable(tap, True)
to recover. Without it, Fn dictation silently dies until Spuk is restarted.

``_handle_tap_event`` is the pure decision: True means "this was a disable event,
re-arm the tap"; False means "a normal flagsChanged event, already processed".
"""

from spuk.mac_flags_tap import CMD_L, CMD_R, MacFlagsTap, _TAP_DISABLED


def _tap():
    fired = []
    return MacFlagsTap(on_dual_cmd=lambda: fired.append(1)), fired


def test_normal_event_is_processed_and_needs_no_rearm():
    tap, fired = _tap()
    # a both-⌘ rising edge fires the gesture and reports "no rearm needed"
    assert tap._handle_tap_event(0, CMD_L | CMD_R) is False
    assert fired == [1]


def test_disable_events_request_rearm_and_are_never_read_as_a_gesture():
    assert _TAP_DISABLED  # the two Apple sentinel types
    for disabled_type in _TAP_DISABLED:
        tap, fired = _tap()
        # even if the (stale) flags look like both-⌘, a disable event must not fire
        assert tap._handle_tap_event(disabled_type, CMD_L | CMD_R) is True
        assert fired == []
