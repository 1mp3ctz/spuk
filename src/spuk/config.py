"""Configuration loading for Spuk.

Reads ``config.toml`` into immutable dataclasses. We validate at this boundary
so the rest of the code can trust the values (see coding-style: validate at
system boundaries, fail fast with clear messages).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

# Project root = two levels up from this file (src/spuk/config.py -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"


@dataclass(frozen=True)
class TranscribeConfig:
    engine: str
    model: str
    language: str
    device: str
    compute_type: str
    vad_filter: bool
    beam_size: int


@dataclass(frozen=True)
class HotkeyConfig:
    mode: str  # "push_to_talk" | "toggle"
    key: str


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
        transcribe = TranscribeConfig(**raw["transcribe"])
        hotkey = HotkeyConfig(**raw["hotkey"])
        audio = AudioConfig(**raw["audio"])
        post_process = PostProcessConfig(**raw["post_process"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid or incomplete config in {cfg_path}: {exc}") from exc

    if hotkey.mode not in ("push_to_talk", "toggle"):
        raise ValueError(f"hotkey.mode must be 'push_to_talk' or 'toggle', got {hotkey.mode!r}")

    return Config(transcribe=transcribe, hotkey=hotkey, audio=audio, post_process=post_process)
