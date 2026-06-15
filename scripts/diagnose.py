"""Permission + hotkey diagnostic.

  uv run python scripts/diagnose.py

Tells us three things directly:
  1. Is this process trusted for Accessibility? (the thing the hotkey needs)
  2. Is a microphone visible?
  3. Does the key listener actually receive keystrokes?
Press keys (especially Ctrl+Option) during the 20-second window.
"""

from __future__ import annotations

import platform
import time

print("=== Spuk diagnostic ===")
print("platform:", platform.platform())

# 1. Accessibility trust (macOS) -------------------------------------------
if platform.system() == "Darwin":
    try:
        from ApplicationServices import AXIsProcessTrusted

        print("Accessibility trusted (AXIsProcessTrusted):", AXIsProcessTrusted())
    except Exception as exc:  # noqa: BLE001
        print("Could not check AXIsProcessTrusted:", exc)

# 2. Microphone visibility -------------------------------------------------
try:
    import sounddevice as sd

    dev = sd.query_devices(kind="input")
    print("Default input device:", dev["name"])
except Exception as exc:  # noqa: BLE001
    print("Mic query error:", exc)

# 3. Key listener -----------------------------------------------------------
from pynput import keyboard

events = {"n": 0}


def on_press(key):
    events["n"] += 1
    print("  KEY DOWN:", key)


def on_release(key):
    print("  KEY UP:  ", key)


print("\n>>> Press keys now — especially hold Ctrl+Option. Listening for 20 seconds...\n")
with keyboard.Listener(on_press=on_press, on_release=on_release):
    t0 = time.time()
    while time.time() - t0 < 20:
        time.sleep(0.1)

print(f"\nReceived {events['n']} key events.")
if events["n"] == 0:
    print("=> 0 events: the listener is NOT trusted. Accessibility is not actually granted")
    print("   to THIS terminal, or the terminal wasn't fully quit (Cmd+Q) after granting.")
else:
    print("=> Listener works. If the app still ignores the hotkey, it's a hotkey-matching issue.")
