from __future__ import annotations

from robotic_classroom.hardware.interface import HardwareStatus


class MockHardwareService:
    """Hardware-free backend for Windows, CI and safe development."""

    def __init__(self) -> None:
        self._started = False

    def start(self) -> None:
        self._started = True

    def status(self) -> HardwareStatus:
        return HardwareStatus(
            backend="mock",
            connected=self._started,
            battery_voltage=7.6 if self._started else None,
            message="Mock TurboPi hardware backend",
        )

    def stop(self) -> None:
        self._started = False
