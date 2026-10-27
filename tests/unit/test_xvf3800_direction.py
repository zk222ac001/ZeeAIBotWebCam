import math
import struct
from unittest.mock import Mock

import pytest

from robotic_classroom.audio.xvf3800 import XVF3800USBBackend


def backend(source="processed", processed=30.0, automatic=170.0, fail_selected=False):
    device = XVF3800USBBackend(0x2886, 0x001A, doa_source=source)
    device._running = True
    selected = (RuntimeError("unsupported command") if fail_selected else
                struct.pack("<ff", math.radians(processed), math.radians(automatic)))
    device._read_control = Mock(side_effect=[struct.pack("<HH", 250, 1), selected])
    return device


@pytest.mark.parametrize("source, expected", [
    ("processed", 30), ("auto_selected", 170), ("primary", 250),
])
def test_explicit_direction_source_uses_the_documented_value(source, expected):
    result = backend(source).observation()
    assert result.doa_source == source
    assert result.doa_degrees_raw == pytest.approx(expected)
    assert result.doa_degrees_processed == pytest.approx(30)
    assert result.doa_degrees_auto_selected == pytest.approx(170)
    assert result.doa_degrees_primary == 250
    assert result.speech_active


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_missing_processed_speech_does_not_fall_back_to_another_beam(value):
    result = backend(processed=value).observation()
    assert result.doa_degrees_raw is None
    assert result.doa_degrees_auto_selected == pytest.approx(170)
    assert result.doa_degrees_primary == 250
    assert result.doa_source == "processed"


def test_control_error_does_not_switch_calibrated_coordinate_source():
    result = backend(fail_selected=True).observation()
    assert result.doa_degrees_raw is None
    assert result.doa_source == "processed"


def test_invalid_source_is_rejected_before_hardware_access():
    with pytest.raises(ValueError, match="Unsupported"):
        XVF3800USBBackend(0x2886, 0x001A, doa_source="invented")
