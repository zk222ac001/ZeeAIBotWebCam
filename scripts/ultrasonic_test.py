#!/usr/bin/env python3
"""Read-only validation for the Hiwonder TurboPi I2C ultrasonic sensor.

The sensor is expected at I2C address 0x77 and Hiwonder's SDK returns distance
in millimetres. This script never commands chassis motion.
"""
from __future__ import annotations

import argparse
import importlib
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "TurboPi"


def load_sonar():
    if not VENDOR.exists():
        raise SystemExit(
            f"TurboPi vendor SDK not found at {VENDOR}. Run scripts/bootstrap_pi.sh first."
        )

    vendor = str(VENDOR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)

    sonar_module = importlib.import_module("HiwonderSDK.Sonar")
    return sonar_module.Sonar()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only TurboPi ultrasonic distance validation"
    )
    parser.add_argument("--samples", type=int, default=20, help="Number of samples (default: 20)")
    parser.add_argument("--interval", type=float, default=0.15, help="Seconds between samples (default: 0.15)")
    parser.add_argument(
        "--obstacle-cm",
        type=float,
        default=30.0,
        help="Distance below which an obstacle is reported (default: 30 cm)",
    )
    args = parser.parse_args()

    if not 1 <= args.samples <= 200:
        raise SystemExit("--samples must be between 1 and 200")
    if not 0.05 <= args.interval <= 5.0:
        raise SystemExit("--interval must be between 0.05 and 5.0 seconds")
    if not 1.0 <= args.obstacle_cm <= 500.0:
        raise SystemExit("--obstacle-cm must be between 1 and 500 cm")

    sonar = load_sonar()
    sonar.setRGBMode(0)

    print("TurboPi ultrasonic sensor validation")
    print("====================================")
    print("Expected I2C address: 0x77")
    print(f"Obstacle threshold: {args.obstacle_cm:.1f} cm")
    print("No motor commands will be sent.\n")

    readings_cm: list[float] = []
    for index in range(1, args.samples + 1):
        distance_mm = sonar.getDistance()
        distance_cm = distance_mm / 10.0
        readings_cm.append(distance_cm)

        status = "OBSTACLE" if distance_cm < args.obstacle_cm else "clear"
        print(f"{index:02d}: {distance_cm:7.1f} cm  [{status}]")
        time.sleep(args.interval)

    valid = [value for value in readings_cm if 0.0 < value < 500.0]
    max_range = [value for value in readings_cm if value >= 500.0]

    print("\nSummary")
    print("-------")
    if valid:
        print(f"Valid samples: {len(valid)}/{len(readings_cm)}")
        print(f"Minimum:       {min(valid):.1f} cm")
        print(f"Median:        {statistics.median(valid):.1f} cm")
        print(f"Maximum:       {max(valid):.1f} cm")
    else:
        print("No in-range readings below 500 cm were observed.")

    if max_range:
        print(f"At/max range:  {len(max_range)}/{len(readings_cm)} sample(s) reported 500 cm")

    if all(value >= 500.0 for value in readings_cm):
        print("RESULT: CHECK SENSOR/WIRING or place an object within 0.05-5 m and repeat.")
    else:
        print("RESULT: Sensor is returning usable distance measurements.")


if __name__ == "__main__":
    main()
