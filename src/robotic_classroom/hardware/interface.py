from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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

    def stop(self) -> None:
        """Release resources safely."""
