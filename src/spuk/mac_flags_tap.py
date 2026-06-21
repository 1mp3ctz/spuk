"""macOS dual-Command gesture: a listen-only flagsChanged CGEventTap.

Spuk's pynput pipeline canonicalises left/right ⌘ into one Key.cmd, so it can't
see "both ⌘". This reads the LIVE device-specific modifier bits from each
flagsChanged event instead. Reading state (not counting edges) means a dropped
event self-corrects on the next one — the gesture cannot wedge.

Device-dependent modifier masks (Apple, IOKit/hidsystem/IOLLEvent.h NX_*):
    left ctrl 0x1  left shift 0x2  right shift 0x4  left cmd 0x8
    right cmd 0x10 left alt 0x20  right alt 0x40   right ctrl 0x2000
    fn/secondary 0x800000 (kCGEventFlagMaskSecondaryFn)
Caps-lock (0x10000) is intentionally NOT in OTHER_MODS — it must not block.
"""

from __future__ import annotations

import logging
import platform
import threading
from typing import Callable

log = logging.getLogger("spuk.mac_flags_tap")

CMD_L = 0x00000008
CMD_R = 0x00000010
OTHER_MODS = (
    0x00000001  # left ctrl
    | 0x00000002  # left shift
    | 0x00000004  # right shift
    | 0x00000020  # left alt
    | 0x00000040  # right alt
    | 0x00002000  # right ctrl
    | 0x00800000  # fn / secondary
)


def both_cmd_only(flags: int) -> bool:
    """True iff both ⌘ are held and no other modifier (caps-lock ignored)."""
    return bool(flags & CMD_L) and bool(flags & CMD_R) and not (flags & OTHER_MODS)


def dual_cmd_edge(active: bool, armed: bool) -> tuple[bool, bool]:
    """Edge detector. Returns (fire, new_armed): fire once on the rising edge."""
    if active and not armed:
        return True, True
    if not active:
        return False, False
    return False, True


class MacFlagsTap:
    """Listen-only flagsChanged tap that fires ``on_dual_cmd`` on both-⌘.

    The stateful edge logic lives in ``_handle_flags`` (unit-tested directly).
    ``start`` installs a real CGEventTap on a background CFRunLoop; the tap's C
    callback only extracts the flags and calls ``_handle_flags`` — so all behaviour
    is testable without a real tap.
    """

    def __init__(self, on_dual_cmd: Callable[[], None]) -> None:
        self._cb = on_dual_cmd
        self._armed = False
        self._tap = None
        self._runloop_source = None
        self._runloop = None
        self._thread: threading.Thread | None = None

    def _handle_flags(self, flags: int) -> None:
        active = both_cmd_only(flags)
        fire, self._armed = dual_cmd_edge(active, self._armed)
        if fire:
            try:
                self._cb()
            except Exception as exc:  # noqa: BLE001 - never kill the tap thread
                log.error("dual-⌘ handler failed: %s", exc)

    def start(self) -> "MacFlagsTap":
        if platform.system() != "Darwin":
            return self
        self._thread = threading.Thread(target=self._run, name="spuk-flags-tap", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        import Quartz

        def callback(proxy, type_, event, refcon):
            try:
                self._handle_flags(int(Quartz.CGEventGetFlags(event)))
            except Exception as exc:  # noqa: BLE001
                log.debug("CGEventGetFlags error: %s", exc)
            return event  # listen-only: pass the event through unchanged

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged),
            callback,
            None,
        )
        if not self._tap:
            log.warning("Could not create flags event tap (Input Monitoring needed?).")
            return
        self._runloop_source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._runloop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._runloop, self._runloop_source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        Quartz.CFRunLoopRun()

    def stop(self) -> None:
        if platform.system() != "Darwin":
            return
        try:
            import Quartz

            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, False)
            if self._runloop is not None:
                Quartz.CFRunLoopStop(self._runloop)
        except Exception as exc:  # noqa: BLE001
            log.debug("flags tap stop error: %s", exc)
