#!/usr/bin/env python3
"""Measure residual speaker-to-microphone coupling on the Raspberry Pi.

This is a diagnostic, not an AEC implementation or validation certificate.
It plays a low-level deterministic tone through the configured conference
speaker while recording the configured conference microphone, then estimates
how strongly that tone is present in the captured signal.

Privacy: captured PCM is stored only in a temporary directory and deleted by
default. The saved report contains scalar measurements only.

Run with the main conferencing application stopped so the ALSA devices are not
already owned by another process.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Sequence

from robotic_classroom.core.config import load_settings

ROOT = Path(__file__).resolve().parents[1]


def finite_positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def dbfs_from_rms(rms: float) -> float:
    if rms <= 0:
        return -120.0
    return 20.0 * math.log10(rms / 32768.0)


def rms(samples: Sequence[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(float(v) * float(v) for v in samples) / len(samples))


def tone_projection(samples: Sequence[int], sample_rate: int, frequency: float) -> float:
    """Return peak-equivalent amplitude at one tone frequency.

    Uses orthogonal sine/cosine projection. This is intentionally simple and
    deterministic so it works without numpy/scipy on the Pi.
    """
    if not samples:
        return 0.0
    omega = 2.0 * math.pi * frequency / float(sample_rate)
    sin_sum = 0.0
    cos_sum = 0.0
    for index, sample in enumerate(samples):
        angle = omega * index
        sin_sum += float(sample) * math.sin(angle)
        cos_sum += float(sample) * math.cos(angle)
    return (2.0 / len(samples)) * math.hypot(sin_sum, cos_sum)


def make_tone(sample_rate: int, duration: float, frequency: float, level_dbfs: float) -> bytes:
    peak = 32767.0 * (10.0 ** (level_dbfs / 20.0))
    count = int(round(sample_rate * duration))
    values = array.array(
        "h",
        (
            int(round(peak * math.sin(2.0 * math.pi * frequency * n / sample_rate)))
            for n in range(count)
        ),
    )
    if os.sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def read_s16le(path: Path) -> array.array:
    values = array.array("h")
    values.frombytes(path.read_bytes())
    if os.sys.byteorder != "little":
        values.byteswap()
    return values


def command_exists(name: str) -> bool:
    return subprocess.run(
        ["sh", "-c", f"command -v {name} >/dev/null 2>&1"],
        check=False,
    ).returncode == 0


def run_capture(
    *,
    input_device: str,
    output_device: str,
    sample_rate: int,
    channels: int,
    settle_seconds: float,
    baseline_seconds: float,
    tone_seconds: float,
    tone_bytes: bytes,
    capture_path: Path,
) -> None:
    total_seconds = settle_seconds + baseline_seconds + tone_seconds + 0.5
    capture_cmd = [
        "arecord",
        "-N",
        "-q",
        "-D",
        input_device,
        "-f",
        "S16_LE",
        "-c",
        str(channels),
        "-r",
        str(sample_rate),
        "-t",
        "raw",
        "-d",
        str(max(1, math.ceil(total_seconds))),
        str(capture_path),
    ]
    playback_cmd = [
        "aplay",
        "-q",
        "-D",
        output_device,
        "-f",
        "S16_LE",
        "-c",
        str(channels),
        "-r",
        str(sample_rate),
        "-t",
        "raw",
    ]

    capture = subprocess.Popen(
        capture_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=False,
    )
    try:
        time.sleep(settle_seconds + baseline_seconds)
        playback = subprocess.run(
            playback_cmd,
            input=tone_bytes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if playback.returncode != 0:
            message = playback.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"speaker playback failed: {message or playback.returncode}")
        try:
            _, stderr = capture.communicate(timeout=max(3.0, tone_seconds + 2.0))
        except subprocess.TimeoutExpired:
            capture.terminate()
            _, stderr = capture.communicate(timeout=2.0)
            raise RuntimeError("microphone capture timed out")
        if capture.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"microphone capture failed: {message or capture.returncode}")
    finally:
        if capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.wait(timeout=2.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.pi.yaml"))
    parser.add_argument("--frequency", type=finite_positive, default=700.0)
    parser.add_argument("--level-dbfs", type=float, default=-30.0)
    parser.add_argument("--baseline-seconds", type=finite_positive, default=2.0)
    parser.add_argument("--tone-seconds", type=finite_positive, default=3.0)
    parser.add_argument("--settle-seconds", type=finite_positive, default=0.5)
    parser.add_argument("--keep-capture", action="store_true")
    args = parser.parse_args()

    if not -50.0 <= args.level_dbfs <= -18.0:
        parser.error("--level-dbfs must be between -50 and -18 dBFS")
    if not 100.0 <= args.frequency <= 4000.0:
        parser.error("--frequency must be between 100 and 4000 Hz")

    if not command_exists("arecord") or not command_exists("aplay"):
        print("ERROR: arecord/aplay are required.")
        return 2

    settings = load_settings(args.config)
    conf = settings.conference
    if not conf.audio_input_validated or not conf.audio_output_validated:
        print("ERROR: configured conference input/output devices are not validated.")
        return 2

    sample_rate = conf.remote_audio_sample_rate
    channels = conf.remote_audio_channels
    if channels != 1:
        print("ERROR: diagnostic currently requires mono conference audio.")
        return 2

    report_dir = ROOT / "logs" / "aec-diagnostic"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / time.strftime("%Y%m%d-%H%M%S-report.json")

    with tempfile.TemporaryDirectory(prefix="zee-aec-") as temp_name:
        temp_dir = Path(temp_name)
        capture_path = temp_dir / "capture.raw"
        tone_bytes = make_tone(
            sample_rate,
            args.tone_seconds,
            args.frequency,
            args.level_dbfs,
        )

        print("AEC residual diagnostic")
        print("=======================")
        print("Keep the room quiet and the conference application STOPPED.")
        print(f"Input : {conf.audio_input_device}")
        print(f"Output: {conf.audio_output_device}")
        print(
            f"Playing {args.frequency:.0f} Hz at {args.level_dbfs:.0f} dBFS "
            f"for {args.tone_seconds:.1f}s."
        )
        print("Captured audio is deleted unless --keep-capture is supplied.")

        try:
            run_capture(
                input_device=conf.audio_input_device,
                output_device=conf.audio_output_device,
                sample_rate=sample_rate,
                channels=channels,
                settle_seconds=args.settle_seconds,
                baseline_seconds=args.baseline_seconds,
                tone_seconds=args.tone_seconds,
                tone_bytes=tone_bytes,
                capture_path=capture_path,
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            print("If the device is busy, stop the HTTPS conference app and disconnect browsers.")
            return 2

        samples = read_s16le(capture_path)
        settle_count = int(sample_rate * args.settle_seconds)
        baseline_count = int(sample_rate * args.baseline_seconds)
        tone_count = int(sample_rate * args.tone_seconds)

        baseline_start = min(settle_count, len(samples))
        baseline_end = min(baseline_start + baseline_count, len(samples))
        tone_start = baseline_end
        tone_end = min(tone_start + tone_count, len(samples))
        baseline = samples[baseline_start:baseline_end]
        tone_window = samples[tone_start:tone_end]

        if len(baseline) < sample_rate or len(tone_window) < sample_rate:
            print("ERROR: capture was too short for a reliable measurement.")
            return 2

        baseline_rms = rms(baseline)
        tone_rms = rms(tone_window)
        baseline_projection = tone_projection(baseline, sample_rate, args.frequency)
        tone_projection_value = tone_projection(tone_window, sample_rate, args.frequency)

        projection_delta_db = (
            20.0 * math.log10(max(tone_projection_value, 1e-9) / max(baseline_projection, 1e-9))
        )
        leakage_dbfs = dbfs_from_rms(tone_projection_value / math.sqrt(2.0))

        if leakage_dbfs <= -55.0:
            classification = "low_residual_tone"
        elif leakage_dbfs <= -40.0:
            classification = "moderate_residual_tone"
        else:
            classification = "strong_residual_tone"

        report = {
            "schema_version": 1,
            "input_device": conf.audio_input_device,
            "output_device": conf.audio_output_device,
            "sample_rate": sample_rate,
            "channels": channels,
            "tone_frequency_hz": args.frequency,
            "playback_level_dbfs": args.level_dbfs,
            "baseline_rms_dbfs": dbfs_from_rms(baseline_rms),
            "tone_window_rms_dbfs": dbfs_from_rms(tone_rms),
            "tone_residual_dbfs": leakage_dbfs,
            "tone_above_baseline_db": projection_delta_db,
            "classification": classification,
            "echo_management_mode": conf.echo_management_mode,
            "echo_reference_validated": conf.echo_reference_validated,
            "interpretation": (
                "This measures residual acoustic coupling only. It does not prove an AEC "
                "reference is wired correctly and does not change validation state."
            ),
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

        print()
        print(f"Baseline RMS        : {report['baseline_rms_dbfs']:.1f} dBFS")
        print(f"Tone-window RMS     : {report['tone_window_rms_dbfs']:.1f} dBFS")
        print(f"Residual 700Hz tone : {report['tone_residual_dbfs']:.1f} dBFS")
        print(f"Tone above baseline : {report['tone_above_baseline_db']:.1f} dB")
        print(f"Classification      : {classification}")
        print(f"Report              : {report_path}")
        print()
        print("IMPORTANT: echo_reference_validated remains unchanged.")

        if args.keep_capture:
            kept = report_dir / time.strftime("%Y%m%d-%H%M%S-capture.raw")
            kept.write_bytes(capture_path.read_bytes())
            print(f"Raw capture kept by request: {kept}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
