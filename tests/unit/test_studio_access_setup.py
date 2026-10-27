import importlib.util
import stat
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/setup_studio_access.py"
SPEC = importlib.util.spec_from_file_location("studio_access_setup", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)

MEDIA = "test-media-token-123456789"
CONTROL = "test-control-token-987654321"


def factory():
    values = iter([MEDIA, CONTROL])
    return lambda: next(values)


def test_new_access_settings_preserve_other_deployment_configuration():
    original = '# Existing settings\nWEBRTC_ICE_SERVERS="turn:relay.example:3478"\nAPPLICATION_ENVIRONMENT=development\n'
    result, generated = setup.prepare_environment(original, token_factory=factory())
    assert result.startswith(original)
    assert generated == 2
    assert "CONFERENCE_AUTH_REQUIRED=true" in result
    assert "CONTROL_AUTH_REQUIRED=true" in result
    assert f"CONFERENCE_ACCESS_TOKEN={MEDIA}" in result
    assert f"CONTROL_ACCESS_TOKEN={CONTROL}" in result
    assert "APPLICATION_ENVIRONMENT=production" not in result
    assert "PILOT_VALIDATED" not in result


def test_second_run_preserves_credentials_and_is_idempotent():
    first, _ = setup.prepare_environment("", token_factory=factory())
    second, generated = setup.prepare_environment(first, token_factory=lambda: pytest.fail("Rotated token"))
    assert second == first
    assert generated == 0


def test_empty_token_overrides_are_initialized_without_rotation():
    result, generated = setup.prepare_environment(
        'CONFERENCE_ACCESS_TOKEN=\nCONTROL_ACCESS_TOKEN=""\n', token_factory=factory(),
    )
    assert generated == 2
    assert f"CONFERENCE_ACCESS_TOKEN={MEDIA}" in result
    assert f"CONTROL_ACCESS_TOKEN={CONTROL}" in result


def test_last_assignment_wins_and_duplicates_are_removed():
    original = f'CONFERENCE_ACCESS_TOKEN=old-token-value-12345\nCONFERENCE_ACCESS_TOKEN="{MEDIA}"\nCONTROL_ACCESS_TOKEN=\'{CONTROL}\'\n'
    result, generated = setup.prepare_environment(original)
    assert generated == 0
    assert result.count("CONFERENCE_ACCESS_TOKEN=") == 1
    assert f"CONFERENCE_ACCESS_TOKEN={MEDIA}" in result


@pytest.mark.parametrize("value", ["short", "replace-with-a-long-random-secret", '"token with whitespace"'])
def test_invalid_or_placeholder_tokens_need_explicit_rotation(value):
    with pytest.raises(ValueError, match="--rotate"):
        setup.prepare_environment(f"CONFERENCE_ACCESS_TOKEN={value}\n")
    result, count = setup.prepare_environment(f"CONFERENCE_ACCESS_TOKEN={value}\n", rotate=True, token_factory=factory())
    assert count == 2
    assert f"CONFERENCE_ACCESS_TOKEN={MEDIA}" in result


def test_shared_token_is_rejected_without_exposing_it():
    original = f"CONFERENCE_ACCESS_TOKEN={MEDIA}\nCONTROL_ACCESS_TOKEN={MEDIA}\n"
    with pytest.raises(ValueError) as caught:
        setup.prepare_environment(original)
    assert MEDIA not in str(caught.value)


@pytest.mark.parametrize("value", ['"unfinished', "continued\\"])
def test_rotation_cannot_leave_a_multiline_setting_half_replaced(value):
    with pytest.raises(ValueError, match="manual review"):
        setup.prepare_environment(f"CONFERENCE_ACCESS_TOKEN={value}\ncontinued-value\n", rotate=True)


def test_secure_atomic_write_and_refusal_to_follow_symlinks(tmp_path):
    target = tmp_path / "env"
    setup.atomic_write(target, "existing\n")
    assert target.read_text() == "existing\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        setup.atomic_write(link, "replaced\n")
    with pytest.raises(ValueError):
        setup.read_environment(link)
    assert target.read_text() == "existing\n"


def test_failed_replace_keeps_original_and_removes_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "env"
    target.write_text("original")
    def fail_replace(*_):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(setup.os, "replace", fail_replace)
    with pytest.raises(OSError):
        setup.atomic_write(target, "updated")
    assert target.read_text() == "original"
    assert not list(tmp_path.glob(".zee-access-*"))


def test_dry_run_does_not_write_or_display_credentials(tmp_path, capsys):
    target = tmp_path / "env"
    target.write_text(f"CONFERENCE_ACCESS_TOKEN={MEDIA}\nCONTROL_ACCESS_TOKEN={CONTROL}\n")
    before = target.read_bytes()
    assert setup.main(["--env-file", str(target)]) == 0
    output = capsys.readouterr()
    assert MEDIA not in output.out + output.err
    assert CONTROL not in output.out + output.err
    assert target.read_bytes() == before
    assert list(tmp_path.iterdir()) == [target]


def test_apply_without_root_stops_before_reading_or_writing(tmp_path, monkeypatch, capsys):
    target = tmp_path / "env"
    monkeypatch.setattr(setup.os, "geteuid", lambda: 1000)
    assert setup.main(["--apply", "--env-file", str(target)]) == 2
    assert not target.exists()
    assert "requires sudo" in capsys.readouterr().err
