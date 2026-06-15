# Build Spuk on Windows. Run from the repo root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# Produces dist\Spuk\Spuk.exe (unsigned). See packaging\README.md for install.
#
# Prereqs on the Windows machine: Python 3.11 + uv installed.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> Creating Python 3.11 env (if missing)…"
uv venv --python 3.11 .venv
uv sync

Write-Host "==> Building Spuk.exe with PyInstaller…"
uv run --with pyinstaller pyinstaller `
    --clean --noconfirm --workpath build\pyi --distpath dist `
    packaging\spuk.spec

Write-Host ""
Write-Host "==> Done: dist\Spuk\Spuk.exe"
Write-Host "    First launch downloads the Whisper model (~480MB) to the user cache."
Write-Host "    Unsigned: Windows SmartScreen will warn -> 'More info' -> 'Run anyway'."
Write-Host "    See packaging\README.md for making a simple installer / shortcut."
