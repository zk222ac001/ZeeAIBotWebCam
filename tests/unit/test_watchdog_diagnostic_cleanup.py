import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/watchdog_hardware_test.py"
SPEC = importlib.util.spec_from_file_location("watchdog_hardware_test", SCRIPT)
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)


def test_stop_error_still_stops_watchdog_and_closes_hardware():
    calls = []

    def fail_stop():
        calls.append("emergency_stop")
        raise OSError("synthetic failure")

    supervisor = SimpleNamespace(emergency_stop=fail_stop,
                                 stop_watchdog=lambda: calls.append("stop_watchdog"))
    hardware = SimpleNamespace(stop=lambda: calls.append("close"))
    with pytest.raises(RuntimeError, match="cleanup failed"):
        watchdog.cleanup_hardware(hardware, supervisor)
    assert calls == ["emergency_stop", "stop_watchdog", "close"]
