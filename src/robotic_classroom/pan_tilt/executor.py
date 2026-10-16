from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from robotic_classroom.core.config import PanTiltConfig, PanTiltControlConfig
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.pan_tilt.models import PanTiltPlan
from robotic_classroom.safety.supervisor import SafetySupervisor


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
        safety: SafetySupervisor | None = None,
    ) -> None:
        self.hardware = hardware
        self.safety = safety
        self.control = control
        self.calibration = calibration
        self._last_pan_pulse: int | None = None
        self._last_tilt_pulse: int | None = None
        self._last_error = ""
        self._executed = False
        self._pan_pose: tuple[int, float] | None = None

    @property
    def requested(self) -> bool:
        return self.control.mode == "execute"

    @property
    def ready(self) -> bool:
        return bool(
            self.safety is not None
            and self.control.enabled
            and self.requested
            and self.calibration.enabled
            and self.calibration.calibration_validated
        )

    def apply(self, plan: PanTiltPlan) -> bool:
        if not self.ready:
            self._pan_pose = None
            self._executed = False
            return False
        # Invalidate before a write that may move the camera (or block/fail).
        # A single immutable tuple makes concurrent readers see a coherent estimate.
        previous_pose = self._pan_pose
        if previous_pose is None or previous_pose[0] != plan.pan.planned_pulse:
            self._pan_pose = None
        try:
            assert self.safety is not None
            decision = self.safety.submit_pan_tilt(plan)
            if not decision.allowed:
                self._pan_pose = None
                self._last_error = decision.reason
                self._executed = False
                return False
            if self._pan_pose is None:
                self._pan_pose = (plan.pan.planned_pulse, monotonic())
            self._last_pan_pulse = plan.pan.planned_pulse
            self._last_tilt_pulse = plan.tilt.planned_pulse
            self._last_error = ""
            self._executed = True
            return True
        except Exception as exc:  # noqa: BLE001 - hardware failures must be reported, not hidden
            self._pan_pose = None
            self._last_error = str(exc)
            self._executed = False
            return False

    def settled_pan_pulse(self, frame_timestamp: float, settle_ms: int) -> int | None:
        """Command-based estimate, never encoder feedback or a future plan.

        Older frames and frames during movement are deliberately rejected.
        Repeated identical successful commands do not restart the settle interval.
        """
        pose = self._pan_pose
        if pose is None or not self.ready:
            return None
        pulse, issued_at = pose
        if not issued_at + settle_ms / 1000.0 <= frame_timestamp <= monotonic():
            return None
        return pulse

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

