from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PanTiltPlanState(str, Enum):
    DISABLED = "disabled"
    SEARCHING = "searching"
    HOLDING = "holding"
    TRACKING = "tracking"
    CENTERED = "centered"


@dataclass(frozen=True, slots=True)
class AxisPlan:
    desired_pulse: int
    planned_pulse: int
    minimum: int
    center: int
    maximum: int
    inverted: bool


@dataclass(frozen=True, slots=True)
class PanTiltPlan:
    state: PanTiltPlanState
    sequence: int
    target_id: str | None
    pan: AxisPlan
    tilt: AxisPlan
    apply_to_hardware: bool
    message: str
