"""Configuration loading for Spuk.

Reads ``config.toml`` into immutable dataclasses. We validate at this boundary
so the rest of the code can trust the values (see coding-style: validate at
system boundaries, fail fast with clear messages).
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Project root = two levels up from this file (src/spuk/config.py -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    """Find config.toml, working both in dev and inside a PyInstaller bundle.

    Order: a user-editable config.toml next to the executable, then the copy
    bundled with a frozen app, then the repo root for normal `python -m spuk`.
    """
    if getattr(sys, "frozen", False):  # running from a PyInstaller bundle
        beside_exe = Path(sys.executable).resolve().parent / "config.toml"
        if beside_exe.exists():
            return beside_exe
        return Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "config.toml"
    return PROJECT_ROOT / "config.toml"


DEFAULT_CONFIG_PATH = _default_config_path()


@dataclass(frozen=True)
class TranscribeConfig:
    engine: str
    model: str
    default_language: str
    languages: tuple[str, ...]
    device: str
    compute_type: str
    vad_filter: bool
    beam_size: int


@dataclass(frozen=True)
class HotkeyConfig:
    mode: str  # "push_to_talk" | "toggle"
    key: str
    cycle_language: str
    # Hands-free (push_to_talk only): double-tap the hotkey to start recording
    # without holding it, then press once more to stop + transcribe. Defaulted so
    # an older config.toml (without these keys) still loads.
    handsfree: bool = True
    double_tap_seconds: float = 0.4  # max gap/length of a tap; also the tap-vs-hold cutoff
    # Shortcut Spuk SENDS to paste the transcript. "" = the OS default (Cmd+V on
    # macOS, Ctrl+V elsewhere). Set to "<ctrl>+<shift>+v" for terminals (VS Code /
    # Cursor), where plain Ctrl+V isn't "paste".
    paste_key: str = ""


@dataclass(frozen=True)
class AudioConfig:
    samplerate: int
    channels: int
    min_seconds: float


@dataclass(frozen=True)
class PostProcessConfig:
    enabled: bool
    i_understand_this_costs_money: bool
    provider: str
    max_calls_per_day: int


@dataclass(frozen=True)
class Config:
    transcribe: TranscribeConfig
    hotkey: HotkeyConfig
    audio: AudioConfig
    post_process: PostProcessConfig


def _overlay_user_languages(t: dict) -> None:
    """Overlay the user's saved language choices onto the transcribe defaults.

    Mutates ``t`` in place. Keeps only known Whisper codes, and guarantees the
    active language is one of the available ones.
    """
    from .languages import is_supported
    from .settings_store import load_user_settings

    user = load_user_settings()

    chosen = user.get("languages")
    if isinstance(chosen, list):
        valid = tuple(c for c in chosen if isinstance(c, str) and is_supported(c))
        if valid:
            t["languages"] = valid

    default = user.get("default_language")
    if isinstance(default, str) and default in t["languages"]:
        t["default_language"] = default
    elif t.get("default_language") not in t.get("languages", ()):  # keep it consistent
        t["default_language"] = t["languages"][0] if t["languages"] else t.get("default_language")


def _overlay_user_hotkey(h: dict) -> None:
    """Overlay the user's saved hotkey choices (settings.json) onto the defaults.

    Mutates ``h`` in place. Ignores missing/blank/invalid values so a partial or
    absent settings.json simply leaves the bundled config.toml defaults in place.
    """
    from .settings_store import load_user_settings

    user = load_user_settings()

    key = user.get("hotkey_key")
    if isinstance(key, str) and key.strip():
        h["key"] = key

    cycle = user.get("hotkey_cycle_language")
    if isinstance(cycle, str) and cycle.strip():
        h["cycle_language"] = cycle

    mode = user.get("hotkey_mode")
    if mode in ("push_to_talk", "toggle"):
        h["mode"] = mode

    handsfree = user.get("hotkey_handsfree")
    if isinstance(handsfree, bool):
        h["handsfree"] = handsfree

    paste = user.get("paste_key")
    if isinstance(paste, str):
        h["paste_key"] = paste


def load_config(path: Path | None = None) -> Config:
    """Load and validate the TOML config. Raises with a clear message on error."""
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found at {cfg_path}. Copy config.toml from the repo root.")

    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)

    try:
        t = dict(raw["transcribe"])
        t["languages"] = tuple(t.get("languages", []))  # list -> immutable tuple
        _overlay_user_languages(t)
        transcribe = TranscribeConfig(**t)
        h = dict(raw["hotkey"])
        _overlay_user_hotkey(h)
        hotkey = HotkeyConfig(**h)
        audio = AudioConfig(**raw["audio"])
        post_process = PostProcessConfig(**raw["post_process"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid or incomplete config in {cfg_path}: {exc}") from exc

    if hotkey.mode not in ("push_to_talk", "toggle"):
        raise ValueError(f"hotkey.mode must be 'push_to_talk' or 'toggle', got {hotkey.mode!r}")

    if not transcribe.languages:
        raise ValueError("transcribe.languages must list at least one language code.")
    if transcribe.default_language not in transcribe.languages:
        raise ValueError(
            f"transcribe.default_language {transcribe.default_language!r} "
            f"must be one of transcribe.languages {transcribe.languages}."
        )

    return Config(transcribe=transcribe, hotkey=hotkey, audio=audio, post_process=post_process)
