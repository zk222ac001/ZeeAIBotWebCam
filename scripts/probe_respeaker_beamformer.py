from __future__ import annotations

import math
import struct
import time
from typing import Any

import usb.core
import usb.util

VID = 0x2886
PID = 0x001A
TIMEOUT_MS = 1000
RETRY = 0x40
ATTEMPTS = 100


def read_control(dev: Any, *, resid: int, cmdid: int, payload_length: int) -> bytes:
    request_type = (
        usb.util.CTRL_IN
        | usb.util.CTRL_TYPE_VENDOR
        | usb.util.CTRL_RECIPIENT_DEVICE
    )
    expected = payload_length + 1
    for attempt in range(ATTEMPTS):
        response = dev.ctrl_transfer(
            request_type,
            0,
            0x80 | cmdid,
            resid,
            expected,
            TIMEOUT_MS,
        )
        data = response.tobytes()
        if len(data) != expected:
            raise RuntimeError(f"unexpected length {len(data)} expected {expected}")
        status = data[0]
        if status == 0:
            return data[1:]
        if status == RETRY:
            time.sleep(0.01)
            continue
        raise RuntimeError(f"status 0x{status:02x}")
    raise RuntimeError("command stayed busy")


def rad_to_deg(value: float) -> float | None:
    if math.isnan(value):
        return None
    return math.degrees(value) % 360.0


def main() -> None:
    print("XVF3800 beamformer diagnostic")
    print("STOP ./scripts/run_pi.sh first. This tool needs exclusive USB control access.")
    print("Speak and move around the microphone while values are printed. Ctrl+C to stop.\n")

    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise SystemExit("ReSpeaker 2886:001a not found")

    try:
        version = read_control(dev, resid=48, cmdid=0, payload_length=3)
        print("firmware=" + ".".join(str(v) for v in version))
        print("Columns: DOA/VAD | selected processed/auto | AEC beams | speech energies")

        while True:
            doa_payload = read_control(dev, resid=20, cmdid=18, payload_length=4)
            doa, vad = struct.unpack("<HH", doa_payload)

            selected_payload = read_control(dev, resid=35, cmdid=11, payload_length=8)
            selected = struct.unpack("<ff", selected_payload)
            selected_deg = [rad_to_deg(v) for v in selected]

            az_payload = read_control(dev, resid=33, cmdid=75, payload_length=16)
            az = struct.unpack("<ffff", az_payload)
            az_deg = [rad_to_deg(v) for v in az]

            energy_payload = read_control(dev, resid=33, cmdid=80, payload_length=16)
            energy = struct.unpack("<ffff", energy_payload)

            print(
                f"doa={doa:3d} vad={vad} | "
                f"selected={selected_deg} | "
                f"aec={az_deg} | "
                f"energy={[round(v, 5) for v in energy]}"
            )
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        usb.util.dispose_resources(dev)


if __name__ == "__main__":
    main()
