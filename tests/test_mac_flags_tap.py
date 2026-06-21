from spuk.mac_flags_tap import CMD_L, CMD_R, MacFlagsTap

SHIFT_L = 0x00000002


def test_handle_flags_fires_callback_once_per_press():
    calls = []
    tap = MacFlagsTap(on_dual_cmd=lambda: calls.append(1))
    tap._handle_flags(CMD_L)              # one cmd: nothing
    tap._handle_flags(CMD_L | CMD_R)      # both: FIRE
    tap._handle_flags(CMD_L | CMD_R)      # still both: no repeat
    tap._handle_flags(0)                  # released: re-arm
    tap._handle_flags(CMD_L | CMD_R)      # both again: FIRE
    assert calls == [1, 1]


def test_handle_flags_other_modifier_does_not_fire():
    calls = []
    tap = MacFlagsTap(on_dual_cmd=lambda: calls.append(1))
    tap._handle_flags(CMD_L | CMD_R | SHIFT_L)  # ⌘⌘⇧ — blocked
    assert calls == []


def test_callback_exception_does_not_propagate():
    def boom():
        raise RuntimeError("handler blew up")

    tap = MacFlagsTap(on_dual_cmd=boom)
    # A misbehaving callback must never kill the tap thread.
    tap._handle_flags(CMD_L | CMD_R)  # should not raise
