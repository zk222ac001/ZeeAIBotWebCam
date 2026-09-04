from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.hardware.models import SensorSnapshot


@dataclass(frozen=True, slots=True)
class HardwareStatus:
    backend: str
    connected: bool
    battery_voltage: float | None = None
    message: str = ""


class HardwareService(Protocol):
    def start(self) -> None:
        """Initialize the hardware backend."""

    def status(self) -> HardwareStatus:
        """Return current hardware status."""

    def sensors(self) -> SensorSnapshot:
        """Return the latest hardware sensor snapshot."""

    def set_pan_pulse(self, pulse: int) -> None:
        """Move the configured pan servo. Implementations must clamp/validate."""

    def set_tilt_pulse(self, pulse: int) -> None:
        """Move the configured tilt servo. Implementations must clamp/validate."""

    def drive(self, command: MotionCommand) -> None:
        """Apply a chassis command. The safety layer must authorize this first."""

    def stop_motion(self) -> None:
        """Immediately command the chassis to stop."""

    def stop(self) -> None:
        """Release resources safely."""
