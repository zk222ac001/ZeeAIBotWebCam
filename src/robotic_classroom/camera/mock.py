from __future__ import annotations

from robotic_classroom.camera.models import CameraSnapshot, CameraStatus, PersonDetection, BoundingBox


class MockCamera:
    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self._running = False
        self._sequence = 0

    def start(self) -> None:
        self._running = True

    def snapshot(self) -> CameraSnapshot:
        if self._running:
            self._sequence += 1
        people = (
            PersonDetection(
                confidence=0.95,
                box=BoundingBox(
                    x=self.width // 3,
                    y=self.height // 4,
                    width=self.width // 5,
                    height=self.height // 2,
                ),
            ),
        ) if self._running else ()
        return CameraSnapshot(
            backend="mock",
            connected=self._running,
            frame_width=self.width,
            frame_height=self.height,
            sequence=self._sequence,
            people=people,
            message="Mock camera backend",
        )

    def jpeg(self) -> bytes | None:
        return None

    def status(self) -> CameraStatus:
        snapshot = self.snapshot()
        return CameraStatus(
            backend=snapshot.backend,
            connected=snapshot.connected,
            running=self._running,
            sequence=snapshot.sequence,
            people_count=len(snapshot.people),
            message=snapshot.message,
        )

    def stop(self) -> None:
        self._running = False
