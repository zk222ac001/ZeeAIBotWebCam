from robotic_classroom.core.config import AxisConfig, PanTiltControlConfig
from robotic_classroom.pan_tilt.controller import PanTiltController
from robotic_classroom.pan_tilt.models import PanTiltPlanState
from robotic_classroom.tracking.models import TrackingObservation, TrackingState


def observation(error_x: float, error_y: float, in_dead_zone: bool = False) -> TrackingObservation:
    return TrackingObservation(
        state=TrackingState.TRACKING,
        sequence=1,
        target_id="Person-01",
        confidence=0.9,
        center_x=0.5 + error_x,
        center_y=0.5 + error_y,
        error_x=error_x,
        error_y=error_y,
        in_dead_zone=in_dead_zone,
        message="test",
    )


def test_pan_tilt_plan_is_bounded_and_plan_only() -> None:
    controller = PanTiltController(
        PanTiltControlConfig(max_step_us=20, pan_gain_us=400, tilt_gain_us=300),
        AxisConfig(center=1500, minimum=1300, maximum=1700),
        AxisConfig(center=1500, minimum=1400, maximum=1600),
    )

    plan = controller.update(observation(0.5, -0.5))

    assert plan.state == PanTiltPlanState.TRACKING
    assert plan.apply_to_hardware is False
    assert plan.pan.desired_pulse == 1700
    assert plan.pan.planned_pulse == 1520
    assert plan.tilt.desired_pulse == 1400
    assert plan.tilt.planned_pulse == 1480


def test_inverted_axis_reverses_direction() -> None:
    controller = PanTiltController(
        PanTiltControlConfig(max_step_us=100, pan_gain_us=400),
        AxisConfig(center=1500, minimum=1300, maximum=1700, inverted=True),
        AxisConfig(),
    )

    plan = controller.update(observation(0.25, 0.0))
    assert plan.pan.desired_pulse == 1400


def test_dead_zone_holds_current_plan() -> None:
    controller = PanTiltController(
        PanTiltControlConfig(),
        AxisConfig(),
        AxisConfig(),
    )

    plan = controller.update(observation(0.02, -0.03, in_dead_zone=True))
    assert plan.state == PanTiltPlanState.CENTERED
    assert plan.pan.planned_pulse == 1500
    assert plan.tilt.planned_pulse == 1500
