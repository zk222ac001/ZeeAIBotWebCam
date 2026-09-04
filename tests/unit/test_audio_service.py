from __future__ import annotations

import time

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
