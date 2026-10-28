from __future__ import annotations

import json
import subprocess
import sys
import urllib.error

from robotic_classroom.core.status_client import read_status

BASE = "https://localhost:8000"


def get_json(path: str) -> dict:
    return read_status(path, timeout=3.0)


def main() -> None:
    print("ZeeAIBotWebCam next-level active-speaker phase")
    print("This step verifies ReSpeaker metadata before calibration.\n")

    try:
        audio = get_json("/api/audio/status")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"FAIL: cannot reach {BASE}: {exc}")
        print("Start the main app first with ./scripts/run_pi.sh")
        sys.exit(1)

    print("audio status:")
    print(json.dumps(audio, indent=2))

    connected = audio.get("connected") is True
    running = audio.get("running") is True
    doa = audio.get("doa_degrees")

    if not connected or not running or doa is None:
        print("\nNOT READY FOR CALIBRATION")
        print("ReSpeaker VAD/DoA metadata must be available first.")
        print("Do not enable geometry_calibrated yet.")
        sys.exit(2)

    print("\nPASS: ReSpeaker metadata is available.")
    print("Launching center/left/right active-speaker calibration...\n")
    raise SystemExit(subprocess.call([sys.executable, "scripts/calibrate_active_speaker.py"]))


if __name__ == "__main__":
    main()
