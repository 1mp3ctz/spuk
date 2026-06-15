#!/usr/bin/env bash
# Build Spuk.app on macOS. Run from the repo root: bash packaging/build_macos.sh
# Produces dist/Spuk.app (unsigned). See packaging/README.md for signing + install.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Building Spuk.app with PyInstaller (Python 3.11 env)…"
UV_LINK_MODE=copy uv run --with pyinstaller pyinstaller \
    --clean --noconfirm --workpath build/pyi --distpath dist \
    packaging/spuk.spec

echo
echo "==> Done: dist/Spuk.app"
echo "    First launch downloads the Whisper model (~480MB) to the user cache."
echo "    Ad-hoc sign (runs on THIS Mac only):"
echo "      codesign --force --deep --sign - dist/Spuk.app"
echo "    For your parents' Macs without a paid signing cert, they must right-click"
echo "    the app -> Open the first time (Gatekeeper). See packaging/README.md."
