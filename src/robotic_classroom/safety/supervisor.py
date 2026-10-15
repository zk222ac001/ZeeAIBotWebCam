from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.control.lease import ControlLease, ControlLeaseManager
from robotic_classroom.control.state_machine import RobotState, RobotStateMachine
from robotic_classroom.core.config import Settings
from robotic_classroom.core.freshness import is_fresh
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.hardware.models import SensorSnapshot
from robotic_classroom.pan_tilt.models import PanTiltPlan
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
        self._sensor_snapshot: SensorSnapshot | None = None
        self._sensor_thread: threading.Thread | None = None
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None

    def start_watchdog(self) -> None:
        with self._lock:
            if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
                return
            if self._sensor_thread is not None and self._sensor_thread.is_alive():
                raise RuntimeError("Previous safety sensor reader has not stopped")
            self._watchdog_stop.clear()
            self._sensor_thread = threading.Thread(
                target=self._sensor_loop, name="safety-sensors", daemon=True
            )
            self._sensor_thread.start()
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
        sensor_thread = self._sensor_thread
        if sensor_thread is not None:
            sensor_thread.join(timeout=1.0)
        # A blocked reader must not be duplicated by a restart.
        if sensor_thread is not None and not sensor_thread.is_alive():
            self._sensor_thread = None

    def _sensor_loop(self) -> None:
        while not self._watchdog_stop.is_set():
            try:
                snapshot = self.hardware.sensors()
            except Exception:  # noqa: BLE001 - invalid samples fail closed
                snapshot = None
            # Publication does not need the actuator lock.
            self._sensor_snapshot = snapshot
            self._watchdog_stop.wait(0.1)

    def sensor_snapshot(self) -> SensorSnapshot | None:
        return self._sensor_snapshot

    def _sensor_blocker(self) -> str:
        snapshot = self._sensor_snapshot
        if snapshot is None or not is_fresh(
            snapshot.timestamp_monotonic, self.settings.safety.sensor_timeout_ms
        ):
            return "sensor data unavailable or stale"
        distance = snapshot.distance_cm
        if distance is None or not math.isfinite(distance) or distance < 0:
            return "ultrasonic distance unavailable or invalid"
        if distance < self.settings.safety.minimum_obstacle_distance_cm:
            return "obstacle inside safety distance"
        return ""

    def _watchdog_loop(self) -> None:
        interval = min(max(self.deadman.timeout_seconds / 4.0, 0.02), 0.10)
        while not self._watchdog_stop.wait(interval):
            with self._lock:
                if self._motion_active and (not self.deadman.fresh or self._sensor_blocker()):
                    try:
                        self.hardware.stop_motion()
                    except Exception:
                        logging.getLogger(__name__).exception("Hardware stop failed")
                    else:
                        self._motion_active = False
                    finally:
                        self.deadman.clear()
                        self.leases.clear()
                        self.state.fault()

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
            if self.settings.safety.require_control_lease and not self.leases.renew(lease_token):
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

        if not self.watchdog_running:
            return SafetyDecision(False, "safety watchdog not running")
        blocker = self._sensor_blocker()
        if blocker:
            return SafetyDecision(False, blocker)

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

    def submit_pan_tilt(self, plan: PanTiltPlan) -> SafetyDecision:
        """Serialize servo requests with E-stop; stationary framing needs no drive lease."""
        with self._lock:
            if self.state.state in {RobotState.EMERGENCY_STOP, RobotState.FAULT, RobotState.SHUTDOWN}:
                return SafetyDecision(False, f"robot state is {self.state.state.value}")
            cfg = self.settings.hardware.pan_tilt
            if (not self.settings.pan_tilt_control.enabled
                or self.settings.pan_tilt_control.mode != "execute"
                or not cfg.enabled or not cfg.calibration_validated):
                return SafetyDecision(False, "pan/tilt execution or calibration disabled")
            if not is_fresh(plan.timestamp_monotonic, self.settings.tracking.observation_timeout_ms):
                return SafetyDecision(False, "pan/tilt observation stale")
            for axis, pulse in ((cfg.pan, plan.pan.planned_pulse),
                                (cfg.tilt, plan.tilt.planned_pulse)):
                if not axis.minimum <= pulse <= axis.maximum:
                    return SafetyDecision(False, "pan/tilt pulse outside calibration")
            self.hardware.set_pan_pulse(plan.pan.planned_pulse)
            self.hardware.set_tilt_pulse(plan.tilt.planned_pulse)
            return SafetyDecision(True, "pan/tilt command permitted")
