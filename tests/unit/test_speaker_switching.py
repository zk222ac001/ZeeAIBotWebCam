from dataclasses import replace

import pytest
from test_active_speaker_fusion import audio_at, camera_with_two_people

from robotic_classroom.core.config import ActiveSpeakerConfig
from robotic_classroom.fusion.active_speaker import ActiveSpeakerFusion
from robotic_classroom.fusion.models import ActiveSpeakerState


@pytest.fixture
def scenario(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr('robotic_classroom.core.freshness.time.monotonic', lambda: clock[0])
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(geometry_calibrated=True))

    def observe(t, doa=339, *, frame_time=None, audio_time=None, reverse=False, silent=False):
        clock[0] = t
        frame = replace(camera_with_two_people(), timestamp_monotonic=t if frame_time is None
                        else frame_time)
        if reverse:
            frame = replace(frame, people=tuple(reversed(frame.people)))
        audio = replace(audio_at(doa), timestamp_monotonic=t if audio_time is None
                        else audio_time, speech_active=not silent)
        return fusion.update(frame, audio)

    return fusion, observe


def test_switch_needs_fresh_samples_and_dwell_then_changes_label(scenario):
    _, observe = scenario
    first = observe(10)
    assert first.speaker_id == 'Speaker-01'
    for t in (10.1, 10.2, 10.3):
        assert observe(t, 21).state == ActiveSpeakerState.AMBIGUOUS
    result = observe(10.4, 21)
    assert result.state == ActiveSpeakerState.SPEAKER_SELECTED
    assert result.speaker_id == 'Speaker-02'
    assert result.candidate_index == 1


@pytest.mark.parametrize('frozen', ['both', 'camera', 'audio'])
def test_polling_or_one_producer_cannot_confirm_switch(scenario, frozen):
    _, observe = scenario
    observe(10)
    observe(10.1, 21)
    for t in (10.2, 10.3, 10.4, 10.5):
        result = observe(t, 21, frame_time=10.1 if frozen in ('both', 'camera') else t,
                         audio_time=10.1 if frozen in ('both', 'audio') else t)
        assert result.state == ActiveSpeakerState.AMBIGUOUS
        assert result.speaker_id is None
        assert result.center_x is None


def test_reordered_detections_keep_label(scenario):
    _, observe = scenario
    first = observe(10)
    second = observe(10.1, reverse=True)
    assert second.candidate_index == 1
    assert second.speaker_id == first.speaker_id


def test_return_to_incumbent_cancels_pending_switch(scenario):
    _, observe = scenario
    observe(10)
    observe(10.1, 21)
    assert observe(10.2).speaker_id == 'Speaker-01'
    assert observe(10.4, 21).state == ActiveSpeakerState.AMBIGUOUS
    assert observe(10.5, 21).state == ActiveSpeakerState.AMBIGUOUS


def test_silence_breaks_consecutive_confirmation(scenario):
    _, observe = scenario
    observe(10)
    observe(10.1, 21)
    observe(10.2, silent=True)
    assert observe(10.4, 21).state == ActiveSpeakerState.AMBIGUOUS
    assert observe(10.5, 21).state == ActiveSpeakerState.AMBIGUOUS


def test_reacquisition_after_expiry_requires_confirmation_and_new_label(scenario):
    _, observe = scenario
    observe(10)
    assert observe(11.1).state == ActiveSpeakerState.AMBIGUOUS
    assert observe(11.3).state == ActiveSpeakerState.AMBIGUOUS
    assert observe(11.5).speaker_id == 'Speaker-02'


def test_timeout_cannot_bypass_switch_confirmation(scenario):
    _, observe = scenario
    observe(10)
    observe(10.8, 21)
    for t in (11.01, 11.1, 11.2, 11.3):
        assert observe(t, 21, frame_time=10.8, audio_time=10.8).speaker_id is None


def test_near_tied_candidates_are_ambiguous(scenario):
    fusion, _ = scenario
    # Symmetric equal-confidence people near the front direction.
    frame = camera_with_two_people()
    left = replace(frame.people[0], box=replace(frame.people[0].box, x=300))
    right = replace(left, box=replace(left.box, x=500))
    result = fusion.update(replace(frame, people=(left, right), timestamp_monotonic=10),
                           replace(audio_at(0), timestamp_monotonic=10))
    assert result.state == ActiveSpeakerState.AMBIGUOUS
    assert result.candidate_index is None


def test_pan_compensation_preserves_association(scenario):
    fusion, _ = scenario
    fusion.config.pan_compensation_enabled = True
    fusion.config.pan_geometry_calibrated = True
    frame = replace(camera_with_two_people(), timestamp_monotonic=10)
    audio = replace(audio_at(339), timestamp_monotonic=10)
    first = fusion.update(frame, audio, camera_pan_degrees=0)
    # Turning 21 degrees left moves the same chassis-bearing person to image center.
    person = replace(frame.people[0], box=replace(frame.people[0].box, x=400))
    second = fusion.update(replace(frame, people=(person,)), audio, camera_pan_degrees=-21)
    assert second.state == ActiveSpeakerState.SPEAKER_SELECTED
    assert second.speaker_id == first.speaker_id
