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


class CameraConfig(BaseModel):
    enabled: bool = True
    mode: Literal["mock", "imx500"] = "mock"
    required: bool = False
    model_path: Path = Path(
        "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
    )
    width: int = Field(default=1280, ge=320, le=4056)
    height: int = Field(default=720, ge=240, le=3040)
    frame_rate: int = Field(default=20, ge=1, le=60)
    confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    jpeg_quality: int = Field(default=80, ge=40, le=100)
    person_label: str = "person"


class TrackingConfig(BaseModel):
    enabled: bool = True
    poll_interval_ms: int = Field(default=50, ge=20, le=1000)
    smoothing_alpha: float = Field(default=0.35, gt=0.0, le=1.0)
    lost_target_timeout_ms: int = Field(default=1200, ge=100, le=10000)
    reacquire_distance_ratio: float = Field(default=0.30, gt=0.0, le=1.0)
    dead_zone_x: float = Field(default=0.08, ge=0.0, le=0.5)
    dead_zone_y: float = Field(default=0.10, ge=0.0, le=0.5)
    center_weight: float = Field(default=0.45, ge=0.0, le=1.0)
    confidence_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    size_weight: float = Field(default=0.20, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_weights(self) -> "TrackingConfig":
        if self.center_weight + self.confidence_weight + self.size_weight <= 0.0:
            raise ValueError("at least one tracking selection weight must be greater than zero")
        return self


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
    camera: CameraConfig = Field(default_factory=CameraConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
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
    camera = raw.setdefault("camera", {})
    tracking = raw.setdefault("tracking", {})

    if value := os.getenv("HARDWARE_MODE"):
        hardware["mode"] = value
    if value := os.getenv("TURBOPI_VENDOR_PATH"):
        hardware["vendor_path"] = value
    if value := os.getenv("TURBOPI_SERIAL_DEVICE"):
        hardware["serial_device"] = value
    if value := os.getenv("CAMERA_MODE"):
        camera["mode"] = value
    if value := os.getenv("IMX500_MODEL_PATH"):
        camera["model_path"] = value
    if value := os.getenv("TRACKING_ENABLED"):
        tracking["enabled"] = value.lower() in {"1", "true", "yes", "on"}

    return Settings.model_validate(raw)
