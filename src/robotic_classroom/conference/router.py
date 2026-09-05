from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from robotic_classroom.conference.media_probe import probe_alsa_devices
from robotic_classroom.conference.models import SessionDescription
from robotic_classroom.conference.security import require_conference_access

router = APIRouter()


class OfferRequest(BaseModel):
    type: str = Field(pattern="^offer$")
    sdp: str = Field(min_length=1)


class OfferResponse(BaseModel):
    session_id: str
    type: str
    sdp: str


def _protect(request: Request) -> None:
    require_conference_access(request, request.app.state.settings.conference)


@router.get("/api/conference/status")
async def conference_status(request: Request) -> dict[str, object]:
    _protect(request)
    status = await request.app.state.conference.status()
    return {
        "backend": status.backend,
        "enabled": status.enabled,
        "running": status.running,
        "active_sessions": status.active_sessions,
        "max_sessions": status.max_sessions,
        "publish_video": status.publish_video,
        "publish_audio": status.publish_audio,
        "auth_required": request.app.state.settings.conference.auth_required,
        "remote_audio_playback": request.app.state.settings.conference.remote_audio_playback,
        "message": request.app.state.conference_start_error or status.message,
        "sessions": [
            {
                "session_id": session.session_id,
                "state": session.state.value,
                "connection_state": session.connection_state,
                "ice_connection_state": session.ice_connection_state,
                "video_published": session.video_published,
                "audio_published": session.audio_published,
                "remote_audio_allowed": session.remote_audio_allowed,
                "message": session.message,
            }
            for session in status.sessions
        ],
    }


@router.get("/api/conference/media-devices")
def conference_media_devices(request: Request) -> dict[str, object]:
    _protect(request)
    config = request.app.state.settings.conference
    if not config.probe_media_devices:
        return {
            "enabled": False,
            "capture_devices": [],
            "playback_devices": [],
            "message": "Media-device probing disabled",
        }

    probe = probe_alsa_devices()
    return {
        "enabled": True,
        "available": probe.available,
        "capture_devices": probe.capture_devices,
        "playback_devices": probe.playback_devices,
        "configured_input": config.audio_input_device,
        "configured_output": config.audio_output_device,
        "publish_audio": config.publish_audio,
        "remote_audio_playback": config.remote_audio_playback,
        "message": probe.message,
    }


@router.get("/api/operator/status")
async def operator_status(request: Request) -> dict[str, object]:
    _protect(request)
    camera = request.app.state.camera.status()
    audio = request.app.state.audio.observation()
    active = request.app.state.active_speaker.observation()
    conference = await request.app.state.conference.status()
    safety = request.app.state.safety
    settings = request.app.state.settings

    return {
        "camera": {
            "backend": camera.backend,
            "connected": camera.connected,
            "running": camera.running,
            "people_count": camera.people_count,
        },
        "audio": {
            "backend": audio.backend,
            "connected": audio.connected,
            "running": audio.running,
            "speech_state": audio.speech_state.value,
            "doa_degrees": audio.doa_degrees,
        },
        "active_speaker": {
            "state": active.state.value,
            "speaker_id": active.speaker_id,
            "confidence": active.confidence,
        },
        "conference": {
            "backend": conference.backend,
            "running": conference.running,
            "active_sessions": conference.active_sessions,
            "publish_video": conference.publish_video,
            "publish_audio": conference.publish_audio,
            "remote_audio_playback": settings.conference.remote_audio_playback,
        },
        "safety": {
            "state": safety.state.state.value,
            "motion_enabled": settings.safety.motion_enabled,
        },
        "privacy": {
            "recording_enabled": settings.privacy.recording_enabled,
            "face_recognition_enabled": settings.privacy.face_recognition_enabled,
        },
    }


@router.post("/api/conference/offer", response_model=OfferResponse)
async def conference_offer(request: Request, offer: OfferRequest) -> OfferResponse:
    _protect(request)
    try:
        answer = await request.app.state.conference.create_answer(
            SessionDescription(type=offer.type, sdp=offer.sdp)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"WebRTC negotiation failed: {exc}") from exc

    return OfferResponse(
        session_id=answer.session_id,
        type=answer.description.type,
        sdp=answer.description.sdp,
    )


@router.delete("/api/conference/sessions/{session_id}")
async def close_conference_session(request: Request, session_id: str) -> dict[str, str]:
    _protect(request)
    closed = await request.app.state.conference.close_session(session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Conference session not found")
    return {"status": "closed", "session_id": session_id}


@router.get("/conference", response_class=HTMLResponse)
def conference_test_page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ZeeAIBotWebCam Conference</title></head>
<body><h1>ZeeAIBotWebCam WebRTC</h1><p>Telepresence media only. This page has no robot movement controls.</p></body></html>"""


@router.get("/operator", response_class=HTMLResponse)
def operator_page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ZeeAIBotWebCam Operator</title></head>
<body><h1>ZeeAIBotWebCam Operator Dashboard</h1><p>Read-only operational status. No motor or servo commands are exposed here.</p></body></html>"""
