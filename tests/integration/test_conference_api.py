from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_conference_status_and_mock_offer() -> None:
    with TestClient(app) as client:
        status_response = client.get("/api/conference/status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["backend"] == "mock"
        assert status["running"] is True
        assert status["publish_video"] is True
        assert status["publish_audio"] is False

        offer_response = client.post(
            "/api/conference/offer",
            json={"type": "offer", "sdp": "v=0\r\ns=mock browser offer\r\n"},
        )
        assert offer_response.status_code == 200
        answer = offer_response.json()
        assert answer["type"] == "answer"
        assert answer["session_id"]

        updated = client.get("/api/conference/status").json()
        assert updated["active_sessions"] == 1

        close_response = client.delete(
            f"/api/conference/sessions/{answer['session_id']}"
        )
        assert close_response.status_code == 200
        assert close_response.json()["status"] == "closed"


def test_conference_browser_page_contains_no_robot_controls() -> None:
    with TestClient(app) as client:
        response = client.get("/conference")

    assert response.status_code == 200
    assert "ZeeAIBotWebCam WebRTC Test" in response.text
    assert "no robot movement controls" in response.text
