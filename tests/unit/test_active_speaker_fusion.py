from robotic_classroom.audio.models import AudioObservation, SpeechState
from robotic_classroom.camera.models import BoundingBox, CameraSnapshot, PersonDetection
from robotic_classroom.core.config import ActiveSpeakerConfig
from robotic_classroom.fusion.active_speaker import ActiveSpeakerFusion
from robotic_classroom.fusion.models import ActiveSpeakerState


def camera_with_two_people() -> CameraSnapshot:
    return CameraSnapshot(
        backend="test",
        connected=True,
        frame_width=1000,
        frame_height=600,
        sequence=1,
        people=(
            PersonDetection(0.95, BoundingBox(x=100, y=100, width=200, height=400)),
            PersonDetection(0.90, BoundingBox(x=700, y=100, width=200, height=400)),
        ),
    )


def audio_at(degrees: float, *, calibrated: bool = True) -> AudioObservation:
    return AudioObservation(
        backend="test",
        connected=True,
        running=True,
        sequence=1,
        speech_state=SpeechState.SPEAKING,
        speech_active=True,
        doa_degrees_raw=degrees,
        doa_degrees=degrees,
        orientation_calibrated=calibrated,
        message="test",
    )


def test_calibration_gate_blocks_speaker_selection() -> None:
    fusion = ActiveSpeakerFusion(ActiveSpeakerConfig(geometry_calibrated=False))

    result = fusion.update(camera_with_two_people(), audio_at(20.0))

    assert result.state is ActiveSpeakerState.CALIBRATION_REQUIRED
    assert result.speaker_id is None


def test_right_side_doa_selects_right_visual_candidate() -> None:
    config = ActiveSpeakerConfig(
        geometry_calibrated=True,
        camera_horizontal_fov_degrees=70.0,
        max_match_error_degrees=25.0,
        minimum_candidate_score=0.30,
    )
    fusion = ActiveSpeakerFusion(config)

    result = fusion.update(camera_with_two_people(), audio_at(21.0))

    assert result.state is ActiveSpeakerState.SPEAKER_SELECTED
    assert result.candidate_index == 1
    assert result.center_x is not None and result.center_x > 0.5
    assert result.speaker_id == "Speaker-01"


def test_left_side_doa_selects_left_visual_candidate() -> None:
    config = ActiveSpeakerConfig(
        geometry_calibrated=True,
        camera_horizontal_fov_degrees=70.0,
        max_match_error_degrees=25.0,
        minimum_candidate_score=0.30,
    )
    fusion = ActiveSpeakerFusion(config)

    result = fusion.update(camera_with_two_people(), audio_at(339.0))

    assert result.state is ActiveSpeakerState.SPEAKER_SELECTED
    assert result.candidate_index == 0
    assert result.center_x is not None and result.center_x < 0.5


def test_silence_does_not_select_a_new_speaker() -> None:
    config = ActiveSpeakerConfig(geometry_calibrated=True)
    fusion = ActiveSpeakerFusion(config)
    audio = audio_at(0.0)
    silent = AudioObservation(
        backend=audio.backend,
        connected=True,
        running=True,
        sequence=2,
        speech_state=SpeechState.SILENT,
        speech_active=False,
        doa_degrees_raw=None,
        doa_degrees=None,
        orientation_calibrated=True,
        message="silent",
    )

    result = fusion.update(camera_with_two_people(), silent)

    assert result.state is ActiveSpeakerState.WAITING_FOR_SPEECH
    assert result.confidence is None
