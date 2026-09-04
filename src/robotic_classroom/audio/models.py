from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic


class SpeechState(str, Enum):
    SILENT = "silent"
    SPEAKING = "speaking"
    HANGOVER = "hangover"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AudioObservation:
    backend: str
    connected: bool
    running: bool
    sequence: int
    speech_state: SpeechState
    speech_active: bool
    doa_degrees_raw: float | None
    doa_degrees: float | None
    orientation_calibrated: bool
    firmware_version: str | None = None
    timestamp_monotonic: float = field(default_factory=monotonic)
    message: str = ""
