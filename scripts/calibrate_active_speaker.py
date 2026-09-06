from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
SAMPLES = 20
INTERVAL = 0.12


def get_operator_status() -> dict:
    with urllib.request.urlopen(BASE + "/api/operator/status", timeout=2) as response:
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
    print("Speak continuously for about 3 seconds...")
    values: list[float] = []
    speech_hits = 0
    for _ in range(SAMPLES):
        status = get_operator_status()
        audio = status.get("audio") or {}
        doa = audio.get("doa_degrees")
        speech_state = audio.get("speech_state")
        if speech_state in {"speaking", "hangover"}:
            speech_hits += 1
        if isinstance(doa, (int, float)):
            values.append(float(doa) % 360.0)
        time.sleep(INTERVAL)

    mean = circular_mean(values)
    print(f"samples={len(values)} speech_hits={speech_hits} mean_doa={mean}")
    return mean


def main() -> None:
    print("ZeeAIBotWebCam ReSpeaker / active-speaker calibration")
    print("Keep ./scripts/run_pi.sh running in another terminal.")
    print("Use one person only and keep the robot/camera stationary during this test.")
    print("Positions should be roughly 1-2 metres from the robot.\n")

    try:
        status = get_operator_status()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"FAIL: cannot reach {BASE}: {exc}")
        return

    audio = status.get("audio") or {}
    if not audio.get("connected"):
        print("FAIL: ReSpeaker audio service is not connected.")
        print("audio status:", audio)
        return

    input("Stand directly in FRONT/CENTER of the camera, then press Enter... ")
    center = collect("CENTER")
    input("Stand clearly to the CAMERA'S LEFT, then press Enter... ")
    left = collect("LEFT")
    input("Stand clearly to the CAMERA'S RIGHT, then press Enter... ")
    right = collect("RIGHT")

    if center is None or left is None or right is None:
        print("\nFAIL: insufficient DoA samples. Speak louder/closer and rerun.")
        return

    offset = (-center) % 360.0
    left_signed = signed_angle(left + offset)
    right_signed = signed_angle(right + offset)

    normal_ok = left_signed < 0 < right_signed
    inverted_ok = (-left_signed) < 0 < (-right_signed)
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
        print("\nLEFT/RIGHT ordering was not clear enough.")
        print("Repeat the test with wider left/right positions and less background noise.")


if __name__ == "__main__":
    main()
