from __future__ import annotations

import asyncio
from typing import Any

from robotic_classroom.conference.interface import ConferenceBackend
from robotic_classroom.conference.models import (
    ConferenceAnswer,
    ConferenceStatus,
    SessionDescription,
)


class ConferenceService:
    """Application-facing WebRTC conference service."""

    def __init__(self, backend: ConferenceBackend) -> None:
        self.backend = backend
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return
            await self.backend.start()
            self._started = True

    async def create_answer(self, offer: SessionDescription) -> ConferenceAnswer:
        if not self._started:
            raise RuntimeError("Conference service has not been started")
        return await self.backend.create_answer(offer)

    async def close_session(self, session_id: str) -> bool:
        if not self._started:
            return False
        return await self.backend.close_session(session_id)

    async def status(self) -> ConferenceStatus:
        return await self.backend.status()

    def audio_pipeline_status(self) -> dict[str, Any]:
        method = getattr(self.backend, "audio_pipeline_status", None)
        if callable(method):
            return dict(method())

        config = getattr(self.backend, "config", None)
        if config is None:
            return {"available": False, "message": "Audio pipeline status unavailable"}

        return {
            "available": True,
            "microphone_publish_enabled": config.publish_audio,
            "microphone_input_validated": config.audio_input_validated,
            "microphone_device": config.audio_input_device,
            "remote_audio_allowed": config.allow_remote_audio,
            "speaker_playback_enabled": config.remote_audio_playback,
            "speaker_output_validated": config.audio_output_validated,
            "speaker_device": config.audio_output_device,
            "speaker_playback_running": False,
            "speaker_frames_written": 0,
            "speaker_last_error": "",
            "echo_management_mode": config.echo_management_mode,
            "echo_reference_validated": config.echo_reference_validated,
            "full_duplex_requested": bool(config.publish_audio and config.remote_audio_playback),
            "full_duplex_validated": bool(
                config.audio_input_validated
                and config.audio_output_validated
                and (
                    config.echo_management_mode != "aec_reference"
                    or config.echo_reference_validated
                )
            ),
        }

    async def stop(self) -> None:
        async with self._lock:
            if not self._started:
                return
            await self.backend.stop()
            self._started = False
