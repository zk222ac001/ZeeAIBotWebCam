from __future__ import annotations

from dataclasses import dataclass

from robotic_classroom.core.config import PanTiltControlConfig, PanTiltConfig
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.pan_tilt.models import PanTiltPlan


@dataclass(frozen=True, slots=True)
class PanTiltExecutionStatus:
    requested: bool
    calibration_validated: bool
    hardware_enabled: bool
    executed: bool
    last_pan_pulse: int | None
    last_tilt_pulse: int | None
    last_error: str


class PanTiltExecutor:
    """Apply validated pan/tilt plans to hardware.

    Execution is refused unless all three independent gates are true:
    control mode is ``execute``, pan/tilt hardware is enabled, and the physical
    calibration has been marked validated.
    """

    def __init__(
        self,
        hardware: HardwareService,
        control: PanTiltControlConfig,
        calibration: PanTiltConfig,
    ) -> None:
        self.hardware = hardware
        self.control = control
        self.calibration = calibration
        self._last_pan_pulse: int | None = None
        self._last_tilt_pulse: int | None = None
        self._last_error = ""
        self._executed = False

    @property
    def requested(self) -> bool:
        return self.control.mode == "execute"

    @property
    def ready(self) -> bool:
        return bool(
            self.requested
            and self.calibration.enabled
            and self.calibration.calibration_validated
        )

    def apply(self, plan: PanTiltPlan) -> bool:
        if not self.ready:
            self._executed = False
            return False
        try:
            self.hardware.set_pan_pulse(plan.pan.planned_pulse)
            self.hardware.set_tilt_pulse(plan.tilt.planned_pulse)
            self._last_pan_pulse = plan.pan.planned_pulse
            self._last_tilt_pulse = plan.tilt.planned_pulse
            self._last_error = ""
            self._executed = True
            return True
        except Exception as exc:  # noqa: BLE001 - hardware failures must be reported, not hidden
            self._last_error = str(exc)
            self._executed = False
            return False

    def status(self) -> PanTiltExecutionStatus:
        return PanTiltExecutionStatus(
            requested=self.requested,
            calibration_validated=self.calibration.calibration_validated,
            hardware_enabled=self.calibration.enabled,
            executed=self._executed,
            last_pan_pulse=self._last_pan_pulse,
            last_tilt_pulse=self._last_tilt_pulse,
            last_error=self._last_error,
        )
