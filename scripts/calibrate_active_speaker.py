from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
SAMPLES = 30
INTERVAL = 0.12


def get_audio_status() -> dict:
    with urllib.request.urlopen(BASE + "/api/audio/status", timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def circular_mean(values: list[float]) -> float | None:
    if not values:
        return None
    x = sum(math.cos(math.radians(v)) for v in values)
    y = sum(math.sin(math.radians(v)) for v in values)
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return math.degrees(math.atan2(y, x)) % 360.0


def signed_angle(degrees: float) -> float:
    return ((degrees + 180.0) % 360.0) - 180.0


def collect(label: str) -> float | None:
    print(f"\n{label}")
    print("Speak continuously for about 4 seconds...")
    print("Only live SPEAKING samples are used; hangover/silent samples are ignored.")
    values: list[float] = []
    speech_hits = 0
    raw_seen: list[float] = []

    for _ in range(SAMPLES):
        audio = get_audio_status()
        doa_raw = audio.get("doa_degrees_raw")
        speech_state = audio.get("speech_state")

        if isinstance(doa_raw, (int, float)):
            raw_seen.append(float(doa_raw) % 360.0)

        if speech_state == "speaking" and isinstance(doa_raw, (int, float)):
            speech_hits += 1
            values.append(float(doa_raw) % 360.0)

        time.sleep(INTERVAL)

    mean = circular_mean(values)
    unique = sorted({round(v, 1) for v in raw_seen})
    print(
        f"speaking_samples={len(values)} speech_hits={speech_hits} "
        f"mean_raw_doa={mean} raw_values_seen={unique[:20]}"
    )
    return mean


def main() -> None:
    print("ZeeAIBotWebCam ReSpeaker / active-speaker calibration")
    print("Keep ./scripts/run_pi.sh running in another terminal.")
    print("Use one person only and keep the robot/camera stationary during this test.")
    print("Positions should be roughly 1-2 metres from the robot.")
    print("Use wide left/right positions, about 45-60 degrees from center.\n")

    try:
        audio = get_audio_status()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"FAIL: cannot reach {BASE}: {exc}")
        return

    if not audio.get("connected"):
        print("FAIL: ReSpeaker audio service is not connected.")
        print("audio status:", audio)
        return

    input("Stand directly in FRONT/CENTER of the camera, then press Enter... ")
    center = collect("CENTER")
    input("Stand about 45-60 degrees to the CAMERA'S LEFT, then press Enter... ")
    left = collect("LEFT")
    input("Stand about 45-60 degrees to the CAMERA'S RIGHT, then press Enter... ")
    right = collect("RIGHT")

    if center is None or left is None or right is None:
        print("\nFAIL: insufficient live speaking DoA samples.")
        print("Speak louder/closer and rerun the calibration.")
        return

    offset = (-center) % 360.0
    left_signed = signed_angle(left + offset)
    right_signed = signed_angle(right + offset)

    normal_ok = left_signed < -5.0 and right_signed > 5.0
    inverted_ok = (-left_signed) < -5.0 and (-right_signed) > 5.0
    doa_inverted = False
    verdict = "PASS"

    if normal_ok:
        doa_inverted = False
    elif inverted_ok:
        doa_inverted = True
    else:
        verdict = "CHECK"

    print("\n--- CALIBRATION RESULT ---")
    print(f"center_mean_doa={center:.2f}")
    print(f"left_mean_doa={left:.2f}")
    print(f"right_mean_doa={right:.2f}")
    print(f"recommended_orientation_offset_degrees={offset:.2f}")
    print(f"left_after_offset={left_signed:.2f}")
    print(f"right_after_offset={right_signed:.2f}")
    print(f"recommended_doa_inverted={str(doa_inverted).lower()}")
    print(f"geometry_verdict={verdict}")

    if verdict == "PASS":
        print("\nSend this result to ChatGPT. It can update config.pi.yaml for you.")
        print("Do not manually enable geometry_calibrated yet.")
    else:
        print("\nDoA did not separate LEFT and RIGHT clearly enough.")
        print("Repeat with wider positions and keep the robot/speaker output quiet.")


if __name__ == "__main__":
    main()
