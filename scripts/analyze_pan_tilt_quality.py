#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import statistics
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
SAMPLE_INTERVAL = 0.2
DURATION_SECONDS = 20.0


def get_json(path: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    print("ZeeAIBotWebCam pan/tilt motion-quality analysis")
    print("Keep ./scripts/run_pi.sh running in another terminal.")
    print("For 20 seconds: stay visible, speak continuously, and move slowly left/right.")
    print("The robot chassis remains disabled.\n")

    samples: list[dict[str, object]] = []
    deadline = time.monotonic() + DURATION_SECONDS
    failures = 0

    while time.monotonic() < deadline:
        try:
            active = get_json("/api/active-speaker/status")
            tracking = get_json("/api/tracking/status")
            pan_tilt = get_json("/api/pan-tilt/plan")
            failures = 0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures += 1
            print(f"temporary API error ({failures}): {exc}")
            if failures >= 5:
                print("FAIL: main application is not reachable.")
                return 1
            time.sleep(SAMPLE_INTERVAL)
            continue

        pan = pan_tilt.get("pan") or {}
        tilt = pan_tilt.get("tilt") or {}
        execution = pan_tilt.get("execution") or {}
        center = tracking.get("center") or {}

        samples.append(
            {
                "active": active.get("state"),
                "target": tracking.get("target_id"),
                "dead_zone": tracking.get("in_dead_zone"),
                "x": center.get("x"),
                "y": center.get("y"),
                "pan": pan.get("planned_pulse"),
                "tilt": tilt.get("planned_pulse"),
                "pan_min": pan.get("minimum"),
                "pan_max": pan.get("maximum"),
                "tilt_min": tilt.get("minimum"),
                "tilt_max": tilt.get("maximum"),
                "executed": execution.get("executed"),
                "error": execution.get("last_error"),
            }
        )
        print(
            f"active={active.get('state'):>18} target={str(tracking.get('target_id')):>10} "
            f"pan={str(pan.get('planned_pulse')):>4} tilt={str(tilt.get('planned_pulse')):>4} "
            f"dead_zone={tracking.get('in_dead_zone')}"
        )
        time.sleep(SAMPLE_INTERVAL)

    usable = [s for s in samples if isinstance(s["pan"], (int, float)) and isinstance(s["tilt"], (int, float))]
    if len(usable) < 5:
        print("\nFAIL: not enough usable pan/tilt samples.")
        return 1

    pan_values = [int(s["pan"]) for s in usable]
    tilt_values = [int(s["tilt"]) for s in usable]
    pan_steps = [abs(b - a) for a, b in zip(pan_values, pan_values[1:])]
    tilt_steps = [abs(b - a) for a, b in zip(tilt_values, tilt_values[1:])]

    selected = sum(1 for s in samples if s["active"] == "speaker_selected")
    speaker_target = sum(1 for s in samples if s["target"] == "Speaker-01")
    executed = sum(1 for s in samples if s["executed"] is True and not s["error"])
    dead_zone = sum(1 for s in samples if s["dead_zone"] is True)

    pan_limit_hits = sum(
        1
        for s in usable
        if s["pan"] in (s["pan_min"], s["pan_max"])
    )
    tilt_limit_hits = sum(
        1
        for s in usable
        if s["tilt"] in (s["tilt_min"], s["tilt_max"])
    )

    pan_mean_step = statistics.fmean(pan_steps) if pan_steps else 0.0
    tilt_mean_step = statistics.fmean(tilt_steps) if tilt_steps else 0.0
    pan_peak_step = max(pan_steps, default=0)
    tilt_peak_step = max(tilt_steps, default=0)

    print("\n--- MOTION QUALITY SUMMARY ---")
    print(f"samples={len(samples)}")
    print(f"speaker_selected_ratio={selected / len(samples):.2f}")
    print(f"speaker_target_ratio={speaker_target / len(samples):.2f}")
    print(f"hardware_execution_ratio={executed / len(samples):.2f}")
    print(f"dead_zone_ratio={dead_zone / len(samples):.2f}")
    print(f"pan_range_seen={min(pan_values)}..{max(pan_values)}")
    print(f"tilt_range_seen={min(tilt_values)}..{max(tilt_values)}")
    print(f"pan_mean_step_us={pan_mean_step:.1f}")
    print(f"pan_peak_step_us={pan_peak_step}")
    print(f"tilt_mean_step_us={tilt_mean_step:.1f}")
    print(f"tilt_peak_step_us={tilt_peak_step}")
    print(f"pan_limit_hits={pan_limit_hits}")
    print(f"tilt_limit_hits={tilt_limit_hits}")

    notes: list[str] = []
    if selected / len(samples) < 0.60:
        notes.append("active-speaker selection is intermittent; improve audio/vision stability before increasing servo speed")
    if speaker_target / len(samples) < 0.60:
        notes.append("tracking does not remain on Speaker-01 consistently")
    if executed / len(samples) < 0.95:
        notes.append("hardware execution is not consistently successful")
    if pan_limit_hits or tilt_limit_hits:
        notes.append("a servo reached a calibrated limit; reduce excursion before increasing gain")
    if pan_peak_step > 25 or tilt_peak_step > 25:
        notes.append("large observed pulse jumps suggest visible jitter or target switching")
    if pan_mean_step < 2 and tilt_mean_step < 2 and dead_zone / len(samples) > 0.70:
        notes.append("tracking is very still; this is good when the speaker remains near frame center")

    if notes:
        print("\nRECOMMENDATION:")
        for note in notes:
            print(f"- {note}")
    else:
        print("\nPASS: motion quality is suitable for conservative tuning.")
        print("Next: adjust gain/dead-zone only if physical movement still feels too slow or too nervous.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
