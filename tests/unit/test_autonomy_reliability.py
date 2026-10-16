"""Failure-injection checks; no SDK imports or physical robot access."""
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from robotic_classroom.audio.models import AudioObservation, SpeechState
from robotic_classroom.autonomy.models import AutonomyState
from robotic_classroom.autonomy.service import AutonomyService
from robotic_classroom.camera.models import BoundingBox, CameraSnapshot, PersonDetection
from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.core.config import (
    ActiveSpeakerConfig,
    AutonomyConfig,
    AxisConfig,
    TrackingConfig,
    load_settings,
)
from robotic_classroom.core.freshness import is_fresh
from robotic_classroom.fusion.active_speaker import ActiveSpeakerFusion
from robotic_classroom.fusion.models import ActiveSpeakerState
from robotic_classroom.hardware.mock import MockHardwareService
from robotic_classroom.pan_tilt.controller import PanTiltController
from robotic_classroom.safety.supervisor import SafetySupervisor
from robotic_classroom.tracking.models import TrackingState
from robotic_classroom.tracking.tracker import PersonTracker


def camera():
    return CameraSnapshot(
        backend="test", connected=True, frame_width=1000, frame_height=600, sequence=1,
        people=(PersonDetection(.9, BoundingBox(700, 100, 100, 400)),),
    )


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < deadline, "background safety response timed out"
        time.sleep(.005)


@pytest.mark.parametrize("age", [1.01, -1, float("nan"), float("inf")])
def test_freshness_rejects_expired_future_and_nonfinite_times(age):
    assert not is_fresh(10 - age, 1000, now=10)


@pytest.mark.parametrize("disconnected", [False, True])
def test_frozen_camera_loses_target_without_a_new_frame(disconnected):
    tracker = PersonTracker(TrackingConfig())
    frame = camera()
    assert tracker.update(frame).state is TrackingState.TRACKING
    failed = replace(frame, connected=False) if disconnected else frame
    result = tracker.update(failed, now=frame.timestamp_monotonic + 2)
    assert result.state is TrackingState.LOST
    assert result.error_x is None
    assert result.timestamp_monotonic == frame.timestamp_monotonic


def test_fusion_polling_cannot_refresh_old_audio():
    frame = camera()
    audio = AudioObservation(
        backend="test", connected=True, running=True, sequence=1,
        speech_state=SpeechState.SPEAKING, speech_active=True,
        doa_degrees_raw=17.5, doa_degrees=17.5, orientation_calibrated=True,
        timestamp_monotonic=time.monotonic() - 10,
    )
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(geometry_calibrated=True))
    for _ in range(10):
        result = fusion.update(frame, audio)
        assert result.state is not ActiveSpeakerState.SPEAKER_SELECTED
        assert result.timestamp_monotonic == audio.timestamp_monotonic


@pytest.mark.parametrize("distance", [None, -1, float("nan"), float("inf"), 10])
def test_unusable_or_blocked_range_rejects_motion(distance):
    settings = load_settings()
    settings.safety.motion_enabled = True
    hw = MockHardwareService()
    hw.start()
    sup = SafetySupervisor(settings, hw)
    sup._sensor_snapshot = replace(hw.sensors(), distance_cm=distance)
    lease = sup.acquire_control_lease("test")
    sup.heartbeat(lease.token)
    sup._watchdog_thread = SimpleNamespace(is_alive=lambda: True)
    assert not sup.submit_motion(MotionCommand(forward=.1), lease.token).allowed
    assert hw.last_motion.is_stop


def test_new_obstacle_stops_existing_command_despite_live_heartbeat():
    settings = load_settings()
    settings.safety.motion_enabled = True
    hw = MockHardwareService()
    hw.start()
    sup = SafetySupervisor(settings, hw)
    sup.start_watchdog()
    try:
        wait_until(lambda: sup.sensor_snapshot() is not None)
        lease = sup.acquire_control_lease("test")
        sup.heartbeat(lease.token)
        assert sup.submit_motion(MotionCommand(forward=.1), lease.token).allowed
        hw.sensors = lambda: replace(MockHardwareService.sensors(hw), distance_cm=10)
        wait_until(lambda: not sup.motion_active)
        assert hw.last_motion.is_stop
        assert sup.state.state.value == "fault"
        assert not sup.heartbeat(lease.token)
    finally:
        sup.stop_watchdog()


def test_blocking_sensor_reader_cannot_block_watchdog():
    settings = load_settings()
    settings.safety.motion_enabled = True
    settings.safety.sensor_timeout_ms = 100
    hw = MockHardwareService()
    hw.start()
    sup = SafetySupervisor(settings, hw)
    release = threading.Event()
    entered = threading.Event()
    sup.start_watchdog()
    try:
        wait_until(lambda: sup.sensor_snapshot() is not None)
        lease = sup.acquire_control_lease("test")
        sup.heartbeat(lease.token)
        assert sup.submit_motion(MotionCommand(forward=.1), lease.token).allowed
        def blocked():
            entered.set()
            release.wait(2)
            return MockHardwareService.sensors(hw)
        hw.sensors = blocked
        assert entered.wait(1)
        wait_until(lambda: not sup.motion_active)
        assert hw.last_motion.is_stop
    finally:
        release.set()
        sup.stop_watchdog()


def test_estop_blocks_servo_commands_until_authorized_reset():
    settings = load_settings()
    settings.pan_tilt_control.mode = "execute"
    cfg = settings.hardware.pan_tilt
    cfg.enabled = True
    cfg.pan.channel, cfg.tilt.channel = 1, 2
    cfg.calibration_validated = True
    hw = MockHardwareService()
    hw.start()
    sup = SafetySupervisor(settings, hw)
    observation = PersonTracker(settings.tracking).update(camera())
    planner = PanTiltController(settings.pan_tilt_control, cfg.pan, cfg.tilt)
    plan = planner.update(observation)
    sup.emergency_stop()
    assert not sup.submit_pan_tilt(plan).allowed
    assert hw.pan_pulse is None and hw.tilt_pulse is None
    lease = sup.acquire_control_lease("test")
    assert sup.reset_emergency_stop(lease.token)
    assert sup.submit_pan_tilt(plan).allowed
    assert not sup.submit_pan_tilt(replace(plan, timestamp_monotonic=0)).allowed


def test_stability_requires_fresh_samples_and_covers_following():
    safety = MagicMock()
    safety.settings.safety.minimum_obstacle_distance_cm = 30
    service = AutonomyService(AutonomyConfig(), AxisConfig(), MagicMock(), MagicMock(),
                              MagicMock(), safety)
    for _ in range(20):
        assert service._update_target_stability(AutonomyState.FOLLOWING, "p1", 1) == 1
    assert service._update_target_stability(AutonomyState.FOLLOWING, "p1", 2) == 2
    assert service._update_target_stability(AutonomyState.FOLLOWING, "p2", 3) == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_motion_is_rejected_at_shared_boundary(value):
    settings = load_settings()
    settings.safety.motion_enabled = True
    sup = SafetySupervisor(settings, MockHardwareService())
    assert not sup.evaluate(MotionCommand(rotation=value)).allowed


def test_execute_autonomy_disarms_on_stale_tracking():
    settings = load_settings()
    hw = MockHardwareService()
    hw.start()
    sup = SafetySupervisor(settings, hw)
    sup._sensor_snapshot = hw.sensors()
    tracking = PersonTracker(settings.tracking).update(camera())
    old = replace(tracking, timestamp_monotonic=time.monotonic() - 10)
    plan = PanTiltController(settings.pan_tilt_control,
                             settings.hardware.pan_tilt.pan,
                             settings.hardware.pan_tilt.tilt).update(tracking)
    service = AutonomyService(
        AutonomyConfig(enabled=True, mode="execute", pilot_validated=True),
        settings.hardware.pan_tilt.pan, SimpleNamespace(observation=lambda: old),
        SimpleNamespace(plan=lambda: plan), hw, sup,
    )
    lease = sup.acquire_control_lease("test")
    assert service.arm(lease.token)[0]
    service.start()
    try:
        wait_until(lambda: not service.status().armed)
        assert hw.last_motion.is_stop
        assert not sup.leases.validate(lease.token)
        assert service.status().state is AutonomyState.FAULT
    finally:
        service.stop()


def test_autonomy_worker_exception_reports_not_running_and_stops():
    settings = load_settings()
    hw = MockHardwareService()
    hw.start()
    sup = SafetySupervisor(settings, hw)
    tracking = MagicMock()
    tracking.observation.side_effect = RuntimeError("injected camera failure")
    service = AutonomyService(
        AutonomyConfig(enabled=True), settings.hardware.pan_tilt.pan,
        tracking, MagicMock(), hw, sup,
    )
    assert service.arm()[0]
    service.start()
    wait_until(lambda: not service.status().running)
    assert not service.status().armed
    assert service.status().state is AutonomyState.FAULT
    assert hw.last_motion.is_stop
    assert sup.state.state.value == "fault"
    service.stop()
