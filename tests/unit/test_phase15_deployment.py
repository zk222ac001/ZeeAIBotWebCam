from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/service_healthcheck.py"
SPEC = importlib.util.spec_from_file_location("service_healthcheck", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)


def test_validate_healthy_startup() -> None:
    issues = health.validate(
        {"status": "ready"},
        {"watchdog_running": True, "motion_active": False},
        {"running": True, "armed": False},
    )
    assert issues == []


def test_validate_rejects_unsafe_startup_state() -> None:
    issues = health.validate(
        {"status": "not-ready"},
        {"watchdog_running": False, "motion_active": True},
        {"running": False, "armed": True},
    )
    assert "application is not ready" in issues
    assert "safety watchdog is not running" in issues
    assert "chassis motion is active or unknown" in issues
    assert "autonomy service is not running" in issues
    assert "autonomy unexpectedly started armed" in issues


def test_healthcheck_requires_https_origin() -> None:
    for value in (
        "http://localhost:8000",
        "https://user:pw@localhost:8000",
        "https://localhost:8000/api/safety",
        "https://localhost:8000?x=1",
    ):
        try:
            health.https_origin(value)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"accepted invalid origin: {value}")


def test_systemd_template_keeps_single_safe_entrypoint() -> None:
    template = (ROOT / "deploy/systemd/zee-robot.service.in").read_text(encoding="utf-8")
    assert "ExecStart=@ROOT@/scripts/run_pi_https.sh" in template
    assert "ExecStartPost=@PYTHON@ @ROOT@/scripts/service_healthcheck.py --wait 30" in template
    assert "Restart=on-failure" in template
    assert "EnvironmentFile=-/etc/zee-robot/zee-robot.env" in template
    assert "ExecStartPre=/usr/bin/test -r @ROOT@/config.pi.yaml" in template


def test_phase15_pi_profile_keeps_autonomy_plan_only() -> None:
    text = (ROOT / "config.pi.yaml").read_text(encoding="utf-8")
    autonomy = text.split("autonomy:", 1)[1].split("\naudio:", 1)[0]
    assert "mode: plan_only" in autonomy
    assert "execution_policy: rotation_only" in autonomy
    assert "pilot_validated: false" in autonomy
    assert "forward_enabled: false" in autonomy
