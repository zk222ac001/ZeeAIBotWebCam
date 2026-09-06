from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ENDPOINTS = [
    ("health", "/health"),
    ("tracking", "/api/tracking/status"),
    ("pan_tilt", "/api/pan-tilt/plan"),
]


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    print("ZeeAIBotWebCam tracking diagnostic")
    print("Keep the main app running in the first terminal.")
    print("Stand off-center in front of the camera and move slowly left/right.\n")

    for i in range(15):
        print(f"--- sample {i + 1}/15 ---")
        try:
            health = get_json("/health")
            tracking = get_json("/api/tracking/status")
            pan_tilt = get_json("/api/pan-tilt/plan")
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"ERROR: cannot reach {BASE}: {exc}")
            print("Make sure ./scripts/run_pi.sh is still running in the first terminal.")
            return

        camera = health.get("camera", {})
        execution = pan_tilt.get("execution") or {}
        pan = pan_tilt.get("pan", {})
        tilt = pan_tilt.get("tilt", {})

        print(
            "camera:",
            f"running={camera.get('running')}",
            f"people={camera.get('people_count')}",
        )
        print(
            "tracking:",
            f"state={tracking.get('state')}",
            f"target={tracking.get('target_id')}",
            f"error={tracking.get('error')}",
            f"dead_zone={tracking.get('in_dead_zone')}",
        )
        print(
            "pan_tilt:",
            f"mode={pan_tilt.get('mode')}",
            f"validated={pan_tilt.get('calibration_validated')}",
            f"enabled={pan_tilt.get('hardware_enabled')}",
        )
        print(
            "pulses:",
            f"pan={pan.get('planned_pulse')}",
            f"tilt={tilt.get('planned_pulse')}",
            f"executed={execution.get('executed')}",
            f"last_pan={execution.get('last_pan_pulse')}",
            f"last_tilt={execution.get('last_tilt_pulse')}",
        )
        if execution.get("last_error"):
            print("executor_error:", execution.get("last_error"))

        print()
        time.sleep(1)


if __name__ == "__main__":
    main()
