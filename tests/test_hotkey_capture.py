from pynput.keyboard import Key

from spuk.hotkey import HotkeyListener


def _listener(on_start=None, on_stop=None):
    return HotkeyListener(
        key_combo="<ctrl>+<alt>", mode="push_to_talk",
        on_start=on_start or (lambda: None),
        on_stop=on_stop or (lambda: None),
    )


def test_capture_returns_combo_on_first_release():
    got = []
    lis = _listener()
    lis.begin_capture(on_done=got.append)
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    lis._feed_release(Key.alt)
    assert got == ["<ctrl>+<alt>"]


def test_capture_suppresses_the_fsm():
    started = []
    lis = _listener(on_start=lambda: started.append(1))
    lis.begin_capture(on_done=lambda _c: None)
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    # Holding the chord during capture must NOT start a recording.
    assert started == []


def test_capture_can_be_cancelled():
    got = []
    lis = _listener()
    lis.begin_capture(on_done=got.append)
    lis.cancel_capture()
    lis._feed_press(Key.ctrl)
    lis._feed_release(Key.ctrl)
    assert got == []


def test_update_bindings_swaps_combo_in_place():
    started = []
    lis = _listener(on_start=lambda: started.append(1))
    # Rebind talk from Ctrl+Alt to Ctrl+Shift, with no restart.
    lis.update_bindings(key_combo="<ctrl>+<shift>", mode="push_to_talk",
                        taps={}, handsfree=True, double_tap_seconds=0.4)
    # The OLD chord (Ctrl+Alt) must no longer start recording.
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    assert started == []
    lis._feed_release(Key.alt)
    lis._feed_release(Key.ctrl)
    # The NEW chord (Ctrl+Shift) must start recording.
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.shift)
    assert started == [1]


def test_update_bindings_switches_to_toggle_mode():
    events = []
    lis = _listener(on_start=lambda: events.append("start"), on_stop=lambda: events.append("stop"))
    lis.update_bindings(key_combo="<ctrl>+<alt>", mode="toggle",
                        taps={}, handsfree=False, double_tap_seconds=0.4)
    # press 1 -> start
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    lis._feed_release(Key.alt)
    lis._feed_release(Key.ctrl)
    # press 2 -> stop
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    assert events == ["start", "stop"]


def test_after_capture_fsm_works_again():
    started = []
    lis = _listener(on_start=lambda: started.append(1))
    lis.begin_capture(on_done=lambda _c: None)
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    lis._feed_release(Key.alt)   # capture done here
    # Now a real chord press should start recording.
    lis._feed_press(Key.ctrl)
    lis._feed_press(Key.alt)
    assert started == [1]
