"""Linux input backend: evdev hotkey source + uinput/ydotool paste injection.

Why a separate backend (and not pynput) on Linux:
pynput cannot grab global keys or inject keystrokes under **Wayland** — its X11
event tap is a no-op there. Reading ``/dev/input/*`` via **evdev** and injecting
via **/dev/uinput** works under BOTH X11 and Wayland because it operates at the
kernel input layer, below the display server. This one backend is therefore how
Spuk satisfies "works for everyone" on Linux.

Everything that touches ``evdev`` is imported lazily, inside functions — never at
module top level — so importing this module (or anything that imports it, e.g.
``paste``) on macOS/Windows never pulls ``evdev`` (which only builds on Linux).
``linux_input_available()`` returns False (it never raises) when evdev is absent.

Two responsibilities:

  * **hotkey source** — :class:`LinuxHotkeySource` reads key events from every
    keyboard device and feeds canonical key down/up edges into the existing
    :class:`~spuk.hotkey.HotkeyListener` FSM (via ``_feed_press``/``_feed_release``),
    so the chord/double-tap/toggle logic is shared with the pynput path.
  * **paste injection** — :func:`build_linux_paste_injector` returns a callable
    that synthesizes Ctrl+V via a uinput virtual keyboard, falling back to the
    ``ydotool`` CLI when ``/dev/uinput`` is not usable.

The clipboard text itself is still set by pyperclip (see ``paste.py``); on Linux
pyperclip shells out to ``wl-clipboard`` (Wayland) or ``xclip``/``xsel`` (X11).
If none is installed, pyperclip raises and ``paste.py`` logs it; we also surface
a clear hint here via :func:`clipboard_tool_available`.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from typing import Callable

log = logging.getLogger("spuk.linux_input")

UINPUT_DEVICE = "/dev/uinput"


# --- evdev availability ----------------------------------------------------


def linux_input_available() -> bool:
    """True if the ``evdev`` module can be imported. Never raises.

    Returns False (not an exception) on non-Linux or when evdev is missing, so
    callers can degrade gracefully and log a clear remedy instead of crashing.
    """
    try:
        import evdev  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - ImportError on non-Linux; be defensive
        log.debug("evdev unavailable: %s", exc)
        return False
    return True


# --- evdev keycode -> canonical (pynput) key translation -------------------
#
# The chord FSM matches against the canonical keys that
# ``pynput.keyboard.HotKey.parse('<ctrl>+<alt>')`` produces: the GENERIC modifier
# members ``Key.ctrl`` / ``Key.alt`` / ``Key.shift`` / ``Key.cmd`` and
# ``KeyCode.from_char('l')`` for letters. We translate each evdev key by its NAME
# (e.g. ``"KEY_LEFTCTRL"``, ``"KEY_L"``) so both left and right physical
# modifiers canonicalise to the SAME generic modifier — and so there are no magic
# keycode integers here (evdev supplies the names at runtime).

# evdev key-name -> generic pynput modifier member name. Left/right collapse to
# one logical modifier so the user can hold either Ctrl/Alt/Shift/Meta.
_MODIFIER_NAME_TO_PYNPUT: dict[str, str] = {
    "KEY_LEFTCTRL": "ctrl",
    "KEY_RIGHTCTRL": "ctrl",
    "KEY_LEFTALT": "alt",
    "KEY_RIGHTALT": "alt",
    "KEY_LEFTSHIFT": "shift",
    "KEY_RIGHTSHIFT": "shift",
    "KEY_LEFTMETA": "cmd",   # pynput names the Super/Meta/Win key 'cmd'
    "KEY_RIGHTMETA": "cmd",
}


def canonical_key_for_keyname(name: str):
    """Map a single evdev key name to the canonical pynput key, or ``None``.

    Pure (no evdev import): takes evdev's ``KEY_*`` name string and returns the
    object the chord FSM expects — a ``pynput.keyboard.Key`` for modifiers or a
    ``KeyCode`` for a printable character (``KEY_L`` -> ``KeyCode.from_char('l')``).
    Returns ``None`` for keys Spuk's hotkeys never use, so the reader can skip them.

    ``name`` may be a single string; evdev sometimes maps one keycode to a list of
    names — callers should resolve that to a single name first (see
    :func:`canonical_key_for_keynames`).
    """
    from pynput.keyboard import Key, KeyCode

    mod = _MODIFIER_NAME_TO_PYNPUT.get(name)
    if mod is not None:
        return getattr(Key, mod)

    # Printable single letters/digits: "KEY_L" -> 'l', "KEY_5" -> '5'.
    if name.startswith("KEY_"):
        tail = name[len("KEY_"):]
        if len(tail) == 1 and (tail.isalpha() or tail.isdigit()):
            return KeyCode.from_char(tail.lower())

    return None


def canonical_key_for_keynames(names) -> object | None:
    """Resolve evdev's per-keycode name(s) to one canonical pynput key.

    ``evdev.ecodes.KEY[code]`` is sometimes a single name and sometimes a list of
    aliases for the same physical key. Return the first name that maps to a key
    the FSM cares about; ``None`` if none do.
    """
    if isinstance(names, (list, tuple)):
        for name in names:
            key = canonical_key_for_keyname(name)
            if key is not None:
                return key
        return None
    return canonical_key_for_keyname(names)


# --- hotkey source ---------------------------------------------------------


def _keyboard_devices():
    """Yield evdev ``InputDevice``s that look like keyboards (expose EV_KEY).

    A device qualifies if it advertises EV_KEY and at least one of the standard
    typing keys, which filters out mice/touchpads that also emit a few EV_KEY
    codes (e.g. BTN_LEFT) without being keyboards.
    """
    import evdev
    from evdev import ecodes

    sentinel_keys = {ecodes.KEY_A, ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_LEFTCTRL}
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except Exception as exc:  # noqa: BLE001 - perms / device vanished
            log.debug("Skipping %s: %s", path, exc)
            continue
        caps = dev.capabilities()
        key_codes = caps.get(ecodes.EV_KEY, [])
        if key_codes and any(code in key_codes for code in sentinel_keys):
            yield dev
        else:
            dev.close()


class LinuxHotkeySource:
    """Reads evdev key events on a background thread and feeds the chord FSM.

    Construct with the configured :class:`~spuk.hotkey.HotkeyListener`; call
    :meth:`start` to read every keyboard device, or :meth:`run` to block. Key
    events are translated to canonical pynput keys and pushed into the listener's
    ``_feed_press`` / ``_feed_release`` so all chord/tap behaviour is shared.
    """

    def __init__(self, listener) -> None:
        self._listener = listener
        self._devices: list = []
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

    # -- device handling --
    def _open_devices(self) -> list:
        if not linux_input_available():
            log.error(
                "Linux input backend needs python-evdev, which isn't installed. "
                "Install it (Linux only) or the hotkey cannot be read."
            )
            return []
        devices = list(_keyboard_devices())
        if not devices:
            log.error(
                "No readable keyboard input devices found under /dev/input. The "
                "hotkey will not fire. Add your user to the 'input' group: "
                "`sudo usermod -aG input $USER`, then log out and back in."
            )
        else:
            log.info("Reading hotkey from %d keyboard device(s).", len(devices))
        return devices

    def _read_device(self, device) -> None:
        """Blocking read loop for one device. Runs on its own daemon thread."""
        from evdev import categorize, ecodes

        try:
            for event in device.read_loop():
                if self._stop.is_set():
                    return
                if event.type != ecodes.EV_KEY:
                    continue
                self._handle_key_event(categorize(event), ecodes)
        except OSError as exc:
            # Device unplugged / lost; not fatal for the others.
            log.debug("Input device read ended (%s): %s", device.path, exc)
        except Exception as exc:  # noqa: BLE001 - keep other devices alive
            log.error("Error reading input device %s: %s", device.path, exc)

    def _handle_key_event(self, key_event, ecodes) -> None:
        """Translate one categorized EV_KEY event and feed the FSM.

        key_event.keystate: 0 = up, 1 = down, 2 = autorepeat (held). We feed only
        true down (1) and up (0) edges; autorepeat is ignored so a held modifier
        doesn't re-trigger the chord.
        """
        scancode = key_event.scancode
        names = ecodes.KEY.get(scancode) if hasattr(ecodes.KEY, "get") else ecodes.KEY[scancode]
        canon = canonical_key_for_keynames(names)
        if canon is None:
            return
        if key_event.keystate == key_event.key_down:
            self._listener._feed_press(canon)
        elif key_event.keystate == key_event.key_up:
            self._listener._feed_release(canon)

    # -- lifecycle --
    def start(self) -> "LinuxHotkeySource":
        """Open keyboard devices and read them on daemon threads (non-blocking).

        Returns ``self`` so callers can hold it and later call :meth:`stop`,
        mirroring the pynput ``HotkeyListener.start()`` contract (whose handle is
        stopped on app quit). If no device could be opened, the source simply
        never feeds events — the app still runs.
        """
        self._devices = self._open_devices()
        for dev in self._devices:
            thread = threading.Thread(
                target=self._read_device, args=(dev,), name=f"spuk-evdev-{dev.path}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
        return self

    def run(self) -> None:
        """Start reading and block until :meth:`stop` (mirrors HotkeyListener.run)."""
        self.start()
        if not self._devices:
            return
        try:
            self._stop.wait()
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        for dev in self._devices:
            try:
                dev.close()
            except Exception:  # noqa: BLE001
                pass
        self._devices = []


# --- paste injection -------------------------------------------------------


def _uinput_writable() -> bool:
    """Whether ``/dev/uinput`` exists and this process can write to it."""
    return os.path.exists(UINPUT_DEVICE) and os.access(UINPUT_DEVICE, os.W_OK)


_PASTE_MODIFIER_KEYCODE_NAMES = {
    "<ctrl>": "KEY_LEFTCTRL",
    "<shift>": "KEY_LEFTSHIFT",
    "<alt>": "KEY_LEFTALT",
    "<cmd>": "KEY_LEFTMETA",
}


def _combo_to_keycodes(combo: str) -> list:
    """Map a canonical combo string ('<ctrl>+<shift>+v') to evdev keycodes.

    Modifiers first, then the key, in press order. Raises if a token has no evdev
    keycode (caller falls back to Ctrl+V).
    """
    from evdev import ecodes

    codes = []
    for tok in (t for t in combo.split("+") if t):
        if tok in _PASTE_MODIFIER_KEYCODE_NAMES:
            codes.append(getattr(ecodes, _PASTE_MODIFIER_KEYCODE_NAMES[tok]))
        elif tok.startswith("<") and tok.endswith(">"):
            codes.append(getattr(ecodes, f"KEY_{tok[1:-1].upper()}"))  # <f8> -> KEY_F8
        else:
            codes.append(getattr(ecodes, f"KEY_{tok.upper()}"))  # v -> KEY_V
    return codes


def _build_uinput_paste_injector(keycodes):
    """Injector that taps the paste combo through a uinput virtual keyboard, or None.

    Returns None when uinput can't be opened so the caller can fall back to
    ydotool. The virtual device is created once and reused.
    """
    try:
        from evdev import UInput, ecodes
    except Exception as exc:  # noqa: BLE001
        log.debug("Cannot import evdev.UInput: %s", exc)
        return None

    try:
        ui = UInput({ecodes.EV_KEY: keycodes}, name="spuk-virtual-keyboard")
    except Exception as exc:  # noqa: BLE001 - PermissionError / missing module
        log.debug("Could not open /dev/uinput for injection: %s", exc)
        return None

    def send_paste() -> None:
        for code in keycodes:  # modifiers then key
            ui.write(ecodes.EV_KEY, code, 1)
        ui.syn()
        for code in reversed(keycodes):  # release in reverse
            ui.write(ecodes.EV_KEY, code, 0)
        ui.syn()

    log.info("Linux paste injection: using /dev/uinput virtual keyboard.")
    return send_paste


def _build_ydotool_paste_injector(keycodes):
    """Injector that taps the paste combo via the ``ydotool`` CLI, or None if absent.

    ydotool takes evdev keycodes with a press/release suffix, e.g. Ctrl+V is
    "29:1 47:1 47:0 29:0" (29=LEFTCTRL, 47=V).
    """
    ydotool = shutil.which("ydotool")
    if not ydotool:
        return None

    seq = [f"{c}:1" for c in keycodes] + [f"{c}:0" for c in reversed(keycodes)]

    def send_paste() -> None:
        subprocess.run(
            [ydotool, "key", *seq],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    log.info("Linux paste injection: using ydotool CLI (%s).", ydotool)
    return send_paste


def build_linux_paste_injector(combo: str = "<ctrl>+v") -> Callable[[], None]:
    """Pick the Linux paste injector for ``combo``: prefer uinput, fall back to ydotool.

    ``combo`` is a canonical combo string ("<ctrl>+v", "<ctrl>+<shift>+v"). Always
    returns a callable. If neither path is available the returned callable logs a
    clear remedy (so a single failed paste doesn't crash the loop) rather than
    raising at construction time.
    """
    try:
        keycodes = _combo_to_keycodes(combo)
    except Exception as exc:  # noqa: BLE001 - unknown token or evdev missing
        log.warning("Could not map paste combo %r (%s); falling back.", combo, exc)
        try:
            from evdev import ecodes

            keycodes = [ecodes.KEY_LEFTCTRL, ecodes.KEY_V]
        except Exception:  # noqa: BLE001 - evdev unavailable; builders below will no-op
            keycodes = []

    injector = _build_uinput_paste_injector(keycodes) or _build_ydotool_paste_injector(keycodes)
    if injector is not None:
        return injector

    log.error(
        "No Linux paste method available: cannot write %s and 'ydotool' is not "
        "installed. Fix one of:\n"
        "  - add your user to the 'input' group and ensure /dev/uinput is writable "
        "(`sudo usermod -aG input $USER`, then re-login), or\n"
        "  - install and start ydotool (and its daemon ydotoold).",
        UINPUT_DEVICE,
    )

    def _unavailable() -> None:
        log.error("Paste skipped: no uinput/ydotool injection available on this Linux host.")

    return _unavailable


def build_linux_typer() -> Callable[[str], None] | None:
    """A typer that injects Unicode text via the ydotool CLI, or None if absent.

    ydotool's ``type`` synthesizes the characters through ``/dev/uinput`` (works on
    X11 and Wayland). Unlike Windows/macOS there's no clean layout-independent
    Unicode-injection API at the uinput level, so we lean on ydotool; when it isn't
    installed we return None and the caller falls back to clipboard paste (Linux
    terminals accept Ctrl+Shift+V, so there's no console paste gap to work around).
    """
    ydotool = shutil.which("ydotool")
    if not ydotool:
        return None

    def typer(text: str) -> None:
        subprocess.run(
            [ydotool, "type", text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    log.info("Linux type-out: using ydotool CLI (%s).", ydotool)
    return typer


# --- clipboard tooling hint ------------------------------------------------


def clipboard_tool_available() -> bool:
    """Whether a clipboard CLI pyperclip can use is installed (Wayland/X11)."""
    return any(shutil.which(tool) for tool in ("wl-copy", "xclip", "xsel"))
