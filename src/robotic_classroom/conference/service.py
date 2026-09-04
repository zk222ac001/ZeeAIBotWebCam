from __future__ import annotations

import asyncio

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

    async def stop(self) -> None:
        async with self._lock:
            if not self._started:
                return
            await self.backend.stop()
            self._started = False
