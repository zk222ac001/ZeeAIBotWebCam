from __future__ import annotations

from fastapi import APIRouter, Request

from robotic_classroom.conference.security import require_conference_access

router = APIRouter()


@router.get("/api/conference/audio-pipeline")
def conference_audio_pipeline(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    require_conference_access(request, settings.conference)

    status = request.app.state.conference.audio_pipeline_status()
    status["movement_requested"] = False
    status["recording_enabled"] = settings.privacy.recording_enabled
    return status
