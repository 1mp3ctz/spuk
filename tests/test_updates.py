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


if __name__ == "__main__":
    unittest.main()
