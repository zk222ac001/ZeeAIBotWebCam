from __future__ import annotations

import json
import math
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
INTERVAL = 0.5


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def signed_angle(degrees: float) -> float:
    return ((degrees + 180.0) % 360.0) - 180.0


def main() -> None:
    print("ZeeAIBotWebCam active-speaker fusion diagnostic")
    print("Keep ./scripts/run_pi.sh running. Stand in view and speak.")
    print("Ctrl+C to stop.\n")

    try:
        while True:
            audio = get_json("/api/audio/status")
            camera = get_json("/api/camera/detections")
            fusion = get_json("/api/active-speaker/status")

            doa = audio.get("doa_degrees")
            doa_signed = signed_angle(float(doa)) if isinstance(doa, (int, float)) else None
            people = camera.get("people") or []
            frame = camera.get("frame") or {}
            width = max(int(frame.get("width") or 1), 1)

            candidates = []
            for index, person in enumerate(people):
                box = person.get("box") or {}
                center_x = (float(box.get("x", 0)) + float(box.get("width", 0)) / 2.0) / width
                camera_angle = (center_x - 0.5) * 70.0
                candidates.append(
                    {
                        "index": index,
                        "confidence": round(float(person.get("confidence") or 0), 3),
                        "center_x": round(center_x, 3),
                        "camera_angle": round(camera_angle, 2),
                    }
                )

            print("=" * 72)
            print(
                f"audio: speech={audio.get('speech_state')} raw={audio.get('doa_degrees_raw')} "
                f"calibrated={doa} signed={None if doa_signed is None else round(doa_signed, 2)}"
            )
            print(f"camera: people={len(people)} candidates={candidates}")
            print(
                "fusion: "
                f"state={fusion.get('state')} speaker={fusion.get('speaker_id')} "
                f"confidence={fusion.get('confidence')} candidate={fusion.get('candidate_index')} "
                f"camera_angle={fusion.get('camera_angle_degrees')} "
                f"doa={fusion.get('doa_degrees')} error={fusion.get('angular_error_degrees')}"
            )
            print(f"reason: {fusion.get('message')}")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
