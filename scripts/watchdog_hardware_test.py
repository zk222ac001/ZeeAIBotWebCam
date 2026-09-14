#!/usr/bin/env python3
"""Guarded real-hardware validation of the chassis heartbeat watchdog.

This script temporarily enables chassis motion in memory only. It does NOT modify
config.pi.yaml. It requires all four wheels to be lifted clear of the surface.

Test sequence:
1. Start the real TurboPi hardware adapter.
2. Start the independent safety watchdog.
3. Acquire a control lease and send one heartbeat.
4. Command forward motion at full normalized input (adapter caps motor duty at 30).
5. Intentionally stop sending heartbeats.
6. Verify the watchdog marks motion inactive after the configured timeout.
7. Always send repeated stop commands and close hardware on exit.
"""
from __future__ import annotations

import argparse
import time

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.core.config import load_settings
from robotic_classroom.hardware.factory import create_hardware_service
from robotic_classroom.safety.supervisor import SafetySupervisor


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded TurboPi watchdog hardware test")
    parser.add_argument(
        "--confirm-wheels-lifted",
        action="store_true",
        help="Required acknowledgement that all four wheels are lifted clear of the surface",
    )
    parser.add_argument(
        "--wait-extra",
        type=float,
        default=0.6,
        help="Extra wait after heartbeat timeout in seconds (default: 0.6)",
    )
    args = parser.parse_args()

    if not args.confirm_wheels_lifted:
        raise SystemExit(
            "Motion refused. Lift all four wheels clear of the work surface and re-run "
            "with --confirm-wheels-lifted."
        )
    if not 0.2 <= args.wait_extra <= 2.0:
        raise SystemExit("--wait-extra must be between 0.2 and 2.0 seconds")

    settings = load_settings("config.pi.yaml")
    if settings.hardware.mode != "real":
        raise SystemExit("config.pi.yaml is not using real hardware mode")
    if not settings.hardware.motor_mapping_validated:
        raise SystemExit("Motor mapping is not marked as validated")

    # Temporary test-only override. The configuration file is never changed.
    settings.safety.motion_enabled = True

    hardware = create_hardware_service(settings)
    supervisor: SafetySupervisor | None = None

    print("TurboPi real-hardware watchdog validation")
    print("==========================================")
    print("IMPORTANT: Keep all four wheels lifted for the entire test.")
    print("config.pi.yaml remains unchanged; motion is enabled only in this process.")
    print(f"Heartbeat timeout: {settings.safety.heartbeat_timeout_ms} ms")

    try:
        hardware.start()
        supervisor = SafetySupervisor(settings, hardware)
        supervisor.start_watchdog()

        snapshot = hardware.sensors()
        if snapshot.distance_cm is None:
            raise RuntimeError("Ultrasonic distance is unavailable; refusing forward test")
        print(f"Ultrasonic distance: {snapshot.distance_cm:.1f} cm")
        if snapshot.distance_cm < settings.safety.minimum_obstacle_distance_cm:
            raise RuntimeError(
                "Obstacle is inside the configured safety distance. Move the object away "
                "from the ultrasonic sensor and repeat the test."
            )

        lease = supervisor.leases.acquire("watchdog-hardware-test")
        supervisor.heartbeat()

        command = MotionCommand(forward=1.0)
        decision = supervisor.submit_motion(command, lease.token)
        print(f"Motion decision: allowed={decision.allowed} reason={decision.reason}")
        if not decision.allowed:
            raise RuntimeError(f"Safety supervisor refused the test command: {decision.reason}")

        print("Forward command sent. Intentionally withholding further heartbeats...")
        timeout_s = settings.safety.heartbeat_timeout_ms / 1000.0
        time.sleep(timeout_s + args.wait_extra)

        print(f"heartbeat_fresh: {supervisor.deadman.fresh}")
        print(f"motion_active:   {supervisor.motion_active}")
        print(f"watchdog_running:{supervisor.watchdog_running}")

        if supervisor.deadman.fresh:
            raise RuntimeError("Heartbeat unexpectedly remained fresh")
        if supervisor.motion_active:
            raise RuntimeError("FAIL: watchdog did not clear active motion")

        print("RESULT: PASS - heartbeat expired and watchdog forced chassis stop.")
    except KeyboardInterrupt:
        print("\nInterrupted by user; forcing stop.")
        raise
    finally:
        if supervisor is not None:
            try:
                supervisor.emergency_stop()
            finally:
                supervisor.stop_watchdog()
        else:
            try:
                hardware.stop_motion()
            except Exception:
                pass
        try:
            hardware.stop()
        except Exception:
            pass
        print("Final stop issued and hardware closed.")


if __name__ == "__main__":
    main()
