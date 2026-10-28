#!/usr/bin/env python3
"""Validate the live production AEC reference mirror without changing configuration.

The conference application must already be running. This script polls the local
conference audio-pipeline endpoint and verifies that the room speaker and
XVF3800 reference paths are active, error-free, and advancing together.

This is a software-path validation only. It does not prove acoustic echo
cancellation quality, speech intelligibility, double-talk behavior, or
long-duration USB clock stability, and it never sets echo_reference_validated.
"""

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
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CA = ROOT / ".local-certs/zee-local-ca.crt"
DEFAULT_URL = "https://localhost:8000/api/conference/audio-pipeline"


@dataclass(frozen=True, slots=True)
class Snapshot:
    speaker_running: bool
    speaker_frames: int
    speaker_error: str
    reference_enabled: bool
    reference_running: bool
    reference_frames: int
    reference_error: str
    reference_validated: bool
    echo_management_mode: str

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> Snapshot:
        return cls(
            speaker_running=bool(payload.get("speaker_playback_running", False)),
            speaker_frames=int(payload.get("speaker_frames_written", 0)),
            speaker_error=str(payload.get("speaker_last_error", "") or ""),
            reference_enabled=bool(payload.get("echo_reference_enabled", False)),
            reference_running=bool(payload.get("echo_reference_running", False)),
            reference_frames=int(payload.get("echo_reference_frames_written", 0)),
            reference_error=str(payload.get("echo_reference_last_error", "") or ""),
            reference_validated=bool(payload.get("echo_reference_validated", False)),
            echo_management_mode=str(payload.get("echo_management_mode", "")),
        )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def pipeline_url(value: str) -> str:
    parts = urllib.parse.urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.path != "/api/conference/audio-pipeline" or parts.query or parts.fragment):
        raise argparse.ArgumentTypeError("Use an HTTPS audio-pipeline endpoint without credentials")
    return value


def fetch_snapshot(
    url: str, timeout: float, *, ca: Path = DEFAULT_CA, token: str = "",
) -> Snapshot:
    pipeline_url(url)
    if any(ord(c) < 32 or ord(c) > 126 for c in token):
        raise ValueError("Token must contain printable ASCII only")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(ca))
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context), NoRedirect(),
    )
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("Audio-pipeline response too large")
        payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise RuntimeError(f"Audio-pipeline request failed (HTTP {code})") from None
    except (OSError, ValueError):
        raise RuntimeError("Could not read trusted audio-pipeline JSON response") from None

    if not isinstance(payload, dict):
        raise TypeError("Audio-pipeline response is not a JSON object")
    return Snapshot.from_payload(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", type=pipeline_url, default=DEFAULT_URL)
    parser.add_argument("--ca", type=Path, default=DEFAULT_CA)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    if any(not math.isfinite(value) or value <= 0
           for value in (args.seconds, args.interval, args.timeout)):
        parser.error("--seconds, --interval, and --timeout must be positive")

    token = os.environ.get("CONFERENCE_ACCESS_TOKEN", "")

    print("Production AEC reference mirror monitor")
    print("=======================================")
    print(f"Endpoint : {args.url}")
    print(f"Duration : {args.seconds:.1f}s")
    print("Keep a WebRTC call connected and send browser audio to the Pi.")
    print()

    first: Snapshot | None = None
    latest: Snapshot | None = None
    maximum_difference = 0
    saw_active = False
    samples = 0
    observed_failures: set[str] = set()
    deadline = time.monotonic() + args.seconds

    while time.monotonic() < deadline:
        try:
            current = fetch_snapshot(args.url, args.timeout, ca=args.ca, token=token)
        except (OSError, ValueError, TypeError, RuntimeError):
            print("RESULT: UNAVAILABLE (trusted endpoint or credentials could not be verified)")
            print("Check the CA and CONFERENCE_ACCESS_TOKEN environment variable locally.")
            return 2
        samples += 1
        if current.speaker_error:
            observed_failures.add("speaker reported an error during sampling")
        if current.reference_error:
            observed_failures.add("reference reported an error during sampling")
        if not current.reference_enabled:
            observed_failures.add("echo reference mirroring was disabled during sampling")
        if latest is not None and (
            current.speaker_frames < latest.speaker_frames
            or current.reference_frames < latest.reference_frames
        ):
            observed_failures.add("audio frame counter reset during sampling")
        latest = current
        if first is None:
            first = current

        difference = abs(current.speaker_frames - current.reference_frames)
        maximum_difference = max(maximum_difference, difference)
        active = current.speaker_running and current.reference_running
        saw_active = saw_active or active

        print(
            f"speaker={current.speaker_frames:6d} "
            f"reference={current.reference_frames:6d} "
            f"diff={difference:3d} "
            f"speaker_run={str(current.speaker_running).lower():5s} "
            f"ref_run={str(current.reference_running).lower():5s}"
        )
        time.sleep(min(args.interval, max(0.0, deadline - time.monotonic())))

    assert first is not None and latest is not None

    speaker_delta = latest.speaker_frames - first.speaker_frames
    reference_delta = latest.reference_frames - first.reference_frames

    failures = sorted(observed_failures)
    warnings: list[str] = []

    if not latest.reference_enabled:
        failures.append("echo reference mirroring is disabled")
    if not saw_active:
        failures.append("speaker and reference were never simultaneously running")
    if speaker_delta <= 0:
        failures.append("speaker frame counter did not advance")
    if reference_delta <= 0:
        failures.append("reference frame counter did not advance")
    if speaker_delta != reference_delta:
        failures.append(
            f"frame deltas diverged: speaker +{speaker_delta}, reference +{reference_delta}"
        )
    if maximum_difference != 0:
        warnings.append(f"maximum absolute counter difference was {maximum_difference} frame(s)")

    if latest.echo_management_mode != "monitor":
        warnings.append(
            f"echo_management_mode is {latest.echo_management_mode!r}; monitor was expected"
        )
    if latest.reference_validated:
        warnings.append("echo_reference_validated is already true")

    print()
    print("Summary")
    print("-------")
    print(f"Samples                       : {samples}")
    print(f"Speaker frames advanced       : +{speaker_delta}")
    print(f"Reference frames advanced     : +{reference_delta}")
    print(f"Maximum counter difference    : {maximum_difference}")

    if warnings:
        print("Warnings:")
        for item in warnings:
            print(f"  - {item}")

    if failures:
        print("RESULT: FAIL")
        for item in failures:
            print(f"  - {item}")
        print("Configuration was not changed.")
        return 1

    print("RESULT: PASS")
    print("The production WebRTC speaker/reference software path stayed synchronized.")
    print("Configuration was not changed; echo_reference_validated was not modified.")
    print("A real speech, echo-listening, double-talk, and longer-duration test is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
