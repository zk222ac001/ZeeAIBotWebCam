from __future__ import annotations

import math

from robotic_classroom.autonomy.models import AutonomyDecision, AutonomyState
from robotic_classroom.control.commands import MotionCommand, STOP_COMMAND
from robotic_classroom.core.config import AutonomyConfig, AxisConfig
from robotic_classroom.hardware.models import SensorSnapshot
from robotic_classroom.pan_tilt.models import PanTiltPlan
from robotic_classroom.tracking.models import TrackingObservation, TrackingState


class AutonomyController:
    """Pure autonomy planner.

    This planner never touches hardware. It can only propose bounded chassis
    commands. Runtime execution, when enabled, must still pass through the
    SafetySupervisor.
    """

    def __init__(
        self,
        config: AutonomyConfig,
        pan_axis: AxisConfig,
        minimum_obstacle_distance_cm: float,
    ) -> None:
        self.config = config
        self.pan_axis = pan_axis
        self.minimum_obstacle_distance_cm = minimum_obstacle_distance_cm

    def _decision(
        self,
        state: AutonomyState,
        command: MotionCommand,
        reason: str,
        tracking: TrackingObservation,
        sensors: SensorSnapshot,
    ) -> AutonomyDecision:
        return AutonomyDecision(
            state=state,
            command=command,
            reason=reason,
            target_id=tracking.target_id,
            distance_cm=sensors.distance_cm,
        )

    def _body_rotation(self, pan_pulse: int) -> float:
        offset = pan_pulse - self.pan_axis.center
        if abs(offset) <= self.config.pan_recentering_deadband_us:
            return 0.0

        if offset > 0:
            travel = max(self.pan_axis.maximum - self.pan_axis.center, 1)
        else:
            travel = max(self.pan_axis.center - self.pan_axis.minimum, 1)

        normalized = max(-1.0, min(1.0, offset / travel))
        if self.pan_axis.inverted:
            normalized = -normalized

        rotation = normalized * self.config.rotation_gain
        return max(-self.config.max_rotation, min(self.config.max_rotation, rotation))

    def plan(
        self,
        tracking: TrackingObservation,
        pan_tilt: PanTiltPlan,
        sensors: SensorSnapshot,
    ) -> AutonomyDecision:
        if not self.config.enabled:
            return self._decision(
                AutonomyState.DISABLED,
                STOP_COMMAND,
                "Autonomy disabled by configuration",
                tracking,
                sensors,
            )

        distance = sensors.distance_cm
        if self.config.require_ultrasonic and (
            distance is None or not math.isfinite(distance)
        ):
            return self._decision(
                AutonomyState.BLOCKED,
                STOP_COMMAND,
                "Ultrasonic distance unavailable",
                tracking,
                sensors,
            )

        if distance is not None and distance < self.minimum_obstacle_distance_cm:
            return self._decision(
                AutonomyState.BLOCKED,
                STOP_COMMAND,
                "Obstacle inside safety distance",
                tracking,
                sensors,
            )

        if tracking.state is TrackingState.TRACKING:
            rotation = self._body_rotation(pan_tilt.pan.planned_pulse)
            if rotation != 0.0:
                return self._decision(
                    AutonomyState.TRACKING,
                    MotionCommand(rotation=rotation),
                    "Recentering chassis toward tracked target",
                    tracking,
                    sensors,
                )

            if not self.config.forward_enabled:
                return self._decision(
                    AutonomyState.HOLDING,
                    STOP_COMMAND,
                    "Target centered; autonomous forward motion disabled",
                    tracking,
                    sensors,
                )

            assert distance is not None
            if distance > self.config.maximum_follow_distance_cm:
                return self._decision(
                    AutonomyState.HOLDING,
                    STOP_COMMAND,
                    "Target/range return is too far for trusted following",
                    tracking,
                    sensors,
                )

            if distance > self.config.follow_distance_cm + self.config.follow_tolerance_cm:
                return self._decision(
                    AutonomyState.FOLLOWING,
                    MotionCommand(forward=self.config.forward_speed),
                    "Following centered target using ultrasonic range",
                    tracking,
                    sensors,
                )

            return self._decision(
                AutonomyState.HOLDING,
                STOP_COMMAND,
                "Target is within the configured follow distance",
                tracking,
                sensors,
            )

        if tracking.state is TrackingState.LOST:
            return self._decision(
                AutonomyState.TARGET_LOST,
                STOP_COMMAND,
                "Target temporarily lost; stopping chassis",
                tracking,
                sensors,
            )

        if tracking.state is TrackingState.SEARCHING:
            if self.config.search_enabled:
                return self._decision(
                    AutonomyState.SEARCHING,
                    MotionCommand(rotation=self.config.search_rotation),
                    "Slow autonomous search rotation",
                    tracking,
                    sensors,
                )
            return self._decision(
                AutonomyState.SEARCHING,
                STOP_COMMAND,
                "Searching for target; chassis search rotation disabled",
                tracking,
                sensors,
            )

        return self._decision(
            AutonomyState.HOLDING,
            STOP_COMMAND,
            f"Tracking state {tracking.state.value} does not permit autonomous motion",
            tracking,
            sensors,
        )
