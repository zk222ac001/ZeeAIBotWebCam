import threading
import time
from dataclasses import replace
from types import SimpleNamespace

from robotic_classroom.core.config import load_settings
from robotic_classroom.hardware.mock import MockHardwareService
from robotic_classroom.pan_tilt.service import PanTiltPlanningService
from robotic_classroom.safety.supervisor import SafetySupervisor
from robotic_classroom.tracking.models import TrackingObservation, TrackingState


def service(*, startup_center_hold=False, execute=True):
    cfg = load_settings("config.yaml")
    cfg.hardware.pan_tilt.enabled = True
    cfg.hardware.pan_tilt.calibration_validated = True
    cfg.hardware.pan_tilt.pan.channel = 1
    cfg.hardware.pan_tilt.tilt.channel = 2
    cfg.pan_tilt_control.mode = "execute" if execute else "plan_only"
    cfg.pan_tilt_control.max_step_us = 5
    cfg.pan_tilt_control.startup_center_hold = startup_center_hold
    target = TrackingObservation(
        state=TrackingState.TRACKING, sequence=1, target_id="test-target", confidence=.9,
        center_x=.9, center_y=.1, error_x=.4, error_y=-.4,
        in_dead_zone=False, message="Synthetic off-center person",
    )
    tracking = SimpleNamespace(observation=lambda: target)
    hardware = MockHardwareService()
    hardware.start()
    safety = SafetySupervisor(cfg, hardware)
    planner = PanTiltPlanningService(
        tracking, cfg.pan_tilt_control, cfg.hardware.pan_tilt.pan, cfg.hardware.pan_tilt.tilt,
        hardware=hardware, calibration=cfg.hardware.pan_tilt, safety=safety,
    )
    return planner, hardware, safety, tracking, target


def test_center_overrides_visible_person_and_holds_until_explicit_resume():
    planner, hardware, _, _, _ = service()
    for _ in range(50):
        planner._cycle()
    old = planner.plan()
    assert old.pan.planned_pulse == old.pan.maximum
    assert old.tilt.planned_pulse == old.tilt.minimum
    planner.center()
    for _ in range(50):
        planner._cycle()
        new = planner.plan()
        assert abs(new.pan.planned_pulse - old.pan.planned_pulse) <= 5
        assert abs(new.tilt.planned_pulse - old.tilt.planned_pulse) <= 5
        assert new.pan.minimum <= new.pan.planned_pulse <= new.pan.maximum
        assert new.tilt.minimum <= new.tilt.planned_pulse <= new.tilt.maximum
        assert new.target_id is None
        old = new
    assert hardware.pan_pulse == hardware.tilt_pulse == 1500
    assert planner.center_hold
    planner.resume_tracking()
    planner._cycle()
    assert not planner.center_hold
    assert hardware.pan_pulse == 1505
    assert hardware.tilt_pulse == 1495


def test_startup_hold_cannot_be_overridden_by_a_visible_person():
    planner, hardware, _, _, _ = service(startup_center_hold=True)
    for _ in range(20):
        planner._cycle()
    assert planner.center_hold
    assert hardware.pan_pulse == hardware.tilt_pulse == 1500


def test_operator_center_request_is_independent_of_stale_perception():
    planner, hardware, _, tracking, target = service()
    tracking.observation = lambda: replace(target, timestamp_monotonic=time.monotonic() - 10)
    planner.center()
    planner._cycle()
    assert hardware.pan_pulse == hardware.tilt_pulse == 1500
    assert planner.execution_status().executed


def test_emergency_stop_still_blocks_manual_centering():
    planner, hardware, safety, _, _ = service()
    safety.emergency_stop()
    planner.center()
    planner._cycle()
    assert hardware.pan_pulse is None and hardware.tilt_pulse is None
    assert not planner.execution_status().executed
    assert "emergency_stop" in planner.execution_status().last_error


def test_center_in_plan_only_mode_never_writes_servos():
    planner, hardware, _, _, _ = service(execute=False)
    planner.center()
    planner._cycle()
    assert planner.center_hold
    assert hardware.pan_pulse is None and hardware.tilt_pulse is None


def test_no_target_returns_to_center_after_tracking_was_at_a_limit():
    planner, hardware, _, tracking, target = service()
    for _ in range(50):
        planner._cycle()
    tracking.observation = lambda: replace(
        target, state=TrackingState.SEARCHING, target_id=None, error_x=None, error_y=None,
        timestamp_monotonic=time.monotonic(),
    )
    for _ in range(50):
        planner._cycle()
    assert hardware.pan_pulse == hardware.tilt_pulse == 1500


def test_center_request_waits_for_an_older_tracking_submission_to_finish():
    planner, hardware, _, _, _ = service()
    entered, release, requested, centered = (threading.Event() for _ in range(4))
    original_apply = planner.executor.apply

    def blocked_apply(plan):
        entered.set()
        assert release.wait(2)
        return original_apply(plan)

    def request_center():
        requested.set()
        planner.center()
        centered.set()

    planner.executor.apply = blocked_apply
    worker = threading.Thread(target=planner._cycle)
    requester = threading.Thread(target=request_center)
    worker.start()
    try:
        assert entered.wait(1)
        requester.start()
        assert requested.wait(1)
        assert not centered.wait(.05)
    finally:
        release.set()
        worker.join(2)
        if requester.ident is not None:
            requester.join(2)
        planner.executor.apply = original_apply
    assert centered.is_set()
    for _ in range(10):
        planner._cycle()
    assert hardware.pan_pulse == hardware.tilt_pulse == 1500
