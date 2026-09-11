#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import wave

BASE_URL = "http://127.0.0.1:8000"
MIC_DEVICE = "plughw:2,0"
SPEAKER_DEVICE = "plughw:3,0"
SAMPLE_RATE = 16000
CHANNELS = 2
DURATION = 4


def get_json(path: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=1.0) as response:
        return json.loads(response.read().decode("utf-8"))


def app_is_running() -> bool:
    try:
        get_json("/health")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    return True


def rms_dbfs(path: str) -> float:
    with wave.open(path, "rb") as wav:
        width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if width != 2 or not frames:
        raise RuntimeError("Expected 16-bit PCM WAV")
    samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
    mean_square = sum(float(v) * float(v) for v in samples) / len(samples)
    if mean_square <= 0.0:
        return -120.0
    rms = math.sqrt(mean_square)
    return 20.0 * math.log10(rms / 32768.0)


def record(path: str, with_speaker: bool) -> None:
    capture = subprocess.Popen(
        [
            "arecord",
            "-D",
            MIC_DEVICE,
            "-f",
            "S16_LE",
            "-r",
            str(SAMPLE_RATE),
            "-c",
            str(CHANNELS),
            "-d",
            str(DURATION),
            path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.5)
    speaker = None
    if with_speaker and capture.poll() is None:
        speaker = subprocess.Popen(
            [
                "speaker-test",
                "-D",
                SPEAKER_DEVICE,
                "-t",
                "sine",
                "-f",
                "700",
                "-r",
                "48000",
                "-c",
                "1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    try:
        _, stderr = capture.communicate(timeout=DURATION + 3)
    finally:
        if speaker is not None:
            speaker.terminate()
            try:
                speaker.wait(timeout=2)
            except subprocess.TimeoutExpired:
                speaker.kill()
    if capture.returncode != 0:
        detail = stderr.strip() or "arecord failed"
        if "Device or resource busy" in detail:
            raise RuntimeError(
                "microphone is busy. Stop ./scripts/run_pi.sh (Ctrl+C) before this exclusive ALSA test"
            )
        raise RuntimeError(detail)


def main() -> int:
    print("ZeeAIBotWebCam echo / speaker-leakage validation")
    print("This does NOT enable AEC automatically.")
    print("This test needs exclusive access to the ALSA microphone and speaker.")
    print("Keep the robot still and keep the room quiet.")
    print("Do not speak during the two recordings.\n")

    if app_is_running():
        print("STOP REQUIRED: ZeeAIBotWebCam is currently running on port 8000.")
        print("The main app owns the ReSpeaker capture device, so arecord cannot open it.")
        print("In the terminal running ./scripts/run_pi.sh, press Ctrl+C once.")
        print("Then run this command again:")
        print("  python scripts/validate_echo_path.py")
        print("After the test, restart the app with:")
        print("  ./scripts/run_pi.sh")
        return 2

    print("Main app is stopped: exclusive audio devices should now be available.")

    with tempfile.TemporaryDirectory(prefix="zee_echo_") as directory:
        quiet_path = os.path.join(directory, "quiet.wav")
        speaker_path = os.path.join(directory, "speaker.wav")

        try:
            input("\nStep 1: make the room quiet and press Enter...")
            print(f"Recording {DURATION}s microphone baseline...")
            record(quiet_path, with_speaker=False)

            input("Step 2: keep silent; the robot speaker will play a test tone. Press Enter...")
            print(f"Recording {DURATION}s while speaker plays 700 Hz tone...")
            record(speaker_path, with_speaker=True)
        except RuntimeError as exc:
            print(f"\nFAIL: {exc}")
            return 1

        quiet_db = rms_dbfs(quiet_path)
        speaker_db = rms_dbfs(speaker_path)
        leakage_db = speaker_db - quiet_db

    print("\n--- ECHO / LEAKAGE RESULT ---")
    print(f"quiet_microphone_level_dbfs={quiet_db:.1f}")
    print(f"speaker_on_microphone_level_dbfs={speaker_db:.1f}")
    print(f"speaker_leakage_increase_db={leakage_db:.1f}")

    if leakage_db < 6.0:
        print("PASS: speaker leakage into the microphone is relatively low in this setup.")
        print(
            "AEC is still not proven; leave echo_reference_validated=false until a real "
            "reference path is implemented and tested."
        )
    elif leakage_db < 15.0:
        print("CHECK: moderate speaker leakage is reaching the microphone.")
        print("Improve physical separation/orientation before relying on full-duplex speech.")
    else:
        print("CHECK: strong speaker leakage is reaching the microphone.")
        print("Move the speaker farther from the ReSpeaker and point it away from the microphone array.")

    print("\nSafety/config note: this test does not modify config.pi.yaml and does not enable chassis motion.")
    print("Restart the main application with: ./scripts/run_pi.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
