from spuk import screenshot


def test_shoot_and_paste_runs_capture_copy_paste_in_order(tmp_path):
    order = []
    png = str(tmp_path / "s.png")

    def capture():
        order.append("capture")
        return png

    def copy(path):
        assert path == png
        order.append("copy")

    def paste():
        order.append("paste")

    ok = screenshot.shoot_and_paste(capture=capture, copy=copy, paste=paste)
    assert ok is True
    assert order == ["capture", "copy", "paste"]


def test_shoot_and_paste_noops_when_capture_returns_none():
    calls = []
    ok = screenshot.shoot_and_paste(
        capture=lambda: None,
        copy=lambda p: calls.append("copy"),
        paste=lambda: calls.append("paste"),
    )
    assert ok is False
    assert calls == []
