from pathlib import Path

import pytest
from pydantic import ValidationError

from robotic_classroom.core.config import (
    AutonomyConfig,
    ConferenceConfig,
    SafetyConfig,
    load_settings,
)


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


@pytest.mark.parametrize("voltage", [0, -1, float("nan"), float("inf")])
def test_battery_cutoff_requires_positive_finite_voltage(voltage) -> None:
    with pytest.raises(ValidationError):
        SafetyConfig(minimum_battery_voltage=voltage)


def test_battery_cutoff_can_be_configured_without_guessing_default(monkeypatch) -> None:
    assert SafetyConfig().minimum_battery_voltage is None
    monkeypatch.setenv("SAFETY_MINIMUM_BATTERY_VOLTAGE", "6.5")
    assert load_settings("config.yaml").safety.minimum_battery_voltage == 6.5


@pytest.mark.parametrize("failure", ["disabled_media", "disabled_control", "shared", "whitespace"])
def test_production_configuration_refuses_insecure_access(failure):
    from robotic_classroom.core.config import Settings

    payload = load_settings("config.yaml").model_dump()
    payload["application"]["environment"] = "production"
    payload["conference"].update(auth_required=True, access_token="synthetic-media-token-123456")
    payload["control_access"].update(auth_required=True, access_token="synthetic-control-token-654321")
    if failure == "disabled_media":
        payload["conference"]["auth_required"] = False
    elif failure == "disabled_control":
        payload["control_access"]["auth_required"] = False
    elif failure == "shared":
        payload["control_access"]["access_token"] = payload["conference"]["access_token"]
    else:
        payload["conference"]["access_token"] = "synthetic token with whitespace"
    with pytest.raises(ValidationError, match="production"):
        Settings.model_validate(payload)


def test_settings_validation_error_does_not_echo_private_configuration():
    from robotic_classroom.core.config import Settings

    payload = load_settings("config.yaml").model_dump()
    payload["application"]["environment"] = "production"
    payload["conference"].update(auth_required=True, access_token="synthetic-private-media-secret")
    payload["control_access"].update(auth_required=True, access_token="synthetic-private-media-secret")
    with pytest.raises(ValidationError) as exc:
        Settings.model_validate(payload)
    assert "synthetic-private-media-secret" not in str(exc.value)
