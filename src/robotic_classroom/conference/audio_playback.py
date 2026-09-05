from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from typing import Any

from robotic_classroom.core.config import ConferenceConfig


@dataclass(frozen=True, slots=True)
class AudioPlaybackStatus:
    enabled: bool
    validated: bool
    device: str
    running: bool
    frames_written: int
    last_error: str
    echo_management_mode: str
    echo_reference_validated: bool


class RemoteAudioPlayback:
    """Render one incoming WebRTC audio track through ALSA using ``aplay``.

    The adapter is intentionally gated by configuration. It never starts a playback
    process unless both remote-audio playback and output validation are enabled.
    """

    def __init__(self, config: ConferenceConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._frames_written = 0
        self._last_error = ""

    @property
    def active(self) -> bool:
        return bool(self.config.remote_audio_playback and self.config.audio_output_validated)

    def status(self) -> AudioPlaybackStatus:
        running = self._process is not None and self._process.poll() is None
        return AudioPlaybackStatus(
            enabled=self.config.remote_audio_playback,
            validated=self.config.audio_output_validated,
            device=self.config.audio_output_device,
            running=running,
            frames_written=self._frames_written,
            last_error=self._last_error,
            echo_management_mode=self.config.echo_management_mode,
            echo_reference_validated=self.config.echo_reference_validated,
        )

    def _start_process(self) -> None:
        if not self.active:
            raise RuntimeError("Remote audio playback is not validated and enabled")
        if self._process is not None and self._process.poll() is None:
            return

        channels = str(self.config.remote_audio_channels)
        rate = str(self.config.remote_audio_sample_rate)
        self._process = subprocess.Popen(  # noqa: S603 - fixed executable and controlled arguments
            [
                "aplay",
                "-q",
                "-D",
                self.config.audio_output_device,
                "-f",
                "S16_LE",
                "-c",
                channels,
                "-r",
                rate,
                "-t",
                "raw",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    async def render(self, track: Any) -> None:
        if not self.active:
            await self.drain(track)
            return

        from av.audio.resampler import AudioResampler

        layout = "mono" if self.config.remote_audio_channels == 1 else "stereo"
        resampler = AudioResampler(
            format="s16",
            layout=layout,
            rate=self.config.remote_audio_sample_rate,
        )

        self._start_process()
        assert self._process is not None
        assert self._process.stdin is not None

        try:
            while True:
                frame = await track.recv()
                converted = resampler.resample(frame)
                for output in converted:
                    payload = bytes(output.planes[0])
                    await asyncio.to_thread(self._process.stdin.write, payload)
                    await asyncio.to_thread(self._process.stdin.flush)
                    self._frames_written += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport/device errors are isolated per session
            self._last_error = str(exc)
        finally:
            self.stop()

    async def drain(self, track: Any) -> None:
        try:
            while True:
                await track.recv()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - peer track shutdown may raise transport-specific errors
            return

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
