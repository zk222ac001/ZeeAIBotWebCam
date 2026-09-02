from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ApplicationConfig(BaseModel):
    name: str = "ZeeAIBotWebCam"
    environment: Literal["development", "testing", "production"] = "development"


class HardwareConfig(BaseModel):
    mode: Literal["mock", "real"] = "mock"
    vendor_path: Path = Path("vendor/TurboPi")
    serial_device: str = "/dev/ttyAMA0"


class WebConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class SafetyConfig(BaseModel):
    motion_enabled: bool = False


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
