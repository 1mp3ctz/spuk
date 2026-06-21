import os
import sys
import types

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


def test_front_window_png_cleans_up_temp_file_on_capture_failure(monkeypatch, tmp_path):
    """Temp file must be removed when capture_window_to_png raises."""
    leaked = []

    def fake_mkstemp(suffix, prefix):
        p = str(tmp_path / "spuk-shot-test.png")
        open(p, "wb").close()
        leaked.append(p)
        fd = os.open(p, os.O_RDWR)
        return fd, p

    def failing_capture(window_id, path, **kwargs):
        raise RuntimeError("simulated screencapture failure")

    class FakeApp:
        def processIdentifier(self):
            return 42

    class FakeWorkspace:
        def frontmostApplication(self):
            return FakeApp()

        @classmethod
        def sharedWorkspace(cls):
            return cls()

    def fake_cg_window_list(*_args, **_kwargs):
        return [
            {
                "kCGWindowOwnerPID": 42,
                "kCGWindowLayer": 0,
                "kCGWindowNumber": 7,
                "kCGWindowBounds": {"Width": 800, "Height": 600},
            }
        ]

    monkeypatch.setattr("tempfile.mkstemp", fake_mkstemp)
    monkeypatch.setattr("spuk.screenshot.capture_window_to_png", failing_capture)

    appkit_mod = types.ModuleType("AppKit")
    appkit_mod.NSWorkspace = FakeWorkspace
    quartz_mod = types.ModuleType("Quartz")
    quartz_mod.CGWindowListCopyWindowInfo = fake_cg_window_list
    quartz_mod.kCGNullWindowID = 0
    quartz_mod.kCGWindowListOptionOnScreenOnly = 1
    monkeypatch.setitem(sys.modules, "AppKit", appkit_mod)
    monkeypatch.setitem(sys.modules, "Quartz", quartz_mod)

    result = screenshot.front_window_png()

    assert result is None
    assert len(leaked) == 1, "mkstemp should have been called once"
    assert not os.path.exists(leaked[0]), "temp file was not cleaned up on failure"
