# PyInstaller spec for Spuk — builds a one-folder app on macOS and Windows.
#
# Run via the platform build scripts (build_macos.sh / build_windows.ps1), which
# invoke PyInstaller with this spec. Native ML libs (ctranslate2, av, faster-
# whisper, tokenizers) ship binary data that PyInstaller can't auto-discover, so
# we collect them explicitly.
#
# NOTE: must be built ON each target OS — you cannot cross-build a Windows .exe
# from macOS. This spec is shared; the output differs per platform.

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH is the directory holding this spec (packaging/); ROOT is the repo root.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hiddenimports = [], [], []
for pkg in ("ctranslate2", "faster_whisper", "av", "tokenizers", "pystray", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("pynput")

# Ship a default, user-editable config beside the app.
datas += [(os.path.join(ROOT, "config.toml"), ".")]

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "packaging", "spuk_launch.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Spuk uses only QtWidgets. Excluding the heavy unused Qt modules cuts the
    # bundle size dramatically and removes the QML/VirtualKeyboard frameworks
    # that carry the FinderInfo metadata which breaks codesigning.
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
        "PySide6.QtQuick3D", "PySide6.QtQuickControls2", "PySide6.QtQmlModels",
        "PySide6.QtQmlMeta", "PySide6.QtVirtualKeyboard",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
        "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtSensors",
        "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSql",
        "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtBluetooth",
        "PySide6.QtNfc", "PySide6.QtSerialPort", "PySide6.QtWebSockets",
        "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    ],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Spuk",
    console=False,          # no terminal window; it's a tray app
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Spuk")

# On macOS, wrap the collected folder into a proper .app bundle.
app = BUNDLE(
    coll,
    name="Spuk.app",
    bundle_identifier="dev.kotowski.spuk",
    info_plist={
        "LSUIElement": True,  # background/menu-bar app, no Dock icon
        "NSMicrophoneUsageDescription": "Spuk transcribes your speech locally.",
        "CFBundleShortVersionString": "0.2.0",
    },
)
