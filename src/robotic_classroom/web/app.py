from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from robotic_classroom.camera.factory import create_camera_backend
from robotic_classroom.camera.service import CameraService
from robotic_classroom.core.config import load_settings
from robotic_classroom.hardware.factory import create_hardware_service
from robotic_classroom.safety.supervisor import SafetySupervisor

settings = load_settings()


class LeaseRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=100)


class LeaseResponse(BaseModel):
    token: str
    owner: str
    ttl_seconds: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    hardware = create_hardware_service(settings)
    hardware.start()
    supervisor = SafetySupervisor(settings, hardware)

    camera = CameraService(create_camera_backend(settings))
    camera_start_error = ""
    try:
        camera.start()
    except Exception as exc:
        camera_start_error = str(exc)
        if settings.camera.required:
            supervisor.emergency_stop()
            hardware.stop()
            raise

    app.state.hardware = hardware
    app.state.safety = supervisor
    app.state.camera = camera
    app.state.camera_start_error = camera_start_error

    try:
        yield
    finally:
        supervisor.emergency_stop()
        camera.stop()
        hardware.stop()


app = FastAPI(
    title="ZeeAIBotWebCam",
    version="0.3.0",
    description="AI-powered robotic classroom telepresence platform.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, object]:
    hardware_status = app.state.hardware.status()
    camera_status = app.state.camera.status()
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
        "camera": {
            "backend": camera_status.backend,
            "connected": camera_status.connected,
            "running": camera_status.running,
            "people_count": camera_status.people_count,
            "message": app.state.camera_start_error or camera_status.message,
        },
        "robot_state": app.state.safety.state.state.value,
        "motion_enabled": settings.safety.motion_enabled,
        "recording_enabled": settings.privacy.recording_enabled,
        "face_recognition_enabled": settings.privacy.face_recognition_enabled,
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/api/sensors")
def sensors() -> dict[str, object]:
    snapshot = app.state.hardware.sensors()
    return {
        "battery_voltage": snapshot.battery_voltage,
        "distance_cm": snapshot.distance_cm,
        "infrared": snapshot.infrared,
    }


@app.get("/api/camera/status")
def camera_status() -> dict[str, object]:
    status = app.state.camera.status()
    return {
        "backend": status.backend,
        "connected": status.connected,
        "running": status.running,
        "sequence": status.sequence,
        "people_count": status.people_count,
        "message": app.state.camera_start_error or status.message,
    }


@app.get("/api/camera/detections")
def camera_detections() -> dict[str, object]:
    snapshot = app.state.camera.snapshot()
    return {
        "backend": snapshot.backend,
        "connected": snapshot.connected,
        "sequence": snapshot.sequence,
        "frame": {"width": snapshot.frame_width, "height": snapshot.frame_height},
        "people": [
            {
                "label": person.label,
                "confidence": person.confidence,
                "box": {
                    "x": person.box.x,
                    "y": person.box.y,
                    "width": person.box.width,
                    "height": person.box.height,
                },
            }
            for person in snapshot.people
        ],
    }


@app.get("/api/camera/frame.jpg")
def camera_frame() -> Response:
    jpeg = app.state.camera.jpeg()
    if jpeg is None:
        raise HTTPException(status_code=503, detail="Camera frame is not available")
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/api/safety")
def safety_status() -> dict[str, object]:
    supervisor = app.state.safety
    return {
        "state": supervisor.state.state.value,
        "motion_enabled": settings.safety.motion_enabled,
        "heartbeat_fresh": supervisor.deadman.fresh,
        "control_lease_required": settings.safety.require_control_lease,
        "minimum_obstacle_distance_cm": settings.safety.minimum_obstacle_distance_cm,
    }


@app.post("/api/control/lease", response_model=LeaseResponse)
def acquire_control_lease(request: LeaseRequest) -> LeaseResponse:
    try:
        lease = app.state.safety.leases.acquire(request.owner)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return LeaseResponse(
        token=lease.token,
        owner=lease.owner,
        ttl_seconds=settings.safety.control_lease_ttl_seconds,
    )


@app.post("/api/control/heartbeat")
def heartbeat() -> dict[str, str]:
    app.state.safety.heartbeat()
    return {"status": "heartbeat accepted"}


@app.post("/api/control/emergency-stop")
def emergency_stop() -> dict[str, str]:
    app.state.safety.emergency_stop()
    return {"status": "emergency stop active"}


@app.post("/api/control/reset-stop")
def reset_emergency_stop() -> dict[str, str]:
    app.state.safety.reset_emergency_stop()
    return {"status": "emergency stop reset"}
