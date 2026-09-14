#!/usr/bin/env python3
"""Safe operator client for the running ZeeAIBotWebCam control API.

This client talks to the already running application on localhost. It acquires a
control lease, sends regular lease-bound heartbeats while a short motion command
is active, and always sends an explicit STOP in a finally block.

Examples:
  python scripts/operator_motion_client.py --direction forward --duration 0.5
  python scripts/operator_motion_client.py --direction left --duration 0.5
  python scripts/operator_motion_client.py --direction rotate-right --duration 0.4
  python scripts/operator_motion_client.py --direction stop

For the first floor test, use a clear area and keep the robot within reach.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
HEARTBEAT_INTERVAL_SECONDS = 0.25

DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "forward": (1.0, 0.0, 0.0),
    "backward": (-1.0, 0.0, 0.0),
    "left": (0.0, -1.0, 0.0),
    "right": (0.0, 1.0, 0.0),
    "rotate-left": (0.0, 0.0, -1.0),
    "rotate-right": (0.0, 0.0, 1.0),
    "stop": (0.0, 0.0, 0.0),
}


def request_json(method: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Cannot reach ZeeAIBotWebCam on http://127.0.0.1:8000. "
            "Start ./scripts/run_pi.sh first."
        ) from exc


def send_stop() -> None:
    request_json(
        "POST",
        "/api/control/motion",
        {"forward": 0.0, "sideways": 0.0, "rotation": 0.0},
    )


def heartbeat_loop(token: str, stop_event: threading.Event, errors: list[Exception]) -> None:
    while not stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
        try:
            request_json("POST", "/api/control/heartbeat", {"token": token})
        except Exception as exc:  # watchdog will stop motion if this fails
            errors.append(exc)
            stop_event.set()
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe operator motion client")
    parser.add_argument("--direction", choices=sorted(DIRECTIONS), required=True)
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Motion duration in seconds (default 0.5, maximum 2.0)",
    )
    args = parser.parse_args()

    if not 0.1 <= args.duration <= 2.0:
        raise SystemExit("--duration must be between 0.1 and 2.0 seconds")

    safety = request_json("GET", "/api/safety")
    print(
        "Safety: "
        f"motion_enabled={safety.get('motion_enabled')} "
        f"watchdog_running={safety.get('watchdog_running')} "
        f"motion_active={safety.get('motion_active')}"
    )

    if args.direction == "stop":
        send_stop()
        print("STOP sent.")
        return

    if not safety.get("motion_enabled"):
        raise SystemExit("Motion is disabled by configuration.")
    if not safety.get("watchdog_running"):
        raise SystemExit("Watchdog is not running; refusing motion.")

    sensors = request_json("GET", "/api/sensors")
    print(f"Ultrasonic distance: {sensors.get('distance_cm')} cm")

    lease = request_json(
        "POST",
        "/api/control/lease",
        {"owner": "operator-motion-client"},
    )
    token = str(lease["token"])

    request_json("POST", "/api/control/heartbeat", {"token": token})

    forward, sideways, rotation = DIRECTIONS[args.direction]
    heartbeat_stop = threading.Event()
    heartbeat_errors: list[Exception] = []
    thread = threading.Thread(
        target=heartbeat_loop,
        args=(token, heartbeat_stop, heartbeat_errors),
        name="operator-heartbeat",
        daemon=True,
    )

    try:
        result = request_json(
            "POST",
            "/api/control/motion",
            {
                "token": token,
                "forward": forward,
                "sideways": sideways,
                "rotation": rotation,
            },
        )
        print(
            f"Motion accepted: direction={args.direction} "
            f"duration={args.duration:.2f}s motion_active={result.get('motion_active')}"
        )
        thread.start()

        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            if heartbeat_errors:
                raise RuntimeError(f"Heartbeat failed: {heartbeat_errors[0]}")
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("Interrupted; sending STOP.")
    finally:
        heartbeat_stop.set()
        if thread.is_alive():
            thread.join(timeout=0.5)
        try:
            send_stop()
            print("STOP sent.")
        except Exception as exc:
            print(f"STOP request failed: {exc}")
            print("The independent 750 ms watchdog should still force chassis stop.")

    final_safety = request_json("GET", "/api/safety")
    print(f"Final motion_active={final_safety.get('motion_active')}")


if __name__ == "__main__":
    main()
