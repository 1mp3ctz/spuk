"""Linux paste-injection selection: uinput preferred, ydotool fallback, noop last.

``evdev`` can't be imported on macOS, so we install a fake ``evdev`` module in
``sys.modules`` for the cases that exercise the uinput path, and patch
``shutil.which`` for the ydotool path. Each test restores global state in
``tearDown`` so it stays isolated.
"""

import sys
import types
import unittest
from unittest import mock

from spuk import linux_input


class FakeUInput:
    """Records writes/syns so we can assert the Ctrl+V sequence is emitted."""

    instances: list["FakeUInput"] = []

    def __init__(self, capabilities=None, name=None):
        self.capabilities = capabilities
        self.name = name
        self.events: list[tuple] = []
        FakeUInput.instances.append(self)

    def write(self, etype, code, value):
        self.events.append(("write", etype, code, value))

    def syn(self):
        self.events.append(("syn",))


class FakeEcodes:
    EV_KEY = 1
    KEY_LEFTCTRL = 29
    KEY_V = 47


def _install_fake_evdev(uinput_cls=FakeUInput):
    """Put a fake ``evdev`` module (with UInput + ecodes) into sys.modules."""
    mod = types.ModuleType("evdev")
    mod.UInput = uinput_cls
    mod.ecodes = FakeEcodes
    sys.modules["evdev"] = mod


class PasteInjectorSelection(unittest.TestCase):
    def setUp(self):
        FakeUInput.instances = []
        self._had_evdev = "evdev" in sys.modules
        self._saved_evdev = sys.modules.get("evdev")

    def tearDown(self):
        if self._had_evdev:
            sys.modules["evdev"] = self._saved_evdev
        else:
            sys.modules.pop("evdev", None)

    def test_prefers_uinput_and_emits_ctrl_v(self):
        _install_fake_evdev()
        injector = linux_input.build_linux_paste_injector()
        injector()  # send one paste
        self.assertEqual(len(FakeUInput.instances), 1)
        events = FakeUInput.instances[0].events
        # Ctrl down, V down, syn, V up, Ctrl up, syn
        self.assertEqual(
            events,
            [
                ("write", FakeEcodes.EV_KEY, FakeEcodes.KEY_LEFTCTRL, 1),
                ("write", FakeEcodes.EV_KEY, FakeEcodes.KEY_V, 1),
                ("syn",),
                ("write", FakeEcodes.EV_KEY, FakeEcodes.KEY_V, 0),
                ("write", FakeEcodes.EV_KEY, FakeEcodes.KEY_LEFTCTRL, 0),
                ("syn",),
            ],
        )

    def test_falls_back_to_ydotool_when_uinput_unavailable(self):
        # UInput construction raises (e.g. /dev/uinput not writable).
        class BoomUInput(FakeUInput):
            def __init__(self, *a, **k):
                raise PermissionError("no uinput")

        _install_fake_evdev(uinput_cls=BoomUInput)
        with mock.patch.object(linux_input.shutil, "which", return_value="/usr/bin/ydotool"):
            with mock.patch.object(linux_input.subprocess, "run") as run:
                injector = linux_input.build_linux_paste_injector()
                injector()
                run.assert_called_once()
                args = run.call_args[0][0]
                self.assertEqual(args[0], "/usr/bin/ydotool")
                self.assertIn("29:1", args)  # Ctrl down
                self.assertIn("47:1", args)  # V down

    def test_noop_when_neither_available(self):
        # No evdev module AND no ydotool → a callable that just logs (never raises).
        sys.modules.pop("evdev", None)
        with mock.patch.object(linux_input.shutil, "which", return_value=None):
            injector = linux_input.build_linux_paste_injector()
            # Must not raise when called.
            injector()


class ClipboardToolHint(unittest.TestCase):
    def test_true_when_wl_copy_present(self):
        def which(tool):
            return "/usr/bin/wl-copy" if tool == "wl-copy" else None

        with mock.patch.object(linux_input.shutil, "which", side_effect=which):
            self.assertTrue(linux_input.clipboard_tool_available())

    def test_false_when_none_present(self):
        with mock.patch.object(linux_input.shutil, "which", return_value=None):
            self.assertFalse(linux_input.clipboard_tool_available())


if __name__ == "__main__":
    unittest.main()
