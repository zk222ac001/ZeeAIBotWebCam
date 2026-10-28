"""Release integrity and exclusion tests use synthetic files, never device media."""
import hashlib
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("build_release")
verifier = load_script("verify_release")
preflight = load_script("deployment_preflight")


def test_release_snapshot_excludes_local_credentials_media_and_diagnostics(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name in ("README.md", "src/sample.py", "scripts/check.py", "docs/guide.md",
                 ".env", "classroom.264", "logs/room.py", ".local-certs/private.key",
                 "config.pi.yaml.backup", "src/__pycache__/capture.py"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("synthetic file")
    selected = {p.as_posix() for p in builder.source_files(tmp_path)}
    assert selected == {"README.md", "src/sample.py", "scripts/check.py", "docs/guide.md"}


def test_release_refuses_yaml_credentials(tmp_path):
    (tmp_path / "config.yaml").write_text("conference:\n  access_token: synthetic-private-secret\n")
    with pytest.raises(ValueError, match="Remove private credentials") as exc:
        builder.reject_config_secrets(tmp_path)
    assert "synthetic-private-secret" not in str(exc.value)


def test_runtime_constraints_respect_transitive_extras(monkeypatch):
    distributions = {
        "server": SimpleNamespace(version="1.2.0", requires=['transport>=2; extra == "tls"',
                                                            'unused; extra == "dev"']),
        "transport": SimpleNamespace(version="2.1.0", requires=[]),
        "media": SimpleNamespace(version="3.0.0", requires=[]),
    }
    monkeypatch.setattr(builder, "distribution", distributions.__getitem__)
    text = builder.runtime_constraints({"dependencies": ["server[tls]>=1"],
                                        "optional-dependencies": {"webrtc": ["media>=3"]}})
    assert "transport==2.1.0" in text
    assert "server==1.2.0" in text
    assert "unused" not in text


def test_release_verification_detects_tampering_and_unlisted_files(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("original")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (tmp_path / "SHA256SUMS").write_text(f"{digest}  app.py\n")
    assert verifier.verify(tmp_path) == []
    target.write_text("modified")
    assert "Missing or changed file: app.py" in verifier.verify(tmp_path)
    target.write_text("original")
    (tmp_path / "unexpected.env").write_text("synthetic")
    assert "Release file inventory differs from the checksums" in verifier.verify(tmp_path)


def test_release_verification_rejects_path_traversal(tmp_path):
    (tmp_path / "SHA256SUMS").write_text(f"{'0' * 64}  ../outside\n")
    with pytest.raises(ValueError, match="Invalid checksum path"):
        verifier.verify(tmp_path)


def test_deployment_preflight_does_not_accept_mock_or_unobserved_hardware():
    from robotic_classroom.core.config import load_settings

    cfg = load_settings(ROOT / "config.yaml")
    issues = preflight.configuration_issues(cfg, production=True)
    assert any("real hardware" in issue for issue in issues)
    assert any("acoustic" in issue for issue in issues)
    assert any("pilot" in issue for issue in issues)
    assert cfg.autonomy.pilot_validated is False
    assert cfg.conference.echo_reference_validated is False
