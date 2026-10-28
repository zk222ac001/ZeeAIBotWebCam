#!/usr/bin/env python3
"""Read-only deployment preflight: configuration, dependencies and trusted TLS.

Run with the intended service environment. Never imports hardware drivers,
resets a stop, captures media, starts a service or sets acceptance flags.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import ssl
import stat
import subprocess
from pathlib import Path

from robotic_classroom.core.config import Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]


def configuration_issues(cfg: Settings, production: bool) -> list[str]:
    issues = []
    if cfg.hardware.mode != "real" or cfg.camera.mode != "imx500" or cfg.audio.mode != "xvf3800_usb":
        issues.append("Deployment requires real hardware, IMX500 camera and XVF3800 audio")
    if not cfg.conference.enabled or cfg.conference.mode != "aiortc":
        issues.append("Real WebRTC conferencing must be enabled")
    if not cfg.camera.enabled or not cfg.audio.enabled:
        issues.append("Camera and audio services must be enabled")
    if not cfg.conference.auth_required or not cfg.control_access.auth_required:
        issues.append("Both access authentication gates must be enabled")
    if not cfg.conference.access_token or not cfg.control_access.access_token:
        issues.append("Separate conference and control credentials must be configured")
    elif cfg.conference.access_token == cfg.control_access.access_token:
        issues.append("Conference and control credentials must differ")
    if cfg.privacy.recording_enabled or cfg.privacy.face_recognition_enabled:
        issues.append("Recording and face recognition must be disabled for this release")
    if not cfg.safety.require_control_lease:
        issues.append("Control leases must remain required")
    if cfg.autonomy.mode != "plan_only" or cfg.autonomy.forward_enabled or cfg.autonomy.search_enabled:
        issues.append("This release requires plan-only chassis autonomy with forward/search disabled")
    if production:
        if cfg.application.environment != "production":
            issues.append("Production environment promotion is pending")
        if not cfg.conference.echo_reference_enabled or not cfg.conference.echo_reference_validated:
            issues.append("Observed acoustic echo/double-talk acceptance is pending")
        if not cfg.autonomy.pilot_validated:
            issues.append("Observed supervised classroom pilot acceptance is pending")
    return issues


def dependency_issues(cfg: Settings) -> list[str]:
    issues = []
    for module in ("aiortc", "av", "picamera2", "serial", "usb"):
        if importlib.util.find_spec(module) is None:
            issues.append(f"Required runtime module unavailable: {module}")
    for executable in ("openssl", "arecord", "aplay"):
        if shutil.which(executable) is None:
            issues.append(f"Required system utility unavailable: {executable}")
    if not cfg.camera.model_path.is_file():
        issues.append("Configured IMX500 model file is unavailable")
    if not (cfg.hardware.vendor_path / "HiwonderSDK/ros_robot_controller_sdk.py").is_file():
        issues.append("Configured TurboPi controller SDK is unavailable")
    return issues


def vendor_issues(cfg: Settings, manifest_path: Path) -> list[str]:
    if not manifest_path.exists():
        return []
    vendor = json.loads(manifest_path.read_text()).get("external_vendor", {})
    if not vendor.get("recorded"):
        return ["Release has no target SDK fingerprint; validate and rebuild for the Pi"]
    for name, digest in vendor.get("driver_sha256", {}).items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            return ["Release SDK fingerprint path is invalid"]
        target = cfg.hardware.vendor_path / path
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            return ["Device SDK drivers do not match the release fingerprint"]
    return []


def tls_issues(ca: Path, cert: Path, key: Path) -> list[str]:
    try:
        if stat.S_IMODE(key.stat().st_mode) & 0o077:
            return ["TLS private key must not be group/world accessible"]
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(ca))
        context.load_cert_chain(certfile=str(cert), keyfile=str(key))
        result = subprocess.run(
            ["openssl", "verify", "-CAfile", str(ca), "-verify_hostname", "localhost", str(cert)],
            check=False, capture_output=True, timeout=5,
        )
        if result.returncode:
            return ["TLS certificate trust, validity or localhost identity check failed"]
    except (OSError, ValueError, subprocess.SubprocessError):
        return ["TLS CA, certificate and matching private key could not be verified"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.pi.yaml")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--ca", type=Path, default=ROOT / ".local-certs/zee-local-ca.crt")
    parser.add_argument("--cert", type=Path, default=ROOT / ".local-certs/zee-server.crt")
    parser.add_argument("--key", type=Path, default=ROOT / ".local-certs/zee-server.key")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg = load_settings(args.config)
        issues = configuration_issues(cfg, args.production) + dependency_issues(cfg)
        issues += tls_issues(args.ca, args.cert, args.key)
        issues += vendor_issues(cfg, ROOT / "release-manifest.json")
    except (OSError, ValueError):
        issues = ["Deployment configuration could not be validated; review it locally"]
    report = {"preflight_passed": not issues, "production_check": args.production,
              "issues": issues, "physical_acceptance_proven": False}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("PASS: deployment preflight" if not issues else "BLOCKED: deployment preflight")
        for issue in issues:
            print(f"  - {issue}")
        print("This check does not establish physical acceptance or runtime readiness.")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
