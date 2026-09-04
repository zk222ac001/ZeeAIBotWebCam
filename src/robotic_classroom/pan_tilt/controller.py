from __future__ import annotations

from robotic_classroom.core.config import AxisConfig, PanTiltControlConfig
from robotic_classroom.pan_tilt.models import AxisPlan, PanTiltPlan, PanTiltPlanState
from robotic_classroom.tracking.models import TrackingObservation, TrackingState


class PanTiltController:
    """Convert image-space tracking error into bounded pan/tilt pulse plans.

    Phase 6 is deliberately plan-only. This class has no hardware dependency and
    cannot send PWM commands. It transforms tracking observations into proposed
    servo pulses that can be inspected and tested safely.
    """

    def __init__(
        self,
        config: PanTiltControlConfig,
        pan: AxisConfig,
        tilt: AxisConfig,
    ) -> None:
        self.config = config
        self.pan_config = pan
        self.tilt_config = tilt
        self._pan_pulse = pan.center
        self._tilt_pulse = tilt.center
        self._sequence = 0

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))

    def _axis_target(self, error: float, axis: AxisConfig, gain_us: float) -> int:
        signed_error = -error if axis.inverted else error
        desired = int(round(axis.center + signed_error * gain_us))
        return self._clamp(desired, axis.minimum, axis.maximum)

    def _slew(self, current: int, desired: int) -> int:
        step = self.config.max_step_us
        if desired > current:
            return min(current + step, desired)
        if desired < current:
            return max(current - step, desired)
        return current

    def _axis_plan(self, axis: AxisConfig, desired: int, planned: int) -> AxisPlan:
        return AxisPlan(
            desired_pulse=desired,
            planned_pulse=planned,
            minimum=axis.minimum,
            center=axis.center,
            maximum=axis.maximum,
            inverted=axis.inverted,
        )

    def update(self, observation: TrackingObservation) -> PanTiltPlan:
        self._sequence += 1

        if not self.config.enabled:
            state = PanTiltPlanState.DISABLED
            desired_pan = self.pan_config.center
            desired_tilt = self.tilt_config.center
            message = "Pan/tilt planning disabled"
        elif observation.state == TrackingState.TRACKING:
            if observation.error_x is None or observation.error_y is None:
                desired_pan = self._pan_pulse
                desired_tilt = self._tilt_pulse
                state = PanTiltPlanState.HOLDING
                message = "Tracking target has no position error; holding plan"
            elif observation.in_dead_zone:
                desired_pan = self._pan_pulse
                desired_tilt = self._tilt_pulse
                state = PanTiltPlanState.CENTERED
                message = "Target is inside tracking dead zone; holding current plan"
            else:
                desired_pan = self._axis_target(
                    observation.error_x,
                    self.pan_config,
                    self.config.pan_gain_us,
                )
                desired_tilt = self._axis_target(
                    observation.error_y,
                    self.tilt_config,
                    self.config.tilt_gain_us,
                )
                state = PanTiltPlanState.TRACKING
                message = "Generated bounded pan/tilt tracking request"
        elif observation.state == TrackingState.LOST and self.config.hold_on_lost_target:
            desired_pan = self._pan_pulse
            desired_tilt = self._tilt_pulse
            state = PanTiltPlanState.HOLDING
            message = "Target temporarily lost; holding last planned position"
        else:
            desired_pan = self.pan_config.center
            desired_tilt = self.tilt_config.center
            state = PanTiltPlanState.SEARCHING
            message = "No active target; planning return toward calibrated center"

        self._pan_pulse = self._slew(self._pan_pulse, desired_pan)
        self._tilt_pulse = self._slew(self._tilt_pulse, desired_tilt)

        return PanTiltPlan(
            state=state,
            sequence=self._sequence,
            target_id=observation.target_id,
            pan=self._axis_plan(self.pan_config, desired_pan, self._pan_pulse),
            tilt=self._axis_plan(self.tilt_config, desired_tilt, self._tilt_pulse),
            apply_to_hardware=False,
            message=message,
        )
