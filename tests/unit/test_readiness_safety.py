"""Readiness failure injection with synthetic observations and no hardware I/O."""
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from robotic_classroom.core.config import load_settings
from robotic_classroom.hardware.mock import MockHardwareService
from robotic_classroom.safety.supervisor import SafetySupervisor
from robotic_classroom.web.app import app, readiness


@pytest.fixture
def ready_system(monkeypatch):
    cfg = load_settings("config.yaml")
    cfg.application.environment = "production"
    cfg.hardware.mode = "real"
    cfg.hardware.motor_mapping_validated = True
    cfg.hardware.pan_tilt.enabled = True
    cfg.hardware.pan_tilt.calibration_validated = True
    cfg.camera.mode = "imx500"
    cfg.audio.mode = "xvf3800_usb"
    cfg.conference.mode = "aiortc"
    cfg.conference.publish_audio = True
    cfg.conference.audio_input_validated = True
    cfg.conference.remote_audio_playback = True
    cfg.conference.audio_output_validated = True
    cfg.conference.echo_reference_enabled = True
    cfg.conference.echo_reference_validated = True
    cfg.conference.auth_required = True
    cfg.conference.access_token = "synthetic-media-secret-123456"
    cfg.control_access.access_token = "synthetic-control-secret-654321"
    cfg.control_access.auth_required = True
    cfg.safety.motion_enabled = True
    cfg.safety.minimum_battery_voltage = 6.5  # Synthetic test threshold.
    cfg.pan_tilt_control.mode = "execute"
    cfg.autonomy.enabled = True
    cfg.autonomy.mode = "execute"
    cfg.autonomy.execution_policy = "full"
    cfg.autonomy.pilot_validated = True
    hw = MockHardwareService()
    hw.start()
    safety = SafetySupervisor(cfg, hw)
    safety._sensor_snapshot = hw.sensors()
    safety._watchdog_thread = Mock()
    safety._watchdog_thread.is_alive.return_value = True
    camera_frame = SimpleNamespace(timestamp_monotonic=time.monotonic())
    audio = SimpleNamespace(backend="xvf3800_usb", connected=True, running=True,
                            timestamp_monotonic=time.monotonic())
    execution = SimpleNamespace(executed=True, last_error="")
    autonomy = SimpleNamespace(running=True, mode="execute", armed=False,
                               execution_policy="full", pilot_validated=True)
    replacements = {
        "settings": cfg,
        "hardware": SimpleNamespace(status=lambda: SimpleNamespace(
            backend="turbopi", connected=True)),
        "camera": SimpleNamespace(
            status=lambda: SimpleNamespace(backend="imx500", connected=True, running=True),
            snapshot=lambda: camera_frame),
        "audio": SimpleNamespace(observation=lambda: audio),
        "conference": SimpleNamespace(status=AsyncMock(return_value=SimpleNamespace(
            backend="aiortc", running=True))),
        "autonomy": SimpleNamespace(status=lambda: autonomy),
        "pan_tilt": SimpleNamespace(execution_status=lambda: execution),
        "safety": safety,
    }
    for name, value in replacements.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    return SimpleNamespace(cfg=cfg, safety=safety, camera=camera_frame, audio=audio,
                           execution=execution, autonomy=autonomy)


@pytest.mark.asyncio
async def test_ready_supervised_system_still_does_not_claim_navigation(ready_system):
    result = await readiness()
    assert result["production_ready"]
    assert result["autonomous_motion_ready"]
    assert result["unattended_navigation_ready"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    "fault", "emergency_stop", "stale_sensors", "obstacle", "stale_camera",
    "stale_audio", "mock_hardware", "motion_disabled", "autonomy_disabled",
    "worker_stopped", "battery_unconfigured", "pan_tilt_failed", "pilot_incomplete",
    "camera_center_hold",
])
async def test_readiness_rejects_runtime_and_configuration_failures(ready_system, failure):
    system = ready_system
    if failure == "fault":
        system.safety.state.fault()
    elif failure == "emergency_stop":
        system.safety.emergency_stop()
    elif failure == "stale_sensors":
        system.safety._sensor_snapshot = None
    elif failure == "obstacle":
        system.safety._sensor_snapshot = replace(
            system.safety.sensor_snapshot(), distance_cm=5)
    elif failure == "stale_camera":
        system.camera.timestamp_monotonic -= 10
    elif failure == "stale_audio":
        system.audio.timestamp_monotonic -= 10
    elif failure == "mock_hardware":
        system.cfg.hardware.mode = "mock"
    elif failure == "motion_disabled":
        system.cfg.safety.motion_enabled = False
    elif failure == "autonomy_disabled":
        system.cfg.autonomy.enabled = False
    elif failure == "worker_stopped":
        system.autonomy.running = False
    elif failure == "battery_unconfigured":
        system.cfg.safety.minimum_battery_voltage = None
    elif failure == "pan_tilt_failed":
        system.execution.executed = False
    elif failure == "pilot_incomplete":
        system.cfg.autonomy.pilot_validated = False
    elif failure == "camera_center_hold":
        app.state.pan_tilt.center_hold = True

    result = await readiness()
    assert not result["autonomous_motion_ready"]
    assert result["categories"]["autonomous_motion"]["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_media", "missing_control", "shared"])
async def test_readiness_requires_present_separate_credentials(ready_system, failure):
    cfg = ready_system.cfg
    if failure == "missing_media":
        cfg.conference.access_token = None
    elif failure == "missing_control":
        cfg.control_access.access_token = None
    else:
        cfg.control_access.access_token = cfg.conference.access_token
    result = await readiness()
    assert not result["production_ready"]
    assert not result["categories"]["privacy_security"]["ready"]
    assert "synthetic-media-secret" not in str(result)
    assert "synthetic-control-secret" not in str(result)
