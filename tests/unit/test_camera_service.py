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


def test_imx500_detection_accepts_picamera2_coordinate_tuple(tmp_path) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from robotic_classroom.camera.imx500 import IMX500Camera

    camera = IMX500Camera(
        model_path=tmp_path / "model.rpk", width=640, height=480,
        frame_rate=20, confidence_threshold=0.5, jpeg_quality=80,
        person_label="person",
    )
    camera._intrinsics = SimpleNamespace(labels=["person"])
    camera._picam2 = Mock()
    camera._imx500 = Mock()
    camera._imx500.get_outputs.return_value = [
        [[[0.1, 0.2, 0.5, 0.6]]], [[0.9]], [[0]],
    ]
    camera._imx500.get_input_size.return_value = (320, 320)
    camera._imx500.convert_inference_coords.return_value = (128, 48, 256, 192)

    people = camera._parse_people({})

    assert len(people) == 1
    assert people[0].label == "person"
    assert (people[0].box.x, people[0].box.y,
            people[0].box.width, people[0].box.height) == (128, 48, 256, 192)
