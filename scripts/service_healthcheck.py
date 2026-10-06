#!/usr/bin/env python3
"""Verify the locally deployed HTTPS application after systemd startup.

The check is read-only. It never acquires a lease, sends motion, arms autonomy,
or disables TLS verification.
"""
from __future__ import annotations

import argparse
import json
import math
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def positive_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return result


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


class HealthClient:
    def __init__(self, base_url: str, ca: Path, timeout: float) -> None:
        self.base_url = base_url
        self.timeout = timeout
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(ca))
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
        )

    def get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            headers={"Accept": "application/json"},
            method="GET",
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("response too large")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        return payload


def validate(
    ready: dict[str, Any],
    safety: dict[str, Any],
    autonomy: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if ready.get("status") != "ready":
        issues.append("application is not ready")
    if safety.get("watchdog_running") is not True:
        issues.append("safety watchdog is not running")
    if safety.get("motion_active") is not False:
        issues.append("chassis motion is active or unknown")
    if autonomy.get("running") is not True:
        issues.append("autonomy service is not running")
    if autonomy.get("armed") is not False:
        issues.append("autonomy unexpectedly started armed")
    return issues


def check_once(client: HealthClient) -> list[str]:
    ready = client.get("/ready")
    safety = client.get("/api/safety")
    autonomy = client.get("/api/autonomy/status")
    return validate(ready, safety, autonomy)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=https_origin, default="https://localhost:8000")
    parser.add_argument(
        "--ca",
        type=Path,
        default=ROOT / ".local-certs/zee-local-ca.crt",
    )
    parser.add_argument("--wait", type=positive_float, default=1.0)
    parser.add_argument("--interval", type=positive_float, default=1.0)
    parser.add_argument("--timeout", type=positive_float, default=2.0)
    args = parser.parse_args(argv)

    try:
        client = HealthClient(args.base_url, args.ca, args.timeout)
    except (OSError, ValueError):
        print("UNHEALTHY: cannot initialize trusted HTTPS health check")
        return 1

    deadline = time.monotonic() + args.wait
    last_error = "application did not become healthy"
    while True:
        try:
            issues = check_once(client)
            if not issues:
                print("HEALTHY: HTTPS, safety watchdog, and autonomy service are ready")
                return 0
            last_error = "; ".join(issues)
        except (OSError, ValueError, urllib.error.URLError):
            last_error = "HTTPS status endpoints are not ready"

        if time.monotonic() >= deadline:
            print(f"UNHEALTHY: {last_error}")
            return 1
        time.sleep(min(args.interval, max(0.0, deadline - time.monotonic())))


if __name__ == "__main__":
    raise SystemExit(main())
