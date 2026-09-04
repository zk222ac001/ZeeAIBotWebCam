from __future__ import annotations

from typing import Protocol

from robotic_classroom.audio.models import AudioObservation


class AudioBackend(Protocol):
    def start(self) -> None:
        """Initialize the audio metadata backend."""

    def observation(self) -> AudioObservation:
        """Return the latest VAD and direction-of-arrival observation."""

    def stop(self) -> None:
        """Release backend resources."""
