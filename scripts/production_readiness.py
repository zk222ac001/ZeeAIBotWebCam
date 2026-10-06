#!/usr/bin/env python3
"""Read-only Phase 16 production-readiness report over trusted local HTTPS."""
from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def https_origin(value: str) -> str:
    parts = urllib.parse.urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise argparse.ArgumentTypeError(
            "use an HTTPS origin, for example https://localhost:8000"
        )
    return value.rstrip("/")


def fetch_readiness(base_url: str, ca: Path, timeout: float) -> dict[str, Any]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(ca))
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
    )
    request = urllib.request.Request(
        base_url + "/api/readiness",
        headers={"Accept": "application/json"},
        method="GET",
    )
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("response too large")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def render(data: dict[str, Any]) -> str:
    lines = [
        "ZeeAIBotWebCam Phase 16 production-readiness report",
        "",
        f"Production ready: {bool(data.get('production_ready'))}",
        f"Autonomous motion ready: {bool(data.get('autonomous_motion_ready'))}",
        "",
    ]
    categories = data.get("categories")
    if isinstance(categories, dict):
        for name, value in categories.items():
            if not isinstance(value, dict):
                continue
            ready = bool(value.get("ready"))
            lines.append(f"{'PASS' if ready else 'BLOCKED':7} {name}")
            blockers = value.get("blockers")
            if isinstance(blockers, list):
                for blocker in blockers:
                    if isinstance(blocker, str):
                        lines.append(f"         - {blocker}")
    autonomy = data.get("autonomy")
    if isinstance(autonomy, dict):
        lines.extend([
            "",
            "Autonomy gate:",
            f"  mode={autonomy.get('mode')}",
            f"  armed={autonomy.get('armed')}",
            f"  execution_policy={autonomy.get('execution_policy')}",
            f"  pilot_validated={autonomy.get('pilot_validated')}",
        ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=https_origin, default="https://localhost:8000")
    parser.add_argument(
        "--ca",
        type=Path,
        default=ROOT / ".local-certs/zee-local-ca.crt",
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    try:
        data = fetch_readiness(args.base_url, args.ca, args.timeout)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        print("UNAVAILABLE: trusted HTTPS readiness endpoint could not be read")
        return 2

    if args.as_json:
        print(json.dumps(data, indent=2))
    else:
        print(render(data))

    return 0 if data.get("production_ready") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
