from robotic_classroom.core.config import Settings
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.hardware.mock import MockHardwareService


def create_hardware_service(settings: Settings) -> HardwareService:
    if settings.hardware.mode == "mock":
        return MockHardwareService()

    # Lazy import is a safety requirement: the Hiwonder Board constructor opens
    # the serial port immediately, so mock mode must never import this backend.
    from robotic_classroom.hardware.real_probe import TurboPiReadOnlyProbe

    return TurboPiReadOnlyProbe(
        vendor_path=settings.hardware.vendor_path,
        serial_device=settings.hardware.serial_device,
    )
