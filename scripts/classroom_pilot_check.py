#!/usr/bin/env python3
"""Observe a supervised classroom pilot using HTTPS status GET requests only.

No hardware imports, control requests, audio/video capture, or configuration writes.
A telemetry report is not physical safety, AEC, media-quality, or identity validation.
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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS = {
    "safety": "/api/safety",
    "conference": "/api/conference/status",
    "camera": "/api/camera/status",
    "audio": "/api/audio/status",
    "speaker": "/api/active-speaker/status",
    "tracking": "/api/tracking/status",
    "pan_tilt": "/api/pan-tilt/plan",
}
# Only these scalar fields are retained. Never retain response messages, tokens,
# session IDs, SDP, person IDs, images, or audio.
FIELDS = {
    "safety": {
        "state": "state", "motion_enabled": "motion_enabled",
        "motion_active": "motion_active", "watchdog_running": "watchdog_running",
    },
    "conference": {
        "running": "running", "active_sessions": "active_sessions",
        "auth_required": "auth_required", "publish_video": "publish_video",
        "publish_audio": "publish_audio", "remote_audio_playback": "remote_audio_playback",
    },
    "camera": {
        "connected": "connected", "running": "running", "sequence": "sequence",
        "people_count": "people_count",
    },
    "audio": {
        "connected": "connected", "running": "running", "sequence": "sequence",
        "speech_state": "speech_state", "speech_active": "speech_active",
        "doa_degrees_raw": "doa_degrees_raw", "doa_degrees": "doa_degrees",
    },
    "speaker": {
        "state": "state", "sequence": "sequence", "confidence": "confidence",
        "candidate_index": "candidate_index", "center_x": "center.x",
        "camera_angle_degrees": "camera_angle_degrees",
        "doa_degrees": "doa_degrees", "angular_error_degrees": "angular_error_degrees",
    },
    "tracking": {
        "state": "state", "sequence": "sequence", "in_dead_zone": "in_dead_zone",
        "error_x": "error.x", "error_y": "error.y",
    },
    "pan_tilt": {
        "state": "state", "sequence": "sequence", "mode": "mode",
        "executed": "execution.executed", "pan": "pan.planned_pulse",
        "pan_min": "pan.minimum", "pan_max": "pan.maximum",
        "tilt": "tilt.planned_pulse", "tilt_min": "tilt.minimum", "tilt_max": "tilt.maximum",
    },
}
STATES = {
    "idle", "emergency_stop", "fault", "shutdown", "tracking", "searching", "lost",
    "disabled", "centered", "holding", "execute", "plan_only", "speaking", "silent",
    "hangover", "unavailable", "waiting_for_speech", "calibration_required",
    "no_visible_candidate", "ambiguous", "speaker_selected",
}
PHASES = (
    ("speaker_switch", "Two visible people: speak one at a time, alternating every 5 seconds."),
    ("slow_tracking", "One visible speaker: move slowly left, center, right within camera view."),
    ("remote_only", "Local people stay quiet; remote participant speaks. Listen for returning echo."),
    ("overlap", "Briefly overlap local and remote speech; stop if feedback becomes loud."),
    ("reconnect", "Disconnect once, wait a few seconds, reconnect, then finish the conversation."),
)
MANUAL_CHECKS = (
    "Moving video remained usable in Chrome (not just a connected status).",
    "Robot microphone was heard clearly in Chrome.",
    "Remote microphone was heard clearly through the robot speaker.",
    "Camera framed the actual speaker during alternation, not just a changing ID.",
    "No strong returning echo or loud feedback during remote speech or overlap.",
    "Camera followed smoothly without grinding, oscillation, or cable strain.",
    "Reconnection restored moving video and both audio directions without an app restart.",
    "Chassis physically remained stationary throughout the pilot.",
)


def number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def extract(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def project(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, path in FIELDS[name].items():
        value = extract(payload, path)
        if type(value) is bool or number(value) or value is None:
            result[key] = value
        elif isinstance(value, str) and value in STATES:
            result[key] = value
        else:
            result[key] = None
    if name == "conference":
        sessions = payload.get("sessions")
        result["connected_sessions"] = (
            sum(isinstance(s, dict) and s.get("connection_state") == "connected" for s in sessions)
            if isinstance(sessions, list) else None
        )
    if name == "pan_tilt":
        error = extract(payload, "execution.last_error")
        result["execution_error"] = bool(error) if isinstance(error, str) else None
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not redirect bearer credentials or any status request elsewhere.
        return None


class StatusClient:
    def __init__(self, base_url: str, ca: Path, token: str = "", timeout: float = 2.0):
        parts = urllib.parse.urlsplit(base_url)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            raise ValueError("Use an HTTPS origin only, such as https://localhost:8000")
        if any(ord(c) < 32 or ord(c) > 126 for c in token):
            raise ValueError("Token must contain printable ASCII only")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        # PROTOCOL_TLS_CLIENT verifies the trust chain and hostname. No -k mode.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(ca))
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context), NoRedirect(),
        )

    def get(self, name: str) -> dict[str, Any]:
        path = ENDPOINTS[name]  # Fixed allowlist; no arbitrary or control paths.
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.base_url + path, headers=headers, method="GET")
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("Response too large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return project(name, data)


def read_sample(client: StatusClient) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name in ENDPOINTS:
        try:
            values[name] = client.get(name)
        except urllib.error.HTTPError as exc:
            errors[name] = f"HTTP {exc.code}"
            exc.close()
        except urllib.error.URLError as exc:
            errors[name] = (
                "TLS certificate validation failed" if isinstance(exc.reason, ssl.SSLError)
                else "Connection failed or timed out"
            )
        except (OSError, ValueError):
            errors[name] = "Connection or JSON response error"
        # On uncertain or active chassis state, stop sampling promptly. This
        # does not send STOP. A person must use the existing stop control.
        if name == "safety" and values.get("safety", {}).get("motion_active") is not False:
            break
    return values, errors


def assess(values: dict[str, Any], errors: dict[str, str], phase: str) -> list[str]:
    flags = [f"{name}:read_failed" for name in errors]
    safety = values.get("safety", {})
    if safety.get("motion_active") is True:
        flags.append("safety:motion_active")
    elif safety.get("motion_active") is not False:
        flags.append("safety:motion_state_unknown")
    if safety.get("watchdog_running") is not True:
        flags.append("safety:watchdog_not_confirmed")
    if safety.get("state") not in {"idle", "emergency_stop"}:
        flags.append("safety:unexpected_state")
    for name in ("camera", "audio"):
        item = values.get(name, {})
        if item.get("connected") is not True or item.get("running") is not True:
            flags.append(f"{name}:not_ready")
    conference = values.get("conference", {})
    if conference.get("running") is not True:
        flags.append("conference:not_running")
    count = conference.get("connected_sessions")
    if not number(count):
        flags.append("conference:session_state_unknown")
    elif count < 1 and phase != "reconnect":
        flags.append("conference:no_connected_session")
    # These are review observations, NOT automatic proof of a hardware fault.
    pan_tilt = values.get("pan_tilt", {})
    if pan_tilt.get("executed") is not True or pan_tilt.get("execution_error") is not False:
        flags.append("pan_tilt:execution_not_confirmed")
    for axis in ("pan", "tilt"):
        pulse, low, high = (pan_tilt.get(axis), pan_tilt.get(f"{axis}_min"),
                            pan_tilt.get(f"{axis}_max"))
        if not all(number(v) for v in (pulse, low, high)) or low >= high:
            flags.append(f"{axis}:range_unavailable")
        elif not low <= pulse <= high:
            flags.append(f"{axis}:outside_configured_range")
        elif pulse in (low, high):
            flags.append(f"{axis}:at_configured_limit")
    speaker = values.get("speaker", {})
    if speaker.get("state") in {"ambiguous", "no_visible_candidate", "calibration_required"}:
        flags.append(f"speaker:{speaker['state']}")
    if phase == "remote_only" and speaker.get("state") == "speaker_selected":
        flags.append("speaker:selected_during_remote_only_REVIEW")
    return flags


class SequenceWatch:
    def __init__(self):
        self.seen: dict[str, tuple[int | float, float]] = {}

    def check(self, values: dict[str, Any], now: float, timeout: float) -> list[str]:
        flags = []
        for name in ("camera", "audio", "speaker", "tracking", "pan_tilt"):
            sequence = values.get(name, {}).get("sequence")
            if not number(sequence):
                flags.append(f"{name}:sequence_unavailable")
                continue
            previous = self.seen.get(name)
            if previous is None or sequence != previous[0]:
                self.seen[name] = (sequence, now)
                if previous is not None and sequence < previous[0]:
                    flags.append(f"{name}:sequence_reset")
            elif now - previous[1] >= timeout:
                flags.append(f"{name}:sequence_not_advancing")
        return flags


def phase_at(elapsed: float, duration: float) -> tuple[str, str]:
    return PHASES[min(len(PHASES) - 1, int(max(0.0, elapsed) / duration * len(PHASES)))]


def make_report(records: list[dict[str, Any]], requested: float, elapsed: float,
                reason: str, interval: float) -> dict[str, Any]:
    counts = Counter(flag for record in records for flag in record["flags"])
    totals = Counter(record["phase"] for record in records)
    gaps = [b["elapsed_s"] - a["elapsed_s"] for a, b in zip(records, records[1:])]
    return {
        "schema_version": 1,
        "result": "INCOMPLETE" if reason != "duration_complete" or not records else (
            "REVIEW" if counts else "NO_TELEMETRY_ALERTS"
        ),
        "stop_reason": reason, "requested_seconds": requested,
        "elapsed_seconds": round(elapsed, 3), "poll_interval_seconds": interval,
        "sample_count": len(records), "samples_by_phase": dict(totals),
        "observed_flag_sample_counts": dict(sorted(counts.items())),
        "max_sample_gap_seconds": round(max(gaps, default=0), 3),
        "max_sample_span_seconds": max((r["span_s"] for r in records), default=0),
        "manual_checks": {item: "NOT_TESTED" for item in MANUAL_CHECKS},
        "limits": [
            "No automatic overall PASS. Human observation is required for every manual check.",
            "Sequential sampled GETs are not atomic, continuous, or hardware feedback.",
            "A connected session is not proof of audible sound, moving video, or low latency.",
            "Executed servo commands and pulse limits are not measured mechanical positions.",
            "Sequence advancement is metadata freshness, not proof of advancing video frames.",
            "Remote-only selection is a review hint, not proof of acoustic echo.",
            "This helper cannot stop motors; stopping the helper does not stop the robot.",
            "No claim of authentication, echo cancellation, motion safety, or autonomy validation.",
        ],
    }


def write_reports(folder: Path, report: dict[str, Any]) -> None:
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Supervised classroom pilot", "", f"**Result: {report['result']}**",
             f"Stop reason: `{report['stop_reason']}`", "",
             f"Duration: {report['elapsed_seconds']} / {report['requested_seconds']} seconds.",
             f"Samples: {report['sample_count']}. Maximum gap: "
             f"{report['max_sample_gap_seconds']} seconds.", "",
             "## Review observations", "",
             "Counts below are samples with an observation, not distinct incidents.", ""]
    flags = report["observed_flag_sample_counts"]
    lines.extend(f"- `{flag}`: {count}" for flag, count in flags.items())
    if not flags:
        lines.append("No automatic telemetry alerts in the collected samples.")
    lines.extend(["", "## Human checks - NOT TESTED by this program", "",
                  "Mark each PASS, FAIL, or NOT TESTED after observing the actual pilot.", ""])
    lines.extend(f"- [ ] {item}" for item in MANUAL_CHECKS)
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {item}" for item in report["limits"])
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def finite_positive(text: str) -> float:
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("Must be a finite positive number")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=finite_positive, default=600.0)
    parser.add_argument("--interval", type=finite_positive, default=2.0)
    parser.add_argument("--base-url", default="https://localhost:8000")
    parser.add_argument("--ca", type=Path, default=ROOT / ".local-certs/zee-local-ca.crt")
    parser.add_argument("--token-env", default="ZEE_CONFERENCE_TOKEN")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "logs/classroom-pilot")
    args = parser.parse_args(argv)
    if args.duration > 3600 or not 0.5 <= args.interval <= 30:
        parser.error("Duration must be <=3600 seconds and interval must be 0.5..30 seconds")
    try:
        client = StatusClient(args.base_url, args.ca, os.environ.get(args.token_env, ""))
    except (OSError, ValueError):
        print("SETUP ERROR: check the HTTPS origin, CA file, and token environment variable.")
        print("Use your existing .local-certs/zee-local-ca.crt; do not disable TLS verification.")
        return 2
    folder = args.output_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    try:
        folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    except OSError:
        print("SETUP ERROR: cannot create the output directory.")
        return 2
    print("Read-only classroom pilot. Keep the existing HTTPS app and ONE conference open.")
    print("Keep chassis stationary. No control requests or recordings of audio/video are made.")
    print("This monitor DOES NOT stop the robot. Use the existing STOP control if needed.")
    print(f"Report directory: {folder}")
    print("A short --duration run is only a smoke test, not a completed classroom pilot.")
    records: list[dict[str, Any]] = []
    watch = SequenceWatch()
    started = time.monotonic()
    reason = "duration_complete"
    last_phase = ""
    try:
        with (folder / "telemetry.jsonl").open("x", encoding="utf-8") as stream:
            while time.monotonic() - started < args.duration:
                sample_start = time.monotonic()
                phase, instruction = phase_at(sample_start - started, args.duration)
                if phase != last_phase:
                    print(f"\nPHASE {phase}: {instruction}", flush=True)
                    last_phase = phase
                values, errors = read_sample(client)
                sampled = time.monotonic()
                flags = assess(values, errors, phase)
                if sampled - sample_start > max(5.0, args.interval * 2.5):
                    flags.append("monitor:slow_sample")
                flags.extend(watch.check(values, sampled, max(5.0, args.interval * 2.5)))
                record = {
                    "elapsed_s": round(sample_start - started, 3), "phase": phase,
                    "span_s": round(sampled - sample_start, 3),
                    "values": values, "errors": errors, "flags": flags,
                }
                records.append(record)
                stream.write(json.dumps(record, allow_nan=False) + "\n")
                stream.flush()
                print(
                    f"{record['elapsed_s']:6.1f}s people={values.get('camera', {}).get('people_count')} "
                    f"speech={values.get('audio', {}).get('speech_state')} "
                    f"speaker={values.get('speaker', {}).get('state')} "
                    f"pan={values.get('pan_tilt', {}).get('pan')} "
                    f"tilt={values.get('pan_tilt', {}).get('tilt')} "
                    f"connected={values.get('conference', {}).get('connected_sessions')} "
                    f"review_flags={len(flags)}", flush=True,
                )
                if errors:
                    print("Read errors: " + json.dumps(errors), flush=True)
                if values.get("safety", {}).get("motion_active") is not False:
                    reason = "motion_active_or_unknown"
                    print("STOP THE PILOT: chassis state active/unknown. Use robot STOP as needed.")
                    break
                if sampled - started >= args.duration:
                    break
                time.sleep(min(max(0.0, args.interval - (sampled - sample_start)),
                               args.duration - (sampled - started)))
    except KeyboardInterrupt:
        reason = "interrupted"
    except OSError:
        reason = "local_io_error"
    elapsed = time.monotonic() - started
    report = make_report(records, args.duration, elapsed, reason, args.interval)
    try:
        write_reports(folder, report)
    except OSError:
        print("REPORT ERROR: could not write the summary; inspect available telemetry.jsonl.")
        return 2
    print(f"\n{report['result']}: {folder / 'report.md'}")
    print("Physical audio, video, framing, echo and stop behavior still require human checks.")
    return 0 if report["result"] == "NO_TELEMETRY_ALERTS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
