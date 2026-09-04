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


def test_command_validator_rejects_out_of_range_values() -> None:
    supervisor, _ = build_supervisor()
    supervisor.settings.safety.motion_enabled = True
    lease = supervisor.leases.acquire("test")
    supervisor.heartbeat()

    decision = supervisor.evaluate(MotionCommand(forward=1.5), lease.token)

    assert decision.allowed is False
    assert "exceeds" in decision.reason
