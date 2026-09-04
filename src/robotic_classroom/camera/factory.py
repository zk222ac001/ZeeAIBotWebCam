from __future__ import annotations

from robotic_classroom.camera.interface import CameraBackend
from robotic_classroom.camera.mock import MockCamera
from robotic_classroom.core.config import Settings


def create_camera_backend(settings: Settings) -> CameraBackend:
    cfg = settings.camera
    if not cfg.enabled or cfg.mode == "mock":
        return MockCamera(width=cfg.width, height=cfg.height)

    from robotic_classroom.camera.imx500 import IMX500Camera

    return IMX500Camera(
        model_path=cfg.model_path,
        width=cfg.width,
        height=cfg.height,
        frame_rate=cfg.frame_rate,
        confidence_threshold=cfg.confidence_threshold,
        jpeg_quality=cfg.jpeg_quality,
        person_label=cfg.person_label,
    )
