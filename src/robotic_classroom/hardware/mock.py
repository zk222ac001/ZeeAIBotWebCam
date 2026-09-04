from __future__ import annotations

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.hardware.interface import HardwareStatus
from robotic_classroom.hardware.models import SensorSnapshot


class MockHardwareService:
    """Hardware-free backend for Windows, CI and safe development."""

    def __init__(self) -> None:
        self._started = False
        self.last_motion = MotionCommand()
        self.pan_pulse: int | None = None
        self.tilt_pulse: int | None = None

    def start(self) -> None:
        self._started = True

    def status(self) -> HardwareStatus:
        return HardwareStatus(
            backend="mock",
            connected=self._started,
            battery_voltage=7.6 if self._started else None,
            message="Mock TurboPi hardware backend",
        )

    def sensors(self) -> SensorSnapshot:
        return SensorSnapshot(
            battery_voltage=7.6 if self._started else None,
            distance_cm=100.0 if self._started else None,
            infrared=(False, False, False, False) if self._started else None,
        )

    def set_pan_pulse(self, pulse: int) -> None:
        self.pan_pulse = pulse

    def set_tilt_pulse(self, pulse: int) -> None:
        self.tilt_pulse = pulse

    def drive(self, command: MotionCommand) -> None:
        self.last_motion = command

    def stop_motion(self) -> None:
        self.last_motion = MotionCommand()

    def stop(self) -> None:
        self.stop_motion()
        self._started = False
