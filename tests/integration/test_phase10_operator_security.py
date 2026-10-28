from fastapi.testclient import TestClient

from robotic_classroom.web.app import app, settings


def test_operator_and_media_device_endpoints_in_default_mode() -> None:
    with TestClient(app) as client:
        operator = client.get("/api/operator/status")
        devices = client.get("/api/conference/media-devices")
        page = client.get("/operator")

    assert operator.status_code == 200
    assert operator.json()["safety"]["motion_enabled"] is False
    assert devices.status_code == 200
    assert "capture_devices" in devices.json()
    assert "playback_devices" in devices.json()
    assert page.status_code == 200
    assert "Read-only operational status" in page.text
    assert "No motor or servo commands" in page.text


def test_conference_bearer_token_gate() -> None:
    previous_required = settings.conference.auth_required
    previous_token = settings.conference.access_token
    settings.conference.auth_required = True
    settings.conference.access_token = "phase10-test-token-123456"

    try:
        with TestClient(app) as client:
            unauthenticated = client.get("/api/conference/status")
            wrong = client.get(
                "/api/conference/status",
                headers={"Authorization": "Bearer wrong-token"},
            )
            allowed = client.get(
                "/api/conference/status",
                headers={"Authorization": "Bearer phase10-test-token-123456"},
            )

        assert unauthenticated.status_code == 401
        assert wrong.status_code == 401
        assert allowed.status_code == 200
        assert allowed.json()["auth_required"] is True
    finally:
        settings.conference.auth_required = previous_required
        settings.conference.access_token = previous_token


def test_detailed_health_requires_media_token_and_public_probe_stays_minimal(monkeypatch):
    token = "synthetic-health-token-123456"
    monkeypatch.setattr(settings.conference, "auth_required", True)
    monkeypatch.setattr(settings.conference, "access_token", token)
    with TestClient(app) as client:
        denied = client.get("/health")
        assert denied.status_code == 401
        assert "people_count" not in denied.text
        assert client.get("/ready").json() == {"status": "ready"}
        allowed = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        assert allowed.status_code == 200
        assert "camera" in allowed.json()
        assert allowed.headers["cache-control"] == "no-store"


def test_non_ascii_bearer_headers_are_rejected_without_server_error(monkeypatch):
    monkeypatch.setattr(settings.conference, "auth_required", True)
    monkeypatch.setattr(settings.conference, "access_token", "synthetic-media-token-123456")
    monkeypatch.setattr(settings.control_access, "auth_required", True)
    monkeypatch.setattr(settings.control_access, "access_token", "synthetic-control-token-123456")
    with TestClient(app) as client:
        headers = {b"Authorization": b"Bearer invalid-\xff-token"}
        assert client.get("/health", headers=headers).status_code == 401
        assert client.post("/api/control/lease", json={"owner": "test"}, headers=headers).status_code == 401
