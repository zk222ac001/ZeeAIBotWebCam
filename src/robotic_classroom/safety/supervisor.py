from __future__ import annotations

from dataclasses import dataclass

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.control.lease import ControlLeaseManager
from robotic_classroom.control.state_machine import RobotState, RobotStateMachine
from robotic_classroom.core.config import Settings
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.safety.command_validator import CommandValidator
from robotic_classroom.safety.deadman import DeadmanTimer


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    reason: str


class SafetySupervisor:
    """Single gatekeeper for all future chassis movement.

    Vision, web, AI and conference code may submit requests only. This class is the
    component that decides whether a command may reach the hardware adapter.
    """

    def __init__(self, settings: Settings, hardware: HardwareService) -> None:
        self.settings = settings
        self.hardware = hardware
        self.state = RobotStateMachine()
        self.deadman = DeadmanTimer(settings.safety.heartbeat_timeout_ms)
        self.leases = ControlLeaseManager(settings.safety.control_lease_ttl_seconds)
        self.validator = CommandValidator(maximum_absolute_command=1.0)
        self.state.set_idle()

    def emergency_stop(self) -> None:
        self.hardware.stop_motion()
        self.deadman.clear()
        self.leases.clear()
        self.state.emergency_stop()

    def reset_emergency_stop(self) -> None:
        self.hardware.stop_motion()
        self.state.reset_to_idle()

    def heartbeat(self) -> None:
        self.deadman.heartbeat()

    def evaluate(self, command: MotionCommand, lease_token: str | None = None) -> SafetyDecision:
        if command.is_stop:
            return SafetyDecision(True, "stop commands are always allowed")

        if not self.settings.safety.motion_enabled:
            return SafetyDecision(False, "motion disabled by configuration")

        if self.state.state in {RobotState.EMERGENCY_STOP, RobotState.FAULT, RobotState.SHUTDOWN}:
            return SafetyDecision(False, f"robot state is {self.state.state.value}")

        try:
            self.validator.validate(command)
        except ValueError as exc:
            return SafetyDecision(False, str(exc))

        if self.settings.safety.require_control_lease and not self.leases.validate(lease_token):
            return SafetyDecision(False, "valid control lease required")

        if not self.deadman.fresh:
            return SafetyDecision(False, "heartbeat expired or missing")

        snapshot = self.hardware.sensors()
        if (
            command.forward > 0
            and snapshot.distance_cm is not None
            and snapshot.distance_cm < self.settings.safety.minimum_obstacle_distance_cm
        ):
            return SafetyDecision(False, "obstacle too close for forward movement")

        return SafetyDecision(True, "command permitted")

    def submit_motion(self, command: MotionCommand, lease_token: str | None = None) -> SafetyDecision:
        decision = self.evaluate(command, lease_token)
        if command.is_stop:
            self.hardware.stop_motion()
            return decision
        if not decision.allowed:
            self.hardware.stop_motion()
            return decision
        self.hardware.drive(command)
        return decision
