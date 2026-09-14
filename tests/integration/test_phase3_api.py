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


def test_emergency_stop_is_always_available_but_reset_requires_lease(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")

    with TestClient(app) as client:
        stopped = client.post("/api/control/emergency-stop")
        safety = client.get("/api/safety")
        denied = client.post("/api/control/reset-stop", json={"token": "not-a-valid-control-lease"})
        lease = client.post("/api/control/lease", json={"owner": "teacher"}).json()
        reset = client.post("/api/control/reset-stop", json={"token": lease["token"]})

    assert stopped.status_code == 200
    assert safety.json()["state"] == "emergency_stop"
    assert denied.status_code == 403
    assert reset.status_code == 200


def test_control_lease(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")

    with TestClient(app) as client:
        response = client.post("/api/control/lease", json={"owner": "teacher"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["owner"] == "teacher"
    assert payload["token"]


def test_heartbeat_requires_valid_control_lease(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")

    with TestClient(app) as client:
        missing = client.post("/api/control/heartbeat", json={"token": "not-a-valid-control-lease"})
        lease = client.post("/api/control/lease", json={"owner": "teacher"}).json()
        accepted = client.post("/api/control/heartbeat", json={"token": lease["token"]})
        safety = client.get("/api/safety")

    assert missing.status_code == 403
    assert accepted.status_code == 200
    assert safety.json()["heartbeat_fresh"] is True
