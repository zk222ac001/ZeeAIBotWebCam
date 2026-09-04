from __future__ import annotations

from robotic_classroom.audio.interface import AudioBackend
from robotic_classroom.audio.mock import MockAudioBackend
from robotic_classroom.core.config import Settings


def create_audio_backend(settings: Settings) -> AudioBackend:
    if settings.audio.mode == "mock":
        return MockAudioBackend()

    from robotic_classroom.audio.xvf3800 import XVF3800USBBackend

    return XVF3800USBBackend(
        vendor_id=settings.audio.vendor_id,
        product_id=settings.audio.product_id,
    )
