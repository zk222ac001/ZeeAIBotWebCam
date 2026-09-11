from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from robotic_classroom.camera.service import CameraService
from robotic_classroom.core.config import TrackingConfig
from robotic_classroom.fusion.models import ActiveSpeakerState
from robotic_classroom.tracking.models import TrackingObservation, TrackingState
from robotic_classroom.tracking.tracker import PersonTracker

if TYPE_CHECKING:
    from robotic_classroom.fusion.service import ActiveSpeakerService


class TrackingService:
    """Background image-space tracking service.

    The normal visual tracker remains the fallback. When an active-speaker
    service is attached and has a validated SPEAKER_SELECTED observation, the
    published tracking observation is temporarily sourced from that speaker's
    image-space center instead. Brief fusion/VAD dropouts hold the last active
    speaker target instead of immediately switching to another visual target.
    The service still has no actuator dependency; pan/tilt remains downstream
    and chassis motion is unaffected.
    """

    ACTIVE_SPEAKER_HOLD_SECONDS = 0.8

    def __init__(self, camera: CameraService, config: TrackingConfig) -> None:
        self.camera = camera
        self.config = config
        self.tracker = PersonTracker(config)
        self._active_speaker: ActiveSpeakerService | None = None
        self._last_active_observation: TrackingObservation | None = None
        self._last_active_monotonic: float | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    def set_active_speaker(self, service: ActiveSpeakerService | None) -> None:
        """Attach or clear the optional active-speaker target source."""
        with self._lock:
            self._active_speaker = service
            if service is None:
                self._last_active_observation = None
                self._last_active_monotonic = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="person-tracking",
            )
            self._thread.start()

    def _run(self) -> None:
        interval = self.config.poll_interval_ms / 1000.0
        while not self._stop_event.is_set():
            snapshot = self.camera.snapshot()
            self.tracker.update(snapshot)
            self._stop_event.wait(interval)

    def _active_speaker_observation(self) -> TrackingObservation | None:
        with self._lock:
            service = self._active_speaker

        if service is None:
            return None

        speaker = service.observation()
        now = time.monotonic()

        if (
            speaker.state is ActiveSpeakerState.SPEAKER_SELECTED
            and speaker.center_x is not None
            and speaker.center_y is not None
        ):
            error_x = speaker.center_x - 0.5
            error_y = speaker.center_y - 0.5
            in_dead_zone = (
                abs(error_x) <= self.config.dead_zone_x
                and abs(error_y) <= self.config.dead_zone_y
            )

            observation = TrackingObservation(
                state=TrackingState.TRACKING,
                sequence=speaker.sequence,
                target_id=speaker.speaker_id or "ActiveSpeaker",
                confidence=speaker.confidence,
                center_x=speaker.center_x,
                center_y=speaker.center_y,
                error_x=error_x,
                error_y=error_y,
                in_dead_zone=in_dead_zone,
                message=(
                    "Active speaker centered"
                    if in_dead_zone
                    else "Tracking selected active speaker"
                ),
            )
            with self._lock:
                self._last_active_observation = observation
                self._last_active_monotonic = now
            return observation

        with self._lock:
            last = self._last_active_observation
            last_time = self._last_active_monotonic

        if (
            last is not None
            and last_time is not None
            and now - last_time <= self.ACTIVE_SPEAKER_HOLD_SECONDS
        ):
            return TrackingObservation(
                state=TrackingState.LOST,
                sequence=speaker.sequence,
                target_id=last.target_id,
                confidence=last.confidence,
                center_x=last.center_x,
                center_y=last.center_y,
                error_x=None,
                error_y=None,
                in_dead_zone=False,
                message="Active speaker briefly unavailable; holding last speaker target",
            )

        with self._lock:
            self._last_active_observation = None
            self._last_active_monotonic = None
        return None

    def observation(self) -> TrackingObservation:
        active = self._active_speaker_observation()
        if active is not None:
            return active
        return self.tracker.observation

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
