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
        transcribe = TranscribeConfig(**t)
        hotkey = HotkeyConfig(**raw["hotkey"])
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
