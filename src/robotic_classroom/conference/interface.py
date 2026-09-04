from __future__ import annotations

from typing import Protocol

from robotic_classroom.conference.models import ConferenceAnswer, ConferenceStatus, SessionDescription


class ConferenceBackend(Protocol):
    async def start(self) -> None: ...

    async def create_answer(self, offer: SessionDescription) -> ConferenceAnswer: ...

    async def close_session(self, session_id: str) -> bool: ...

    async def status(self) -> ConferenceStatus: ...

    async def stop(self) -> None: ...
