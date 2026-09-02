from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_health_endpoint_in_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["hardware"]["backend"] == "mock"
    assert payload["motion_enabled"] is False


def test_ready_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
