from __future__ import annotations

import importlib
import math
import sys
import time
from pathlib import Path
from typing import Any

from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.core.config import Settings
from robotic_classroom.hardware.interface import HardwareStatus
from robotic_classroom.hardware.models import SensorSnapshot


class TurboPiAdapter:
    """Production-facing wrapper around the verified Hiwonder TurboPi SDK.

    Vendor imports are lazy because constructing ``Board`` immediately opens the
    serial device. Chassis movement remains unavailable until Phase 2 motor mapping
    has been explicitly marked as validated in configuration.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.vendor_path = settings.hardware.vendor_path.resolve()
        self.serial_device = settings.hardware.serial_device
        self._board: Any | None = None
        self._sonar: Any | None = None
        self._infrared: Any | None = None

    def _load_vendor(self) -> None:
        if not self.vendor_path.exists():
            raise RuntimeError(f"TurboPi vendor repository not found: {self.vendor_path}")
        vendor = str(self.vendor_path)
        if vendor not in sys.path:
            sys.path.insert(0, vendor)

    def start(self) -> None:
        self._load_vendor()
        rrc = importlib.import_module("HiwonderSDK.ros_robot_controller_sdk")
        self._board = rrc.Board(device=self.serial_device)
        self._board.enable_reception()

        if self.settings.hardware.ultrasonic_enabled:
            sonar_mod = importlib.import_module("HiwonderSDK.Sonar")
            self._sonar = sonar_mod.Sonar()
        if self.settings.hardware.infrared_enabled:
            infrared_mod = importlib.import_module("HiwonderSDK.FourInfrared")
            self._infrared = infrared_mod.FourInfrared()

    def _require_board(self) -> Any:
        if self._board is None:
            raise RuntimeError("TurboPiAdapter has not been started")
        return self._board

    def _battery_voltage(self) -> float | None:
        board = self._require_board()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            value = board.get_battery()
            if value is not None:
                return float(value) / 1000.0
            time.sleep(0.02)
        return None

    def status(self) -> HardwareStatus:
        connected = self._board is not None
        voltage = self._battery_voltage() if connected else None
        return HardwareStatus(
            backend="turbopi",
            connected=connected,
            battery_voltage=voltage,
            message="TurboPi production adapter" if connected else "TurboPi adapter stopped",
        )

    def sensors(self) -> SensorSnapshot:
        voltage = self._battery_voltage()

        distance_cm: float | None = None
        if self._sonar is not None:
            raw = self._sonar.getDistance()
            if raw is not None and math.isfinite(float(raw)) and int(raw) < 99999:
                distance_cm = float(raw) / 10.0

        infrared: tuple[bool, bool, bool, bool] | None = None
        if self._infrared is not None:
            values = self._infrared.readData()
            if len(values) == 4:
                infrared = tuple(bool(v) for v in values)  # type: ignore[assignment]

        return SensorSnapshot(
            battery_voltage=voltage,
            distance_cm=distance_cm,
            infrared=infrared,
        )

    def _set_axis(self, axis_name: str, pulse: int) -> None:
        board = self._require_board()
        axis = getattr(self.settings.hardware.pan_tilt, axis_name)
        if not self.settings.hardware.pan_tilt.enabled:
            raise RuntimeError("pan/tilt is disabled in configuration")
        if axis.channel is None:
            raise RuntimeError(f"{axis_name} servo channel has not been calibrated")
        if not axis.minimum <= pulse <= axis.maximum:
            raise ValueError(
                f"{axis_name} pulse {pulse} outside calibrated range "
                f"{axis.minimum}..{axis.maximum}"
            )
        board.pwm_servo_set_position(0.3, [[axis.channel, pulse]])

    def set_pan_pulse(self, pulse: int) -> None:
        self._set_axis("pan", pulse)

    def set_tilt_pulse(self, pulse: int) -> None:
        self._set_axis("tilt", pulse)

    def drive(self, command: MotionCommand) -> None:
        # Phase 3 deliberately refuses chassis movement until the physical motor
        # mapping has been validated and committed to configuration.
        if not self.settings.hardware.motor_mapping_validated:
            raise RuntimeError("motor mapping has not been validated")
        if command.is_stop:
            self.stop_motion()
            return
        raise RuntimeError("chassis motion implementation is locked until motor calibration is complete")

    def stop_motion(self) -> None:
        if self._board is None:
            return
        self._board.set_motor_duty([[1, 0], [2, 0], [3, 0], [4, 0]])

    def stop(self) -> None:
        if self._board is None:
            return
        try:
            self.stop_motion()
            self._board.enable_reception(False)
        finally:
            port = getattr(self._board, "port", None)
            if port is not None and getattr(port, "is_open", False):
                port.close()
            self._board = None
            self._sonar = None
            self._infrared = None
