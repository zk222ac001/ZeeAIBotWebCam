from robotic_classroom.core.config import AxisConfig, PanTiltConfig, PanTiltControlConfig
from robotic_classroom.hardware.mock import MockHardwareService
from robotic_classroom.pan_tilt.executor import PanTiltExecutor
from robotic_classroom.pan_tilt.models import AxisPlan, PanTiltPlan, PanTiltPlanState


def plan() -> PanTiltPlan:
    return PanTiltPlan(
        state=PanTiltPlanState.TRACKING,
        sequence=1,
        target_id="Person-01",
        pan=AxisPlan(
            desired_pulse=1520,
            planned_pulse=1515,
            minimum=1300,
            center=1500,
            maximum=1700,
            inverted=False,
        ),
        tilt=AxisPlan(
            desired_pulse=1490,
            planned_pulse=1490,
            minimum=1300,
            center=1500,
            maximum=1700,
            inverted=False,
        ),
        apply_to_hardware=False,
        message="test",
    )


def test_executor_refuses_when_not_calibrated() -> None:
    hardware = MockHardwareService()
    hardware.start()
    executor = PanTiltExecutor(
        hardware,
        PanTiltControlConfig(mode="execute"),
        PanTiltConfig(enabled=True, calibration_validated=False),
    )

    assert executor.apply(plan()) is False
    assert hardware.pan_pulse is None
    assert hardware.tilt_pulse is None


def test_executor_applies_only_when_all_gates_are_true() -> None:
    hardware = MockHardwareService()
    hardware.start()
    executor = PanTiltExecutor(
        hardware,
        PanTiltControlConfig(mode="execute"),
        PanTiltConfig(
            enabled=True,
            calibration_validated=True,
            pan=AxisConfig(channel=1),
            tilt=AxisConfig(channel=2),
        ),
    )

    assert executor.apply(plan()) is True
    assert hardware.pan_pulse == 1515
    assert hardware.tilt_pulse == 1490
    assert executor.status().executed is True


def test_plan_only_mode_never_executes() -> None:
    hardware = MockHardwareService()
    hardware.start()
    executor = PanTiltExecutor(
        hardware,
        PanTiltControlConfig(mode="plan_only"),
        PanTiltConfig(
            enabled=True,
            calibration_validated=True,
            pan=AxisConfig(channel=1),
            tilt=AxisConfig(channel=2),
        ),
    )

    assert executor.apply(plan()) is False
    assert hardware.pan_pulse is None
    assert hardware.tilt_pulse is None
