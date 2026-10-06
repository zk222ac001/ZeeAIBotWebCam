from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


class AutonomyArmRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16, max_length=200)


def _status_payload(request: Request) -> dict[str, object]:
    status = request.app.state.autonomy.status()
    command = status.planned_command
    return {
        "enabled": status.enabled,
        "mode": status.mode,
        "execution_policy": status.execution_policy,
        "pilot_validated": status.pilot_validated,
        "running": status.running,
        "armed": status.armed,
        "state": status.state.value,
        "target_id": status.target_id,
        "distance_cm": status.distance_cm,
        "stable_target_cycles": status.stable_target_cycles,
        "required_target_stability_cycles": status.required_target_stability_cycles,
        "planned_command": {
            "forward": command.forward,
            "sideways": command.sideways,
            "rotation": command.rotation,
        },
        "motion_executed": status.motion_executed,
        "safety_reason": status.safety_reason,
        "message": status.message,
    }


@router.get("/status")
def autonomy_status(request: Request) -> dict[str, object]:
    return _status_payload(request)


@router.post("/arm")
def autonomy_arm(payload: AutonomyArmRequest, request: Request) -> dict[str, object]:
    armed, reason = request.app.state.autonomy.arm(payload.token)
    if not armed:
        status_code = 403 if "lease" in reason else 409
        raise HTTPException(status_code=status_code, detail=reason)
    return _status_payload(request)


@router.post("/stop")
def autonomy_stop(request: Request) -> dict[str, object]:
    """Disarm autonomy and issue STOP. Stopping never requires a lease."""
    request.app.state.autonomy.disarm()
    return _status_payload(request)
