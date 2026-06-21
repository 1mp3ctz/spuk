from spuk.screenshot import capture_window_to_png, pick_window


def _win(pid, layer, number, w, h):
    return {
        "kCGWindowOwnerPID": pid,
        "kCGWindowLayer": layer,
        "kCGWindowNumber": number,
        "kCGWindowBounds": {"Width": w, "Height": h},
    }


def test_pick_window_returns_layer0_window_for_pid():
    infos = [
        _win(99, 0, 11, 800, 600),   # another app
        _win(42, 0, 22, 1200, 800),  # our app, main window
        _win(42, 25, 33, 50, 20),    # our app, a menu/overlay (layer != 0)
    ]
    assert pick_window(infos, 42) == 22


def test_pick_window_prefers_largest_layer0():
    infos = [
        _win(42, 0, 1, 400, 300),
        _win(42, 0, 2, 1600, 1000),  # biggest -> the real window
    ]
    assert pick_window(infos, 42) == 2


def test_pick_window_none_when_no_match():
    assert pick_window([_win(99, 0, 1, 800, 600)], 42) is None


def test_capture_window_builds_expected_screencapture_argv(tmp_path):
    seen = {}

    def fake_runner(argv, check):
        seen["argv"] = argv
        seen["check"] = check

    out = str(tmp_path / "shot.png")
    capture_window_to_png(123, out, runner=fake_runner)
    assert seen["argv"] == ["screencapture", "-x", "-o", "-l", "123", out]
    assert seen["check"] is True
