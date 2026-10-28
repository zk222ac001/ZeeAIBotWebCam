"""Exercise launcher environment precedence without starting any hardware service."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("systemd", [True, False])
def test_managed_service_ignores_manual_environment(tmp_path, systemd):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "run_pi.sh"
    shutil.copyfile(ROOT / "scripts/run_pi.sh", launcher)
    local_env = tmp_path / ".env"
    local_env.write_text("CONTROL_ACCESS_TOKEN=manual-test-token\n")
    local_env.chmod(0o600)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Stop at flock, before process discovery, network or hardware access.
    flock = bin_dir / "flock"
    flock.write_text('#!/bin/bash\nprintf "%s" "$CONTROL_ACCESS_TOKEN" > "$OBSERVED_ENV"\nexit 1\n')
    flock.chmod(0o700)
    observed = tmp_path / "observed"
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
               CONTROL_ACCESS_TOKEN="managed-test-token", CONFERENCE_ACCESS_TOKEN="managed-media-test-token",
               CONFERENCE_AUTH_REQUIRED="true", CONTROL_AUTH_REQUIRED="true", OBSERVED_ENV=str(observed),
               XDG_RUNTIME_DIR=str(tmp_path))
    env.pop("INVOCATION_ID", None)
    if systemd:
        env["INVOCATION_ID"] = "synthetic-systemd-invocation"
    result = subprocess.run(["bash", str(launcher)], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert observed.read_text() == ("managed-test-token" if systemd else "manual-test-token")
    assert "test-token" not in result.stdout + result.stderr


def test_managed_service_refuses_missing_managed_authentication(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "run_pi.sh"
    shutil.copyfile(ROOT / "scripts/run_pi.sh", launcher)
    # A local file must not silently restore credentials missing from systemd.
    local_env = tmp_path / ".env"
    local_env.write_text("CONFERENCE_AUTH_REQUIRED=true\nCONTROL_AUTH_REQUIRED=true\n")
    local_env.chmod(0o600)
    env = dict(os.environ, INVOCATION_ID="synthetic-service")
    env.pop("CONFERENCE_AUTH_REQUIRED", None)
    result = subprocess.run(["bash", str(launcher)], env=env, capture_output=True,
                            text=True, check=False)
    assert result.returncode == 1
    assert "Configure conference authentication" in result.stdout
