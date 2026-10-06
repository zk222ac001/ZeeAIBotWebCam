from pathlib import Path

import pytest
from pydantic import ValidationError

from robotic_classroom.core.config import AutonomyConfig, ConferenceConfig, load_settings


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


def test_rotation_only_autonomy_rejects_forward_enable() -> None:
    with pytest.raises(ValidationError, match="requires forward_enabled=false"):
        AutonomyConfig(execution_policy="rotation_only", forward_enabled=True)


def test_phase14_safe_defaults_require_pilot_validation() -> None:
    config = AutonomyConfig()

    assert config.mode == "plan_only"
    assert config.execution_policy == "rotation_only"
    assert config.require_pilot_validation is True
    assert config.pilot_validated is False
