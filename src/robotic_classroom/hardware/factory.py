from robotic_classroom.core.config import Settings
from robotic_classroom.hardware.interface import HardwareService
from robotic_classroom.hardware.mock import MockHardwareService


def create_hardware_service(settings: Settings) -> HardwareService:
    if settings.hardware.mode == "mock":
        return MockHardwareService()

    # Lazy import is a safety requirement: the Hiwonder Board constructor opens
    # the serial port immediately, so mock mode must never import this backend.
    from robotic_classroom.hardware.turbopi_adapter import TurboPiAdapter

    return TurboPiAdapter(settings)
