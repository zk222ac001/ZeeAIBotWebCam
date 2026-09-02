from pathlib import Path

from robotic_classroom.core.config import load_settings


def test_default_configuration_loads() -> None:
    settings = load_settings(Path("config.yaml"))
    assert settings.hardware.mode == "mock"
    assert settings.safety.motion_enabled is False
    assert settings.privacy.recording_enabled is False
    assert settings.privacy.face_recognition_enabled is False
