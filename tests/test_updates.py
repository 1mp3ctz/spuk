"""Version-comparison logic for the update checker (no network)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spuk import updates


class _FakeResponse:
    """Minimal stand-in for an http response: context manager + headers + read()."""

    def __init__(self, data: bytes, total: int | None = None) -> None:
        self._data = data
        self._pos = 0
        self.headers = {"Content-Length": str(len(data) if total is None else total)}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self, n: int) -> bytes:
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk


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


class CanSelfUpdate(unittest.TestCase):
    """Self-update is allowed only for the frozen macOS/Windows build."""

    def test_frozen_macos_can_self_update(self):
        with mock.patch.object(updates.sys, "platform", "darwin"), \
             mock.patch.object(updates.sys, "frozen", True, create=True):
            self.assertTrue(updates.can_self_update())

    def test_frozen_windows_can_self_update(self):
        with mock.patch.object(updates.sys, "platform", "win32"), \
             mock.patch.object(updates.sys, "frozen", True, create=True):
            self.assertTrue(updates.can_self_update())

    def test_frozen_linux_cannot_self_update(self):
        # A deb/rpm owns its files; never overwrite them in place.
        with mock.patch.object(updates.sys, "platform", "linux"), \
             mock.patch.object(updates.sys, "frozen", True, create=True):
            self.assertFalse(updates.can_self_update())

    def test_source_macos_cannot_self_update(self):
        # Running from source isn't frozen → nothing to swap.
        with mock.patch.object(updates.sys, "platform", "darwin"), \
             mock.patch.object(updates.sys, "frozen", False, create=True):
            self.assertFalse(updates.can_self_update())


class PackagedLinuxDetection(unittest.TestCase):
    def test_usr_bin_is_packaged(self):
        with mock.patch.object(updates.sys, "platform", "linux"), \
             mock.patch.object(updates.sys, "executable", "/usr/bin/spuk"):
            self.assertTrue(updates._is_packaged_linux_install())

    def test_opt_is_packaged(self):
        with mock.patch.object(updates.sys, "platform", "linux"), \
             mock.patch.object(updates.sys, "executable", "/opt/spuk/spuk"):
            self.assertTrue(updates._is_packaged_linux_install())

    def test_home_checkout_is_not_packaged(self):
        with mock.patch.object(updates.sys, "platform", "linux"), \
             mock.patch.object(updates.sys, "executable", "/home/user/spuk/.venv/bin/python"):
            self.assertFalse(updates._is_packaged_linux_install())

    def test_non_linux_is_not_packaged_linux(self):
        with mock.patch.object(updates.sys, "platform", "darwin"), \
             mock.patch.object(updates.sys, "executable", "/usr/bin/python"):
            self.assertFalse(updates._is_packaged_linux_install())


class DownloadProgress(unittest.TestCase):
    """The download streams in chunks, reporting progress and honouring cancel."""

    def test_reports_increasing_progress_ending_at_total(self):
        data = b"x" * (1024 * 1024 + 777)  # spans several read() chunks
        calls: list[tuple[int, int]] = []
        with mock.patch.object(updates.urllib.request, "urlopen", return_value=_FakeResponse(data)):
            with tempfile.TemporaryDirectory() as d:
                path = updates._download_zip(
                    "http://x/u.zip", Path(d), progress=lambda done, total: calls.append((done, total))
                )
                self.assertTrue(path.exists())
                self.assertEqual(path.read_bytes(), data)
        self.assertGreater(len(calls), 1)
        dones = [c[0] for c in calls]
        self.assertEqual(dones, sorted(dones))            # never goes backwards
        self.assertEqual(dones[-1], len(data))            # ends at the full size
        self.assertEqual(calls[-1][1], len(data))         # total reported correctly

    def test_cancel_aborts_with_update_cancelled(self):
        data = b"x" * (1024 * 1024)
        with mock.patch.object(updates.urllib.request, "urlopen", return_value=_FakeResponse(data)):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(updates.UpdateCancelled):
                    updates._download_zip("http://x/u.zip", Path(d), cancel=lambda: True)

    def test_works_without_progress_or_cancel(self):
        data = b"hello-zip"
        with mock.patch.object(updates.urllib.request, "urlopen", return_value=_FakeResponse(data)):
            with tempfile.TemporaryDirectory() as d:
                path = updates._download_zip("http://x/u.zip", Path(d))
                self.assertEqual(path.read_bytes(), data)

    def test_download_uses_a_verifying_ssl_context(self):
        # Frozen Windows builds can't rely on the system CA store; the download
        # must pass an explicit cert-verifying context (certifi) to urlopen.
        captured: dict = {}

        def fake_urlopen(req, timeout=None, context=None):
            captured["context"] = context
            return _FakeResponse(b"zip")

        with mock.patch.object(updates.urllib.request, "urlopen", side_effect=fake_urlopen):
            with tempfile.TemporaryDirectory() as d:
                updates._download_zip("http://x/u.zip", Path(d))
        import ssl
        self.assertIsInstance(captured["context"], ssl.SSLContext)
        self.assertEqual(captured["context"].verify_mode, ssl.CERT_REQUIRED)


class SslContext(unittest.TestCase):
    """The TLS context used for the check + download verifies certificates."""

    def test_is_a_verifying_context(self):
        import ssl
        ctx = updates._ssl_context()
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)


class WindowsUpdateScript(unittest.TestCase):
    """The detached swap-and-relaunch .bat must survive a console-less launch."""

    def _script(self) -> str:
        return updates._windows_update_script(
            Path(r"C:\Temp\spuk\extracted\Spuk"), Path(r"C:\Users\x\Spuk"), 4321
        )

    def test_does_not_use_console_only_timeout(self):
        # `timeout` needs a console input handle; the helper runs DETACHED (no
        # console), where it aborts instantly and busy-loops. Must use `ping`.
        script = self._script().lower()
        self.assertNotIn("timeout", script)
        self.assertIn("ping", script)

    def test_waits_on_our_pid_then_mirrors_then_relaunches(self):
        script = self._script()
        self.assertIn("4321", script)            # waits for THIS Spuk to exit
        self.assertIn("robocopy", script.lower())
        self.assertIn("Spuk.exe", script)

    def test_relaunches_even_if_the_in_place_swap_failed(self):
        # If robocopy can't write the install dir (locked / admin-only), the app
        # has already quit — it must still come back, from the downloaded copy.
        script = self._script()
        self.assertIn("if exist", script.lower())
        self.assertIn(r"C:\Temp\spuk\extracted\Spuk\Spuk.exe", script)  # fallback target


class ExtractUpdate(unittest.TestCase):
    """The extractor must preserve a macOS .app's symlink farm.

    Python's zipfile flattens symlinks into plain files, which corrupts a macOS
    .app bundle (every framework's ``Versions/Current`` link) so it won't launch
    ("Spuk can't be opened"). On macOS the extractor must use ditto, which keeps
    symlinks; other platforms fall back to the stdlib extractor.
    """

    @unittest.skipUnless(sys.platform == "darwin", "ditto + bundle symlinks are macOS-only")
    def test_macos_extract_preserves_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # A minimal framework-shaped bundle: Versions/A holds the real file;
            # Versions/Current and the top-level entry are symlinks into it.
            fw = root / "Spuk.app" / "Contents" / "Frameworks" / "Foo.framework"
            (fw / "Versions" / "A").mkdir(parents=True)
            (fw / "Versions" / "A" / "Foo").write_bytes(b"binary")
            (fw / "Versions" / "Current").symlink_to("A")
            (fw / "Foo").symlink_to("Versions/Current/Foo")
            zip_path = root / "u.zip"
            # Zip it exactly the way the release workflow does.
            subprocess.run(
                ["/usr/bin/ditto", "-c", "-k", "--keepParent", str(root / "Spuk.app"), str(zip_path)],
                check=True,
            )

            out = root / "out"
            out.mkdir()
            updates._extract_update(zip_path, out)

            current = out / "Spuk.app/Contents/Frameworks/Foo.framework/Versions/Current"
            top = out / "Spuk.app/Contents/Frameworks/Foo.framework/Foo"
            self.assertTrue(current.is_symlink(), "Versions/Current must stay a symlink, not a flattened file")
            self.assertEqual(os.readlink(current), "A")
            self.assertTrue(top.is_symlink(), "the framework's top-level entry must stay a symlink")

    def test_non_macos_uses_stdlib_zipfile(self):
        # Windows/Linux archives carry no symlinks, so the stdlib path is used —
        # and must not depend on macOS-only ditto.
        import zipfile as _zf

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            zip_path = root / "u.zip"
            with _zf.ZipFile(zip_path, "w") as z:
                z.writestr("hello.txt", "hi")
            out = root / "out"
            out.mkdir()
            with mock.patch.object(updates.sys, "platform", "win32"):
                updates._extract_update(zip_path, out)
            self.assertEqual((out / "hello.txt").read_text(), "hi")


if __name__ == "__main__":
    unittest.main()
