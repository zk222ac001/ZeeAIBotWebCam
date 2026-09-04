from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import monotonic


class ConferenceState(str, Enum):
    DISABLED = "disabled"
    IDLE = "idle"
    NEGOTIATING = "negotiating"
    CONNECTED = "connected"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class ConferenceSession:
    session_id: str
    state: ConferenceState
    connection_state: str
    ice_connection_state: str
    video_published: bool
    audio_published: bool
    remote_audio_allowed: bool
    created_monotonic: float
    last_activity_monotonic: float
    message: str = ""


@dataclass(frozen=True, slots=True)
class ConferenceStatus:
    backend: str
    enabled: bool
    running: bool
    active_sessions: int
    max_sessions: int
    publish_video: bool
    publish_audio: bool
    sessions: tuple[ConferenceSession, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class SessionDescription:
    type: str
    sdp: str


@dataclass(frozen=True, slots=True)
class ConferenceAnswer:
    session_id: str
    description: SessionDescription


def new_session(
    session_id: str,
    *,
    state: ConferenceState,
    connection_state: str = "new",
    ice_connection_state: str = "new",
    video_published: bool = False,
    audio_published: bool = False,
    remote_audio_allowed: bool = True,
    message: str = "",
) -> ConferenceSession:
    now = monotonic()
    return ConferenceSession(
        session_id=session_id,
        state=state,
        connection_state=connection_state,
        ice_connection_state=ice_connection_state,
        video_published=video_published,
        audio_published=audio_published,
        remote_audio_allowed=remote_audio_allowed,
        created_monotonic=now,
        last_activity_monotonic=now,
        message=message,
    )
