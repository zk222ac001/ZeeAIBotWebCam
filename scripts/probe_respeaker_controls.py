from __future__ import annotations

import math
import struct

import usb.core
import usb.util

VID = 0x2886
PID = 0x001A
TIMEOUT_MS = 1000


def read_control(dev, *, resid: int, cmdid: int, payload_length: int) -> tuple[int, bytes]:
    response = dev.ctrl_transfer(
        usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
        0,
        0x80 | cmdid,
        resid,
        payload_length + 1,
        TIMEOUT_MS,
    )
    data = response.tobytes()
    if not data:
        raise RuntimeError("Empty response")
    return data[0], data[1:]


def main() -> None:
    print("ReSpeaker XVF3800 control probe")
    print("Read-only test: no configuration is changed.\n")

    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        print(f"FAIL: device {VID:04x}:{PID:04x} not found")
        return

    try:
        print(f"device: {VID:04x}:{PID:04x} found")

        status, payload = read_control(dev, resid=48, cmdid=0, payload_length=3)
        if status == 0 and len(payload) == 3:
            print("VERSION: PASS", ".".join(str(v) for v in payload))
        else:
            print(f"VERSION: FAIL status=0x{status:02x} payload={payload.hex()}")

        status, payload = read_control(dev, resid=20, cmdid=18, payload_length=4)
        if status == 0 and len(payload) == 4:
            doa, vad = struct.unpack("<HH", payload)
            print(f"DOA_VALUE: PASS doa={doa} vad={vad}")
        else:
            print(f"DOA_VALUE: FAIL status=0x{status:02x} payload={payload.hex()}")

        status, payload = read_control(dev, resid=33, cmdid=75, payload_length=16)
        if status == 0 and len(payload) == 16:
            values = struct.unpack("<ffff", payload)
            degrees = [math.degrees(v) for v in values]
            print(
                "AEC_AZIMUTH_VALUES: PASS",
                " ".join(f"{d:.1f}deg" for d in degrees),
            )
            print(f"auto_selected_beam={degrees[-1] % 360.0:.1f}deg")
        else:
            print(
                f"AEC_AZIMUTH_VALUES: FAIL status=0x{status:02x} "
                f"payload={payload.hex()}"
            )

        print("\nInterpretation:")
        print("- VERSION PASS confirms USB control access is working.")
        print("- DOA_VALUE PASS gives both DoA and VAD and is preferred.")
        print("- If DOA_VALUE fails but AEC_AZIMUTH_VALUES passes, this firmware supports")
        print("  the older/alternate azimuth command and the app needs a compatibility path.")
    finally:
        usb.util.dispose_resources(dev)


if __name__ == "__main__":
    main()
