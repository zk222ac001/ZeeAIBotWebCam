from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from robotic_classroom.core.config import load_settings
from robotic_classroom.hardware.factory import create_hardware_service

settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    hardware = create_hardware_service(settings)
    hardware.start()
    app.state.hardware = hardware
    try:
        yield
    finally:
        hardware.stop()


app = FastAPI(
    title="ZeeAIBotWebCam",
    version="0.1.0",
    description="AI-powered robotic classroom telepresence platform.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, object]:
    hardware_status = app.state.hardware.status()
    return {
        "status": "ok",
        "application": settings.application.name,
        "environment": settings.application.environment,
        "hardware": {
            "backend": hardware_status.backend,
            "connected": hardware_status.connected,
            "battery_voltage": hardware_status.battery_voltage,
            "message": hardware_status.message,
        },
        "motion_enabled": settings.safety.motion_enabled,
        "recording_enabled": settings.privacy.recording_enabled,
        "face_recognition_enabled": settings.privacy.face_recognition_enabled,
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}
