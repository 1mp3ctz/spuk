"""Selects the global-hotkey backend by platform — the input seam.

The chord/double-tap/toggle FSM lives in :class:`~spuk.hotkey.HotkeyListener` and
is platform-neutral. What differs per OS is only *how key events reach it*:

  * **macOS / Windows** — pynput's keyboard ``Listener`` (unchanged behaviour).
    The ``HotkeyListener`` itself owns that listener, so it IS the backend.
  * **Linux** — :class:`~spuk.linux_input.LinuxHotkeySource`, which reads
    ``/dev/input`` via evdev (works under X11 *and* Wayland, unlike pynput) and
    feeds the very same FSM.

Both backends expose the same tiny surface the app already relied on:
``run()`` (block) and ``start()`` (background; returns a handle with ``stop()``).
Selection is by ``platform.system()`` and nothing else — minimal and obvious.

Importing this module on macOS/Windows must not import evdev: the Linux branch
imports ``linux_input`` lazily, only when actually on Linux.
"""

from __future__ import annotations

import platform

from .hotkey import HotkeyListener


def make_input_backend(listener: HotkeyListener):
    """Return the hotkey backend for this platform, driving ``listener``'s FSM.

    On Linux this wraps the listener in a :class:`LinuxHotkeySource`; elsewhere
    the ``HotkeyListener`` (pynput) is itself the backend, so behaviour on
    macOS/Windows is byte-for-byte what it was before the seam existed.
    """
    if platform.system() == "Linux":
        from .linux_input import LinuxHotkeySource

        return LinuxHotkeySource(listener)
    return listener
