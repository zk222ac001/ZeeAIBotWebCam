from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ApplicationConfig(BaseModel):
    name: str = "ZeeAIBotWebCam"
    environment: Literal["development", "testing", "production"] = "development"


class AxisConfig(BaseModel):
    channel: int | None = Field(default=None, ge=1, le=4)
    center: int = Field(default=1500, ge=500, le=2500)
    minimum: int = Field(default=1300, ge=500, le=2500)
    maximum: int = Field(default=1700, ge=500, le=2500)
    inverted: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> "AxisConfig":
        if not self.minimum <= self.center <= self.maximum:
            raise ValueError("axis calibration must satisfy minimum <= center <= maximum")
        return self


class PanTiltConfig(BaseModel):
    enabled: bool = False
    pan: AxisConfig = Field(default_factory=AxisConfig)
    tilt: AxisConfig = Field(default_factory=AxisConfig)


class HardwareConfig(BaseModel):
    mode: Literal["mock", "real"] = "mock"
    vendor_path: Path = Path("vendor/TurboPi")
    serial_device: str = "/dev/ttyAMA0"
    ultrasonic_enabled: bool = True
    infrared_enabled: bool = True
    motor_mapping_validated: bool = False
    pan_tilt: PanTiltConfig = Field(default_factory=PanTiltConfig)


class WebConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class SafetyConfig(BaseModel):
    motion_enabled: bool = False
    minimum_obstacle_distance_cm: float = Field(default=30.0, gt=0)
    heartbeat_timeout_ms: int = Field(default=750, ge=100, le=10_000)
    control_lease_ttl_seconds: float = Field(default=10.0, ge=1.0, le=300.0)
    require_control_lease: bool = True


class PrivacyConfig(BaseModel):
    recording_enabled: bool = False
    face_recognition_enabled: bool = False


class Settings(BaseModel):
    application: ApplicationConfig
    hardware: HardwareConfig
    web: WebConfig
    logging: LoggingConfig
    safety: SafetyConfig
    privacy: PrivacyConfig


def load_settings(config_file: str | Path | None = None) -> Settings:
    path = Path(config_file or os.getenv("APP_CONFIG", "config.yaml"))

    if not path.exists():
        raise FileNotFoundError(f"Configuration file does not exist: {path.resolve()}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    hardware = raw.setdefault("hardware", {})

    if value := os.getenv("HARDWARE_MODE"):
        hardware["mode"] = value
    if value := os.getenv("TURBOPI_VENDOR_PATH"):
        hardware["vendor_path"] = value
    if value := os.getenv("TURBOPI_SERIAL_DEVICE"):
        hardware["serial_device"] = value

    return Settings.model_validate(raw)
