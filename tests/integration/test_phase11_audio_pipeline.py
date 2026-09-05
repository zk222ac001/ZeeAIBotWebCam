from fastapi.testclient import TestClient

from robotic_classroom.web.app import app


def test_audio_pipeline_is_safe_by_default() -> None:
    with TestClient(app) as client:
        response = client.get("/api/conference/audio-pipeline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["microphone_publish_enabled"] is False
    assert payload["microphone_input_validated"] is False
    assert payload["speaker_playback_enabled"] is False
    assert payload["speaker_output_validated"] is False
    assert payload["echo_management_mode"] == "monitor"
    assert payload["echo_reference_validated"] is False
    assert payload["full_duplex_requested"] is False
    assert payload["full_duplex_validated"] is False
    assert payload["movement_requested"] is False
    assert payload["recording_enabled"] is False
