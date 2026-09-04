from __future__ import annotations

import threading

from robotic_classroom.camera.interface import CameraBackend
from robotic_classroom.camera.models import CameraSnapshot, CameraStatus


class CameraService:
    """Application-wide camera owner.

    Every consumer reads from this service; no other module may instantiate
    Picamera2 or open the physical camera directly.
    """

    def __init__(self, backend: CameraBackend) -> None:
        self._backend = backend
        self._lock = threading.RLock()
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._backend.start()
            self._started = True

    def snapshot(self) -> CameraSnapshot:
        with self._lock:
            return self._backend.snapshot()

    def jpeg(self) -> bytes | None:
        with self._lock:
            return self._backend.jpeg()

    def status(self) -> CameraStatus:
        with self._lock:
            return self._backend.status()

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            self._backend.stop()
            self._started = False
