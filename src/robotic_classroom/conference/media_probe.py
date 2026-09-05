from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MediaDeviceProbe:
    capture_devices: tuple[str, ...]
    playback_devices: tuple[str, ...]
    available: bool
    message: str


def _run(command: list[str]) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return tuple(lines)


def probe_alsa_devices() -> MediaDeviceProbe:
    capture = _run(["arecord", "-l"])
    playback = _run(["aplay", "-l"])
    available = bool(capture or playback)
    message = "ALSA devices detected" if available else "No ALSA device listing available"
    return MediaDeviceProbe(
        capture_devices=capture,
        playback_devices=playback,
        available=available,
        message=message,
    )
