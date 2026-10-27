"""Shared, build-free operator interface served by the robot application."""
from __future__ import annotations

from html import escape
from pathlib import Path
from string import Template

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).parent
router = APIRouter()

ICONS = {
    "overview": '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    "video": '<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10 5-3v10l-5-3"/>',
    "camera": '<path d="M8 5 6 8H3v12h18V8h-3l-2-3Z"/><circle cx="12" cy="13" r="3"/>',
    "control": '<path d="M9 6H7a4 4 0 0 0-4 3l-1 7a3 3 0 0 0 5 2l3-3h4l3 3a3 3 0 0 0 5-2l-1-7a4 4 0 0 0-4-3h-2"/><path d="M7 9v5m-2-2h4m7-1h.01M18 13h.01M10 4h4"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "shield": '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
    "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    "mic": '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8"/>',
    "battery": '<rect x="3" y="7" width="17" height="10" rx="2"/><path d="M23 10v4M7 10v4m4-4v4m4-4v4"/>',
    "people": '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-17a3 3 0 0 1 0 6m2 5a5 5 0 0 1 3 4v2"/>',
    "activity": '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
    "speaker": '<path d="m11 4-6 5H2v6h3l6 5Zm4 4a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
    "link": '<path d="m10 13 4-4m-6 7-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m2 1 2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="m10 2-1 3-3 1-3-1-1 4 2 3-2 3 1 4 3-1 3 1 1 3h4l1-3 3-1 3 1 1-4-2-3 2-3-1-4-3 1-3-1-1-3Z"/>',
    "expand": '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 5 2c-2 1-2 2-2 3m0 3h.01"/>',
}


def icon(name: str, css: str = "") -> str:
    return (f'<svg class="icon {css}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def render_page(page: str, *, attributes: dict[str, object] | None = None) -> str:
    names = {
        "overview": ("Overview", "Your classroom, at a glance."),
        "conference": ("Live session", "Bring everyone into the room."),
        "camera": ("Camera & tracking", "Find the right frame. Keep the conversation in focus."),
        "control": ("Robot control", "Deliberate movement. Clear control."),
        "readiness": ("System readiness", "A clear view of what is working and what comes next."),
    }
    title, subtitle = names[page]
    links = [
        ("overview", "/", "Overview", "overview"),
        ("conference", "/conference", "Live session", "video"),
        ("camera", "/api/pan-tilt/ui", "Camera & tracking", "camera"),
        ("control", "/api/control/ui", "Robot control", "control"),
        ("readiness", "/readiness", "System readiness", "shield"),
    ]
    navigation = "".join(
        f'<a href="{url}" class="nav-link {"active" if key == page else ""}" '
        f'{"aria-current=page" if key == page else ""}>{icon(symbol)}'
        f'<span>{label}</span></a>' for key, url, label, symbol in links
    )
    content = (ROOT / "templates" / f"{page}.html").read_text(encoding="utf-8")
    for name in ICONS:
        content = content.replace(f"@icon:{name}@", icon(name))
    body_attributes = " ".join(
        f'data-{key}="{escape(str(value), quote=True)}"'
        for key, value in (attributes or {}).items()
    )
    return Template((ROOT / "templates" / "shell.html").read_text(encoding="utf-8")).substitute(
        title=title, subtitle=subtitle, page=page, navigation=navigation,
        content=content, attributes=body_attributes,
        access_icon=icon("shield"), help_icon=icon("help"), arrow_icon=icon("arrow"),
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def overview_page() -> str:
    return render_page("overview")


@router.get("/readiness", response_class=HTMLResponse, include_in_schema=False)
def readiness_page() -> str:
    return render_page("readiness")
