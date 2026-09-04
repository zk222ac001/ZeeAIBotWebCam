from __future__ import annotations

import argparse
import subprocess
import time

from robotic_classroom.audio.xvf3800 import XVF3800USBBackend


def run(command: list[str]) -> None:
    print(f"\n$ {' '.join(command)}")
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    print(result.stdout.strip() or "(no stdout)")
    if result.stderr.strip():
        print(result.stderr.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7 ReSpeaker XVF3800 validation")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args()

    print("=== USB enumeration ===")
    run(["lsusb"])

    print("\n=== ALSA capture devices ===")
    run(["arecord", "-l"])

    print("\n=== XVF3800 VAD / DoA control ===")
    backend = XVF3800USBBackend(vendor_id=0x2886, product_id=0x001A)
    try:
        backend.start()
        for _ in range(args.samples):
            observation = backend.observation()
            print(
                f"seq={observation.sequence:03d} "
                f"speech={int(observation.speech_active)} "
                f"doa={observation.doa_degrees_raw} "
                f"firmware={observation.firmware_version}"
            )
            time.sleep(args.interval)
    except Exception as exc:
        print(f"ERROR: {exc}")
        print(
            "If lsusb shows 2886:001a but this control read fails with permission denied, "
            "configure an appropriate udev rule for the XVF3800 USB device."
        )
        raise SystemExit(1) from exc
    finally:
        backend.stop()


if __name__ == "__main__":
    main()
