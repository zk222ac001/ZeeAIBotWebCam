from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_manual_stop_disarms_autonomy_without_a_lease():
    with TestClient(app) as client:
        app.state.autonomy.config.enabled = True
        try:
            assert app.state.autonomy.arm()[0]
            assert app.state.autonomy.status().armed
            response = client.post('/api/control/motion', json={})
            assert response.status_code == 200
            assert not app.state.autonomy.status().armed
            assert not app.state.safety.motion_active
        finally:
            app.state.autonomy.config.enabled = False


def test_emergency_stop_disarms_autonomy_and_latches_stop():
    with TestClient(app) as client:
        app.state.autonomy.config.enabled = True
        try:
            assert app.state.autonomy.arm()[0]
            assert client.post('/api/control/emergency-stop').status_code == 200
            assert not app.state.autonomy.status().armed
            assert app.state.safety.state.state.value == 'emergency_stop'
        finally:
            app.state.autonomy.config.enabled = False
