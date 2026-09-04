from __future__ import annotations

import asyncio
from time import monotonic
from uuid import uuid4

from robotic_classroom.conference.models import (
    ConferenceAnswer,
    ConferenceSession,
    ConferenceState,
    ConferenceStatus,
    SessionDescription,
    new_session,
)
from robotic_classroom.core.config import ConferenceConfig


class MockConferenceBackend:
    def __init__(self, config: ConferenceConfig) -> None:
        self.config = config
        self._running = False
        self._sessions: dict[str, ConferenceSession] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._running = self.config.enabled

    async def create_answer(self, offer: SessionDescription) -> ConferenceAnswer:
        if not self._running:
            raise RuntimeError("Conference backend is not running")
        if offer.type != "offer" or not offer.sdp.strip():
            raise ValueError("A non-empty SDP offer is required")

        async with self._lock:
            if len(self._sessions) >= self.config.max_sessions:
                raise RuntimeError("Maximum conference session count reached")

            session_id = uuid4().hex
            session = new_session(
                session_id,
                state=ConferenceState.CONNECTED,
                connection_state="connected",
                ice_connection_state="connected",
                video_published=self.config.publish_video,
                audio_published=self.config.publish_audio,
                remote_audio_allowed=self.config.allow_remote_audio,
                message="Mock WebRTC session connected",
            )
            self._sessions[session_id] = session

        answer = SessionDescription(
            type="answer",
            sdp="v=0\r\no=mock 0 0 IN IP4 127.0.0.1\r\ns=ZeeAIBotWebCam Mock\r\nt=0 0\r\n",
        )
        return ConferenceAnswer(session_id=session_id, description=answer)

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            return session is not None

    async def status(self) -> ConferenceStatus:
        now = monotonic()
        timeout = float(self.config.session_timeout_seconds)
        async with self._lock:
            stale = [
                sid
                for sid, session in self._sessions.items()
                if now - session.last_activity_monotonic > timeout
            ]
            for sid in stale:
                self._sessions.pop(sid, None)

            sessions = tuple(self._sessions.values())

        return ConferenceStatus(
            backend="mock",
            enabled=self.config.enabled,
            running=self._running,
            active_sessions=len(sessions),
            max_sessions=self.config.max_sessions,
            publish_video=self.config.publish_video,
            publish_audio=self.config.publish_audio,
            sessions=sessions,
            message="Mock conference backend",
        )

    async def stop(self) -> None:
        async with self._lock:
            self._sessions.clear()
        self._running = False
