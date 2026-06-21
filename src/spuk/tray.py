"""Cross-platform system-tray UI (macOS menu bar + Windows system tray).

Uses pystray, which wraps the native tray APIs on macOS, Windows, and Linux, so
non-technical users get a clickable icon instead of a terminal. The tray runs on
the main thread (required on macOS); the global hotkey listener runs on a
background thread.
"""

from __future__ import annotations

import logging

from .config import Config, ScreenshotConfig
from .core import SpukCore
from .screenshot_gesture import start_if_enabled as _start_screenshot

log = logging.getLogger("spuk.tray")

# Friendly names for the languages we support.
LANGUAGE_NAMES = {"en": "English", "de": "Deutsch", "pl": "Polski"}


def _make_icon_image():
    """Generate a simple purple icon at runtime (no binary asset to ship)."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, size - 4, size - 4], radius=14, fill=(139, 92, 246, 255))
    # A small white "ghost" blob.
    d.ellipse([18, 14, 46, 42], fill=(255, 255, 255, 255))
    d.rectangle([18, 28, 46, 48], fill=(255, 255, 255, 255))
    for cx in (26, 38):
        d.ellipse([cx - 4, 24, cx + 4, 32], fill=(139, 92, 246, 255))
    return img


def run_tray(config: Config, core: SpukCore) -> None:
    import pystray
    from pystray import Menu, MenuItem
    from .settings_store import update_user_settings

    def lang_label(code: str) -> str:
        return LANGUAGE_NAMES.get(code, code)

    def set_lang(code: str):
        def _action(icon, item):
            core.set_language(code)
            icon.update_menu()
        return _action

    def is_lang(code: str):
        return lambda item: core.language == code

    language_items = [
        MenuItem(lang_label(code), set_lang(code), checked=is_lang(code), radio=True)
        for code in core.languages
    ]

    # Mutable container so the toggle callback can swap the handle.
    _tap = [None]

    def is_screenshot_enabled(item):
        return _tap[0] is not None

    def toggle_screenshot(icon, item):
        if _tap[0] is not None:
            _tap[0].stop()
            _tap[0] = None
            update_user_settings(screenshot_enabled=False)
        else:
            cfg = type("_C", (), {"screenshot": ScreenshotConfig(enabled=True)})()
            _tap[0] = _start_screenshot(cfg)
            update_user_settings(screenshot_enabled=True)
        icon.update_menu()

    def on_quit(icon, item):
        log.info("Quitting Spuk.")
        if _tap[0] is not None:
            _tap[0].stop()
        # Clean stop: end the tray loop and let the process exit normally. The
        # hotkey listener is a daemon thread, so it doesn't block shutdown.
        icon.stop()

    menu = Menu(
        MenuItem(lambda item: f"Spuk — {lang_label(core.language)}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("Language", Menu(*language_items)),
        MenuItem("Screenshot on ⌘ + ⌘", toggle_screenshot, checked=is_screenshot_enabled),
        Menu.SEPARATOR,
        MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon("spuk", _make_icon_image(), "Spuk", menu)

    # Refresh the menu (title + checkmark) when language changes via hotkey.
    core.on_language_change = lambda _lang: icon.update_menu()

    # Start the global hotkey backend on a background thread, then warm the
    # model, then block on the tray (main thread). Backend is pynput on
    # macOS/Windows, evdev on Linux — both return a handle with .stop().
    core.start_input()
    _tap[0] = _start_screenshot(config)
    log.info("Warming model… (first launch downloads it)")
    core.warm()
    log.info(
        "Spuk ready in the tray. Hold %s to dictate; %s cycles language.",
        config.hotkey.key, config.hotkey.cycle_language,
    )
    icon.run()
