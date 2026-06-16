"""Cross-platform system-tray UI (macOS menu bar + Windows system tray).

Uses pystray, which wraps the native tray APIs on macOS, Windows, and Linux, so
non-technical users get a clickable icon instead of a terminal. The tray runs on
the main thread (required on macOS); the global hotkey listener runs on a
background thread.
"""

from __future__ import annotations

import logging

from .config import Config
from .core import SpukCore

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

    def on_quit(icon, item):
        log.info("Quitting Spuk.")
        core.stop_input()  # stop the background hotkey thread so the process exits
        icon.stop()

    menu = Menu(
        MenuItem(lambda item: f"Spuk — {lang_label(core.language)}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("Language", Menu(*language_items)),
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
    log.info("Warming model… (first launch downloads it)")
    core.warm()
    log.info(
        "Spuk ready in the tray. Hold %s to dictate; %s cycles language.",
        config.hotkey.key, config.hotkey.cycle_language,
    )
    icon.run()
