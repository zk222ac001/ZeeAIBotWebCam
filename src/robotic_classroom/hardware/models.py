from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass(frozen=True, slots=True)
class SensorSnapshot:
    battery_voltage: float | None
    distance_cm: float | None
    infrared: tuple[bool, bool, bool, bool] | None
    timestamp_monotonic: float = field(default_factory=monotonic)


@dataclass(frozen=True, slots=True)
class PanTiltPosition:
    pan_pulse: int | None
    tilt_pulse: int | None
