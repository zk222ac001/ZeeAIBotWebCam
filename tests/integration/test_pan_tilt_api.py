from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_pan_tilt_plan_endpoint_is_plan_only(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_MODE", "mock")
    monkeypatch.setenv("CAMERA_MODE", "mock")

    with TestClient(app) as client:
        response = client.get("/api/pan-tilt/plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "plan_only"
    assert payload["apply_to_hardware"] is False
    assert payload["pan"]["minimum"] <= payload["pan"]["planned_pulse"] <= payload["pan"]["maximum"]
    assert payload["tilt"]["minimum"] <= payload["tilt"]["planned_pulse"] <= payload["tilt"]["maximum"]
