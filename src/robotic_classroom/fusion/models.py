from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActiveSpeakerState(str, Enum):
    DISABLED = "disabled"
    WAITING_FOR_SPEECH = "waiting_for_speech"
    CALIBRATION_REQUIRED = "calibration_required"
    NO_VISIBLE_CANDIDATE = "no_visible_candidate"
    SPEAKER_SELECTED = "speaker_selected"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ActiveSpeakerObservation:
    state: ActiveSpeakerState
    sequence: int
    speaker_id: str | None
    confidence: float | None
    candidate_index: int | None
    center_x: float | None
    center_y: float | None
    camera_angle_degrees: float | None
    doa_degrees: float | None
    angular_error_degrees: float | None
    message: str
