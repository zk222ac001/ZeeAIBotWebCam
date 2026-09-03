#!/usr/bin/env python3
"""Guarded, manual-only actuator validation for Phase 2.

This script never performs autonomous movement. It requires an explicit
--confirm-motion flag and is intended for bench testing with wheels lifted.
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


def load_board():
    if not VENDOR.exists():
        raise RuntimeError(f"Vendor repository missing: {VENDOR}")
    vendor = str(VENDOR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    rrc = importlib.import_module("HiwonderSDK.ros_robot_controller_sdk")
    device = os.getenv("TURBOPI_SERIAL_DEVICE", "/dev/ttyAMA0")
    return rrc.Board(device=device)


def require_confirmation(args: argparse.Namespace) -> None:
    if not args.confirm_motion:
        raise SystemExit(
            "Motion refused. Re-run with --confirm-motion only after the robot is safely prepared."
        )


def stop_all(board) -> None:
    board.set_motor_duty([[1, 0], [2, 0], [3, 0], [4, 0]])


def motor_test(args: argparse.Namespace) -> None:
    require_confirmation(args)
    if args.id not in {1, 2, 3, 4}:
        raise SystemExit("Motor ID must be 1, 2, 3 or 4")
    if abs(args.duty) > 20:
        raise SystemExit("Phase 2 limits motor duty to +/-20")
    if not 0.05 <= args.duration <= 0.5:
        raise SystemExit("Phase 2 limits duration to 0.05..0.5 seconds")

    print("SAFETY CHECK: all wheels must be lifted clear of the work surface.")
    print(f"Testing motor {args.id}: duty={args.duty}, duration={args.duration}s")
    board = load_board()
    try:
        stop_all(board)
        time.sleep(0.2)
        board.set_motor_duty([[args.id, args.duty]])
        time.sleep(args.duration)
    finally:
        try:
            stop_all(board)
            time.sleep(0.1)
        finally:
            port = getattr(board, "port", None)
            if port is not None and getattr(port, "is_open", False):
                port.close()
    print("Motor test complete; all motor duties commanded to zero.")


def servo_test(args: argparse.Namespace) -> None:
    require_confirmation(args)
    if args.id not in {1, 2}:
        raise SystemExit("Phase 2 PWM servo ID must be 1 or 2")
    if not 1350 <= args.pulse <= 1650:
        raise SystemExit("Phase 2 initially restricts servo pulse to 1350..1650")

    print("SAFETY CHECK: camera ribbon and mechanical mount must be clear through servo motion.")
    print(f"Testing PWM servo {args.id}: pulse={args.pulse}")
    board = load_board()
    try:
        board.pwm_servo_set_position(0.3, [[args.id, args.pulse]])
        time.sleep(0.5)
    finally:
        port = getattr(board, "port", None)
        if port is not None and getattr(port, "is_open", False):
            port.close()
    print("Servo command complete. Record actual axis, centre and mechanical behaviour.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Phase 2 actuator tests")
    sub = parser.add_subparsers(dest="command", required=True)

    motor = sub.add_parser("motor")
    motor.add_argument("--id", type=int, required=True)
    motor.add_argument("--duty", type=int, required=True)
    motor.add_argument("--duration", type=float, default=0.25)
    motor.add_argument("--confirm-motion", action="store_true")
    motor.set_defaults(func=motor_test)

    servo = sub.add_parser("servo")
    servo.add_argument("--id", type=int, required=True)
    servo.add_argument("--pulse", type=int, default=1500)
    servo.add_argument("--confirm-motion", action="store_true")
    servo.set_defaults(func=servo_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
