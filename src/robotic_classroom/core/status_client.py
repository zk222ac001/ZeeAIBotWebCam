"""Trusted, read-only transport for local operator diagnostics."""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PATHS = frozenset({
    "/health", "/ready", "/api/readiness", "/api/safety", "/api/sensors",
    "/api/camera/status", "/api/audio/status", "/api/active-speaker/status",
    "/api/tracking/status", "/api/pan-tilt/plan", "/api/conference/status",
    "/api/conference/audio-pipeline", "/api/autonomy/status",
})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_status(path: str, *, timeout: float = 2.0, base_url: str | None = None) -> dict[str, Any]:
    """Read an allowlisted endpoint; never redirect credentials or print responses.

    ZEE_BASE_URL and ZEE_CA override the local trusted HTTPS defaults. Only the
    conference token is used here; control leases and writes are unsupported.
    """
    base = base_url or os.environ.get("ZEE_BASE_URL", "https://localhost:8000")
    token = os.environ.get("CONFERENCE_ACCESS_TOKEN", "")
    try:
        parts = urllib.parse.urlsplit(base)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.path not in ("", "/") or parts.query or parts.fragment
                or path not in PATHS):
            raise ValueError("Unsupported diagnostic endpoint")
        if any(ord(c) < 32 or ord(c) > 126 for c in token):
            raise ValueError("Invalid token characters")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=os.environ.get(
            "ZEE_CA", str(Path.cwd() / ".local-certs/zee-local-ca.crt"),
        ))
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context), NoRedirect(),
        )
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(base.rstrip("/") + path, headers=headers, method="GET")
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("Response too large")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise TypeError("Expected JSON object")
        return payload
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise urllib.error.URLError(f"Diagnostic endpoint returned HTTP {code}") from None
    except (OSError, ValueError, TypeError):
        raise urllib.error.URLError("Check diagnostic HTTPS origin, CA and conference token") from None
