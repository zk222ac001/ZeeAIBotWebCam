from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from robotic_classroom.core.config import ConferenceConfig


def require_conference_access(request: Request, config: ConferenceConfig) -> None:
    if not config.auth_required:
        return

    header = request.headers.get("authorization", "")
    scheme, _, supplied = header.partition(" ")
    expected = config.access_token or ""

    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Conference authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
