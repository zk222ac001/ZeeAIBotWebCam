from __future__ import annotations

import math

from robotic_classroom.audio.models import AudioObservation
from robotic_classroom.camera.models import CameraSnapshot, PersonDetection
from robotic_classroom.core.config import ActiveSpeakerConfig
from robotic_classroom.fusion.models import ActiveSpeakerObservation, ActiveSpeakerState


class ActiveSpeakerFusion:
    """Fuse anonymous person detections with VAD/DoA evidence.

    This module is intentionally decision-only. It does not import any actuator,
    hardware, or safety implementation and therefore cannot move the robot.
    """

    def __init__(self, config: ActiveSpeakerConfig) -> None:
        self.config = config
        self._sequence = 0
        self._speaker_counter = 0
        self._speaker_id: str | None = None
        self._last_center_x: float | None = None
        self._last_center_y: float | None = None
        self._latest = ActiveSpeakerObservation(
            state=ActiveSpeakerState.DISABLED if not config.enabled else ActiveSpeakerState.WAITING_FOR_SPEECH,
            sequence=0,
            speaker_id=None,
            confidence=None,
            candidate_index=None,
            center_x=None,
            center_y=None,
            camera_angle_degrees=None,
            doa_degrees=None,
            angular_error_degrees=None,
            message="Active-speaker fusion disabled" if not config.enabled else "Waiting for speech",
        )

    @staticmethod
    def _signed_angle(degrees: float) -> float:
        return ((degrees + 180.0) % 360.0) - 180.0

    @staticmethod
    def _center(person: PersonDetection, width: int, height: int) -> tuple[float, float]:
        x = (person.box.x + person.box.width / 2.0) / max(width, 1)
        y = (person.box.y + person.box.height / 2.0) / max(height, 1)
        return x, y

    def _camera_angle(self, center_x: float) -> float:
        return (center_x - 0.5) * self.config.camera_horizontal_fov_degrees

    def _continuity_score(self, center_x: float, center_y: float) -> float:
        if self._last_center_x is None or self._last_center_y is None:
            return 0.0
        distance = math.hypot(center_x - self._last_center_x, center_y - self._last_center_y)
        ratio = self.config.continuity_distance_ratio
        return max(0.0, 1.0 - distance / ratio)

    def _candidate_score(
        self,
        person: PersonDetection,
        center_x: float,
        center_y: float,
        frame_width: int,
        frame_height: int,
        doa_signed: float,
    ) -> tuple[float, float, float]:
        camera_angle = self._camera_angle(center_x)
        angular_error = abs(camera_angle - doa_signed)
        audio_alignment = max(0.0, 1.0 - angular_error / self.config.max_match_error_degrees)
        area_ratio = min(
            (person.box.width * person.box.height) / max(frame_width * frame_height, 1),
            1.0,
        )
        continuity = self._continuity_score(center_x, center_y)

        total_weight = (
            self.config.audio_alignment_weight
            + self.config.detection_confidence_weight
            + self.config.size_weight
            + self.config.continuity_weight
        )
        score = (
            audio_alignment * self.config.audio_alignment_weight
            + person.confidence * self.config.detection_confidence_weight
            + area_ratio * self.config.size_weight
            + continuity * self.config.continuity_weight
        ) / total_weight
        return score, camera_angle, angular_error

    def _new_speaker_id(self) -> str:
        self._speaker_counter += 1
        return f"Speaker-{self._speaker_counter:02d}"

    def update(
        self,
        camera: CameraSnapshot,
        audio: AudioObservation,
    ) -> ActiveSpeakerObservation:
        self._sequence += 1

        if not self.config.enabled:
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.DISABLED,
                sequence=self._sequence,
                speaker_id=None,
                confidence=None,
                candidate_index=None,
                center_x=None,
                center_y=None,
                camera_angle_degrees=None,
                doa_degrees=audio.doa_degrees,
                angular_error_degrees=None,
                message="Active-speaker fusion disabled",
            )
            return self._latest

        if not audio.speech_active:
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.WAITING_FOR_SPEECH,
                sequence=self._sequence,
                speaker_id=self._speaker_id,
                confidence=None,
                candidate_index=None,
                center_x=self._last_center_x,
                center_y=self._last_center_y,
                camera_angle_degrees=None,
                doa_degrees=audio.doa_degrees,
                angular_error_degrees=None,
                message="Waiting for active speech",
            )
            return self._latest

        if (
            not audio.orientation_calibrated
            or not self.config.geometry_calibrated
            or audio.doa_degrees is None
        ):
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.CALIBRATION_REQUIRED,
                sequence=self._sequence,
                speaker_id=None,
                confidence=None,
                candidate_index=None,
                center_x=None,
                center_y=None,
                camera_angle_degrees=None,
                doa_degrees=audio.doa_degrees,
                angular_error_degrees=None,
                message="Audio/camera geometry calibration is required before speaker matching",
            )
            return self._latest

        if not camera.people:
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.NO_VISIBLE_CANDIDATE,
                sequence=self._sequence,
                speaker_id=None,
                confidence=None,
                candidate_index=None,
                center_x=None,
                center_y=None,
                camera_angle_degrees=None,
                doa_degrees=audio.doa_degrees,
                angular_error_degrees=None,
                message="Speech detected but no visible person is available for matching",
            )
            return self._latest

        doa_signed = self._signed_angle(audio.doa_degrees)
        if self.config.doa_inverted:
            doa_signed = -doa_signed

        half_fov = self.config.camera_horizontal_fov_degrees / 2.0
        if abs(doa_signed) > half_fov + self.config.outside_fov_margin_degrees:
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.NO_VISIBLE_CANDIDATE,
                sequence=self._sequence,
                speaker_id=None,
                confidence=None,
                candidate_index=None,
                center_x=None,
                center_y=None,
                camera_angle_degrees=None,
                doa_degrees=audio.doa_degrees,
                angular_error_degrees=None,
                message="Speech direction is outside the camera horizontal field of view",
            )
            return self._latest

        ranked: list[tuple[float, int, PersonDetection, float, float, float, float]] = []
        for index, person in enumerate(camera.people):
            center_x, center_y = self._center(person, camera.frame_width, camera.frame_height)
            score, camera_angle, angular_error = self._candidate_score(
                person,
                center_x,
                center_y,
                camera.frame_width,
                camera.frame_height,
                doa_signed,
            )
            ranked.append(
                (score, index, person, center_x, center_y, camera_angle, angular_error)
            )

        ranked.sort(key=lambda item: item[0], reverse=True)
        best = ranked[0]
        best_score, index, _person, center_x, center_y, camera_angle, angular_error = best

        if best_score < self.config.minimum_candidate_score:
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.AMBIGUOUS,
                sequence=self._sequence,
                speaker_id=None,
                confidence=best_score,
                candidate_index=index,
                center_x=center_x,
                center_y=center_y,
                camera_angle_degrees=camera_angle,
                doa_degrees=audio.doa_degrees,
                angular_error_degrees=angular_error,
                message="No visible person matched the speech direction strongly enough",
            )
            return self._latest

        if self._speaker_id is None:
            self._speaker_id = self._new_speaker_id()
        self._last_center_x = center_x
        self._last_center_y = center_y
        self._latest = ActiveSpeakerObservation(
            state=ActiveSpeakerState.SPEAKER_SELECTED,
            sequence=self._sequence,
            speaker_id=self._speaker_id,
            confidence=best_score,
            candidate_index=index,
            center_x=center_x,
            center_y=center_y,
            camera_angle_degrees=camera_angle,
            doa_degrees=audio.doa_degrees,
            angular_error_degrees=angular_error,
            message="Most likely active speaker selected from anonymous visual candidates",
        )
        return self._latest

    @property
    def observation(self) -> ActiveSpeakerObservation:
        return self._latest
