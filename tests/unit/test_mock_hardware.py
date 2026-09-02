from robotic_classroom.hardware.mock import MockHardwareService


def test_mock_hardware_lifecycle() -> None:
    hardware = MockHardwareService()
    hardware.start()

    status = hardware.status()
    assert status.connected is True
    assert status.backend == "mock"
    assert status.battery_voltage is not None

    hardware.stop()
    assert hardware.status().connected is False
