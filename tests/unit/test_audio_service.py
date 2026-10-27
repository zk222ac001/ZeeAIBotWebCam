from __future__ import annotations

import time
from dataclasses import replace

from robotic_classroom.audio.interface import AudioBackend
from robotic_classroom.audio.models import AudioObservation, SpeechState
from robotic_classroom.audio.service import AudioService
from robotic_classroom.core.config import AudioConfig


class SequenceBackend(AudioBackend):
    def __init__(self, observations: list[AudioObservation]) -> None:
        self.observations = observations
        self.index = 0
        self.running = False

    def start(self) -> None:
        self.running = True

    def observation(self) -> AudioObservation:
        value = self.observations[min(self.index, len(self.observations) - 1)]
        self.index += 1
        return value

    def stop(self) -> None:
        self.running = False


def sample(sequence: int, angle: float, speaking: bool) -> AudioObservation:
    return AudioObservation(
        backend="test",
        connected=True,
        running=True,
        sequence=sequence,
        speech_state=SpeechState.SPEAKING if speaking else SpeechState.SILENT,
        speech_active=speaking,
        doa_degrees_raw=angle,
        doa_degrees=angle,
        orientation_calibrated=False,
        firmware_version="2.0.10",
    )


def test_circular_angle_blending_handles_zero_crossing() -> None:
    blended = AudioService._blend_angle(359.0, 1.0, 0.5)
    assert blended < 5.0 or blended > 355.0


def test_audio_service_applies_orientation_and_vad_hangover() -> None:
    backend = SequenceBackend(
        [
            sample(1, 350.0, True),
            sample(2, 10.0, False),
        ]
    )
    config = AudioConfig(
        mode="mock",
        poll_interval_ms=50,
        doa_smoothing_alpha=0.5,
        vad_hangover_ms=300,
        orientation_offset_degrees=20.0,
        orientation_calibrated=True,
    )
    service = AudioService(backend, config)
    service.start()
    try:
        time.sleep(0.13)
        observation = service.observation()
        assert observation.connected is True
        assert observation.orientation_calibrated is True
        assert observation.speech_active is True
        assert observation.speech_state in {SpeechState.SPEAKING, SpeechState.HANGOVER}
        assert observation.doa_degrees is not None
        assert 0.0 <= observation.doa_degrees < 360.0
    finally:
        service.stop()


def test_missing_live_speech_direction_clears_previous_bearing() -> None:
    backend = SequenceBackend([
        replace(sample(1, 30, True), doa_source="processed"),
        replace(sample(2, 30, True), doa_degrees_raw=None, doa_degrees=None,
                doa_source="processed", doa_degrees_processed=None),
    ])
    service = AudioService(backend, AudioConfig(poll_interval_ms=50))
    # Drive exactly two iterations without scheduling or accessing real hardware.
    count = 0

    def next_iteration(_):
        nonlocal count
        count += 1
        if count == 2:
            service._stop_event.set()

    service._stop_event.wait = next_iteration
    service._run()
    observation = service.observation()
    assert observation.speech_active
    assert observation.doa_degrees is None
    assert observation.doa_source == "processed"


def collect_directions(observations, config=None):
    service = AudioService(SequenceBackend(observations), config or AudioConfig())
    directions = []

    def next_iteration(_):
        directions.append(service.observation().doa_degrees)
        if len(directions) == len(observations):
            service._stop_event.set()

    service._stop_event.wait = next_iteration
    service._run()
    return directions


def test_consistent_new_bearing_can_recover_from_large_jump_during_continuous_speech():
    directions = collect_directions([
        sample(1, 272, True), sample(2, 6, True), sample(3, 7, True),
        sample(4, 5, True), sample(5, 6, True),
    ])
    assert directions[1:3] == [272, 272]  # Wait for corroborating observations.
    assert abs(AudioService._signed_delta(directions[3], 6)) < 2
    assert abs(AudioService._signed_delta(directions[4], 6)) < 2


def test_isolated_direction_spike_does_not_change_the_selected_bearing():
    directions = collect_directions([
        sample(1, 0, True), sample(2, 180, True), sample(3, 1, True),
    ])
    assert directions[1] == 0
    assert abs(AudioService._signed_delta(directions[2], 0)) < 2


def test_duplicate_producer_samples_cannot_confirm_a_new_direction():
    directions = collect_directions([
        sample(1, 272, True), sample(2, 6, True), sample(2, 6, True),
        sample(2, 6, True), sample(3, 7, True), sample(4, 5, True),
    ])
    assert directions[1:5] == [272] * 4
    assert abs(AudioService._signed_delta(directions[5], 6)) < 2


def test_inconsistent_new_bearings_do_not_confirm_a_switch():
    directions = collect_directions([
        sample(1, 272, True), sample(2, 0, True), sample(3, 90, True),
        sample(4, 0, True), sample(5, 90, True),
    ])
    assert directions == [272] * 5


def test_recovered_direction_averages_across_zero_degrees():
    directions = collect_directions([
        sample(1, 180, True), sample(2, 359, True), sample(3, 1, True), sample(4, 0, True),
    ])
    assert abs(AudioService._signed_delta(directions[-1], 0)) < 1


def test_silence_clears_the_previous_bearing_after_hangover():
    directions = collect_directions([
        sample(1, 30, True), sample(2, 40, False), sample(3, 90, True),
    ], AudioConfig(vad_hangover_ms=0))
    assert directions == [30, None, 90]
