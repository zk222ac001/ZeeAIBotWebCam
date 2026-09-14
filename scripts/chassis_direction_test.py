#!/usr/bin/env python3
"""Guarded TurboPi mecanum direction validation.

Manual bench diagnostic only. This script does not enable application chassis
motion. It sends one short, explicitly requested wheel pattern at a time so the
physical motor mapping and direction can be validated safely.

Keep all four wheels lifted clear of the work surface for the first validation.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "TurboPi"

# Hiwonder TurboPi mecanum sign convention derived from upstream mecanum.py:
# forward (direction=90):  M1 -, M2 +, M3 -, M4 +
# backward:                inverse
# left (direction=180):    M1 +, M2 +, M3 -, M4 -
# right (direction=0):     inverse
# Rotation candidates follow the same upstream angular-rate convention and
# must be physically observed before being treated as validated left/right.
PATTERNS = {
    "forward": (-1, +1, -1, +1),
    "backward": (+1, -1, +1, -1),
    "left": (+1, +1, -1, -1),
    "right": (-1, -1, +1, +1),
    "rotate-left": (+1, +1, +1, +1),
    "rotate-right": (-1, -1, -1, -1),
}


def load_board():
    if not VENDOR.exists():
        raise SystemExit(
            f"TurboPi vendor SDK not found at {VENDOR}. "
            "Run scripts/bootstrap_pi.sh first."
        )

    vendor = str(VENDOR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)

    rrc = importlib.import_module("HiwonderSDK.ros_robot_controller_sdk")
    device = os.getenv("TURBOPI_SERIAL_DEVICE", "/dev/ttyAMA0")
    return rrc.Board(device=device)


def stop_all(board, repeats: int = 10, interval: float = 0.05) -> None:
    for _ in range(repeats):
        board.set_motor_duty([[1, 0], [2, 0], [3, 0], [4, 0]])
        time.sleep(interval)


def close_board(board) -> None:
    port = getattr(board, "port", None)
    if port is not None and getattr(port, "is_open", False):
        try:
            port.flush()
        except Exception:
            pass
        time.sleep(0.1)
        port.close()


def duties_for(step: str, duty: int) -> list[list[int]]:
    signs = PATTERNS[step]
    return [[index + 1, signs[index] * duty] for index in range(4)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Guarded TurboPi forward/back/strafe/rotation direction test"
    )
    parser.add_argument(
        "--step",
        required=True,
        choices=list(PATTERNS),
        help="Run exactly one short chassis direction pattern",
    )
    parser.add_argument(
        "--duty",
        type=int,
        default=30,
        help="Absolute motor duty, limited to 20..35 (default: 30)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.35,
        help="Pattern duration in seconds, limited to 0.10..0.50 (default: 0.35)",
    )
    parser.add_argument(
        "--confirm-motion",
        action="store_true",
        help="Required acknowledgement that the robot is safely prepared",
    )
    args = parser.parse_args()

    if not args.confirm_motion:
        raise SystemExit(
            "Motion refused. Lift all wheels clear of the work surface and re-run with --confirm-motion."
        )
    if not 20 <= args.duty <= 35:
        raise SystemExit("For this diagnostic, --duty must be between 20 and 35.")
    if not 0.10 <= args.duration <= 0.50:
        raise SystemExit("For this diagnostic, --duration must be between 0.10 and 0.50 seconds.")

    commands = duties_for(args.step, args.duty)

    print("TurboPi guarded chassis direction test")
    print("=======================================")
    print("IMPORTANT: first validation must be performed with all four wheels lifted.")
    print("Application chassis motion remains disabled; this is a manual bench test only.")
    print(f"Step: {args.step}")
    print(f"Duty commands: {commands}")
    print(f"Duration: {args.duration:.2f}s")
    if args.step.startswith("rotate-"):
        print("Observe the physical rotation direction; rotation naming is not validated until you confirm it.")

    board = load_board()
    try:
        stop_all(board)
        time.sleep(0.3)
        board.set_motor_duty(commands)
        time.sleep(args.duration)
    except KeyboardInterrupt:
        print("\nEmergency stop requested.")
    finally:
        try:
            stop_all(board, repeats=12)
            print("STOP sent repeatedly to M1-M4.")
        finally:
            close_board(board)


if __name__ == "__main__":
    main()
