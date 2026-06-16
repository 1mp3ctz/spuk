"""Linux input/uinput permission checks (the macOS path is untouched).

Pure logic: we patch the two probes (``_in_input_group`` / ``_uinput_accessible``)
and ``platform.system`` so the tests run identically on any OS.
"""

import unittest
from unittest import mock

from spuk import permissions


class LinuxAccessOk(unittest.TestCase):
    def test_ok_when_in_input_group(self):
        with mock.patch.object(permissions, "_in_input_group", return_value=True), \
             mock.patch.object(permissions, "_uinput_accessible", return_value=False):
            self.assertTrue(permissions.linux_input_access_ok())

    def test_ok_when_uinput_writable_even_without_group(self):
        # Some setups grant access via udev rules instead of the group.
        with mock.patch.object(permissions, "_in_input_group", return_value=False), \
             mock.patch.object(permissions, "_uinput_accessible", return_value=True):
            self.assertTrue(permissions.linux_input_access_ok())

    def test_not_ok_when_neither(self):
        with mock.patch.object(permissions, "_in_input_group", return_value=False), \
             mock.patch.object(permissions, "_uinput_accessible", return_value=False):
            self.assertFalse(permissions.linux_input_access_ok())


class EnsurePermissionsLinux(unittest.TestCase):
    def test_returns_true_and_does_not_block_when_ok(self):
        with mock.patch.object(permissions.platform, "system", return_value="Linux"), \
             mock.patch.object(permissions, "linux_input_access_ok", return_value=True):
            self.assertTrue(permissions.ensure_permissions(prompt=True))

    def test_returns_false_but_does_not_raise_when_missing(self):
        # Mirrors the macOS pattern: app keeps running, hotkey just won't fire.
        with mock.patch.object(permissions.platform, "system", return_value="Linux"), \
             mock.patch.object(permissions, "linux_input_access_ok", return_value=False):
            self.assertFalse(permissions.ensure_permissions(prompt=True))

    def test_other_unix_without_checks_returns_true(self):
        # A platform that is neither Darwin nor Linux has nothing to check.
        with mock.patch.object(permissions.platform, "system", return_value="FreeBSD"):
            self.assertTrue(permissions.ensure_permissions(prompt=True))


if __name__ == "__main__":
    unittest.main()
