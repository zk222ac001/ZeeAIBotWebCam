from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from robotic_classroom.control.security import require_control_access
from robotic_classroom.control.state_machine import RobotState
from robotic_classroom.web.ui import render_page

router = APIRouter(prefix="/api/pan-tilt", tags=["pan-tilt"])


def _authorize(request: Request) -> None:
    require_control_access(request, request.app.state.settings.control_access)
    if request.app.state.safety.state.state in {
        RobotState.EMERGENCY_STOP, RobotState.FAULT, RobotState.SHUTDOWN,
    }:
        raise HTTPException(status_code=409, detail="Clear the safety stop or fault before camera control")
    if not request.app.state.settings.pan_tilt_control.enabled:
        raise HTTPException(status_code=409, detail="Camera planning is disabled")


@router.post("/center", status_code=202)
def center_camera(request: Request) -> dict[str, object]:
    _authorize(request)
    request.app.state.autonomy.disarm()
    if request.app.state.safety.motion_active:
        raise HTTPException(status_code=503, detail="Hardware stop failed; camera centering blocked")
    request.app.state.pan_tilt.center()
    return {
        "center_hold": True,
        "message": "Center requested; automatic camera tracking paused",
        "chassis_motion_requested": False,
    }


@router.post("/resume", status_code=202)
def resume_camera_tracking(request: Request) -> dict[str, object]:
    _authorize(request)
    autonomy = request.app.state.autonomy.status()
    if autonomy.armed and autonomy.mode == "execute":
        raise HTTPException(status_code=409, detail="Disarm chassis autonomy before camera control")
    request.app.state.pan_tilt.resume_tracking()
    return {
        "center_hold": False,
        "message": "Automatic camera tracking requested",
        "chassis_motion_requested": False,
    }


@router.get("/ui", response_class=HTMLResponse)
def camera_control_page(request: Request) -> str:
    config = request.app.state.settings.tracking
    return render_page("camera", attributes={
        "dead-zone-x": config.dead_zone_x,
        "dead-zone-y": config.dead_zone_y,
        "observation-timeout-ms": config.observation_timeout_ms,
    })
