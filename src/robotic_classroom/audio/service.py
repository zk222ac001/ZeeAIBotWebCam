from __future__ import annotations

import math
import threading
import time

from robotic_classroom.audio.interface import AudioBackend
from robotic_classroom.audio.models import AudioObservation, SpeechState
from robotic_classroom.core.config import AudioConfig


class AudioService:
    """Single-owner VAD/DoA service for the ReSpeaker metadata path."""

    def __init__(self, backend: AudioBackend, config: AudioConfig) -> None:
        self.backend = backend
        self.config = config
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._last_speech_monotonic: float | None = None
        self._smoothed_degrees: float | None = None
        self._latest = AudioObservation(
            backend=config.mode,
            connected=False,
            running=False,
            sequence=0,
            speech_state=SpeechState.UNAVAILABLE,
            speech_active=False,
            doa_degrees_raw=None,
            doa_degrees=None,
            orientation_calibrated=config.orientation_calibrated,
            message="Audio service not started",
        )

    @staticmethod
    def _normalize_degrees(value: float) -> float:
        return value % 360.0

    @staticmethod
    def _blend_angle(previous: float, measured: float, alpha: float) -> float:
        prev_rad = math.radians(previous)
        measured_rad = math.radians(measured)
        x = (1.0 - alpha) * math.cos(prev_rad) + alpha * math.cos(measured_rad)
        y = (1.0 - alpha) * math.sin(prev_rad) + alpha * math.sin(measured_rad)
        return math.degrees(math.atan2(y, x)) % 360.0

    def start(self) -> None:
        if not self.config.enabled:
            with self._lock:
                self._latest = AudioObservation(
                    backend=self.config.mode,
                    connected=False,
                    running=False,
                    sequence=0,
                    speech_state=SpeechState.UNAVAILABLE,
                    speech_active=False,
                    doa_degrees_raw=None,
                    doa_degrees=None,
                    orientation_calibrated=self.config.orientation_calibrated,
                    message="Audio service disabled",
                )
            return

        self.backend.start()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="audio-metadata")
        self._thread.start()

    def _run(self) -> None:
        interval = self.config.poll_interval_ms / 1000.0
        hangover_s = self.config.vad_hangover_ms / 1000.0

        while not self._stop_event.is_set():
            try:
                raw = self.backend.observation()
                now = time.monotonic()

                if raw.speech_active:
                    self._last_speech_monotonic = now

                within_hangover = (
                    self._last_speech_monotonic is not None
                    and now - self._last_speech_monotonic <= hangover_s
                )
                speech_active = raw.speech_active or within_hangover
                if raw.speech_active:
                    speech_state = SpeechState.SPEAKING
                elif within_hangover:
                    speech_state = SpeechState.HANGOVER
                else:
                    speech_state = SpeechState.SILENT

                doa_raw = raw.doa_degrees_raw
                doa = None
                if doa_raw is not None:
                    calibrated = self._normalize_degrees(
                        doa_raw + self.config.orientation_offset_degrees
                    )
                    if self._smoothed_degrees is None:
                        self._smoothed_degrees = calibrated
                    else:
                        self._smoothed_degrees = self._blend_angle(
                            self._smoothed_degrees,
                            calibrated,
                            self.config.doa_smoothing_alpha,
                        )
                    doa = self._smoothed_degrees

                latest = AudioObservation(
                    backend=raw.backend,
                    connected=raw.connected,
                    running=True,
                    sequence=raw.sequence,
                    speech_state=speech_state,
                    speech_active=speech_active,
                    doa_degrees_raw=doa_raw,
                    doa_degrees=doa,
                    orientation_calibrated=self.config.orientation_calibrated,
                    firmware_version=raw.firmware_version,
                    message=raw.message,
                )
            except Exception as exc:
                latest = AudioObservation(
                    backend=self.config.mode,
                    connected=False,
                    running=True,
                    sequence=self._latest.sequence,
                    speech_state=SpeechState.UNAVAILABLE,
                    speech_active=False,
                    doa_degrees_raw=None,
                    doa_degrees=None,
                    orientation_calibrated=self.config.orientation_calibrated,
                    firmware_version=self._latest.firmware_version,
                    message=f"Audio metadata error: {exc}",
                )

            with self._lock:
                self._latest = latest

            self._stop_event.wait(interval)

    def observation(self) -> AudioObservation:
        with self._lock:
            return self._latest

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self.backend.stop()
