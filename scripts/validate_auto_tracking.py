from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    print("ZeeAIBotWebCam automatic tracking validation")
    print("Keep the main app running in another terminal.")
    print("Stand 1-2 m in front of the camera and move slowly left/right, then up/down.\n")

    detected = False
    tracked = False
    pulse_changed = False
    executed = False
    pan_values: set[int] = set()
    tilt_values: set[int] = set()

    for i in range(20):
        try:
            health = get_json("/health")
            tracking = get_json("/api/tracking/status")
            plan = get_json("/api/pan-tilt/plan")
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"FAIL: cannot reach {BASE}: {exc}")
            print("Start the app first with ./scripts/run_pi.sh")
            return

        camera = health.get("camera", {})
        execution = plan.get("execution") or {}
        pan = plan.get("pan", {})
        tilt = plan.get("tilt", {})

        people = int(camera.get("people_count") or 0)
        state = tracking.get("state")
        pan_pulse = pan.get("planned_pulse")
        tilt_pulse = tilt.get("planned_pulse")

        if people > 0:
            detected = True
        if state == "tracking":
            tracked = True
        if isinstance(pan_pulse, int):
            pan_values.add(pan_pulse)
        if isinstance(tilt_pulse, int):
            tilt_values.add(tilt_pulse)
        if execution.get("executed") is True:
            executed = True

        if len(pan_values) > 1 or len(tilt_values) > 1:
            pulse_changed = True

        print(
            f"{i + 1:02d}/20 "
            f"people={people} state={state} "
            f"pan={pan_pulse} tilt={tilt_pulse} "
            f"executed={execution.get('executed')} "
            f"error={execution.get('last_error') or '-'}"
        )
        time.sleep(0.75)

    print("\n--- RESULT ---")
    print("person_detection:", "PASS" if detected else "FAIL")
    print("person_tracking:", "PASS" if tracked else "FAIL")
    print("servo_execution_gate:", "PASS" if executed else "FAIL")
    print("tracking_pulse_changes:", "PASS" if pulse_changed else "FAIL")
    print("pan_values:", sorted(pan_values))
    print("tilt_values:", sorted(tilt_values))

    if detected and tracked and executed and pulse_changed:
        print("\nPASS: automatic person-following pipeline is active.")
        print("Visually confirm the camera moves toward you, not away from you.")
    elif not detected:
        print("\nFAIL: no person detection reached the tracker.")
    elif not tracked:
        print("\nFAIL: detections exist but tracking did not acquire a target.")
    elif not executed:
        print("\nFAIL: tracking exists but hardware execution is not active.")
    else:
        print("\nFAIL: tracking is active but pulse values did not change.")
        print("Move farther away from the image center and rerun the test.")


if __name__ == "__main__":
    main()
