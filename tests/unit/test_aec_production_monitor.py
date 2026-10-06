import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/aec_production_monitor.py"
SPEC = importlib.util.spec_from_file_location("aec_production_monitor", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


def test_snapshot_maps_audio_pipeline_payload() -> None:
    # Mirrors the fields exposed by /api/conference/audio-pipeline.
    payload = {
        "speaker_playback_running": True,
        "speaker_frames_written": 123,
        "speaker_last_error": "",
        "echo_reference_enabled": True,
        "echo_reference_running": True,
        "echo_reference_frames_written": 123,
        "echo_reference_last_error": "",
        "echo_reference_validated": False,
        "echo_management_mode": "monitor",
    }

    snapshot = monitor.Snapshot.from_payload(payload)

    assert snapshot.speaker_running is True
    assert snapshot.speaker_frames == 123
    assert snapshot.reference_enabled is True
    assert snapshot.reference_running is True
    assert snapshot.reference_frames == 123
    assert snapshot.reference_validated is False
    assert snapshot.echo_management_mode == "monitor"
