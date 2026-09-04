from __future__ import annotations

from enum import Enum


class RobotState(str, Enum):
    STARTING = "starting"
    IDLE = "idle"
    MANUAL = "manual"
    TRACKING = "tracking"
    EMERGENCY_STOP = "emergency_stop"
    FAULT = "fault"
    SHUTDOWN = "shutdown"


class RobotStateMachine:
    def __init__(self) -> None:
        self._state = RobotState.STARTING

    @property
    def state(self) -> RobotState:
        return self._state

    def set_idle(self) -> None:
        if self._state not in {RobotState.EMERGENCY_STOP, RobotState.FAULT, RobotState.SHUTDOWN}:
            self._state = RobotState.IDLE

    def set_manual(self) -> None:
        if self._state == RobotState.IDLE:
            self._state = RobotState.MANUAL

    def set_tracking(self) -> None:
        if self._state == RobotState.IDLE:
            self._state = RobotState.TRACKING

    def emergency_stop(self) -> None:
        self._state = RobotState.EMERGENCY_STOP

    def fault(self) -> None:
        self._state = RobotState.FAULT

    def reset_to_idle(self) -> None:
        if self._state in {RobotState.EMERGENCY_STOP, RobotState.FAULT}:
            self._state = RobotState.IDLE

    def shutdown(self) -> None:
        self._state = RobotState.SHUTDOWN
