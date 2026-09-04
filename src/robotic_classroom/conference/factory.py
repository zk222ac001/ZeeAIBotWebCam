from __future__ import annotations

from robotic_classroom.camera.service import CameraService
from robotic_classroom.conference.aiortc_backend import AiortcConferenceBackend
from robotic_classroom.conference.interface import ConferenceBackend
from robotic_classroom.conference.mock import MockConferenceBackend
from robotic_classroom.core.config import Settings


def create_conference_backend(settings: Settings, camera: CameraService) -> ConferenceBackend:
    if settings.conference.mode == "mock":
        return MockConferenceBackend(settings.conference)
    if settings.conference.mode == "aiortc":
        return AiortcConferenceBackend(
            settings.conference,
            camera,
            frame_rate=settings.camera.frame_rate,
        )
    raise ValueError(f"Unsupported conference mode: {settings.conference.mode}")
