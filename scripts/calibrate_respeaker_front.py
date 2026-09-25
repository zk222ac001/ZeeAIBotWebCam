#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request


def circular_mean_degrees(values: list[float]) -> float:
    if not values:
        raise ValueError("No values")
    x = sum(math.cos(math.radians(v)) for v in values)
    y = sum(math.sin(math.radians(v)) for v in values)
    return math.degrees(math.atan2(y, x)) % 360.0


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2.0) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate XVF3800 front direction from live raw DoA samples."
    )
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/api/audio/status",
        help="Audio status endpoint",
    )
    args = parser.parse_args()

    print("XVF3800 front-direction calibration")
    print("Stand directly in front of the camera and speak continuously.")
    print(f"Sampling for {args.duration:.1f}s ...")

    samples: list[float] = []
    deadline = time.monotonic() + args.duration

    while time.monotonic() < deadline:
        try:
            data = fetch_json(args.url)
        except Exception as exc:
            print(f"Read error: {exc}")
            time.sleep(args.interval)
            continue

        if data.get("speech_active") and data.get("doa_degrees_raw") is not None:
            value = float(data["doa_degrees_raw"]) % 360.0
            samples.append(value)
            print(f"raw DoA: {value:7.2f} deg")

        time.sleep(args.interval)

    if len(samples) < 5:
        raise SystemExit(
            "Not enough valid speech samples. Speak continuously and run the test again."
        )

    mean_raw = circular_mean_degrees(samples)
    recommended_offset = (-mean_raw) % 360.0

    print()
    print(f"Valid samples: {len(samples)}")
    print(f"Circular mean raw DoA: {mean_raw:.2f} deg")
    print(f"Recommended orientation_offset_degrees: {recommended_offset:.2f}")
    print()
    print("Update config.pi.yaml with:")
    print(f"  orientation_offset_degrees: {recommended_offset:.2f}")


if __name__ == "__main__":
    main()
