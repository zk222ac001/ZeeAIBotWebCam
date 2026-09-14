#!/usr/bin/env python3
"""Guarded real-hardware validation of the FastAPI chassis control path.

The test enables chassis motion only in memory and never edits config.pi.yaml.
It exercises the same FastAPI endpoints used by an operator client:

1. acquire control lease
2. send lease-bound heartbeat
3. send one short forward command through /api/control/motion
4. send an explicit zero-motion STOP
5. verify safety status reports motion inactive

All four wheels must be lifted clear of the work surface.
Do not run the normal application at the same time because both processes would
compete for the TurboPi serial device.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ["APP_CONFIG"] = str(ROOT / "config.pi.yaml")

from fastapi.testclient import TestClient
from robotic_classroom.web import app as app_module


def port_in_use(host: str = "127.0.0.1", port: int = 8000) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def require_ok(response, label: str) -> dict:
    try:
        payload = response.json()
    except Exception:
        payload = {"text": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"{label} failed: HTTP {response.status_code} {payload}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded API-controlled TurboPi motion test")
    parser.add_argument(
        "--confirm-wheels-lifted",
        action="store_true",
        help="Required acknowledgement that all four wheels are lifted clear of the surface",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.30,
        help="Forward motion duration in seconds, limited to 0.10..0.40 (default: 0.30)",
    )
    args = parser.parse_args()

    if not args.confirm_wheels_lifted:
        raise SystemExit(
            "Motion refused. Lift all four wheels clear of the work surface and re-run "
            "with --confirm-wheels-lifted."
        )
    if not 0.10 <= args.duration <= 0.40:
        raise SystemExit("--duration must be between 0.10 and 0.40 seconds")
    if port_in_use():
        raise SystemExit(
            "Port 8000 is already in use. Stop ./scripts/run_pi.sh first so this guarded "
            "hardware test has exclusive access to the TurboPi controller."
        )

    settings = app_module.settings
    if settings.hardware.mode != "real":
        raise SystemExit("config.pi.yaml is not using real hardware mode")
    if not settings.hardware.motor_mapping_validated:
        raise SystemExit("Motor mapping is not marked as validated")

    # Test-only override. The YAML file is never modified.
    settings.safety.motion_enabled = True

    print("TurboPi API motion hardware validation")
    print("=======================================")
    print("IMPORTANT: Keep all four wheels lifted for the entire test.")
    print("config.pi.yaml remains unchanged; motion is enabled only in this process.")
    print(f"Command duration: {args.duration:.2f}s")

    with TestClient(app_module.app) as client:
        sensors = require_ok(client.get("/api/sensors"), "sensor check")
        distance = sensors.get("distance_cm")
        print(f"Ultrasonic distance: {distance} cm")
        if distance is None:
            raise RuntimeError("Ultrasonic distance is unavailable; refusing motion test")
        if float(distance) < settings.safety.minimum_obstacle_distance_cm:
            raise RuntimeError(
                "Obstacle is inside the configured safety distance. Clear the area in front "
                "of the ultrasonic sensor and repeat the test."
            )

        lease = require_ok(
            client.post("/api/control/lease", json={"owner": "api-motion-hardware-test"}),
            "control lease",
        )
        token = lease["token"]
        print("Control lease acquired.")

        require_ok(
            client.post("/api/control/heartbeat", json={"token": token}),
            "heartbeat",
        )
        print("Lease-bound heartbeat accepted.")

        motion = require_ok(
            client.post(
                "/api/control/motion",
                json={
                    "token": token,
                    "forward": 1.0,
                    "sideways": 0.0,
                    "rotation": 0.0,
                },
            ),
            "forward motion",
        )
        print(
            "Forward API command accepted: "
            f"allowed={motion.get('allowed')} motion_active={motion.get('motion_active')}"
        )
        if not motion.get("motion_active"):
            raise RuntimeError("Motion command was accepted but motion_active was not true")

        time.sleep(args.duration)

        stop = require_ok(
            client.post(
                "/api/control/motion",
                json={
                    "forward": 0.0,
                    "sideways": 0.0,
                    "rotation": 0.0,
                },
            ),
            "explicit stop",
        )
        print(f"STOP API command accepted: motion_active={stop.get('motion_active')}")

        safety = require_ok(client.get("/api/safety"), "safety status")
        print(f"watchdog_running: {safety.get('watchdog_running')}")
        print(f"heartbeat_fresh:  {safety.get('heartbeat_fresh')}")
        print(f"motion_active:    {safety.get('motion_active')}")

        if safety.get("motion_active"):
            raise RuntimeError("FAIL: chassis still reports active motion after explicit STOP")
        if not safety.get("watchdog_running"):
            raise RuntimeError("FAIL: watchdog is not running")

        print("RESULT: PASS - API lease, heartbeat, motion and explicit STOP path validated.")


if __name__ == "__main__":
    main()
