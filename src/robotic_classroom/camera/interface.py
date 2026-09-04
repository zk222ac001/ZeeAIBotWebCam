from __future__ import annotations

from typing import Protocol

from robotic_classroom.camera.models import CameraSnapshot, CameraStatus


class CameraBackend(Protocol):
    def start(self) -> None:
        """Initialize and start the camera backend."""

    def snapshot(self) -> CameraSnapshot:
        """Return the latest frame metadata snapshot."""

    def jpeg(self) -> bytes | None:
        """Return the latest frame encoded as JPEG when available."""

    def status(self) -> CameraStatus:
        """Return backend health and activity state."""

    def stop(self) -> None:
        """Stop the backend and release camera resources."""
