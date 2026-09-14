#!/usr/bin/env python3
"""Report ALSA capture/playback devices and current conference audio settings."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.pi.yaml"


def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return f"Command not found: {cmd[0]}"
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or f"(no output, exit={result.returncode})"


def main() -> None:
    print("ALSA audio device report")
    print("========================")

    if CONFIG.exists():
        data = yaml.safe_load(CONFIG.read_text()) or {}
        conference = data.get("conference", {})
        print("\nConfigured devices")
        print("------------------")
        print(f"input : {conference.get('audio_input_device')}")
        print(f"output: {conference.get('audio_output_device')}")
    else:
        print(f"\nConfig not found: {CONFIG}")

    for title, cmd in [
        ("Capture devices (arecord -l)", ["arecord", "-l"]),
        ("Playback devices (aplay -l)", ["aplay", "-l"]),
        ("Named capture PCMs (arecord -L)", ["arecord", "-L"]),
        ("Named playback PCMs (aplay -L)", ["aplay", "-L"]),
    ]:
        print(f"\n{title}\n{'-' * len(title)}")
        print(run(cmd))


if __name__ == "__main__":
    main()
