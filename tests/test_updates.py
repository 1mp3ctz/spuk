"""Version-comparison logic for the update checker (no network)."""

import unittest

from spuk import updates


class ParseVersion(unittest.TestCase):
    def test_strips_v_prefix_and_splits(self):
        self.assertEqual(updates._parse_version("v0.3.1"), (0, 3, 1))
        self.assertEqual(updates._parse_version("0.3.1"), (0, 3, 1))

    def test_ignores_suffixes(self):
        self.assertEqual(updates._parse_version("1.2.3-beta"), (1, 2, 3))
        self.assertEqual(updates._parse_version("v2"), (2,))

    def test_blank_is_zero(self):
        self.assertEqual(updates._parse_version(""), (0,))


class IsNewer(unittest.TestCase):
    def test_newer_versions(self):
        self.assertTrue(updates.is_newer("v0.3.2", "0.3.1"))
        self.assertTrue(updates.is_newer("v1.0.0", "0.9.9"))
        self.assertTrue(updates.is_newer("0.3.10", "0.3.9"))  # numeric, not lexical

    def test_same_or_older(self):
        self.assertFalse(updates.is_newer("v0.3.1", "0.3.1"))
        self.assertFalse(updates.is_newer("v0.3.0", "0.3.1"))


class AssetForPlatform(unittest.TestCase):
    ASSETS = [
        {"name": "Spuk-macos.zip", "browser_download_url": "https://x/mac.zip"},
        {"name": "Spuk-windows.zip", "browser_download_url": "https://x/win.zip"},
    ]

    def test_picks_macos(self):
        self.assertEqual(updates._asset_for_platform(self.ASSETS, "darwin"), "https://x/mac.zip")

    def test_picks_windows(self):
        self.assertEqual(updates._asset_for_platform(self.ASSETS, "win32"), "https://x/win.zip")

    def test_unsupported_platform(self):
        self.assertIsNone(updates._asset_for_platform(self.ASSETS, "linux"))

    def test_missing_asset(self):
        self.assertIsNone(updates._asset_for_platform([], "darwin"))


if __name__ == "__main__":
    unittest.main()
