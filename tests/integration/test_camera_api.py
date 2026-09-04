from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_camera_status_and_detections_in_mock_mode() -> None:
    with TestClient(app) as client:
        status_response = client.get("/api/camera/status")
        detection_response = client.get("/api/camera/detections")

    assert status_response.status_code == 200
    status = status_response.json()
    assert status["backend"] == "mock"
    assert status["connected"] is True
    assert status["running"] is True

    assert detection_response.status_code == 200
    detections = detection_response.json()
    assert detections["backend"] == "mock"
    assert detections["connected"] is True
    assert len(detections["people"]) == 1
    assert detections["people"][0]["label"] == "person"


def test_mock_camera_has_no_jpeg_frame() -> None:
    with TestClient(app) as client:
        response = client.get("/api/camera/frame.jpg")

    assert response.status_code == 503
