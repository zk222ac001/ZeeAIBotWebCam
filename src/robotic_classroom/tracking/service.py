from __future__ import annotations

import threading

from robotic_classroom.camera.service import CameraService
from robotic_classroom.core.config import TrackingConfig
from robotic_classroom.tracking.models import TrackingObservation
from robotic_classroom.tracking.tracker import PersonTracker


class TrackingService:
    """Background image-space tracking service.

    It consumes CameraService snapshots and publishes anonymous target state.
    It has no actuator dependency and cannot command servos or motors.
    """

    def __init__(self, camera: CameraService, config: TrackingConfig) -> None:
        self.camera = camera
        self.config = config
        self.tracker = PersonTracker(config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="person-tracking",
            )
            self._thread.start()

    def _run(self) -> None:
        interval = self.config.poll_interval_ms / 1000.0
        while not self._stop_event.is_set():
            snapshot = self.camera.snapshot()
            self.tracker.update(snapshot)
            self._stop_event.wait(interval)

    def observation(self) -> TrackingObservation:
        return self.tracker.observation

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
