from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_audio_status_endpoint_in_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")
    monkeypatch.setenv("CAMERA_MODE", "mock")
    monkeypatch.setenv("AUDIO_MODE", "mock")

    with TestClient(app) as client:
        response = client.get("/api/audio/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "mock"
    assert payload["connected"] is True
    assert payload["running"] is True
    assert payload["speech_state"] in {"silent", "speaking", "hangover"}
    assert "doa_degrees" in payload
    assert payload["orientation_calibrated"] is False
