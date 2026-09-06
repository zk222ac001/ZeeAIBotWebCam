from __future__ import annotations

import math
import time

from robotic_classroom.audio.xvf3800 import XVF3800USBBackend

SAMPLES = 30
INTERVAL = 0.12


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


def collect(backend: XVF3800USBBackend, label: str) -> float | None:
    print(f"\n{label}")
    print("Speak continuously for about 4 seconds...")
    values: list[float] = []
    vad_hits = 0
    errors = 0

    for _ in range(SAMPLES):
        try:
            observation = backend.observation()
            if observation.speech_active:
                vad_hits += 1
            if observation.doa_degrees_raw is not None:
                values.append(float(observation.doa_degrees_raw) % 360.0)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  metadata retry: {exc}")
        time.sleep(INTERVAL)

    mean = circular_mean(values)
    unique = sorted({round(v, 1) for v in values})
    print(
        f"valid_samples={len(values)} vad_hits={vad_hits} errors={errors} "
        f"mean_raw_doa={mean} raw_values_seen={unique[:24]}"
    )
    return mean


def main() -> None:
    print("Direct ReSpeaker XVF3800 DoA calibration")
    print("IMPORTANT: stop ./scripts/run_pi.sh before running this tool.")
    print("This script talks directly to the ReSpeaker USB control interface.")
    print("Keep the robot stationary and use one speaker, 1-2 metres away.\n")

    backend = XVF3800USBBackend(vendor_id=0x2886, product_id=0x001A)
    backend.start()
    try:
        input("Stand directly in FRONT/CENTER, then press Enter... ")
        center = collect(backend, "CENTER")
        input("Stand about 60 degrees to the CAMERA'S LEFT, then press Enter... ")
        left = collect(backend, "LEFT")
        input("Stand about 60 degrees to the CAMERA'S RIGHT, then press Enter... ")
        right = collect(backend, "RIGHT")
        input("Stand directly BEHIND the robot, then press Enter... ")
        back = collect(backend, "BACK")
    finally:
        backend.stop()

    print("\n--- DIRECT DOA MAP ---")
    print(f"front={center}")
    print(f"left={left}")
    print(f"right={right}")
    print(f"back={back}")

    if center is None or left is None or right is None:
        print("result=CHECK")
        print("Not enough valid DoA samples. Do not enable active-speaker geometry.")
        return

    offset = (-center) % 360.0
    left_signed = signed_angle(left + offset)
    right_signed = signed_angle(right + offset)

    normal_ok = left_signed < -5.0 and right_signed > 5.0
    inverted_ok = (-left_signed) < -5.0 and (-right_signed) > 5.0

    if normal_ok:
        inverted = False
        verdict = "PASS"
    elif inverted_ok:
        inverted = True
        verdict = "PASS"
    else:
        inverted = False
        verdict = "CHECK"

    print("\n--- CALIBRATION RESULT ---")
    print(f"recommended_orientation_offset_degrees={offset:.2f}")
    print(f"left_after_offset={left_signed:.2f}")
    print(f"right_after_offset={right_signed:.2f}")
    print(f"recommended_doa_inverted={str(inverted).lower()}")
    print(f"geometry_verdict={verdict}")


if __name__ == "__main__":
    main()
