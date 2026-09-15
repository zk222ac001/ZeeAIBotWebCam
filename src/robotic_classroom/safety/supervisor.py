from __future__ import annotations

from dataclasses import dataclass
import threading

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.control.lease import ControlLease, ControlLeaseManager
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
    """Single gatekeeper for all chassis movement and operator authorization."""

    def __init__(self, settings: Settings, hardware: HardwareService) -> None:
        self.settings = settings
        self.hardware = hardware
        self.state = RobotStateMachine()
        self.deadman = DeadmanTimer(settings.safety.heartbeat_timeout_ms)
        self.leases = ControlLeaseManager(settings.safety.control_lease_ttl_seconds)
        self.validator = CommandValidator(maximum_absolute_command=1.0)
        self.state.set_idle()

        self._lock = threading.RLock()
        self._motion_active = False
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None

    def start_watchdog(self) -> None:
        with self._lock:
            if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
                return
            self._watchdog_stop.clear()
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="chassis-deadman-watchdog",
                daemon=True,
            )
            self._watchdog_thread.start()

    def stop_watchdog(self) -> None:
        self._watchdog_stop.set()
        thread = self._watchdog_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._watchdog_thread = None

    def _watchdog_loop(self) -> None:
        interval = min(max(self.deadman.timeout_seconds / 4.0, 0.02), 0.10)
        while not self._watchdog_stop.wait(interval):
            if not self._motion_active or self.deadman.fresh:
                continue
            with self._lock:
                if self._motion_active and not self.deadman.fresh:
                    self.hardware.stop_motion()
                    self._motion_active = False

    @property
    def watchdog_running(self) -> bool:
        thread = self._watchdog_thread
        return thread is not None and thread.is_alive()

    @property
    def motion_active(self) -> bool:
        return self._motion_active

    def acquire_control_lease(self, owner: str) -> ControlLease:
        """Acquire the single operator lease under the supervisor lock."""
        with self._lock:
            return self.leases.acquire(owner)

    def emergency_stop(self) -> None:
        with self._lock:
            self.hardware.stop_motion()
            self._motion_active = False
            self.deadman.clear()
            self.leases.clear()
            self.state.emergency_stop()

    def reset_emergency_stop(self, lease_token: str | None = None) -> bool:
        """Reset E-stop only for an authorized operator when leases are required."""
        with self._lock:
            if self.settings.safety.require_control_lease and not self.leases.validate(lease_token):
                return False
            self.hardware.stop_motion()
            self._motion_active = False
            self.deadman.clear()
            self.state.reset_to_idle()
            return True

    def heartbeat(self, lease_token: str | None = None) -> bool:
        """Accept a heartbeat and renew the lease atomically when required."""
        with self._lock:
            if self.settings.safety.require_control_lease:
                if not self.leases.renew(lease_token):
                    return False
            self.deadman.heartbeat()
            return True

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
        with self._lock:
            decision = self.evaluate(command, lease_token)
            if command.is_stop:
                self.hardware.stop_motion()
                self._motion_active = False
                return decision
            if not decision.allowed:
                self.hardware.stop_motion()
                self._motion_active = False
                return decision
            self.hardware.drive(command)
            self._motion_active = True
            return decision
