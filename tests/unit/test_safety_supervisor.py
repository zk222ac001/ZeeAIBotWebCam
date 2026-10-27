import time
from dataclasses import replace
from unittest.mock import Mock

import pytest

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.core.config import load_settings
from robotic_classroom.hardware.mock import MockHardwareService
from robotic_classroom.safety.supervisor import SafetySupervisor


def build_supervisor() -> tuple[SafetySupervisor, MockHardwareService]:
    settings = load_settings("config.yaml")
    hardware = MockHardwareService()
    hardware.start()
    supervisor = SafetySupervisor(settings, hardware)
    return supervisor, hardware


def test_motion_is_disabled_by_default() -> None:
    supervisor, hardware = build_supervisor()

    decision = supervisor.submit_motion(MotionCommand(forward=0.2))

    assert decision.allowed is False
    assert "disabled" in decision.reason
    assert hardware.last_motion.is_stop


def test_stop_command_is_always_allowed() -> None:
    supervisor, hardware = build_supervisor()

    decision = supervisor.submit_motion(MotionCommand())

    assert decision.allowed is True
    assert hardware.last_motion.is_stop


def test_emergency_stop_latches_state() -> None:
    supervisor, hardware = build_supervisor()

    supervisor.emergency_stop()

    assert supervisor.state.state.value == "emergency_stop"
    assert hardware.last_motion.is_stop


def test_failed_emergency_stop_revokes_control_and_keeps_stop_latched() -> None:
    supervisor, hardware = build_supervisor()
    lease = supervisor.acquire_control_lease("operator")
    supervisor.heartbeat(lease.token)
    hardware.stop_motion = Mock(side_effect=OSError("controller unavailable"))

    assert supervisor.emergency_stop() is False

    assert supervisor.state.state.value == "emergency_stop"
    assert not supervisor.leases.validate(lease.token)
    assert not supervisor.deadman.fresh
    assert supervisor.motion_active  # Physical stopping could not be confirmed.


def test_failed_normal_stop_latches_fault_until_successful_authorized_reset() -> None:
    supervisor, hardware = build_supervisor()
    lease = supervisor.acquire_control_lease("operator")
    supervisor.heartbeat(lease.token)
    hardware.stop_motion = Mock(side_effect=OSError("controller unavailable"))

    decision = supervisor.submit_motion(MotionCommand())

    assert not decision.allowed
    assert "stop failed" in decision.reason
    assert supervisor.state.state.value == "fault"
    assert not supervisor.leases.validate(lease.token)
    assert not supervisor.deadman.fresh
    assert supervisor.motion_active
    replacement = supervisor.acquire_control_lease("inspect-and-reset")
    assert not supervisor.reset_emergency_stop(replacement.token)
    assert supervisor.state.state.value == "fault"
    hardware.stop_motion = Mock()
    replacement = supervisor.acquire_control_lease("retry-reset")
    assert supervisor.reset_emergency_stop(replacement.token)
    assert supervisor.state.state.value == "idle"
    assert not supervisor.motion_active


def test_watchdog_retry_does_not_replace_emergency_stop_with_fault() -> None:
    supervisor, hardware = build_supervisor()
    hardware.stop_motion = Mock(side_effect=[OSError("first write failed"), None])
    assert not supervisor.emergency_stop()
    supervisor.start_watchdog()
    try:
        deadline = time.monotonic() + 1
        while supervisor.motion_active:
            assert time.monotonic() < deadline
            time.sleep(0.005)
        assert hardware.stop_motion.call_count == 2
        assert supervisor.state.state.value == "emergency_stop"
    finally:
        supervisor.stop_watchdog()


def test_failed_drive_attempts_stop_and_revokes_control() -> None:
    supervisor, hardware = build_supervisor()
    supervisor.settings.safety.motion_enabled = True
    lease = supervisor.acquire_control_lease("operator")
    supervisor.heartbeat(lease.token)
    supervisor._sensor_snapshot = hardware.sensors()
    supervisor._watchdog_thread = Mock()
    supervisor._watchdog_thread.is_alive.return_value = True
    hardware.drive = Mock(side_effect=OSError("partial controller write"))
    hardware.stop_motion = Mock()

    decision = supervisor.submit_motion(MotionCommand(forward=0.1), lease.token)

    assert not decision.allowed
    assert supervisor.state.state.value == "fault"
    assert not supervisor.leases.validate(lease.token)
    hardware.stop_motion.assert_called_once()


@pytest.mark.parametrize("voltage", [None, -1, float("nan"), float("inf"), 6.4])
def test_configured_battery_cutoff_blocks_unusable_or_low_voltage(voltage) -> None:
    supervisor, hardware = build_supervisor()
    supervisor.settings.safety.motion_enabled = True
    supervisor.settings.safety.minimum_battery_voltage = 6.5  # Synthetic test threshold.
    supervisor._sensor_snapshot = replace(hardware.sensors(), battery_voltage=voltage)
    supervisor._watchdog_thread = Mock()
    supervisor._watchdog_thread.is_alive.return_value = True
    lease = supervisor.acquire_control_lease("operator")
    supervisor.heartbeat(lease.token)

    decision = supervisor.submit_motion(MotionCommand(forward=0.1), lease.token)

    assert not decision.allowed
    assert "battery" in decision.reason
    assert hardware.last_motion.is_stop


def test_battery_drop_stops_active_motion_and_latches_fault() -> None:
    supervisor, hardware = build_supervisor()
    supervisor.settings.safety.motion_enabled = True
    supervisor.settings.safety.minimum_battery_voltage = 6.5
    supervisor.start_watchdog()
    try:
        deadline = time.monotonic() + 1
        while supervisor.sensor_snapshot() is None:
            assert time.monotonic() < deadline
            time.sleep(0.005)
        lease = supervisor.acquire_control_lease("operator")
        supervisor.heartbeat(lease.token)
        assert supervisor.submit_motion(MotionCommand(forward=0.1), lease.token).allowed
        original_sensors = hardware.sensors
        hardware.sensors = lambda: replace(original_sensors(), battery_voltage=6.4)
        deadline = time.monotonic() + 1
        while supervisor.motion_active:
            assert time.monotonic() < deadline
            time.sleep(0.005)
        assert hardware.last_motion.is_stop
        assert supervisor.state.state.value == "fault"
        assert not supervisor.leases.validate(lease.token)
    finally:
        supervisor.stop_watchdog()


def test_command_validator_rejects_out_of_range_values() -> None:
    supervisor, _ = build_supervisor()
    supervisor.settings.safety.motion_enabled = True
    lease = supervisor.leases.acquire("test")
    supervisor.heartbeat()

    decision = supervisor.evaluate(MotionCommand(forward=1.5), lease.token)

    assert decision.allowed is False
    assert "exceeds" in decision.reason


def test_watchdog_forces_stop_after_heartbeat_expires() -> None:
    supervisor, hardware = build_supervisor()
    supervisor.settings.safety.motion_enabled = True
    supervisor.settings.safety.heartbeat_timeout_ms = 80
    supervisor.deadman.timeout_seconds = 0.08
    lease = supervisor.leases.acquire("watchdog-test")

    supervisor.start_watchdog()
    try:
        assert supervisor.heartbeat(lease.token) is True
        decision = supervisor.submit_motion(MotionCommand(forward=0.2), lease.token)

        assert decision.allowed is True
        assert supervisor.motion_active is True
        assert hardware.last_motion.forward == 0.2

        deadline = time.monotonic() + 0.5
        while supervisor.motion_active and time.monotonic() < deadline:
            time.sleep(0.01)

        assert supervisor.motion_active is False
        assert hardware.last_motion.is_stop
    finally:
        supervisor.stop_watchdog()
