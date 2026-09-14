#!/usr/bin/env python3
"""Reusable guarded TurboPi motor test.

Bench-test M1-M4 one at a time at low duty. The script refuses to run unless
--confirm-motion is supplied and should only be used with all wheels lifted
clear of the work surface.
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
MOTOR_NAMES = {
    1: "M1 - left front",
    2: "M2 - right front",
    3: "M3 - left rear",
    4: "M4 - right rear",
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


def stop_all(board, repeats: int = 8, interval: float = 0.05) -> None:
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


def test_motor(board, motor_id: int, duty: int, duration: float, pause: float) -> None:
    print(f"\nTesting {MOTOR_NAMES[motor_id]}: duty={duty}, duration={duration:.2f}s")
    stop_all(board)
    time.sleep(0.2)

    board.set_motor_duty([[motor_id, duty]])
    time.sleep(duration)

    stop_all(board)
    print(f"{MOTOR_NAMES[motor_id]} stopped")
    time.sleep(pause)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safe low-speed TurboPi M1-M4 bench test"
    )
    parser.add_argument(
        "--confirm-motion",
        action="store_true",
        help="Required acknowledgement that all wheels are lifted clear of the work surface",
    )
    parser.add_argument(
        "--motor",
        type=int,
        choices=[1, 2, 3, 4],
        help="Test only one motor. Omit to test M1, M2, M3 and M4 sequentially.",
    )
    parser.add_argument(
        "--duty",
        type=int,
        default=15,
        help="Motor duty, limited to -20..20 (default: 15)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Run time per motor in seconds, limited to 0.1..0.5 (default: 0.5)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="Pause between motors in seconds (default: 1.0)",
    )
    args = parser.parse_args()

    if not args.confirm_motion:
        raise SystemExit(
            "Motion refused. Lift all four wheels clear of the table, then re-run with --confirm-motion."
        )
    if abs(args.duty) > 20:
        raise SystemExit("Duty is limited to -20..20 for this safety test.")
    if not 0.1 <= args.duration <= 0.5:
        raise SystemExit("Duration must be between 0.1 and 0.5 seconds.")
    if args.pause < 0.2:
        raise SystemExit("Pause must be at least 0.2 seconds.")

    print("TurboPi safe motor test")
    print("=======================")
    print("SAFETY: all four wheels must be lifted clear of the work surface.")
    print("Press Ctrl+C at any time to stop the test.")
    print("Expected mapping: M1 left-front, M2 right-front, M3 left-rear, M4 right-rear.")

    board = load_board()
    try:
        stop_all(board, repeats=10)
        motors = [args.motor] if args.motor else [1, 2, 3, 4]
        for motor_id in motors:
            test_motor(board, motor_id, args.duty, args.duration, args.pause)
    except KeyboardInterrupt:
        print("\nEmergency stop requested.")
    finally:
        try:
            stop_all(board, repeats=12)
            print("All M1-M4 motor duties commanded to zero.")
        finally:
            close_board(board)


if __name__ == "__main__":
    main()
