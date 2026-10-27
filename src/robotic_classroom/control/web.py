from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from robotic_classroom.web.ui import render_page

router = APIRouter()


@router.get("/ui", response_class=HTMLResponse)
def control_page() -> str:
    return render_page("control")
