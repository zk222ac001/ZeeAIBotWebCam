from __future__ import annotations

from robotic_classroom.audio.models import AudioObservation, SpeechState


class MockAudioBackend:
    def __init__(self) -> None:
        self._running = False
        self._sequence = 0

    def start(self) -> None:
        self._running = True

    def observation(self) -> AudioObservation:
        if self._running:
            self._sequence += 1
        speaking = self._running and (self._sequence // 10) % 2 == 1
        return AudioObservation(
            backend="mock",
            connected=self._running,
            running=self._running,
            sequence=self._sequence,
            speech_state=SpeechState.SPEAKING if speaking else SpeechState.SILENT,
            speech_active=speaking,
            doa_degrees_raw=90.0 if speaking else None,
            doa_degrees=90.0 if speaking else None,
            orientation_calibrated=True,
            firmware_version="mock",
            message="Mock audio backend",
        )

    def stop(self) -> None:
        self._running = False
