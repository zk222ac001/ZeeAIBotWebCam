from __future__ import annotations

import math
import time

from robotic_classroom.camera.models import CameraSnapshot, PersonDetection
from robotic_classroom.core.config import TrackingConfig
from robotic_classroom.tracking.models import TrackingObservation, TrackingState


class PersonTracker:
    """Anonymous single-target tracker over camera person detections.

    This class performs only target selection and image-space tracking math.
    It never imports hardware or safety modules and therefore cannot move the robot.
    """

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config
        self._target_id: str | None = None
        self._target_counter = 0
        self._center_x: float | None = None
        self._center_y: float | None = None
        self._last_seen_monotonic: float | None = None
        self._last_sequence = -1
        self._last_observation = TrackingObservation(
            state=TrackingState.SEARCHING if config.enabled else TrackingState.DISABLED,
            sequence=0,
            target_id=None,
            confidence=None,
            center_x=None,
            center_y=None,
            error_x=None,
            error_y=None,
            in_dead_zone=False,
            message="Waiting for person detections" if config.enabled else "Tracking disabled",
        )

    @staticmethod
    def _detection_center(person: PersonDetection, width: int, height: int) -> tuple[float, float]:
        cx = (person.box.x + person.box.width / 2.0) / max(width, 1)
        cy = (person.box.y + person.box.height / 2.0) / max(height, 1)
        return cx, cy

    def _acquisition_score(self, person: PersonDetection, width: int, height: int) -> float:
        cx, cy = self._detection_center(person, width, height)
        center_distance = min(math.hypot(cx - 0.5, cy - 0.5) / math.hypot(0.5, 0.5), 1.0)
        centered = 1.0 - center_distance
        area_ratio = min((person.box.width * person.box.height) / max(width * height, 1), 1.0)

        total_weight = (
            self.config.center_weight
            + self.config.confidence_weight
            + self.config.size_weight
        )
        return (
            centered * self.config.center_weight
            + person.confidence * self.config.confidence_weight
            + area_ratio * self.config.size_weight
        ) / total_weight

    def _select_detection(self, snapshot: CameraSnapshot) -> PersonDetection | None:
        if not snapshot.people:
            return None

        if self._center_x is not None and self._center_y is not None:
            candidates: list[tuple[float, PersonDetection]] = []
            for person in snapshot.people:
                cx, cy = self._detection_center(person, snapshot.frame_width, snapshot.frame_height)
                distance = math.hypot(cx - self._center_x, cy - self._center_y)
                if distance <= self.config.reacquire_distance_ratio:
                    candidates.append((distance, person))
            if candidates:
                candidates.sort(key=lambda item: item[0])
                return candidates[0][1]

        return max(
            snapshot.people,
            key=lambda person: self._acquisition_score(
                person, snapshot.frame_width, snapshot.frame_height
            ),
        )

    def _new_target_id(self) -> str:
        self._target_counter += 1
        return f"Person-{self._target_counter:02d}"

    def update(self, snapshot: CameraSnapshot, now: float | None = None) -> TrackingObservation:
        if not self.config.enabled:
            self._last_observation = TrackingObservation(
                state=TrackingState.DISABLED,
                sequence=snapshot.sequence,
                target_id=None,
                confidence=None,
                center_x=None,
                center_y=None,
                error_x=None,
                error_y=None,
                in_dead_zone=False,
                message="Tracking disabled",
            )
            return self._last_observation

        if snapshot.sequence == self._last_sequence:
            return self._last_observation
        self._last_sequence = snapshot.sequence

        current_time = time.monotonic() if now is None else now
        selected = self._select_detection(snapshot)

        if selected is None:
            timeout_s = self.config.lost_target_timeout_ms / 1000.0
            if (
                self._target_id is not None
                and self._last_seen_monotonic is not None
                and current_time - self._last_seen_monotonic <= timeout_s
            ):
                state = TrackingState.LOST
                message = "Target temporarily lost; holding anonymous target identity"
            else:
                self._target_id = None
                self._center_x = None
                self._center_y = None
                state = TrackingState.SEARCHING
                message = "Searching for a person"

            self._last_observation = TrackingObservation(
                state=state,
                sequence=snapshot.sequence,
                target_id=self._target_id,
                confidence=None,
                center_x=self._center_x,
                center_y=self._center_y,
                error_x=None,
                error_y=None,
                in_dead_zone=False,
                message=message,
            )
            return self._last_observation

        measured_x, measured_y = self._detection_center(
            selected, snapshot.frame_width, snapshot.frame_height
        )

        if self._target_id is None:
            self._target_id = self._new_target_id()
            self._center_x = measured_x
            self._center_y = measured_y
        else:
            alpha = self.config.smoothing_alpha
            assert self._center_x is not None and self._center_y is not None
            self._center_x = alpha * measured_x + (1.0 - alpha) * self._center_x
            self._center_y = alpha * measured_y + (1.0 - alpha) * self._center_y

        self._last_seen_monotonic = current_time
        error_x = self._center_x - 0.5
        error_y = self._center_y - 0.5
        in_dead_zone = (
            abs(error_x) <= self.config.dead_zone_x
            and abs(error_y) <= self.config.dead_zone_y
        )

        self._last_observation = TrackingObservation(
            state=TrackingState.TRACKING,
            sequence=snapshot.sequence,
            target_id=self._target_id,
            confidence=selected.confidence,
            center_x=self._center_x,
            center_y=self._center_y,
            error_x=error_x,
            error_y=error_y,
            in_dead_zone=in_dead_zone,
            message="Target centered" if in_dead_zone else "Tracking target in image space",
        )
        return self._last_observation

    @property
    def observation(self) -> TrackingObservation:
        return self._last_observation
