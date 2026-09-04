from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_tracking_status_endpoint_in_mock_mode() -> None:
    with TestClient(app) as client:
        response = client.get("/api/tracking/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] in {"searching", "tracking", "lost"}
    assert "in_dead_zone" in payload
    assert "message" in payload
