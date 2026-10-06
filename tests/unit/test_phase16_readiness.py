from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from robotic_classroom.core.config import ControlAccessConfig

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/production_readiness.py"
SPEC = importlib.util.spec_from_file_location("production_readiness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def test_control_access_requires_token_when_enabled() -> None:
    with pytest.raises(ValidationError, match="CONTROL_ACCESS_TOKEN"):
        ControlAccessConfig(auth_required=True)


def test_control_access_accepts_long_token() -> None:
    config = ControlAccessConfig(
        auth_required=True,
        access_token="1234567890abcdef",
    )
    assert config.auth_required is True


def test_readiness_report_render_lists_blockers() -> None:
    text = reporter.render(
        {
            "production_ready": False,
            "autonomous_motion_ready": False,
            "categories": {
                "runtime": {"ready": True, "blockers": []},
                "aec": {
                    "ready": False,
                    "blockers": ["acoustic echo reference not validated"],
                },
            },
            "autonomy": {
                "mode": "plan_only",
                "armed": False,
                "execution_policy": "rotation_only",
                "pilot_validated": False,
            },
        }
    )
    assert "PASS    runtime" in text
    assert "BLOCKED aec" in text
    assert "acoustic echo reference not validated" in text
    assert "mode=plan_only" in text


def test_readiness_report_requires_https_origin() -> None:
    for value in ("http://localhost:8000", "https://host/path", "https://u:p@host"):
        with pytest.raises(argparse.ArgumentTypeError):
            reporter.https_origin(value)
