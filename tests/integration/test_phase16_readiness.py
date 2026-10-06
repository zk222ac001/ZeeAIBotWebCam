from fastapi.testclient import TestClient

from robotic_classroom.web.app import app, settings


def test_phase16_readiness_reports_blockers_without_secrets() -> None:
    with TestClient(app) as client:
        response = client.get("/api/readiness")

    assert response.status_code == 200
    data = response.json()
    assert "production_ready" in data
    assert "autonomous_motion_ready" in data
    assert "categories" in data
    assert "privacy_security" in data["categories"]
    encoded = response.text.lower()
    assert "access_token" not in encoded
    assert "ice_credential" not in encoded


def test_control_lease_can_be_protected_by_bearer_token() -> None:
    previous_required = settings.control_access.auth_required
    previous_token = settings.control_access.access_token
    settings.control_access.auth_required = True
    settings.control_access.access_token = "phase16-control-token-123456"

    try:
        with TestClient(app) as client:
            denied = client.post("/api/control/lease", json={"owner": "test"})
            wrong = client.post(
                "/api/control/lease",
                json={"owner": "test"},
                headers={"Authorization": "Bearer wrong-token"},
            )
            allowed = client.post(
                "/api/control/lease",
                json={"owner": "test"},
                headers={"Authorization": "Bearer phase16-control-token-123456"},
            )

        assert denied.status_code == 401
        assert wrong.status_code == 401
        assert allowed.status_code == 200
        assert len(allowed.json()["token"]) >= 16
    finally:
        settings.control_access.auth_required = previous_required
        settings.control_access.access_token = previous_token
