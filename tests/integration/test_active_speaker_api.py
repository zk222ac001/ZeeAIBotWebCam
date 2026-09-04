from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_active_speaker_status_endpoint_is_decision_only(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")
    monkeypatch.setenv("CAMERA_MODE", "mock")
    monkeypatch.setenv("AUDIO_MODE", "mock")
    monkeypatch.setenv("ACTIVE_SPEAKER_ENABLED", "true")
    monkeypatch.setenv("ACTIVE_SPEAKER_GEOMETRY_CALIBRATED", "false")

    with TestClient(app) as client:
        response = client.get("/api/active-speaker/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["movement_requested"] is False
    assert payload["geometry_calibrated"] is False
    assert payload["state"] in {
        "waiting_for_speech",
        "calibration_required",
        "no_visible_candidate",
    }
