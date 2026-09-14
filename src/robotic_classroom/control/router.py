from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from robotic_classroom.control.commands import MotionCommand

router = APIRouter(prefix="/api/control", tags=["control"])


class MotionRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16, max_length=200)
    forward: float = Field(default=0.0, ge=-1.0, le=1.0)
    sideways: float = Field(default=0.0, ge=-1.0, le=1.0)
    rotation: float = Field(default=0.0, ge=-1.0, le=1.0)


@router.post("/motion")
def submit_motion(payload: MotionRequest, request: Request) -> dict[str, object]:
    """Submit one bounded chassis command through the SafetySupervisor.

    Non-zero motion remains subject to all configured safety gates: motion enable,
    robot state, command validation, control lease, heartbeat freshness, ultrasonic
    obstacle clearance and the independent watchdog. A zero command is always
    allowed so any client can request STOP even without a lease token.
    """

    command = MotionCommand(
        forward=payload.forward,
        sideways=payload.sideways,
        rotation=payload.rotation,
    )
    decision = request.app.state.safety.submit_motion(command, payload.token)

    if not decision.allowed:
        status_code = 403 if "lease" in decision.reason else 409
        raise HTTPException(status_code=status_code, detail=decision.reason)

    return {
        "allowed": True,
        "reason": decision.reason,
        "motion_active": request.app.state.safety.motion_active,
        "command": {
            "forward": command.forward,
            "sideways": command.sideways,
            "rotation": command.rotation,
        },
    }
