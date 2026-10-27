import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/calibrate_active_speaker.py"
SPEC = importlib.util.spec_from_file_location("speaker_calibration", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
calibration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calibration)


def observation(**kwargs):
    return {"connected": True, "running": True, "sequence": 1,
            "speech_state": "speaking", "doa_degrees_raw": 123.0} | kwargs


def test_repeated_polling_cannot_supply_additional_calibration_samples():
    seen = set()
    assert calibration.live_direction(observation(), seen) == 123
    for _ in range(20):
        assert calibration.live_direction(observation(), seen) is None


@pytest.mark.parametrize("changes", [
    {"connected": False}, {"running": False}, {"speech_state": "hangover"},
    {"speech_state": "silent"}, {"sequence": None}, {"doa_degrees_raw": None},
    {"doa_degrees_raw": float("nan")}, {"doa_degrees_raw": float("inf")},
    {"doa_degrees_raw": True},
])
def test_only_fresh_live_finite_speech_is_eligible(changes):
    assert calibration.live_direction(observation(**changes), set()) is None


def test_direction_quality_handles_wraparound_and_rejects_scatter():
    mean = calibration.stable_direction([359, 1] * 10)
    assert mean is not None
    assert abs(calibration.signed_angle(mean)) < 0.01
    assert calibration.stable_direction([0, 180] * 10) is None
    assert calibration.stable_direction([0, 60, 120, 180, 240, 300] * 3) is None
    assert calibration.stable_direction([0] * 9) is None


@pytest.mark.parametrize("origin", [
    "http://localhost:8000", "https://localhost:8000/path", "https://user:secret@localhost",
])
def test_calibration_requires_https_origin_without_credentials(origin):
    with pytest.raises(ValueError, match="HTTPS origin"):
        calibration.status_client(origin, Path("unused.crt"))


def test_collection_refuses_mixing_direction_sources(monkeypatch):
    monkeypatch.setattr(calibration.time, "sleep", lambda _: None)
    monkeypatch.setattr(calibration, "get_audio_status",
                        lambda *_: observation(doa_source="auto_selected"))
    with pytest.raises(ValueError, match="source changed"):
        calibration.collect("TEST", None, "https://localhost:8000", 1, "processed")
