from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from robotic_classroom.control.commands import MotionCommand


class AutonomyState(str, Enum):
    DISABLED = "disabled"
    IDLE = "idle"
    SEARCHING = "searching"
    TRACKING = "tracking"
    FOLLOWING = "following"
    HOLDING = "holding"
    TARGET_LOST = "target_lost"
    BLOCKED = "blocked"
    FAULT = "fault"


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    state: AutonomyState
    command: MotionCommand
    reason: str
    target_id: str | None
    distance_cm: float | None


@dataclass(frozen=True, slots=True)
class AutonomyStatus:
    enabled: bool
    mode: str
    execution_policy: str
    pilot_validated: bool
    running: bool
    armed: bool
    state: AutonomyState
    target_id: str | None
    distance_cm: float | None
    stable_target_cycles: int
    required_target_stability_cycles: int
    planned_command: MotionCommand
    motion_executed: bool
    safety_reason: str
    message: str
