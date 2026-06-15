"""macOS permission helpers for the global hotkey + synthetic paste.

The global push-to-talk hotkey is a pynput keyboard ``Listener``, which on macOS
is a CoreGraphics event tap. Modern macOS gates the hotkey + paste behind TWO
separate permissions:

  * **Input Monitoring** — required to *listen* for the global hotkey.
  * **Accessibility**    — required to *post* the synthetic Cmd+V paste.

Granting only Accessibility (what older Spuk versions prompted for) leaves the
hotkey silently dead: the app runs, but never hears the keys. We therefore:

  * check **silently** first, so an already-trusted launch shows NO popup
    (older Spuk re-fired the system dialog on every single launch);
  * only raise the system prompt when trust is actually missing;
  * always name *both* permissions in the guidance.

In dev (``uv run python -m spuk``) the "responsible process" macOS attributes the
permission to is the *terminal app*, not the bare Python binary — so trust must
be granted to that terminal (or to a built Spuk.app) and the host **fully
relaunched** before macOS applies it. That is why re-clicking the popup never
helps: macOS already remembers it asked you, and only applies grants to
freshly-started processes.
"""

from __future__ import annotations

import logging
import platform

log = logging.getLogger("spuk.permissions")

_GUIDANCE = (
    "Spuk needs macOS permission to hear the hotkey and paste text.\n"
    "  Open  System Settings → Privacy & Security  and turn ON the app that runs "
    "Spuk (the built Spuk.app, or — when running from a terminal — that terminal "
    "app) under BOTH of these:\n"
    "    - Input Monitoring   (so the hold-to-talk hotkey is heard)\n"
    "    - Accessibility      (so the transcribed text can be pasted)\n"
    "  Then FULLY QUIT (Cmd+Q) the app/terminal and relaunch — macOS only applies "
    "the grant to newly-started processes. The hotkey stays dead until you do.\n"
    "  Re-clicking the popup will NOT help: macOS only re-checks on a fresh launch."
)


def accessibility_trusted(prompt: bool = False) -> bool:
    """Whether this process is trusted for Accessibility.

    With ``prompt=False`` (default) the check is silent — no system dialog. With
    ``prompt=True`` macOS shows its Accessibility prompt when trust is missing
    (and registers the app in System Settings). Non-macOS / missing API → True.
    """
    if platform.system() != "Darwin":
        return True
    try:
        if prompt:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
                kAXTrustedCheckOptionPrompt,
            )

            return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not check Accessibility trust: %s", exc)
        return True  # don't block where the API is unavailable


_LISTEN_EVENT = 1  # kIOHIDRequestTypeListenEvent
_ACCESS_GRANTED = 0  # kIOHIDAccessTypeGranted (1=denied, 2=unknown/not-determined)
_iokit_cache: dict | None = None


def _iokit() -> dict:
    """Load IOHIDCheckAccess / IOHIDRequestAccess from IOKit (cached).

    These C functions aren't exposed on pyobjc's ``Quartz`` namespace in every
    build, so we load them straight from the framework. Returns {} on failure.
    """
    global _iokit_cache
    if _iokit_cache is not None:
        return _iokit_cache
    funcs: dict = {}
    try:
        import objc

        iokit = objc.loadBundle(
            "IOKit", {}, bundle_path="/System/Library/Frameworks/IOKit.framework"
        )
        objc.loadBundleFunctions(
            iokit,
            funcs,
            [("IOHIDCheckAccess", b"Ii"), ("IOHIDRequestAccess", b"Zi")],
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not load IOKit Input-Monitoring functions: %s", exc)
    _iokit_cache = funcs
    return funcs


def input_monitoring_trusted() -> bool | None:
    """Whether this process may listen for global key events (Input Monitoring).

    Returns True/False when macOS can tell us, or None when the check is
    unavailable so callers can fall back gracefully. Never prompts.
    """
    if platform.system() != "Darwin":
        return True
    check = _iokit().get("IOHIDCheckAccess")
    if check is None:
        return None
    try:
        return check(_LISTEN_EVENT) == _ACCESS_GRANTED
    except Exception:  # noqa: BLE001
        return None


def request_input_monitoring() -> bool | None:
    """Trigger the macOS Input-Monitoring system prompt. Returns granted-or-not.

    Like the Accessibility prompt, a fresh grant only applies after the app is
    relaunched. Returns None when the API is unavailable.
    """
    if platform.system() != "Darwin":
        return True
    request = _iokit().get("IOHIDRequestAccess")
    if request is None:
        return None
    try:
        return bool(request(_LISTEN_EVENT))
    except Exception:  # noqa: BLE001
        return None


def ensure_permissions(prompt: bool = True) -> bool:
    """Ensure the hotkey + paste permissions are granted. Returns True if good.

    Silent when already trusted — no nagging popup. Only raises the system
    Accessibility prompt when trust is actually missing. Always True off macOS.
    The app should keep running even when this returns False (so the UI still
    appears); the hotkey simply won't fire until the user grants + relaunches.
    """
    if platform.system() != "Darwin":
        return True

    ax_ok = accessibility_trusted(prompt=False)
    im_ok = input_monitoring_trusted()  # True / False / None(unknown)

    # Good to go: Accessibility trusted AND Input Monitoring not explicitly denied.
    if ax_ok and im_ok is not False:
        log.debug("macOS permissions OK (accessibility=%s, input_monitoring=%s).", ax_ok, im_ok)
        return True

    # Something's missing. Raise BOTH system prompts so the user can grant them in
    # one go. Each grant only takes effect after the app is relaunched.
    if prompt:
        if not ax_ok:
            accessibility_trusted(prompt=True)
        if im_ok is False:
            request_input_monitoring()

    log.warning("%s", _GUIDANCE)
    return False


# Backwards-compatible alias: older call sites imported ``ensure_accessibility``.
def ensure_accessibility(prompt: bool = True) -> bool:
    return ensure_permissions(prompt=prompt)
