from __future__ import annotations

from robotic_classroom.control.commands import MotionCommand


class CommandValidator:
    def __init__(self, maximum_absolute_command: float = 1.0) -> None:
        self.maximum_absolute_command = maximum_absolute_command

    def validate(self, command: MotionCommand) -> None:
        for name, value in (
            ("forward", command.forward),
            ("sideways", command.sideways),
            ("rotation", command.rotation),
        ):
            if abs(value) > self.maximum_absolute_command:
                raise ValueError(
                    f"{name} command {value} exceeds +/-{self.maximum_absolute_command}"
                )
