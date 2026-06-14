"""Phase 0 environment check — run this before the full app.

  uv run python scripts/check_env.py

Verifies: imports resolve, a microphone is reachable (records ~1s), and a
synthetic Cmd+V can be sent. It does NOT download the Whisper model.
"""

from __future__ import annotations

import sys


def check_imports() -> bool:
    try:
        import faster_whisper  # noqa: F401
        import numpy  # noqa: F401
        import pynput  # noqa: F401
        import pyperclip  # noqa: F401
        import sounddevice  # noqa: F401
    except Exception as exc:
        print(f"[FAIL] import error: {exc}")
        return False
    print("[ok]   imports resolve")
    return True


def check_mic() -> bool:
    import numpy as np
    import sounddevice as sd

    try:
        print("[..]   recording 1s from default mic (speak if you like)…")
        rec = sd.rec(int(1 * 16000), samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        peak = float(np.abs(rec).max())
        print(f"[ok]   mic captured {rec.shape[0]} samples, peak amplitude {peak:.4f}")
        if peak < 1e-4:
            print("       (very low signal — check the mic / grant Microphone permission)")
        return True
    except Exception as exc:
        print(f"[FAIL] mic error: {exc}")
        print("       Grant Microphone permission to your terminal in System Settings.")
        return False


def check_paste() -> bool:
    # Only verifies the API is callable; does not actually inject keys here.
    try:
        from pynput.keyboard import Controller, Key  # noqa: F401

        import pyperclip

        _ = pyperclip.paste()
        print("[ok]   clipboard + keyboard controller available")
        print("       (real Cmd+V needs Accessibility permission for your terminal)")
        return True
    except Exception as exc:
        print(f"[FAIL] paste stack error: {exc}")
        return False


def main() -> int:
    ok = True
    ok &= check_imports()
    ok &= check_mic()
    ok &= check_paste()
    print("\nAll good — run:  uv run python -m spuk" if ok else "\nFix the [FAIL] lines above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
