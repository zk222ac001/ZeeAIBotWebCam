from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Any

from robotic_classroom.hardware.interface import HardwareStatus


class TurboPiReadOnlyProbe:
    """Minimal real-hardware probe used only for Phase 1/2 validation.

    This class intentionally exposes no motor or servo API. It lazily imports the
    Hiwonder SDK so mock mode never opens /dev/ttyAMA0 or starts vendor threads.
    """

    def __init__(self, vendor_path: Path, serial_device: str) -> None:
        self.vendor_path = vendor_path.resolve()
        self.serial_device = serial_device
        self._board: Any | None = None

    def start(self) -> None:
        if not self.vendor_path.exists():
            raise RuntimeError(f"TurboPi vendor repository not found: {self.vendor_path}")

        vendor_string = str(self.vendor_path)
        if vendor_string not in sys.path:
            sys.path.insert(0, vendor_string)

        rrc = importlib.import_module("HiwonderSDK.ros_robot_controller_sdk")
        self._board = rrc.Board(device=self.serial_device)
        self._board.enable_reception()

    def status(self) -> HardwareStatus:
        if self._board is None:
            return HardwareStatus(
                backend="turbopi-read-only",
                connected=False,
                message="TurboPi controller has not been started",
            )

        deadline = time.monotonic() + 2.0
        raw_voltage = None

        while time.monotonic() < deadline:
            raw_voltage = self._board.get_battery()
            if raw_voltage is not None:
                break
            time.sleep(0.05)

        voltage = raw_voltage / 1000.0 if raw_voltage is not None else None

        return HardwareStatus(
            backend="turbopi-read-only",
            connected=True,
            battery_voltage=voltage,
            message="TurboPi serial controller opened successfully",
        )

    def stop(self) -> None:
        if self._board is None:
            return

        try:
            self._board.enable_reception(False)
        finally:
            port = getattr(self._board, "port", None)
            if port is not None and getattr(port, "is_open", False):
                port.close()
            self._board = None
