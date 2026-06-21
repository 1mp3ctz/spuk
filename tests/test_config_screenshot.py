from pathlib import Path

from spuk.config import load_config


def test_screenshot_config_loads_from_bundled_toml():
    cfg = load_config(Path("config.toml"))
    assert cfg.screenshot.enabled is True
    assert cfg.screenshot.gesture == "dual_cmd"


def test_screenshot_defaults_when_section_absent(tmp_path):
    src = Path("config.toml").read_text()
    trimmed = src.split("[screenshot]")[0]
    p = tmp_path / "old.toml"
    p.write_text(trimmed)
    cfg = load_config(p)
    assert cfg.screenshot.enabled is True
    assert cfg.screenshot.gesture == "dual_cmd"
