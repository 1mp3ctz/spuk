"""Entry point.

  uv run python -m spuk              # system-tray app (default; what users get)
  uv run python -m spuk --headless   # terminal-only loop (handy for dev)
"""

from __future__ import annotations

import argparse
import logging

from .config import load_config
from .core import SpukCore
from .permissions import ensure_accessibility


def main() -> None:
    parser = argparse.ArgumentParser(prog="spuk", description="Local dictation.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run with no UI (terminal only).",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Run with the menu-bar/tray icon instead of the floating bar.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy third-party loggers so Spuk's own output is readable.
    for noisy in ("httpx", "httpcore", "huggingface_hub", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Trigger the macOS Accessibility prompt early (and register the app in
    # System Settings). The hotkey/paste won't work until this is granted.
    ensure_accessibility(prompt=True)

    config = load_config()
    core = SpukCore(config)

    if args.headless:
        core.warm()
        core.run_headless()
        return

    if args.tray:
        try:
            from .tray import run_tray
        except Exception as exc:  # pystray/Pillow missing
            logging.getLogger("spuk").warning("Tray unavailable (%s) — headless.", exc)
            core.warm()
            core.run_headless()
            return
        run_tray(config, core)
        return

    # Default: the floating bar (Qt). Falls back to headless if Qt is missing.
    try:
        from .ui_bar import run_bar
    except Exception as exc:  # PySide6 missing or no display
        logging.getLogger("spuk").warning("Floating bar unavailable (%s) — headless.", exc)
        core.warm()
        core.run_headless()
        return

    run_bar(config, core)


if __name__ == "__main__":
    main()
