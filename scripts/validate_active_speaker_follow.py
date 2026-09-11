#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
INTERVAL_SECONDS = 0.5


def get_json(path: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    print("ZeeAIBotWebCam active-speaker follow validation")
    print("Keep ./scripts/run_pi.sh running in another terminal.")
    print("Stand in view, speak continuously, then move slowly LEFT/CENTER/RIGHT.")
    print("Ctrl+C to stop.\n")

    failures = 0
    selected_samples = 0
    executed_samples = 0
    last_pan: int | None = None
    last_tilt: int | None = None

    while True:
        try:
            tracking = get_json("/api/tracking/status")
            pan_tilt = get_json("/api/pan-tilt/plan")
            active = get_json("/api/active-speaker/status")
            failures = 0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures += 1
            print(f"temporary API error ({failures}): {exc}")
            if failures >= 5:
                print("Main application is not reachable. Start ./scripts/run_pi.sh first.")
                return 1
            time.sleep(INTERVAL_SECONDS)
            continue

        state = str(active.get("state"))
        target_id = tracking.get("target_id")
        tracking_message = tracking.get("message")
        in_dead_zone = tracking.get("in_dead_zone")

        pan = pan_tilt.get("pan") or {}
        tilt = pan_tilt.get("tilt") or {}
        execution = pan_tilt.get("execution") or {}

        pan_planned = pan.get("planned_pulse")
        tilt_planned = tilt.get("planned_pulse")
        pan_desired = pan.get("desired_pulse")
        tilt_desired = tilt.get("desired_pulse")
        executed = bool(execution.get("executed"))
        error = execution.get("last_error")

        if state == "speaker_selected":
            selected_samples += 1
        if executed:
            executed_samples += 1

        pan_delta = None if last_pan is None or pan_planned is None else int(pan_planned) - last_pan
        tilt_delta = None if last_tilt is None or tilt_planned is None else int(tilt_planned) - last_tilt
        if pan_planned is not None:
            last_pan = int(pan_planned)
        if tilt_planned is not None:
            last_tilt = int(tilt_planned)

        print("=" * 72)
        print(
            f"active={state} tracking_target={target_id} dead_zone={in_dead_zone} "
            f"message={tracking_message}"
        )
        print(
            f"pan:  desired={pan_desired} planned={pan_planned} delta={pan_delta} "
            f"range={pan.get('minimum')}..{pan.get('maximum')}"
        )
        print(
            f"tilt: desired={tilt_desired} planned={tilt_planned} delta={tilt_delta} "
            f"range={tilt.get('minimum')}..{tilt.get('maximum')}"
        )
        print(
            f"execution: requested={execution.get('requested')} executed={executed} "
            f"last_pan={execution.get('last_pan_pulse')} "
            f"last_tilt={execution.get('last_tilt_pulse')} error={error!r}"
        )

        if target_id == "Speaker-01" and executed and not error:
            print("RESULT: active speaker is driving the calibrated pan/tilt path.")
        elif state == "speaker_selected" and target_id != "Speaker-01":
            print("CHECK: speaker selected, but tracking has not switched to Speaker-01 yet.")
        elif state != "speaker_selected":
            print("WAIT: keep speaking while remaining visible to the camera.")

        if pan_planned in (pan.get("minimum"), pan.get("maximum")):
            print("NOTE: pan is at a calibrated limit; do not move farther in that direction.")
        if tilt_planned in (tilt.get("minimum"), tilt.get("maximum")):
            print("NOTE: tilt is at a calibrated limit; do not move farther vertically.")

        print(
            f"samples: speaker_selected={selected_samples} hardware_executed={executed_samples}"
        )
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nValidation stopped.")
