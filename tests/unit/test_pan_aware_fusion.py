from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_active_speaker_fusion import audio_at, camera_with_two_people
from test_pan_tilt_executor import plan

from robotic_classroom.core.config import (
    ActiveSpeakerConfig,
    AxisConfig,
    PanTiltConfig,
    PanTiltControlConfig,
)
from robotic_classroom.fusion.active_speaker import ActiveSpeakerFusion
from robotic_classroom.fusion.models import ActiveSpeakerState
from robotic_classroom.pan_tilt.executor import PanTiltExecutor


def fusion(**kwargs):
    return ActiveSpeakerFusion(ActiveSpeakerConfig(
        geometry_calibrated=True, pan_compensation_enabled=True,
        pan_geometry_calibrated=True, minimum_candidate_score=0.3, **kwargs,
    ))


@pytest.mark.parametrize(('pan', 'doa', 'candidate'), [
    (40, 61, 1), (-40, 299, 0), (170, 191, 1), (-170, 169, 0),
])
def test_pan_compensates_before_fov_and_candidate_gates(pan, doa, candidate):
    result = fusion().update(camera_with_two_people(), audio_at(doa), camera_pan_degrees=pan)
    assert result.state == ActiveSpeakerState.SPEAKER_SELECTED
    assert result.candidate_index == candidate
    assert result.angular_error_degrees == pytest.approx(0)


@pytest.mark.parametrize('pan', [None, float('nan'), float('inf')])
def test_missing_or_invalid_pose_clears_previous_selection(pan):
    f = fusion()
    f.update(camera_with_two_people(), audio_at(61), camera_pan_degrees=40)
    result = f.update(camera_with_two_people(), audio_at(61), camera_pan_degrees=pan)
    assert result.state == ActiveSpeakerState.CALIBRATION_REQUIRED
    assert result.candidate_index is None
    assert result.center_x is None
    assert result.angular_error_degrees is None


def test_pan_requires_separate_calibration():
    f = fusion()
    f.config.pan_geometry_calibrated = False
    assert f.update(camera_with_two_people(), audio_at(61), camera_pan_degrees=40).state == (
        ActiveSpeakerState.CALIBRATION_REQUIRED
    )


def test_doa_inversion_is_applied_before_pan_subtraction():
    result = fusion(doa_inverted=True).update(
        camera_with_two_people(), audio_at(299), camera_pan_degrees=40,
    )
    assert result.candidate_index == 1


def test_chassis_front_is_outside_a_camera_turned_away():
    result = fusion().update(camera_with_two_people(), audio_at(0), camera_pan_degrees=70)
    assert result.state == ActiveSpeakerState.NO_VISIBLE_CANDIDATE


def executor():
    safety = Mock()
    safety.submit_pan_tilt.return_value.allowed = True
    return PanTiltExecutor(Mock(), PanTiltControlConfig(mode='execute'), PanTiltConfig(
        enabled=True, calibration_validated=True,
        pan=AxisConfig(channel=1), tilt=AxisConfig(channel=2),
    ), safety)


def test_pose_timing_duplicate_commands_and_new_movement(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr('robotic_classroom.pan_tilt.executor.monotonic', lambda: clock[0])
    e = executor()
    assert e.settled_pan_pulse(10, 400) is None
    assert e.apply(plan())
    clock[0] = 11
    assert e.settled_pan_pulse(9, 400) is None  # old capture
    assert e.settled_pan_pulse(10.2, 400) is None  # still moving
    assert e.settled_pan_pulse(12, 400) is None  # future capture
    assert e.settled_pan_pulse(10.5, 400) == 1515
    assert e.apply(plan())  # identical pulse must not postpone settling forever
    assert e.settled_pan_pulse(10.5, 400) == 1515
    moved = replace(plan(), pan=replace(plan().pan, planned_pulse=1530))
    assert e.apply(moved)
    assert e.settled_pan_pulse(10.5, 400) is None
    clock[0] = 12
    assert e.settled_pan_pulse(11.5, 400) == 1530


@pytest.mark.parametrize('failure', ['denied', 'exception', 'plan_only'])
def test_failed_execution_invalidates_pose(monkeypatch, failure):
    monkeypatch.setattr('robotic_classroom.pan_tilt.executor.monotonic', lambda: 10.0)
    e = executor()
    e.apply(plan())
    if failure == 'denied':
        e.safety.submit_pan_tilt.return_value.allowed = False
    elif failure == 'exception':
        e.safety.submit_pan_tilt.side_effect = RuntimeError('partial write')
    else:
        e.control.mode = 'plan_only'
    assert not e.apply(plan())
    monkeypatch.setattr('robotic_classroom.pan_tilt.executor.monotonic', lambda: 12.0)
    assert e.settled_pan_pulse(11, 400) is None


def test_service_uses_capture_timestamp_for_pose():
    from robotic_classroom.fusion.service import ActiveSpeakerService

    camera = Mock()
    snapshot = camera_with_two_people()
    camera.snapshot.return_value = snapshot
    audio = Mock()
    audio.observation.return_value = audio_at(61)
    pose = Mock(return_value=40)
    service = ActiveSpeakerService(camera, audio, fusion().config, pan_angle_at=pose)
    service._stop_event.wait = lambda _: service._stop_event.set()
    service._run()
    pose.assert_called_once_with(snapshot.timestamp_monotonic)
    assert service.observation().candidate_index == 1


def test_service_without_pose_provider_refuses_compensated_selection():
    from robotic_classroom.fusion.service import ActiveSpeakerService

    camera, audio = Mock(), Mock()
    camera.snapshot.return_value = camera_with_two_people()
    audio.observation.return_value = audio_at(21)
    service = ActiveSpeakerService(camera, audio, fusion().config)
    service._stop_event.wait = lambda _: service._stop_event.set()
    service._run()
    assert service.observation().state == ActiveSpeakerState.CALIBRATION_REQUIRED
