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
