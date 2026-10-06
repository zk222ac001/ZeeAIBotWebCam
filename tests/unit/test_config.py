from pathlib import Path

import pytest
from pydantic import ValidationError

from robotic_classroom.core.config import ConferenceConfig, load_settings


def test_default_configuration_loads() -> None:
    settings = load_settings(Path("config.yaml"))
    assert settings.hardware.mode == "mock"
    assert settings.safety.motion_enabled is False
    assert settings.privacy.recording_enabled is False
    assert settings.privacy.face_recognition_enabled is False


def test_aec_reference_requires_mono_remote_audio() -> None:
    with pytest.raises(ValidationError, match="requires mono remote audio"):
        ConferenceConfig(echo_reference_enabled=True, remote_audio_channels=2)


def test_aec_reference_mode_requires_reference_mirroring_enabled() -> None:
    with pytest.raises(ValidationError, match="requires echo_reference_enabled=true"):
        ConferenceConfig(echo_management_mode="aec_reference")


def test_aec_reference_monitor_configuration_is_valid() -> None:
    config = ConferenceConfig(
        echo_reference_enabled=True,
        echo_reference_device="plughw:CARD=Array,DEV=0",
        echo_management_mode="monitor",
        remote_audio_channels=1,
    )

    assert config.echo_reference_enabled is True
    assert config.echo_reference_device == "plughw:CARD=Array,DEV=0"
