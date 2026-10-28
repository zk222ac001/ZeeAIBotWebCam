#!/usr/bin/env python3
"""Safe operator client for the running ZeeAIBotWebCam control API.

This client uses verified HTTPS to reach the already running application.
Provide CONTROL_ACCESS_TOKEN in the local process environment for protected access. It acquires a
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
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://localhost:8000"
DEFAULT_CA = Path(__file__).resolve().parents[1] / ".local-certs/zee-local-ca.crt"
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ControlClient:
    def __init__(self, base_url: str, ca: Path, access_token: str = "") -> None:
        parts = urllib.parse.urlsplit(base_url)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            raise ValueError("Use an HTTPS origin without credentials")
        if any(ord(c) < 32 or ord(c) > 126 for c in access_token):
            raise ValueError("Control token must contain printable ASCII only")
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(ca))
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context), NoRedirect(),
        )

    def request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        allowed = {
            ("GET", "/api/safety"), ("GET", "/api/sensors"),
            ("POST", "/api/control/lease"), ("POST", "/api/control/heartbeat"),
            ("POST", "/api/control/motion"),
        }
        if (method, path) not in allowed:
            raise ValueError("Unsupported operator request")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        request = urllib.request.Request(
            self.base_url + path, data=body, method=method, headers=headers,
        )
        try:
            with self.opener.open(request, timeout=2.0) as response:
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError("Response too large")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise TypeError("Expected JSON object")
            return result
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise RuntimeError(f"Operator request failed (HTTP {code})") from None
        except (OSError, ValueError, TypeError):
            raise RuntimeError("Cannot read trusted operator endpoint") from None

    def send_stop(self) -> None:
        self.request_json(
            "POST", "/api/control/motion",
            {"forward": 0.0, "sideways": 0.0, "rotation": 0.0},
        )

    def heartbeat_loop(self, token: str, stop_event: threading.Event, errors: list[Exception]) -> None:
        while not stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                self.request_json("POST", "/api/control/heartbeat", {"token": token})
            except RuntimeError as exc:
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
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--ca", type=Path, default=DEFAULT_CA)
    args = parser.parse_args()

    if not 0.1 <= args.duration <= 2.0:
        raise SystemExit("--duration must be between 0.1 and 2.0 seconds")

    try:
        client = ControlClient(args.base_url, args.ca, os.environ.get("CONTROL_ACCESS_TOKEN", ""))
    except (OSError, ValueError):
        raise SystemExit("Cannot initialize trusted operator client; check HTTPS origin, CA and token") from None

    safety = client.request_json("GET", "/api/safety")
    print(
        "Safety: "
        f"motion_enabled={safety.get('motion_enabled')} "
        f"watchdog_running={safety.get('watchdog_running')} "
        f"motion_active={safety.get('motion_active')}"
    )

    if args.direction == "stop":
        client.send_stop()
        print("STOP sent.")
        return

    if safety.get("state") != "idle":
        raise SystemExit("Robot must be idle; inspect and clear any stop/fault latch through the operator UI.")
    if safety.get("motion_active") is not False:
        raise SystemExit("Chassis is active or unknown; send STOP and inspect before commanding motion.")
    if not safety.get("motion_enabled"):
        raise SystemExit("Motion is disabled by configuration.")
    if not safety.get("watchdog_running"):
        raise SystemExit("Watchdog is not running; refusing motion.")

    sensors = client.request_json("GET", "/api/sensors")
    print(f"Ultrasonic distance: {sensors.get('distance_cm')} cm")

    lease = client.request_json(
        "POST",
        "/api/control/lease",
        {"owner": "operator-motion-client"},
    )
    token = str(lease["token"])

    client.request_json("POST", "/api/control/heartbeat", {"token": token})

    forward, sideways, rotation = DIRECTIONS[args.direction]
    heartbeat_stop = threading.Event()
    heartbeat_errors: list[Exception] = []
    thread = threading.Thread(
        target=client.heartbeat_loop,
        args=(token, heartbeat_stop, heartbeat_errors),
        name="operator-heartbeat",
        daemon=True,
    )

    try:
        result = client.request_json(
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
            client.send_stop()
            print("STOP sent.")
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"STOP request failed: {exc}")
            print("Physical stop is unconfirmed. Use the physical emergency stop and inspect the robot.")
            raise RuntimeError("STOP was not confirmed") from None

    final_safety = client.request_json("GET", "/api/safety")
    print(f"Final motion_active={final_safety.get('motion_active')}")
    if final_safety.get("motion_active") is not False:
        raise RuntimeError("Final chassis motion is active or unknown; inspect the robot")


if __name__ == "__main__":
    main()
