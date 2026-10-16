from __future__ import annotations

import math
import threading
from dataclasses import replace

from robotic_classroom.audio.models import AudioObservation
from robotic_classroom.camera.models import CameraSnapshot, PersonDetection
from robotic_classroom.core.config import ActiveSpeakerConfig
from robotic_classroom.core.freshness import is_fresh
from robotic_classroom.fusion.models import ActiveSpeakerObservation, ActiveSpeakerState


class ActiveSpeakerFusion:
    """Fuse anonymous person detections with VAD/DoA evidence.

    This module is intentionally decision-only. It does not import any actuator,
    hardware, or safety implementation and therefore cannot move the robot.
    """

    def __init__(self, config: ActiveSpeakerConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._sequence = 0
        self._speaker_counter = 0
        self._speaker_id: str | None = None
        self._accepted_location: tuple[float, float] | None = None
        self._accepted_timestamp: float | None = None
        self._pending_location: tuple[float, float] | None = None
        self._pending_samples: tuple[float, float] | None = None
        self._pending_since = 0.0
        self._pending_count = 0
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
        angular_error = abs(self._signed_angle(camera_angle - doa_signed))
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

    def _same_location(
        self, left: tuple[float, float], right: tuple[float, float],
    ) -> bool:
        horizontal = self._signed_angle(left[0] - right[0])
        return math.hypot(
            horizontal / self.config.camera_horizontal_fov_degrees, left[1] - right[1],
        ) <= self.config.continuity_distance_ratio

    def _clear_pending(self) -> None:
        self._pending_location = None
        self._pending_samples = None
        self._pending_count = 0

    def update(
        self, camera: CameraSnapshot, audio: AudioObservation, *,
        camera_pan_degrees: float | None = None,
    ) -> ActiveSpeakerObservation:
        # Do not expose an intermediate winner before switch confirmation.
        with self._lock:
            return self._update(camera, audio, camera_pan_degrees=camera_pan_degrees)

    def _update(
        self, camera: CameraSnapshot, audio: AudioObservation, *,
        camera_pan_degrees: float | None = None,
    ) -> ActiveSpeakerObservation:
        # Expire association even across silence, camera loss or calibration failures.
        if self._accepted_timestamp is not None and not is_fresh(
            self._accepted_timestamp, self.config.observation_timeout_ms,
        ):
            self._speaker_id = None
            self._accepted_location = None
            self._accepted_timestamp = None
            self._last_center_x = self._last_center_y = None
            self._clear_pending()
        result = self._evaluate(camera, audio, camera_pan_degrees=camera_pan_degrees)
        if result.state is not ActiveSpeakerState.SPEAKER_SELECTED:
            self._clear_pending()
            return result

        assert result.camera_angle_degrees is not None and result.center_y is not None
        pan = camera_pan_degrees if self.config.pan_compensation_enabled else 0.0
        assert pan is not None
        location = (self._signed_angle(result.camera_angle_degrees + pan), result.center_y)
        switching = self._speaker_counter > 0 and (
            self._accepted_location is None
            or not self._same_location(self._accepted_location, location)
        )
        if switching:
            samples = (camera.timestamp_monotonic, audio.timestamp_monotonic)
            if self._pending_location is None or not self._same_location(
                self._pending_location, location,
            ):
                self._pending_location = location
                self._pending_samples = samples
                self._pending_since = min(samples)
                self._pending_count = 1
            elif self._pending_samples is not None and all(
                current > previous for current, previous in zip(samples, self._pending_samples)
            ):
                # Both producers must advance; polling or only new audio is not evidence.
                self._pending_samples = samples
                self._pending_count += 1
            confirmed = (
                self._pending_count >= self.config.switch_confirmations
                and self._pending_samples is not None
                and min(self._pending_samples) - self._pending_since
                >= self.config.switch_dwell_ms / 1000.0
            )
            if not confirmed:
                self._latest = replace(
                    result, state=ActiveSpeakerState.AMBIGUOUS,
                    speaker_id=None, candidate_index=None, center_x=None, center_y=None,
                    message="Waiting for fresh observations to confirm a speaker switch",
                )
                return self._latest

        if self._speaker_id is None or switching:
            self._speaker_id = self._new_speaker_id()
        self._accepted_location = location
        self._accepted_timestamp = result.timestamp_monotonic
        self._last_center_x = result.center_x
        self._last_center_y = result.center_y
        self._clear_pending()
        self._latest = replace(result, speaker_id=self._speaker_id)
        return self._latest

    def _evaluate(
        self,
        camera: CameraSnapshot,
        audio: AudioObservation,
        *,
        camera_pan_degrees: float | None = None,
    ) -> ActiveSpeakerObservation:
        self._sequence += 1

        if (not camera.connected or not audio.connected or not audio.running
            or not is_fresh(camera.timestamp_monotonic, self.config.observation_timeout_ms)
            or not is_fresh(audio.timestamp_monotonic, self.config.observation_timeout_ms)):
            self._latest = replace(
                self._latest, state=ActiveSpeakerState.NO_VISIBLE_CANDIDATE,
                sequence=self._sequence, speaker_id=None, candidate_index=None,
                center_x=None, center_y=None, confidence=None,
                timestamp_monotonic=min(camera.timestamp_monotonic, audio.timestamp_monotonic),
                message="Camera/audio unavailable or stale",
            )
            return self._latest

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

        if self.config.pan_compensation_enabled and (
            not self.config.pan_geometry_calibrated
            or camera_pan_degrees is None
            or not math.isfinite(camera_pan_degrees)
        ):
            self._latest = replace(
                self._latest, state=ActiveSpeakerState.CALIBRATION_REQUIRED,
                sequence=self._sequence, speaker_id=None, candidate_index=None,
                center_x=None, center_y=None, confidence=None,
                camera_angle_degrees=None, doa_degrees=audio.doa_degrees,
                angular_error_degrees=None,
                timestamp_monotonic=min(camera.timestamp_monotonic, audio.timestamp_monotonic),
                message="Calibrated, settled camera pan estimate required for this frame",
            )
            return self._latest

        doa_signed = self._signed_angle(audio.doa_degrees)
        if self.config.doa_inverted:
            doa_signed = -doa_signed

        if self.config.pan_compensation_enabled:
            assert camera_pan_degrees is not None
            # Audio is chassis-relative; detections are camera-relative.
            doa_signed = self._signed_angle(doa_signed - camera_pan_degrees)

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
            # This is an eligibility gate, not merely a score contribution.
            # Confidence/size/continuity cannot rescue a geometrically invalid match.
            if (
                not math.isfinite(angular_error)
                or angular_error > self.config.max_match_error_degrees
                or not math.isfinite(score)
            ):
                continue
            ranked.append(
                (score, index, person, center_x, center_y, camera_angle, angular_error)
            )

        if not ranked:
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.AMBIGUOUS,
                sequence=self._sequence,
                speaker_id=None,
                confidence=None,
                candidate_index=None,
                center_x=None,
                center_y=None,
                camera_angle_degrees=None,
                doa_degrees=audio.doa_degrees,
                angular_error_degrees=None,
                message="No visible person is within the maximum audio/visual angular error",
            )
            return self._latest

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

        if len(ranked) > 1 and best_score - ranked[1][0] < self.config.candidate_score_margin:
            self._latest = ActiveSpeakerObservation(
                state=ActiveSpeakerState.AMBIGUOUS, sequence=self._sequence,
                speaker_id=None, candidate_index=None, confidence=None,
                center_x=None, center_y=None, camera_angle_degrees=None,
                doa_degrees=audio.doa_degrees, angular_error_degrees=None,
                timestamp_monotonic=min(camera.timestamp_monotonic, audio.timestamp_monotonic),
                message="Visible candidates are too close in score to select a speaker",
            )
            return self._latest

        self._latest = ActiveSpeakerObservation(
            state=ActiveSpeakerState.SPEAKER_SELECTED,
            timestamp_monotonic=min(camera.timestamp_monotonic, audio.timestamp_monotonic),
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
        with self._lock:
            return self._latest

