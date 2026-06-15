"""User settings persistence.

The bundled ``config.toml`` lives inside the (read-only) app bundle, so anything
the user changes at runtime — their chosen languages, the active language, the
microphone — is saved here instead, in a per-user, writable location:

  * macOS:   ~/Library/Application Support/Spuk/settings.json
  * Windows: %APPDATA%\\Spuk\\settings.json
  * Linux:   $XDG_CONFIG_HOME/Spuk/settings.json  (or ~/.config/Spuk)

These values are overlaid on top of the bundled defaults at startup (see
``config.load_config``) and re-saved whenever the user changes something.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from pathlib import Path

log = logging.getLogger("spuk.settings")

APP_NAME = "Spuk"


def user_config_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def settings_path() -> Path:
    return user_config_dir() / "settings.json"


def load_user_settings() -> dict:
    """Return saved settings, or {} if none/unreadable (never raises)."""
    path = settings_path()
    try:
        if path.exists():
            data = json.loads(path.read_text("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read settings (%s); using defaults.", exc)
    return {}


def save_user_settings(data: dict) -> None:
    """Write the full settings dict (best-effort; never raises)."""
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not save settings to %s: %s", path, exc)


def update_user_settings(**changes) -> None:
    """Merge the given keys into the saved settings and write them back."""
    data = load_user_settings()
    data.update(changes)
    save_user_settings(data)
