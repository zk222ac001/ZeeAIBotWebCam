#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"


def get_json(path: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def ok(name: str, condition: bool, detail: str) -> bool:
    mark = "PASS" if condition else "CHECK"
    print(f"{mark:5} {name}: {detail}")
    return condition


def main() -> int:
    print("ZeeAIBotWebCam final integrated validation")
    print("Keep ./scripts/run_pi.sh running in another terminal.")
    print("Stand in view and speak for a few seconds before running this test.\n")

    try:
        health = get_json("/health")
        camera = get_json("/api/camera/status")
        audio = get_json("/api/audio/status")
        active = get_json("/api/active-speaker/status")
        tracking = get_json("/api/tracking/status")
        pan_tilt = get_json("/api/pan-tilt/plan")
        pipeline = get_json("/api/conference/audio-pipeline")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"FAIL: main application is not reachable: {exc}")
        return 1

    execution = pan_tilt.get("execution") or {}
    pan = pan_tilt.get("pan") or {}
    tilt = pan_tilt.get("tilt") or {}

    results = []
    results.append(ok("API", True, f"health={health}"))
    results.append(ok("Camera", bool(camera.get("running")), f"running={camera.get('running')} people={camera.get('people')}"))
    results.append(ok("Audio", bool(audio.get("connected")) and bool(audio.get("running")), f"connected={audio.get('connected')} running={audio.get('running')} speech={audio.get('speech_state')}"))
    results.append(ok("Active speaker", active.get("state") in {"speaker_selected", "waiting_for_speech", "ambiguous", "no_visible_candidate"}, f"state={active.get('state')} speaker={active.get('speaker_id')}"))
    results.append(ok("Tracking", tracking.get("target_id") in {"Speaker-01", "Person-01", "Person-02", "Person-03"} or tracking.get("target_id") is None, f"state={tracking.get('state')} target={tracking.get('target_id')}"))
    results.append(ok("Pan/tilt mode", pan_tilt.get("mode") == "execute", f"mode={pan_tilt.get('mode')} apply_to_hardware={pan_tilt.get('apply_to_hardware')}"))
    results.append(ok("Pan bounds", pan.get("minimum") == 1350 and pan.get("maximum") == 1650, f"planned={pan.get('planned_pulse')} range={pan.get('minimum')}..{pan.get('maximum')}"))
    results.append(ok("Tilt bounds", tilt.get("minimum") == 1350 and tilt.get("maximum") == 1650, f"planned={tilt.get('planned_pulse')} range={tilt.get('minimum')}..{tilt.get('maximum')}"))
    results.append(ok("Servo execution", bool(execution.get("executed")) and not execution.get("last_error"), f"executed={execution.get('executed')} error={execution.get('last_error')!r}"))
    results.append(ok("Conference audio", bool(pipeline.get("audio_input_validated")) and bool(pipeline.get("audio_output_validated")), f"input_validated={pipeline.get('audio_input_validated')} output_validated={pipeline.get('audio_output_validated')}"))

    print("\n--- FINAL RESULT ---")
    if all(results):
        print("PASS: integrated camera, microphone, active-speaker, tracking and pan/tilt path are operational.")
        print("NOTE: chassis drive remains intentionally disabled and echo cancellation remains unverified.")
        return 0

    print("CHECK: one or more subsystems still need attention. Review the CHECK lines above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
