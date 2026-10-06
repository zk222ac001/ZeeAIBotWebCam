from __future__ import annotations

import threading

from robotic_classroom.autonomy.controller import AutonomyController
from robotic_classroom.autonomy.models import AutonomyState, AutonomyStatus
from robotic_classroom.control.commands import STOP_COMMAND
from robotic_classroom.core.config import AutonomyConfig, AxisConfig
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.pan_tilt.service import PanTiltPlanningService
from robotic_classroom.safety.supervisor import SafetySupervisor
from robotic_classroom.tracking.service import TrackingService


class AutonomyService:
    """Background supervised autonomy service.

    The service is intentionally unarmed after startup. In plan-only mode it may
    be armed without a control lease because it cannot move hardware. Execute
    mode requires an already-issued control lease token; the service renews that
    lease with the normal dead-man heartbeat while armed.
    """

    def __init__(
        self,
        config: AutonomyConfig,
        pan_axis: AxisConfig,
        tracking: TrackingService,
        pan_tilt: PanTiltPlanningService,
        hardware: HardwareService,
        safety: SafetySupervisor,
    ) -> None:
        self.config = config
        self.tracking = tracking
        self.pan_tilt = pan_tilt
        self.hardware = hardware
        self.safety = safety
        self.controller = AutonomyController(
            config,
            pan_axis,
            safety.settings.safety.minimum_obstacle_distance_cm,
        )

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._armed = False
        self._lease_token: str | None = None
        self._status = AutonomyStatus(
            enabled=config.enabled,
            mode=config.mode,
            running=False,
            armed=False,
            state=AutonomyState.DISABLED if not config.enabled else AutonomyState.IDLE,
            target_id=None,
            distance_cm=None,
            planned_command=STOP_COMMAND,
            motion_executed=False,
            safety_reason="",
            message="Autonomy service not started",
        )

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="supervised-autonomy",
            )
            self._thread.start()

    def arm(self, lease_token: str | None = None) -> tuple[bool, str]:
        with self._lock:
            if not self.config.enabled:
                return False, "autonomy disabled by configuration"
            if self.config.mode == "execute":
                if not self.safety.leases.validate(lease_token):
                    return False, "valid control lease required to arm execute mode"
                if not self.safety.heartbeat(lease_token):
                    return False, "control heartbeat rejected"
                self._lease_token = lease_token
                self.safety.state.set_autonomous()
            self._armed = True
            return True, "autonomy armed"

    def disarm(self) -> None:
        with self._lock:
            token = self._lease_token
            self._armed = False
            self._lease_token = None
            self.safety.submit_motion(STOP_COMMAND)
            if token is not None:
                self.safety.leases.release(token)
            self.safety.state.set_idle()

    def _publish(
        self,
        *,
        state: AutonomyState,
        target_id: str | None,
        distance_cm: float | None,
        command,
        motion_executed: bool,
        safety_reason: str,
        message: str,
    ) -> None:
        with self._lock:
            self._status = AutonomyStatus(
                enabled=self.config.enabled,
                mode=self.config.mode,
                running=True,
                armed=self._armed,
                state=state,
                target_id=target_id,
                distance_cm=distance_cm,
                planned_command=command,
                motion_executed=motion_executed,
                safety_reason=safety_reason,
                message=message,
            )

    def _run(self) -> None:
        interval = self.config.poll_interval_ms / 1000.0
        while not self._stop_event.is_set():
            with self._lock:
                armed = self._armed
                token = self._lease_token

            if not self.config.enabled:
                self._publish(
                    state=AutonomyState.DISABLED,
                    target_id=None,
                    distance_cm=None,
                    command=STOP_COMMAND,
                    motion_executed=False,
                    safety_reason="",
                    message="Autonomy disabled by configuration",
                )
                self._stop_event.wait(interval)
                continue

            tracking = self.tracking.observation()
            pan_tilt = self.pan_tilt.plan()
            sensors = self.hardware.sensors()
            decision = self.controller.plan(tracking, pan_tilt, sensors)

            if not armed:
                self._publish(
                    state=AutonomyState.IDLE,
                    target_id=decision.target_id,
                    distance_cm=decision.distance_cm,
                    command=decision.command,
                    motion_executed=False,
                    safety_reason="",
                    message=f"Unarmed preview: {decision.reason}",
                )
                self._stop_event.wait(interval)
                continue

            if self.config.mode == "plan_only":
                self._publish(
                    state=decision.state,
                    target_id=decision.target_id,
                    distance_cm=decision.distance_cm,
                    command=decision.command,
                    motion_executed=False,
                    safety_reason="plan-only mode",
                    message=decision.reason,
                )
                self._stop_event.wait(interval)
                continue

            if token is None or not self.safety.heartbeat(token):
                self.safety.submit_motion(STOP_COMMAND)
                with self._lock:
                    self._armed = False
                    self._lease_token = None
                self._publish(
                    state=AutonomyState.FAULT,
                    target_id=decision.target_id,
                    distance_cm=decision.distance_cm,
                    command=STOP_COMMAND,
                    motion_executed=False,
                    safety_reason="control heartbeat rejected",
                    message="Autonomy disarmed after losing its control lease",
                )
                self._stop_event.wait(interval)
                continue

            safety_decision = self.safety.submit_motion(decision.command, token)
            self._publish(
                state=decision.state if safety_decision.allowed else AutonomyState.BLOCKED,
                target_id=decision.target_id,
                distance_cm=decision.distance_cm,
                command=decision.command,
                motion_executed=bool(safety_decision.allowed and not decision.command.is_stop),
                safety_reason=safety_decision.reason,
                message=decision.reason,
            )
            self._stop_event.wait(interval)

    def status(self) -> AutonomyStatus:
        with self._lock:
            return self._status

    def stop(self) -> None:
        self.disarm()
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        with self._lock:
            self._status = AutonomyStatus(
                enabled=self.config.enabled,
                mode=self.config.mode,
                running=False,
                armed=False,
                state=AutonomyState.DISABLED if not self.config.enabled else AutonomyState.IDLE,
                target_id=None,
                distance_cm=None,
                planned_command=STOP_COMMAND,
                motion_executed=False,
                safety_reason="",
                message="Autonomy service stopped",
            )
