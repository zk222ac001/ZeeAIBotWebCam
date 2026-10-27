from types import SimpleNamespace
from unittest.mock import Mock

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


def test_center_and_resume_controls_disarm_autonomy_and_preserve_mock_safety(monkeypatch):
    with TestClient(app) as client, monkeypatch.context() as patch:
        patch.setattr(app.state.autonomy.config, "enabled", True)
        assert app.state.autonomy.arm()[0]
        response = client.post('/api/pan-tilt/center')
        assert response.status_code == 202
        assert response.json()['center_hold'] is True
        assert not app.state.autonomy.status().armed
        assert client.get('/api/pan-tilt/plan').json()['center_hold'] is True
        assert app.state.hardware.last_motion.is_stop
        assert app.state.hardware.pan_pulse is None
        assert client.post('/api/pan-tilt/resume').status_code == 202
        assert client.get('/api/pan-tilt/plan').json()['center_hold'] is False


def test_camera_control_uses_control_authentication(monkeypatch):
    with TestClient(app) as client, monkeypatch.context() as patch:
        patch.setattr(app.state.settings.control_access, 'auth_required', True)
        patch.setattr(app.state.settings.control_access, 'access_token', 'camera-control-test-token')
        assert client.post('/api/pan-tilt/center').status_code == 401
        assert not app.state.pan_tilt.center_hold
        assert client.post('/api/pan-tilt/center', headers={
            'Authorization': 'Bearer camera-control-test-token',
        }).status_code == 202


def test_camera_control_cannot_clear_or_bypass_emergency_stop():
    with TestClient(app) as client:
        assert client.post('/api/control/emergency-stop').status_code == 200
        assert client.post('/api/pan-tilt/center').status_code == 409
        assert client.post('/api/pan-tilt/resume').status_code == 409
        assert app.state.safety.state.state.value == 'emergency_stop'


def test_resume_rejects_active_execute_mode_autonomy(monkeypatch):
    with TestClient(app) as client, monkeypatch.context() as patch:
        patch.setattr(app.state.autonomy, 'status',
                      lambda: SimpleNamespace(armed=True, mode='execute'))
        assert client.post('/api/pan-tilt/resume').status_code == 409


def test_center_request_stays_blocked_if_chassis_stop_fails(monkeypatch):
    with TestClient(app) as client, monkeypatch.context() as patch:
        patch.setattr(app.state.hardware, 'stop_motion',
                      Mock(side_effect=OSError('controller unavailable')))
        assert client.post('/api/pan-tilt/center').status_code == 503
        assert not app.state.pan_tilt.center_hold
        assert app.state.safety.state.state.value == 'fault'
