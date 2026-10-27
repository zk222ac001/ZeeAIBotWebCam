from __future__ import annotations

import argparse
import json
import math
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://localhost:8000"
INTERVAL = 0.12


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def status_client(base_url: str, ca: Path):
    parts = urllib.parse.urlsplit(base_url)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
        or parts.path not in ("", "/") or parts.query or parts.fragment):
        raise ValueError("Use an HTTPS origin, for example https://localhost:8000")
    context = ssl.create_default_context(cafile=str(ca))
    client = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context), NoRedirect(),
    )
    token = os.environ.get("CONFERENCE_ACCESS_TOKEN", "")
    if token:
        if any(ord(char) < 32 or ord(char) > 126 for char in token):
            raise ValueError("Conference token must contain printable ASCII only")
        client.addheaders = [("Authorization", f"Bearer {token}")]
    return client


def get_audio_status(client, base_url: str) -> dict:
    with client.open(base_url.rstrip("/") + "/api/audio/status", timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def circular_mean(values: list[float]) -> float | None:
    if not values:
        return None
    x = sum(math.cos(math.radians(v)) for v in values)
    y = sum(math.sin(math.radians(v)) for v in values)
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return math.degrees(math.atan2(y, x)) % 360.0


def stable_direction(values: list[float]) -> float | None:
    """Reject weak or scattered measurements instead of inventing calibration."""
    if len(values) < 10 or not all(math.isfinite(v) for v in values):
        return None
    mean = circular_mean(values)
    if mean is None:
        return None
    # Measurement-quality criterion, not a robot safety or accuracy guarantee.
    close = sum(abs(signed_angle(v - mean)) <= 15 for v in values)
    return mean if close / len(values) >= 0.8 else None


def signed_angle(degrees: float) -> float:
    return ((degrees + 180.0) % 360.0) - 180.0


def live_direction(audio: dict, seen: set[int]) -> float | None:
    sequence = audio.get("sequence")
    if type(sequence) is not int or sequence in seen:
        return None
    seen.add(sequence)
    raw = audio.get("doa_degrees_raw")
    if (audio.get("connected") is not True or audio.get("running") is not True
        or audio.get("speech_state") != "speaking"
        or type(raw) not in (int, float) or not math.isfinite(raw)):
        return None
    return float(raw) % 360.0


def collect(
    label: str, client, base_url: str, duration: float, source: str
) -> float | None:
    print(f"\n{label}")
    print("Stay still at this position and start speaking; allowing 2 seconds to settle...",
          flush=True)
    time.sleep(2)
    print(f"Speak continuously for {duration:g} seconds...")
    print("Only live SPEAKING samples are used; hangover/silent samples are ignored.")
    values: list[float] = []
    seen: set[int] = set()
    deadline = time.monotonic() + duration

    while time.monotonic() < deadline:
        audio = get_audio_status(client, base_url)
        if audio.get("doa_source") != source:
            raise ValueError("Direction source changed during calibration")
        value = live_direction(audio, seen)
        if value is not None:
            values.append(value)
        time.sleep(INTERVAL)

    mean = stable_direction(values)
    print(
        f"fresh_speaking_samples={len(values)} stable_mean_raw_doa={mean}"
    )
    if values:
        bins: dict[int, int] = {}
        for value in values:
            bucket = int(value // 15) * 15
            bins[bucket] = bins.get(bucket, 0) + 1
        print(f"Direction bins (degrees: sample count): {dict(sorted(bins.items()))}")
    return mean


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only fixed-microphone direction calibration")
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument("--ca", type=Path, default=ROOT / ".local-certs/zee-local-ca.crt")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--source", choices=["processed", "auto_selected", "primary"],
                        default="processed")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 3 <= args.duration <= 30:
        parser.error("--duration must be 3..30 seconds")
    print("ZeeAIBotWebCam ReSpeaker / active-speaker calibration")
    print("Keep the existing application running; do not start another instance.")
    print("For a microphone FIXED TO THE CHASSIS: use the robot's forward direction,")
    print("not the camera's current pan direction. Keep the chassis stationary.")
    print("Use one local speaker. Pause YouTube, mute browser sending, and keep others quiet.")
    print("This helper only reads status; it does not move hardware or change configuration.")
    print("Positions should be roughly 1-2 metres from the robot.")
    print("Use left/right positions about 30-45 degrees from chassis front.\n")

    try:
        client = status_client(args.base_url, args.ca)
        audio = get_audio_status(client, args.base_url)
    except (OSError, ValueError):
        print("FAIL: check the HTTPS origin, trusted CA file, and running service.")
        return

    if not audio.get("connected"):
        print("FAIL: ReSpeaker audio service is not connected.")
        print("audio status:", audio)
        return
    if audio.get("doa_source") != args.source:
        print(f"FAIL: running direction source={audio.get('doa_source', 'unreported')}; "
              f"expected={args.source}.")
        print("Restart the service with the updated source configuration before calibrating.")
        return
    print(f"Calibrating direction source: {args.source}")

    try:
        input("Stand directly in front of the ROBOT CHASSIS, then press Enter... ")
        center = collect("CENTER", client, args.base_url, args.duration, args.source)
        input("Move 30-45 degrees to the ROBOT'S LEFT (viewed from behind), press Enter... ")
        left = collect("LEFT", client, args.base_url, args.duration, args.source)
        input("Move 30-45 degrees to the ROBOT'S RIGHT (viewed from behind), press Enter... ")
        right = collect("RIGHT", client, args.base_url, args.duration, args.source)
    except (OSError, ValueError):
        print("FAIL: status read failed; no calibration recommendation produced.")
        return

    if center is None or left is None or right is None:
        print("\nFAIL: insufficient fresh speech samples or direction was too scattered.")
        print("Use one speaker in a quiet room and repeat. Configuration was not changed.")
        return

    offset = (-center) % 360.0
    left_signed = signed_angle(left + offset)
    right_signed = signed_angle(right + offset)

    normal_ok = -120 < left_signed < -10 and 10 < right_signed < 120
    inverted_ok = -120 < -left_signed < -10 and 10 < -right_signed < 120
    doa_inverted = False
    verdict = "PASS"

    if normal_ok:
        doa_inverted = False
    elif inverted_ok:
        doa_inverted = True
    else:
        verdict = "CHECK"

    print("\n--- CALIBRATION RESULT ---")
    print(f"doa_source={args.source}")
    print(f"center_mean_doa={center:.2f}")
    print(f"left_mean_doa={left:.2f}")
    print(f"right_mean_doa={right:.2f}")
    print(f"recommended_orientation_offset_degrees={offset:.2f}")
    print(f"left_after_offset={left_signed:.2f}")
    print(f"right_after_offset={right_signed:.2f}")
    print(f"recommended_doa_inverted={str(doa_inverted).lower()}")
    print(f"geometry_verdict={verdict}")

    if verdict == "PASS":
        print("\nShare the result for review before applying it to config.pi.yaml.")
        print("This checks microphone direction only; camera pan geometry still needs measurement.")
    else:
        print("\nDoA did not separate LEFT and RIGHT clearly enough.")
        print("Repeat with wider positions and keep the robot/speaker output quiet.")


if __name__ == "__main__":
    main()
