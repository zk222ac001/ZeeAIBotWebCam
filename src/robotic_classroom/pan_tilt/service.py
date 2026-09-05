from __future__ import annotations

import threading

from robotic_classroom.core.config import AxisConfig, PanTiltConfig, PanTiltControlConfig
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.pan_tilt.controller import PanTiltController
from robotic_classroom.pan_tilt.executor import PanTiltExecutionStatus, PanTiltExecutor
from robotic_classroom.pan_tilt.models import PanTiltPlan
from robotic_classroom.tracking.service import TrackingService


class PanTiltPlanningService:
    """Background pan/tilt planning service with an optional gated executor."""

    def __init__(
        self,
        tracking: TrackingService,
        config: PanTiltControlConfig,
        pan: AxisConfig,
        tilt: AxisConfig,
        *,
        hardware: HardwareService | None = None,
        calibration: PanTiltConfig | None = None,
    ) -> None:
        self.tracking = tracking
        self.config = config
        self.controller = PanTiltController(config, pan, tilt)
        self.executor = (
            PanTiltExecutor(hardware, config, calibration)
            if hardware is not None and calibration is not None
            else None
        )
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._plan = self.controller.update(self.tracking.observation())

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="pan-tilt-planning",
            )
            self._thread.start()

    def _run(self) -> None:
        interval = self.config.poll_interval_ms / 1000.0
        while not self._stop_event.is_set():
            plan = self.controller.update(self.tracking.observation())
            if self.executor is not None:
                self.executor.apply(plan)
            with self._lock:
                self._plan = plan
            self._stop_event.wait(interval)

    def plan(self) -> PanTiltPlan:
        with self._lock:
            return self._plan

    def execution_status(self) -> PanTiltExecutionStatus | None:
        if self.executor is None:
            return None
        return self.executor.status()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
