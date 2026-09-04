from robotic_classroom.camera.mock import MockCamera
from robotic_classroom.camera.service import CameraService


def test_mock_camera_service_lifecycle() -> None:
    service = CameraService(MockCamera(width=640, height=480))

    service.start()
    snapshot = service.snapshot()

    assert snapshot.connected is True
    assert snapshot.frame_width == 640
    assert snapshot.frame_height == 480
    assert len(snapshot.people) == 1
    assert snapshot.people[0].label == "person"

    status = service.status()
    assert status.running is True
    assert status.people_count == 1

    service.stop()
    assert service.status().connected is False
