#!/usr/bin/env bash
# Build Spuk.app on macOS. Run from the repo root: bash packaging/build_macos.sh
# Produces dist/Spuk.app (unsigned). See packaging/README.md for signing + install.
set -euo pipefail

cd "$(dirname "$0")/.."

# On exFAT/non-HFS volumes macOS scatters AppleDouble "._*" sidecar files through
# the tree. PyInstaller's own --clean chokes trying to remove them, and they later
# break codesigning, so we clean the build dirs ourselves (deleting ._* first) and
# run PyInstaller WITHOUT --clean.
echo "==> Cleaning previous build artifacts…"
find build dist -name '._*' -delete 2>/dev/null || true
rm -rf build dist

echo "==> Building Spuk.app with PyInstaller (Python 3.11 env)…"
UV_LINK_MODE=copy uv run --with pyinstaller pyinstaller \
    --noconfirm --workpath build/pyi --distpath dist \
    packaging/spuk.spec

# Purge AppleDouble junk PyInstaller may have copied in, so codesign won't fail.
echo "==> Stripping AppleDouble sidecar files from the bundle…"
find dist/Spuk.app -name '._*' -delete 2>/dev/null || true

# Sign with our STABLE self-signed identity if it's available, else fall back to
# ad-hoc. The stable identity gives the bundle a constant code-signing identity
# ("certificate leaf = …"), so macOS keeps the user's Accessibility / Input
# Monitoring / Microphone grants across every update instead of resetting them on
# each ad-hoc rebuild. Override the identity/keychain via env for CI.
SIGN_IDENTITY="${SPUK_SIGN_IDENTITY:-Spuk Self-Signed}"
SIGN_KEYCHAIN="${SPUK_SIGN_KEYCHAIN:-spuk-codesign.keychain}"
if security find-identity -v -p codesigning "$SIGN_KEYCHAIN" 2>/dev/null | grep -q "$SIGN_IDENTITY"; then
    echo "==> Signing with stable identity: $SIGN_IDENTITY"
    codesign --force --deep --sign "$SIGN_IDENTITY" --keychain "$SIGN_KEYCHAIN" dist/Spuk.app
    codesign -d -r- dist/Spuk.app 2>&1 | grep -i designated || true
else
    echo "==> Stable identity not found — ad-hoc signing (permissions will reset on update)."
    codesign --force --deep --sign - dist/Spuk.app
fi

echo
echo "==> Done: dist/Spuk.app"
echo "    First launch downloads the Whisper model (~480MB) to the user cache."
echo "    First launch on each Mac still needs right-click -> Open once (Gatekeeper);"
echo "    the stable signature keeps permission grants across later updates."
