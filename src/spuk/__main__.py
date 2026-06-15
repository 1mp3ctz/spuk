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
        help="Run without the tray icon (terminal only).",
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

    try:
        from .tray import run_tray
    except Exception as exc:  # pystray/Pillow missing or no display
        logging.getLogger("spuk").warning("Tray unavailable (%s) — running headless.", exc)
        core.warm()
        core.run_headless()
        return

    run_tray(config, core)


if __name__ == "__main__":
    main()
