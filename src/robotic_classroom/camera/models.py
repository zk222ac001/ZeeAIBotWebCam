from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PersonDetection:
    confidence: float
    box: BoundingBox
    label: str = "person"


@dataclass(frozen=True, slots=True)
class CameraSnapshot:
    backend: str
    connected: bool
    frame_width: int
    frame_height: int
    sequence: int
    timestamp_monotonic: float = field(default_factory=monotonic)
    people: tuple[PersonDetection, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class CameraStatus:
    backend: str
    connected: bool
    running: bool
    sequence: int
    people_count: int
    message: str = ""
