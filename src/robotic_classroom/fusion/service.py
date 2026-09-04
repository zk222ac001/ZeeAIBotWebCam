from __future__ import annotations

import threading

from robotic_classroom.audio.service import AudioService
from robotic_classroom.camera.service import CameraService
from robotic_classroom.core.config import ActiveSpeakerConfig
from robotic_classroom.fusion.active_speaker import ActiveSpeakerFusion
from robotic_classroom.fusion.models import ActiveSpeakerObservation


class ActiveSpeakerService:
    """Background vision/audio fusion service with no actuator dependency."""

    def __init__(
        self,
        camera: CameraService,
        audio: AudioService,
        config: ActiveSpeakerConfig,
    ) -> None:
        self.camera = camera
        self.audio = audio
        self.config = config
        self.fusion = ActiveSpeakerFusion(config)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="active-speaker-fusion",
        )
        self._thread.start()

    def _run(self) -> None:
        interval = self.config.poll_interval_ms / 1000.0
        while not self._stop_event.is_set():
            self.fusion.update(
                self.camera.snapshot(),
                self.audio.observation(),
            )
            self._stop_event.wait(interval)

    def observation(self) -> ActiveSpeakerObservation:
        return self.fusion.observation

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
