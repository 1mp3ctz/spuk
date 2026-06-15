# PyInstaller spec for Spuk — builds a one-folder app on macOS and Windows.
#
# Run via the platform build scripts (build_macos.sh / build_windows.ps1), which
# invoke PyInstaller with this spec. Native ML libs (ctranslate2, av, faster-
# whisper, tokenizers) ship binary data that PyInstaller can't auto-discover, so
# we collect them explicitly.
#
# NOTE: must be built ON each target OS — you cannot cross-build a Windows .exe
# from macOS. This spec is shared; the output differs per platform.

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("ctranslate2", "faster_whisper", "av", "tokenizers", "pystray", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("pynput")

# Ship a default, user-editable config beside the app.
datas += [("../config.toml", ".")]

block_cipher = None

a = Analysis(
    ["../src/spuk/__main__.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
        "CFBundleShortVersionString": "0.1.0",
    },
)
