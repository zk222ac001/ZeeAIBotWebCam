#!/usr/bin/env python3
"""Read-only Phase 2 hardware validation for ZeeAIBotWebCam.

This script intentionally sends no motor or servo commands.
"""
from __future__ import annotations

import argparse
import importlib
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "TurboPi"


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = (proc.stdout + proc.stderr).strip()
    return proc.returncode, text


def system_check() -> None:
    model_path = Path("/proc/device-tree/model")
    model = model_path.read_text(errors="ignore").replace("\x00", "").strip() if model_path.exists() else "unknown"
    print(f"Raspberry Pi model: {model}")
    print(f"Platform: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Architecture: {platform.machine()}")
    print(f"Project root: {ROOT}")
    print(f"Vendor repo present: {VENDOR.exists()}")


def i2c_check() -> None:
    code, output = run(["i2cdetect", "-y", "1"])
    if code != 0:
        print("i2cdetect failed. Install i2c-tools and confirm I2C is enabled.")
        print(output)
        return
    print(output)
    print("Expected TurboPi devices: ultrasonic 0x77, four-channel IR 0x78")


def _vendor_import(module: str):
    if not VENDOR.exists():
        raise RuntimeError(f"Vendor repository missing: {VENDOR}")
    vendor = str(VENDOR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    return importlib.import_module(module)


def controller_check() -> None:
    rrc = _vendor_import("HiwonderSDK.ros_robot_controller_sdk")
    device = os.getenv("TURBOPI_SERIAL_DEVICE", "/dev/ttyAMA0")
    print(f"Opening Hiwonder controller: {device}")
    board = rrc.Board(device=device)
    board.enable_reception()
    try:
        values: list[int] = []
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and len(values) < 5:
            value = board.get_battery()
            if value is not None:
                values.append(int(value))
                print(f"Battery sample: {value} mV ({value / 1000.0:.3f} V)")
            time.sleep(0.1)
        if not values:
            print("No battery telemetry received. Controller opened, but reception/board communication needs investigation.")
        else:
            avg = sum(values) / len(values)
            print(f"Average battery: {avg:.1f} mV ({avg / 1000.0:.3f} V)")
    finally:
        board.enable_reception(False)
        port = getattr(board, "port", None)
        if port is not None and getattr(port, "is_open", False):
            port.close()
        print("Controller serial port closed.")


def sonar_check() -> None:
    sonar_mod = _vendor_import("HiwonderSDK.Sonar")
    sonar = sonar_mod.Sonar()
    print("Ultrasonic samples (raw vendor units):")
    for _ in range(10):
        raw = sonar.getDistance()
        print(f"  {raw}  (~{raw / 10.0:.1f} cm using TurboPi example convention)")
        time.sleep(0.2)


def ir_check() -> None:
    infrared_mod = _vendor_import("HiwonderSDK.FourInfrared")
    sensor = infrared_mod.FourInfrared()
    print("Four-channel IR samples (vendor True = black line detected):")
    for _ in range(20):
        values = sensor.readData()
        print("  " + " ".join(f"IR{i + 1}={value}" for i, value in enumerate(values)))
        time.sleep(0.25)


def audio_check() -> None:
    for command in (["lsusb"], ["arecord", "-l"], ["aplay", "-l"]):
        print(f"\n$ {' '.join(command)}")
        _, output = run(list(command))
        print(output or "(no output)")


def all_readonly() -> None:
    system_check()
    print("\n--- I2C ---")
    i2c_check()
    print("\n--- Audio/USB ---")
    audio_check()
    print("\nController, sonar and IR are not automatically opened by --all to keep discovery minimally invasive.")
    print("Run --controller, --sonar and --ir explicitly after confirming wiring and power.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe read-only Phase 2 hardware validation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--system", action="store_true")
    group.add_argument("--i2c", action="store_true")
    group.add_argument("--controller", action="store_true")
    group.add_argument("--sonar", action="store_true")
    group.add_argument("--ir", action="store_true")
    group.add_argument("--audio", action="store_true")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.system:
        system_check()
    elif args.i2c:
        i2c_check()
    elif args.controller:
        controller_check()
    elif args.sonar:
        sonar_check()
    elif args.ir:
        ir_check()
    elif args.audio:
        audio_check()
    else:
        all_readonly()


if __name__ == "__main__":
    main()
