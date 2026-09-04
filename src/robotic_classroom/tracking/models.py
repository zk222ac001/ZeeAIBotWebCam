from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TrackingState(str, Enum):
    DISABLED = "disabled"
    SEARCHING = "searching"
    TRACKING = "tracking"
    LOST = "lost"


@dataclass(frozen=True, slots=True)
class TrackingObservation:
    state: TrackingState
    sequence: int
    target_id: str | None
    confidence: float | None
    center_x: float | None
    center_y: float | None
    error_x: float | None
    error_y: float | None
    in_dead_zone: bool
    message: str
