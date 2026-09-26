"""Pure-software regressions for the classroom pilot findings; no hardware I/O."""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from robotic_classroom.audio.models import AudioObservation, SpeechState
from robotic_classroom.camera.models import BoundingBox, CameraSnapshot, PersonDetection
from robotic_classroom.camera.service import CameraService
from robotic_classroom.core.config import ActiveSpeakerConfig, AxisConfig, PanTiltControlConfig, TrackingConfig
from robotic_classroom.fusion.active_speaker import ActiveSpeakerFusion
from robotic_classroom.fusion.models import ActiveSpeakerObservation, ActiveSpeakerState
from robotic_classroom.pan_tilt.controller import PanTiltController
from robotic_classroom.pan_tilt.models import PanTiltPlanState
from robotic_classroom.tracking.models import TrackingObservation, TrackingState
from robotic_classroom.tracking.service import TrackingService
from robotic_classroom.tracking.tracker import PersonTracker


def snapshot(x: float = .7, y: float = .52, sequence: int = 5000) -> CameraSnapshot:
    return CameraSnapshot(
        backend="test", connected=True, frame_width=1000, frame_height=1000,
        sequence=sequence, people=(PersonDetection(
            .95, BoundingBox(round(x * 1000) - 100, round(y * 1000) - 100, 200, 200)
        ),),
    )


def speaker(sequence: int = 200, x: float = .7, y: float = .52) -> ActiveSpeakerObservation:
    return ActiveSpeakerObservation(
        state=ActiveSpeakerState.SPEAKER_SELECTED, sequence=sequence,
        speaker_id="Speaker-01", confidence=.9, candidate_index=0, center_x=x,
        center_y=y, camera_angle_degrees=(x - .5) * 70, doa_degrees=0,
        angular_error_degrees=0, message="synthetic observation",
    )


def service() -> TrackingService:
    result = TrackingService(cast(CameraService, None), TrackingConfig(smoothing_alpha=1))
    result.tracker.update(snapshot())
    return result


def tracking(source: str, x: float, y: float, config: TrackingConfig | None = None) -> TrackingObservation:
    config = config or TrackingConfig(smoothing_alpha=1)
    if source == "visual":
        return PersonTracker(config).update(snapshot(x, y))
    result = TrackingService(cast(CameraService, None), config)
    result.set_active_speaker(SimpleNamespace(observation=lambda: speaker(x=x, y=y)))
    return result.observation()


def controller(inverted: bool = False) -> PanTiltController:
    return PanTiltController(
        PanTiltControlConfig(pan_gain_us=220, tilt_gain_us=160, max_step_us=5),
        AxisConfig(minimum=1350, maximum=1650, inverted=inverted),
        AxisConfig(minimum=1350, maximum=1650, inverted=inverted),
    )


def audio(degrees: float) -> AudioObservation:
    return AudioObservation(
        backend="test", connected=True, running=True, sequence=1,
        speech_state=SpeechState.SPEAKING, speech_active=True,
        doa_degrees_raw=degrees, doa_degrees=degrees, orientation_calibrated=True,
    )


@pytest.mark.parametrize("source", ["visual", "active_speaker"])
@pytest.mark.parametrize("small_error", [-.02, .02])
def test_horizontal_motion_does_not_accumulate_vertical_error(source, small_error):
    control = controller()
    observed = tracking(source, .7, .5 + small_error)
    for _ in range(100):
        plan = control.update(observed)
        assert plan.tilt.planned_pulse == 1500
    assert plan.pan.planned_pulse > 1500


@pytest.mark.parametrize("source", ["visual", "active_speaker"])
@pytest.mark.parametrize("small_error", [-.02, .02])
def test_vertical_motion_does_not_accumulate_horizontal_error(source, small_error):
    control = controller()
    observed = tracking(source, .5 + small_error, .7)
    for _ in range(100):
        plan = control.update(observed)
        assert plan.pan.planned_pulse == 1500
    assert plan.tilt.planned_pulse > 1500


@pytest.mark.parametrize("source", ["visual", "active_speaker"])
@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_axis_specific_dead_zone_boundary_and_custom_config(source, axis, sign):
    config = TrackingConfig(smoothing_alpha=1, dead_zone_x=.125, dead_zone_y=.125)
    x, y = (.5 + sign * .125, .8) if axis == "x" else (.8, .5 + sign * .125)
    observed = tracking(source, x, y, config)
    assert getattr(observed, f"in_dead_zone_{axis}") is True
    plan = controller().update(observed)
    assert (plan.pan if axis == "x" else plan.tilt).planned_pulse == 1500
    assert (plan.tilt if axis == "x" else plan.pan).planned_pulse == 1505


@pytest.mark.parametrize("source", ["visual", "active_speaker"])
def test_hold_axis_at_current_pulse_not_mechanical_center(source):
    control = controller()
    for _ in range(10):
        before = control.update(tracking(source, .8, .8))
    for _ in range(20):
        after = control.update(tracking(source, .8, .52))
        assert after.tilt.planned_pulse == before.tilt.planned_pulse == 1550
    assert after.pan.planned_pulse == 1650


@pytest.mark.parametrize("inverted", [False, True])
def test_bounded_slew_and_escape_from_a_limit(inverted):
    control = controller(inverted)
    last = (1500, 1500)
    for x, y in [(.9, .9)] * 100 + [(.1, .1)] * 100:
        plan = control.update(tracking("visual", x, y))
        for value, previous in zip((plan.pan.planned_pulse, plan.tilt.planned_pulse), last):
            assert 1350 <= value <= 1650
            assert abs(value - previous) <= 5
        assert plan.apply_to_hardware is False
        last = plan.pan.planned_pulse, plan.tilt.planned_pulse
    assert last == ((1650, 1650) if inverted else (1350, 1350))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_position_error_holds_plan(bad):
    control = controller()
    observed = tracking("visual", .8, .8)
    before = control.update(observed)
    after = control.update(replace(observed, error_y=bad))
    assert after.state == PanTiltPlanState.HOLDING
    assert after.pan.planned_pulse == before.pan.planned_pulse
    assert after.tilt.planned_pulse == before.tilt.planned_pulse


def test_lost_target_still_holds_and_search_still_slews_to_center():
    control = controller()
    observed = tracking("visual", .8, .8)
    before = control.update(observed)
    held = control.update(replace(observed, state=TrackingState.LOST, error_x=None, error_y=None))
    assert held.pan.planned_pulse == before.pan.planned_pulse
    assert held.tilt.planned_pulse == before.tilt.planned_pulse
    assert held.state == PanTiltPlanState.HOLDING
    returning = control.update(replace(observed, state=TrackingState.SEARCHING))
    assert returning.state == PanTiltPlanState.SEARCHING
    assert returning.pan.planned_pulse == returning.tilt.planned_pulse == 1500


def test_source_changes_do_not_reset_publication_sequence():
    tracking_service = service()
    visual = tracking_service.observation()
    tracking_service.set_active_speaker(SimpleNamespace(observation=lambda: speaker()))
    active = tracking_service.observation()
    assert active.sequence > visual.sequence
    assert active.source == "active_speaker" and active.source_sequence == 200
    tracking_service.set_active_speaker(None)
    fallback = tracking_service.observation()
    assert fallback.sequence > active.sequence
    assert fallback.source == "visual" and fallback.source_sequence == 5000


def test_repeated_reads_do_not_manufacture_fresh_observations():
    tracking_service = service()
    tracking_service.set_active_speaker(SimpleNamespace(observation=lambda: speaker()))
    first = tracking_service.observation()
    for _ in range(100):
        assert tracking_service.observation() is first
    tracking_service.tracker.update(snapshot(sequence=9000))
    assert tracking_service.observation() is first


def test_source_restart_counter_is_preserved_separately():
    tracking_service = service()
    first = tracking_service.observation()
    tracking_service.tracker.update(snapshot(sequence=1))
    second = tracking_service.observation()
    assert second.sequence > first.sequence
    assert second.source_sequence == 1


def test_hold_then_fallback_has_explicit_source(monkeypatch):
    now = [10.0]
    monkeypatch.setattr("robotic_classroom.tracking.service.time.monotonic", lambda: now[0])
    tracking_service = service()
    current = [speaker()]
    tracking_service.set_active_speaker(SimpleNamespace(observation=lambda: current[0]))
    active = tracking_service.observation()
    current[0] = replace(current[0], state=ActiveSpeakerState.AMBIGUOUS, sequence=201)
    now[0] = 10.5
    held = tracking_service.observation()
    assert held.sequence > active.sequence
    assert held.state == TrackingState.LOST and held.source == "active_speaker_hold"
    assert held.error_x is None and held.error_y is None
    now[0] = 12.0
    fallback = tracking_service.observation()
    assert fallback.sequence > held.sequence
    assert fallback.source == "visual"


def test_concurrent_readers_reuse_one_immutable_publication():
    tracking_service = service()
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: tracking_service.observation(), range(100)))
    assert len({value.sequence for value in values}) == 1
    assert all(value is values[0] for value in values)


def test_outside_angle_never_selected_despite_continuity_bonus():
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(
        geometry_calibrated=True, doa_inverted=True, max_match_error_degrees=25,
        minimum_candidate_score=.30,
    ))
    frame = CameraSnapshot(
        backend="test", connected=True, frame_width=1280, frame_height=720, sequence=1,
        people=(PersonDetection(1.0, BoundingBox(720, 0, 400, 720)),),
    )
    assert fusion.update(frame, audio(344.6875)).state == ActiveSpeakerState.SPEAKER_SELECTED
    result = fusion.update(frame, audio(38.48683686517112))
    assert result.state == ActiveSpeakerState.AMBIGUOUS
    assert result.speaker_id is None and result.candidate_index is None


def test_invalid_high_score_cannot_hide_valid_lower_score_candidate():
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(
        geometry_calibrated=True, max_match_error_degrees=25, minimum_candidate_score=.3,
        audio_alignment_weight=0, detection_confidence_weight=1,
        size_weight=0, continuity_weight=0,
    ))
    frame = replace(snapshot(), people=(
        PersonDetection(1, BoundingBox(700, 100, 200, 400)),
        PersonDetection(.6, BoundingBox(100, 100, 200, 400)),
    ))
    result = fusion.update(frame, audio(339))
    assert result.state == ActiveSpeakerState.SPEAKER_SELECTED
    assert result.candidate_index == 1
    assert result.angular_error_degrees <= 25


@pytest.mark.parametrize("angle,selected", [(25, True), (335, True), (25.001, False), (334.999, False)])
def test_angular_gate_is_inclusive_at_configured_boundary(angle, selected):
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(
        geometry_calibrated=True, max_match_error_degrees=25, minimum_candidate_score=0,
    ))
    result = fusion.update(snapshot(x=.5, y=.5), audio(angle))
    assert (result.state == ActiveSpeakerState.SPEAKER_SELECTED) is selected


@pytest.mark.parametrize("angle", [0, 1, 359, -1, 360])
def test_wrapped_front_angles_remain_eligible(angle):
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(geometry_calibrated=True))
    result = fusion.update(snapshot(x=.5, y=.5), audio(angle))
    assert result.state == ActiveSpeakerState.SPEAKER_SELECTED


def test_rejection_does_not_replace_last_valid_continuity_center():
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(geometry_calibrated=True, minimum_candidate_score=.1))
    valid = fusion.update(snapshot(x=.5), audio(0))
    assert valid.state == ActiveSpeakerState.SPEAKER_SELECTED
    result = fusion.update(snapshot(x=.8), audio(330))
    assert result.state != ActiveSpeakerState.SPEAKER_SELECTED
    assert fusion._last_center_x == valid.center_x


@pytest.mark.parametrize("angle", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_angles_cannot_select_any_candidate(angle):
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(geometry_calibrated=True, minimum_candidate_score=0))
    result = fusion.update(snapshot(), audio(angle))
    assert result.state != ActiveSpeakerState.SPEAKER_SELECTED


def test_tracking_status_serializer_exposes_source_and_axis_flags():
    # Execute only the serializer, not application startup or any hardware factory.
    path = Path(__file__).resolve().parents[2] / "src/robotic_classroom/web/app.py"
    parsed = ast.parse(path.read_text(encoding="utf-8"))
    function = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == "tracking_status")
    function.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    tracking_service = service()
    namespace = {"app": SimpleNamespace(state=SimpleNamespace(tracking=tracking_service))}
    exec(compile(module, str(path), "exec"), namespace)
    output = namespace["tracking_status"]()
    assert output["source"] == "visual"
    assert output["source_sequence"] == 5000
    assert output["in_dead_zone_x"] is False
    assert output["in_dead_zone_y"] is True
    assert output["in_dead_zone"] is False
