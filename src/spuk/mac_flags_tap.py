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
