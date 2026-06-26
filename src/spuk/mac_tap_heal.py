"""Make pynput's macOS keyboard tap self-heal after macOS disables it.

macOS disables a CGEventTap on ``kCGEventTapDisabledByTimeout`` /
``kCGEventTapDisabledByUserInput`` and across sleep/wake. pynput's darwin backend
enables its tap once at startup and never re-enables it (it doesn't even keep the
tap handle around), so the global push-to-talk hotkey silently dies until Spuk is
restarted. We wrap pynput's tap callback to re-enable the tap on those events.

Spuk's own Fn/dual-⌘ tap (``mac_flags_tap.py``) already self-heals the same way;
this module covers the pynput hotkey path. The patch is idempotent, guarded, and
a no-op off macOS or if pynput's internals ever change — it only *adds* recovery,
it never alters normal key handling.
"""

from __future__ import annotations

import logging
import platform

log = logging.getLogger("spuk.mac_tap_heal")

# Apple CGEventTypes.h sentinels delivered to a tap callback when the system
# disables the tap (ByTimeout = 0xFFFFFFFE, ByUserInput = 0xFFFFFFFF). Stable ABI.
_TAP_DISABLED = (0xFFFFFFFE, 0xFFFFFFFF)


def _apply_patch(mixin, quartz, disabled=_TAP_DISABLED) -> bool:
    """Patch a pynput darwin ListenerMixin class so its tap re-enables on disable.

    Wraps ``_create_event_tap`` (to remember the tap handle on the instance) and
    ``_handler`` (to re-enable that tap on a disable event, then short-circuit).
    Returns True if applied, False if already applied or the class lacks the
    expected internals. Pure of any real pynput/Quartz import so it's unit-testable.
    """
    if getattr(mixin, "_spuk_healing", False):
        return False
    if not hasattr(mixin, "_create_event_tap") or not hasattr(mixin, "_handler"):
        return False

    orig_create = mixin._create_event_tap
    orig_handler = mixin._handler

    def _create_and_store(self):
        tap = orig_create(self)
        self._spuk_tap = tap  # remember it so _handler can re-enable it
        return tap

    def _healing_handler(self, proxy, event_type, event, refcon):
        if event_type in disabled:
            tap = getattr(self, "_spuk_tap", None)
            if tap is not None:
                quartz.CGEventTapEnable(tap, True)
                log.info("Re-enabled the keyboard event tap after macOS disabled it.")
            return event
        return orig_handler(self, proxy, event_type, event, refcon)

    mixin._create_event_tap = _create_and_store
    mixin._handler = _healing_handler
    mixin._spuk_healing = True
    return True


def install_pynput_tap_healing() -> None:
    """Install the self-heal patch on the real pynput backend (macOS only)."""
    if platform.system() != "Darwin":
        return
    try:
        import Quartz
        from pynput._util import darwin as _d
    except Exception as exc:  # pynput/Quartz absent or restructured
        log.debug("tap-healing not installed: %s", exc)
        return
    mixin = getattr(_d, "ListenerMixin", None)
    if mixin is None:
        log.debug("tap-healing not installed: ListenerMixin missing")
        return
    if _apply_patch(mixin, Quartz):
        log.debug("pynput tap-healing installed.")
