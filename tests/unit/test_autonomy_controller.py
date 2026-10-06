from robotic_classroom.autonomy.controller import AutonomyController
from robotic_classroom.autonomy.models import AutonomyState
from robotic_classroom.core.config import AutonomyConfig, AxisConfig
from robotic_classroom.hardware.models import SensorSnapshot
from robotic_classroom.pan_tilt.models import AxisPlan, PanTiltPlan, PanTiltPlanState
from robotic_classroom.tracking.models import TrackingObservation, TrackingState


def tracking(
    *,
    state: TrackingState = TrackingState.TRACKING,
    target_id: str | None = "Person-01",
) -> TrackingObservation:
    return TrackingObservation(
        state=state,
        sequence=1,
        target_id=target_id,
        confidence=0.9 if target_id else None,
        center_x=0.5 if target_id else None,
        center_y=0.5 if target_id else None,
        error_x=0.0 if target_id else None,
        error_y=0.0 if target_id else None,
        in_dead_zone=True if target_id else False,
        message="test",
    )


def plan(pan_pulse: int = 1500) -> PanTiltPlan:
    pan = AxisPlan(
        desired_pulse=pan_pulse,
        planned_pulse=pan_pulse,
        minimum=1350,
        center=1500,
        maximum=1650,
        inverted=False,
    )
    tilt = AxisPlan(
        desired_pulse=1500,
        planned_pulse=1500,
        minimum=1350,
        center=1500,
        maximum=1650,
        inverted=False,
    )
    return PanTiltPlan(
        state=PanTiltPlanState.CENTERED,
        sequence=1,
        target_id="Person-01",
        pan=pan,
        tilt=tilt,
        apply_to_hardware=False,
        message="test",
    )


def sensors(distance_cm: float | None = 100.0) -> SensorSnapshot:
    return SensorSnapshot(
        battery_voltage=7.6,
        distance_cm=distance_cm,
        infrared=(False, False, False, False),
    )


def controller(**overrides: object) -> AutonomyController:
    config = AutonomyConfig(enabled=True, **overrides)
    return AutonomyController(
        config,
        AxisConfig(
            channel=1,
            center=1500,
            minimum=1350,
            maximum=1650,
            inverted=False,
        ),
        minimum_obstacle_distance_cm=30.0,
    )


def test_obstacle_inside_safety_distance_forces_stop() -> None:
    decision = controller().plan(tracking(), plan(), sensors(20.0))

    assert decision.state is AutonomyState.BLOCKED
    assert decision.command.is_stop


def test_target_loss_forces_stop() -> None:
    decision = controller().plan(
        tracking(state=TrackingState.LOST),
        plan(),
        sensors(100.0),
    )

    assert decision.state is AutonomyState.TARGET_LOST
    assert decision.command.is_stop


def test_pan_offset_requests_bounded_body_rotation() -> None:
    decision = controller().plan(tracking(), plan(1650), sensors(100.0))

    assert decision.state is AutonomyState.TRACKING
    assert decision.command.forward == 0.0
    assert 0.0 < decision.command.rotation <= 0.18


def test_centered_target_does_not_move_forward_by_default() -> None:
    decision = controller().plan(tracking(), plan(1500), sensors(180.0))

    assert decision.state is AutonomyState.HOLDING
    assert decision.command.is_stop
    assert "forward motion disabled" in decision.reason


def test_forward_following_requires_explicit_enable_and_finite_range() -> None:
    moving = controller(forward_enabled=True).plan(tracking(), plan(1500), sensors(180.0))
    no_range = controller(forward_enabled=True, require_ultrasonic=False).plan(
        tracking(),
        plan(1500),
        sensors(None),
    )

    assert moving.state is AutonomyState.FOLLOWING
    assert moving.command.forward > 0.0
    assert no_range.state is AutonomyState.HOLDING
    assert no_range.command.is_stop


def test_search_rotation_is_disabled_by_default() -> None:
    decision = controller().plan(
        tracking(state=TrackingState.SEARCHING, target_id=None),
        plan(1500),
        sensors(100.0),
    )

    assert decision.state is AutonomyState.SEARCHING
    assert decision.command.is_stop
