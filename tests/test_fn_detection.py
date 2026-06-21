from spuk.mac_flags_tap import FN_BIT, fn_edge, MacFlagsTap

CMD_L = 0x00000008
CMD_R = 0x00000010


def test_fn_edge_press():
    """Bit goes 0 → 1: press fires, not release."""
    press, release, new_down = fn_edge(FN_BIT, fn_down=False)
    assert press is True
    assert release is False
    assert new_down is True


def test_fn_edge_release():
    """Bit goes 1 → 0: release fires, not press."""
    press, release, new_down = fn_edge(0, fn_down=True)
    assert press is False
    assert release is True
    assert new_down is False


def test_fn_edge_held():
    """Bit stays 1: nothing fires."""
    press, release, new_down = fn_edge(FN_BIT, fn_down=True)
    assert press is False
    assert release is False
    assert new_down is True


def test_fn_edge_not_pressed():
    """Bit stays 0: nothing fires."""
    press, release, new_down = fn_edge(0, fn_down=False)
    assert press is False
    assert release is False
    assert new_down is False


def test_fn_callbacks_fired_from_handle_flags():
    press_calls = []
    release_calls = []

    tap = MacFlagsTap(
        on_dual_cmd=lambda: None,
        on_fn_press=lambda: press_calls.append(1),
        on_fn_release=lambda: release_calls.append(1),
    )
    tap._handle_flags(FN_BIT)   # press
    tap._handle_flags(FN_BIT)   # still held — no duplicate
    tap._handle_flags(0)         # release

    assert press_calls == [1]
    assert release_calls == [1]


def test_fn_and_dual_cmd_independent():
    """Fn press does not fire dual-⌘ callback and vice versa."""
    fn_fired = []
    cmd_fired = []

    tap = MacFlagsTap(
        on_dual_cmd=lambda: cmd_fired.append(1),
        on_fn_press=lambda: fn_fired.append(1),
    )
    tap._handle_flags(FN_BIT)       # only fn
    tap._handle_flags(0)
    tap._handle_flags(CMD_L | CMD_R) # only dual-⌘ (no Fn)

    assert fn_fired == [1]
    assert cmd_fired == [1]


def test_no_fn_callbacks_when_omitted():
    """MacFlagsTap with no fn callbacks stays backward-compatible."""
    tap = MacFlagsTap(on_dual_cmd=lambda: None)
    tap._handle_flags(FN_BIT)  # must not raise
    tap._handle_flags(0)
