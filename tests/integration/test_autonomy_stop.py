from unittest.mock import Mock

import pytest
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


@pytest.mark.parametrize("endpoint, state", [
    ("/api/control/emergency-stop", "emergency_stop"),
    ("/api/autonomy/stop", "fault"),
    ("/api/control/motion", "fault"),
])
def test_failed_stop_reports_unconfirmed_motion_and_disarms(endpoint, state, monkeypatch):
    with TestClient(app) as client, monkeypatch.context() as patch:
        patch.setattr(app.state.autonomy.config, "enabled", True)
        assert app.state.autonomy.arm()[0]
        patch.setattr(app.state.hardware, "stop_motion",
                      Mock(side_effect=OSError("controller unavailable")))
        response = client.post(endpoint, json={})
        assert response.status_code == 503
        assert not app.state.autonomy.status().armed
        assert app.state.autonomy.status().state.value == "fault"
        assert app.state.safety.state.state.value == state
        assert app.state.safety.motion_active
