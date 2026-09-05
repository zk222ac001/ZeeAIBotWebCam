"""WebRTC conference transport services."""

from robotic_classroom.conference.audio_router import router as audio_router
from robotic_classroom.conference.router import router as conference_router

conference_router.include_router(audio_router)
