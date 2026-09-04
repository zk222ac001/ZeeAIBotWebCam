from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MotionCommand:
    forward: float = 0.0
    sideways: float = 0.0
    rotation: float = 0.0

    @property
    def is_stop(self) -> bool:
        return self.forward == 0 and self.sideways == 0 and self.rotation == 0


STOP_COMMAND = MotionCommand()
