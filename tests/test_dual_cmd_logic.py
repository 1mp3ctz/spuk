from spuk.mac_flags_tap import CMD_L, CMD_R, both_cmd_only, dual_cmd_edge

CTRL_L = 0x00000001
SHIFT_L = 0x00000002
ALT_L = 0x00000020
FN = 0x00800000
CAPS = 0x00010000


def test_both_cmd_true_when_only_both_commands():
    assert both_cmd_only(CMD_L | CMD_R) is True


def test_one_command_is_not_enough():
    assert both_cmd_only(CMD_L) is False
    assert both_cmd_only(CMD_R) is False
    assert both_cmd_only(0) is False


def test_other_modifier_blocks_the_gesture():
    assert both_cmd_only(CMD_L | CMD_R | SHIFT_L) is False
    assert both_cmd_only(CMD_L | CMD_R | CTRL_L) is False
    assert both_cmd_only(CMD_L | CMD_R | ALT_L) is False
    assert both_cmd_only(CMD_L | CMD_R | FN) is False


def test_caps_lock_is_ignored():
    assert both_cmd_only(CMD_L | CMD_R | CAPS) is True


def test_edge_fires_once_on_rising_then_rearms():
    # not held -> held: fire
    fire, armed = dual_cmd_edge(active=True, armed=False)
    assert fire is True and armed is True
    # still held: no repeat
    fire, armed = dual_cmd_edge(active=True, armed=armed)
    assert fire is False and armed is True
    # released: re-arm, no fire
    fire, armed = dual_cmd_edge(active=False, armed=armed)
    assert fire is False and armed is False
    # held again: fire again
    fire, armed = dual_cmd_edge(active=True, armed=armed)
    assert fire is True and armed is True
