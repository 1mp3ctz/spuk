from spuk.config import load_config, AppleSpeechConfig  # noqa: F401


def test_apple_speech_config_defaults_when_section_absent(tmp_path):
    """Load a config.toml that has no [apple_speech] section — defaults apply."""
    minimal = tmp_path / "config.toml"
    minimal.write_text(
        "[transcribe]\n"
        'engine = "faster-whisper"\nmodel = "small"\ndefault_language = "en"\n'
        'languages = ["en"]\ndevice = "cpu"\ncompute_type = "int8"\n'
        "vad_filter = true\nbeam_size = 1\n\n"
        "[hotkey]\nmode = \"push_to_talk\"\nkey = \"<ctrl>+<alt>\"\n"
        "cycle_language = \"<ctrl>+<shift>+l\"\n\n"
        "[audio]\nsamplerate = 16000\nchannels = 1\nmin_seconds = 0.3\n\n"
        "[post_process]\nenabled = false\ni_understand_this_costs_money = false\n"
        'provider = "claude"\nmax_calls_per_day = 50\n'
    )
    cfg = load_config(minimal)
    assert cfg.apple_speech.enabled is True


def test_apple_speech_config_honours_toml(tmp_path):
    minimal = tmp_path / "config.toml"
    minimal.write_text(
        "[transcribe]\n"
        'engine = "faster-whisper"\nmodel = "small"\ndefault_language = "en"\n'
        'languages = ["en"]\ndevice = "cpu"\ncompute_type = "int8"\n'
        "vad_filter = true\nbeam_size = 1\n\n"
        "[hotkey]\nmode = \"push_to_talk\"\nkey = \"<ctrl>+<alt>\"\n"
        "cycle_language = \"<ctrl>+<shift>+l\"\n\n"
        "[audio]\nsamplerate = 16000\nchannels = 1\nmin_seconds = 0.3\n\n"
        "[post_process]\nenabled = false\ni_understand_this_costs_money = false\n"
        'provider = "claude"\nmax_calls_per_day = 50\n\n'
        "[apple_speech]\nenabled = false\n"
    )
    cfg = load_config(minimal)
    assert cfg.apple_speech.enabled is False


def test_speech_recognition_authorized_uses_status():
    from spuk import permissions
    import spuk.apple_speech as asp

    original = asp.speech_auth_status

    asp.speech_auth_status = lambda: "authorized"
    assert permissions.speech_recognition_authorized() is True

    asp.speech_auth_status = lambda: "denied"
    assert permissions.speech_recognition_authorized() is False

    asp.speech_auth_status = lambda: "not_determined"
    assert permissions.speech_recognition_authorized() is None

    asp.speech_auth_status = original
