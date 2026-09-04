from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_sensor_endpoint_in_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")

    with TestClient(app) as client:
        response = client.get("/api/sensors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["distance_cm"] == 100.0
    assert payload["infrared"] == [False, False, False, False]


def test_emergency_stop_and_reset(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")

    with TestClient(app) as client:
        stopped = client.post("/api/control/emergency-stop")
        safety = client.get("/api/safety")
        reset = client.post("/api/control/reset-stop")

    assert stopped.status_code == 200
    assert safety.json()["state"] == "emergency_stop"
    assert reset.status_code == 200


def test_control_lease(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")

    with TestClient(app) as client:
        response = client.post("/api/control/lease", json={"owner": "teacher"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["owner"] == "teacher"
    assert payload["token"]
