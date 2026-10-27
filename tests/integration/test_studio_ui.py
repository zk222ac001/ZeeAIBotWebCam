from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from robotic_classroom.web.app import app, settings


class AssetLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value and value.startswith("/assets/"):
                self.paths.add(value)


@pytest.mark.parametrize("path,page", [
    ("/", "overview"), ("/operator", "overview"), ("/conference", "conference"),
    ("/api/pan-tilt/ui", "camera"), ("/api/control/ui", "control"),
    ("/readiness", "readiness"),
])
def test_studio_pages_and_their_assets_are_installable_and_do_not_move(path, page):
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert f'data-page="{page}"' in response.text
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"
        parser = AssetLinks()
        parser.feed(response.text)
        assert len(parser.paths) >= 4
        for asset in parser.paths:
            assert client.get(asset).status_code == 200, asset
        assert not app.state.safety.motion_active
        assert app.state.hardware.pan_pulse is None
        assert not app.state.autonomy.status().armed


def test_conference_auth_also_protects_camera_frames_and_tracking_metadata(monkeypatch):
    with TestClient(app) as client, monkeypatch.context() as patch:
        patch.setattr(settings.conference, "auth_required", True)
        patch.setattr(settings.conference, "access_token", "private-media-token-test")
        headers = {"Authorization": "Bearer private-media-token-test"}
        for path in [
            "/api/camera/status", "/api/camera/detections", "/api/camera/frame.jpg",
            "/api/tracking/status", "/api/audio/status", "/api/active-speaker/status",
            "/api/pan-tilt/plan", "/api/conference/client-config",
        ]:
            denied = client.get(path)
            assert denied.status_code == 401, path
            allowed = client.get(path, headers=headers)
            assert allowed.status_code == (503 if path.endswith("frame.jpg") else 200)
        assert client.post("/api/control/emergency-stop").status_code == 200


def test_browser_ice_configuration_is_authorized_without_injecting_secrets_into_html(monkeypatch):
    with TestClient(app) as client, monkeypatch.context() as patch:
        patch.setattr(settings.conference, "auth_required", True)
        patch.setattr(settings.conference, "access_token", "private-config-token-test")
        patch.setattr(settings.conference, "ice_servers", ["turn:relay.example.test:3478"])
        patch.setattr(settings.conference, "ice_username", "relay-user-test")
        patch.setattr(settings.conference, "ice_credential", "relay-secret-test")
        response = client.get("/api/conference/client-config", headers={
            "Authorization": "Bearer private-config-token-test",
        })
        assert response.status_code == 200
        assert response.json()["iceServers"] == [{
            "urls": ["turn:relay.example.test:3478"],
            "username": "relay-user-test", "credential": "relay-secret-test",
        }]
        page = client.get("/conference").text
        assert "relay-secret-test" not in page
        assert "private-config-token-test" not in page
        assert "/assets/control.js" not in page
        assert "/assets/camera.js" not in page
        readiness = client.get("/api/readiness").text
        assert "relay-secret-test" not in readiness
        assert "private-config-token-test" not in readiness
