#!/usr/bin/env python3
"""Compare XVF3800 residual echo with and without a mirrored USB AEC reference.

This diagnostic keeps the normal conference configuration unchanged. It runs
two short measurements with the conference application stopped:

1. Current path: test tone -> configured robot speaker only.
2. Mirror path: the same test tone -> configured robot speaker AND, at nearly
   the same time, left channel of the XVF3800 USB playback input.

The XVF3800 documentation states that the far-end AEC reference is taken from
left channel 0 of its USB/I2S input. Right-channel input is ignored for the AEC
reference. The mirror path therefore sends tone on XVF left and silence on XVF
right.

The result is a diagnostic comparison only. It does not set
echo_reference_validated and does not modify config.pi.yaml.

Privacy: capture files live in a temporary directory and are deleted
automatically. Only scalar measurements are saved.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Sequence

from robotic_classroom.core.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_DEVICE = "plughw:CARD=Array,DEV=0"


def finite_positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def dbfs_from_rms(value: float) -> float:
    if value <= 0:
        return -120.0
    return 20.0 * math.log10(value / 32768.0)


def rms(samples: Sequence[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(float(v) * float(v) for v in samples) / len(samples))


def tone_projection(samples: Sequence[int], sample_rate: int, frequency: float) -> float:
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


def make_mono_tone(sample_rate: int, duration: float, frequency: float, level_dbfs: float) -> bytes:
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


def mono_to_reference_stereo(mono_bytes: bytes) -> bytes:
    """Interleave mono samples as XVF left=tone, right=silence."""
    mono = array.array("h")
    mono.frombytes(mono_bytes)
    if os.sys.byteorder != "little":
        mono.byteswap()

    stereo = array.array("h")
    for sample in mono:
        stereo.append(sample)
        stereo.append(0)

    if os.sys.byteorder != "little":
        stereo.byteswap()
    return stereo.tobytes()


def read_s16le(path: Path) -> array.array:
    values = array.array("h")
    values.frombytes(path.read_bytes())
    if os.sys.byteorder != "little":
        values.byteswap()
    return values


def playback_command(device: str, sample_rate: int, channels: int) -> list[str]:
    return [
        "aplay", "-q", "-D", device, "-f", "S16_LE", "-c", str(channels),
        "-r", str(sample_rate), "-t", "raw",
    ]


def run_playback(*, device: str, sample_rate: int, channels: int, payload: bytes,
                 result: dict[str, str], key: str) -> None:
    completed = subprocess.run(
        playback_command(device, sample_rate, channels),
        input=payload,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        result[key] = message or f"aplay exited {completed.returncode}"


def capture_measurement(*, input_device: str, speaker_device: str,
                        reference_device: str | None, sample_rate: int,
                        settle_seconds: float, baseline_seconds: float,
                        tone_seconds: float, mono_tone: bytes,
                        reference_stereo: bytes, capture_path: Path) -> None:
    total_seconds = settle_seconds + baseline_seconds + tone_seconds + 0.75
    capture_cmd = [
        "arecord", "-N", "-q", "-D", input_device, "-f", "S16_LE", "-c", "1",
        "-r", str(sample_rate), "-t", "raw", "-d",
        str(max(1, math.ceil(total_seconds))), str(capture_path),
    ]
    capture = subprocess.Popen(
        capture_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        time.sleep(settle_seconds + baseline_seconds)
        errors: dict[str, str] = {}
        threads = [
            threading.Thread(
                target=run_playback,
                kwargs={
                    "device": speaker_device,
                    "sample_rate": sample_rate,
                    "channels": 1,
                    "payload": mono_tone,
                    "result": errors,
                    "key": "speaker",
                },
                daemon=True,
            )
        ]
        if reference_device is not None:
            threads.append(
                threading.Thread(
                    target=run_playback,
                    kwargs={
                        "device": reference_device,
                        "sample_rate": sample_rate,
                        "channels": 2,
                        "payload": reference_stereo,
                        "result": errors,
                        "key": "reference",
                    },
                    daemon=True,
                )
            )

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=tone_seconds + 3.0)

        if any(thread.is_alive() for thread in threads):
            raise RuntimeError("audio playback did not finish in time")
        if errors:
            details = "; ".join(f"{name}: {message}" for name, message in errors.items())
            raise RuntimeError(details)

        try:
            _, stderr = capture.communicate(timeout=tone_seconds + 3.0)
        except subprocess.TimeoutExpired:
            capture.terminate()
            _, stderr = capture.communicate(timeout=2.0)
            raise RuntimeError("microphone capture timed out")

        if capture.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or f"arecord exited {capture.returncode}")
    finally:
        if capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.wait(timeout=2.0)


def analyse(path: Path, *, sample_rate: int, settle_seconds: float,
            baseline_seconds: float, tone_seconds: float,
            frequency: float) -> dict[str, float]:
    samples = read_s16le(path)
    settle_count = int(sample_rate * settle_seconds)
    baseline_count = int(sample_rate * baseline_seconds)
    tone_count = int(sample_rate * tone_seconds)
    baseline_start = min(settle_count, len(samples))
    baseline_end = min(baseline_start + baseline_count, len(samples))
    tone_start = baseline_end
    tone_end = min(tone_start + tone_count, len(samples))
    baseline = samples[baseline_start:baseline_end]
    tone_window = samples[tone_start:tone_end]
    if len(baseline) < sample_rate or len(tone_window) < sample_rate:
        raise RuntimeError("capture was too short for a reliable measurement")

    baseline_projection = tone_projection(baseline, sample_rate, frequency)
    tone_projection_value = tone_projection(tone_window, sample_rate, frequency)
    return {
        "baseline_rms_dbfs": dbfs_from_rms(rms(baseline)),
        "tone_window_rms_dbfs": dbfs_from_rms(rms(tone_window)),
        "tone_residual_dbfs": dbfs_from_rms(tone_projection_value / math.sqrt(2.0)),
        "tone_above_baseline_db": 20.0 * math.log10(
            max(tone_projection_value, 1e-9) / max(baseline_projection, 1e-9)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.pi.yaml"))
    parser.add_argument("--reference-device", default=DEFAULT_REFERENCE_DEVICE)
    parser.add_argument("--frequency", type=finite_positive, default=700.0)
    parser.add_argument("--level-dbfs", type=float, default=-30.0)
    parser.add_argument("--settle-seconds", type=finite_positive, default=0.5)
    parser.add_argument("--baseline-seconds", type=finite_positive, default=2.0)
    parser.add_argument("--tone-seconds", type=finite_positive, default=3.0)
    args = parser.parse_args()

    if not -50.0 <= args.level_dbfs <= -18.0:
        parser.error("--level-dbfs must be between -50 and -18 dBFS")
    if not 100.0 <= args.frequency <= 4000.0:
        parser.error("--frequency must be between 100 and 4000 Hz")

    settings = load_settings(args.config)
    conf = settings.conference
    if not conf.audio_input_validated or not conf.audio_output_validated:
        print("ERROR: configured input/output devices are not validated.")
        return 2
    if conf.remote_audio_channels != 1:
        print("ERROR: diagnostic expects the current mono conference playback path.")
        return 2

    sample_rate = conf.remote_audio_sample_rate
    mono_tone = make_mono_tone(sample_rate, args.tone_seconds, args.frequency, args.level_dbfs)
    reference_stereo = mono_to_reference_stereo(mono_tone)

    report_dir = ROOT / "logs" / "aec-reference-diagnostic"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    report_path = report_dir / f"{timestamp}-report.json"

    print("XVF3800 mirrored AEC-reference diagnostic")
    print("==========================================")
    print("The conference application MUST be stopped.")
    print("Keep the room quiet and do not speak during either measurement.")
    print(f"Microphone       : {conf.audio_input_device}")
    print(f"Room speaker     : {conf.audio_output_device}")
    print(f"XVF reference USB: {args.reference_device}")
    print(f"Tone             : {args.frequency:.0f} Hz at {args.level_dbfs:.0f} dBFS")
    print()
    print("Phase A: current speaker path, no XVF reference.")

    try:
        with tempfile.TemporaryDirectory(prefix="zee-aec-reference-") as temp_name:
            temp_dir = Path(temp_name)
            current_path = temp_dir / "current.raw"
            mirror_path = temp_dir / "mirror.raw"

            capture_measurement(
                input_device=conf.audio_input_device,
                speaker_device=conf.audio_output_device,
                reference_device=None,
                sample_rate=sample_rate,
                settle_seconds=args.settle_seconds,
                baseline_seconds=args.baseline_seconds,
                tone_seconds=args.tone_seconds,
                mono_tone=mono_tone,
                reference_stereo=reference_stereo,
                capture_path=current_path,
            )
            current = analyse(
                current_path,
                sample_rate=sample_rate,
                settle_seconds=args.settle_seconds,
                baseline_seconds=args.baseline_seconds,
                tone_seconds=args.tone_seconds,
                frequency=args.frequency,
            )

            print(f"  Current residual: {current['tone_residual_dbfs']:.1f} dBFS")
            print()
            print("Phase B: same speaker tone + mirrored XVF left-channel reference.")

            capture_measurement(
                input_device=conf.audio_input_device,
                speaker_device=conf.audio_output_device,
                reference_device=args.reference_device,
                sample_rate=sample_rate,
                settle_seconds=args.settle_seconds,
                baseline_seconds=args.baseline_seconds,
                tone_seconds=args.tone_seconds,
                mono_tone=mono_tone,
                reference_stereo=reference_stereo,
                capture_path=mirror_path,
            )
            mirrored = analyse(
                mirror_path,
                sample_rate=sample_rate,
                settle_seconds=args.settle_seconds,
                baseline_seconds=args.baseline_seconds,
                tone_seconds=args.tone_seconds,
                frequency=args.frequency,
            )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print(
            "Do not change configuration. Confirm the HTTPS conference app is stopped, "
            "then check aplay -l and arecord -l."
        )
        return 2

    improvement_db = current["tone_residual_dbfs"] - mirrored["tone_residual_dbfs"]
    if improvement_db >= 12.0:
        classification = "reference_path_promising"
    elif improvement_db >= 6.0:
        classification = "reference_path_some_reduction"
    elif improvement_db > -3.0:
        classification = "reference_path_no_clear_benefit"
    else:
        classification = "reference_path_worse"

    report = {
        "schema_version": 1,
        "input_device": conf.audio_input_device,
        "speaker_device": conf.audio_output_device,
        "reference_device": args.reference_device,
        "sample_rate": sample_rate,
        "tone_frequency_hz": args.frequency,
        "playback_level_dbfs": args.level_dbfs,
        "current_path": current,
        "mirrored_reference_path": mirrored,
        "residual_improvement_db": improvement_db,
        "classification": classification,
        "echo_management_mode": conf.echo_management_mode,
        "echo_reference_validated": conf.echo_reference_validated,
        "interpretation": (
            "This compares residual tone with and without an XVF USB left-channel "
            "reference mirror. It is not sufficient by itself to validate production "
            "AEC because a separate room-speaker clock/path can introduce delay/drift."
        ),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"  Mirrored residual: {mirrored['tone_residual_dbfs']:.1f} dBFS")
    print()
    print(f"Residual improvement: {improvement_db:+.1f} dB")
    print(f"Classification      : {classification}")
    print(f"Report              : {report_path}")
    print()
    print("IMPORTANT: config.pi.yaml was not changed.")
    print("IMPORTANT: echo_reference_validated remains unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
