from __future__ import annotations

import array
import asyncio
import os
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
    echo_reference_enabled: bool
    echo_reference_device: str
    echo_reference_running: bool
    echo_reference_frames_written: int
    echo_reference_last_error: str
    echo_reference_validated: bool


def mono_s16le_to_reference_stereo(payload: bytes) -> bytes:
    """Map mono S16_LE PCM to XVF3800 reference stereo: left=signal, right=silence."""
    mono = array.array("h")
    mono.frombytes(payload)
    if os.sys.byteorder != "little":
        mono.byteswap()

    stereo = array.array("h")
    for sample in mono:
        stereo.append(sample)
        stereo.append(0)

    if os.sys.byteorder != "little":
        stereo.byteswap()
    return stereo.tobytes()


class RemoteAudioPlayback:
    """Render one incoming WebRTC audio track through ALSA using ``aplay``.

    The room-speaker path is always the primary output. When the explicitly gated
    echo-reference mirror is enabled, the same mono PCM is also sent to the
    XVF3800 USB playback input as stereo with left=signal and right=silence.
    """

    def __init__(self, config: ConferenceConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._reference_process: subprocess.Popen[bytes] | None = None
        self._frames_written = 0
        self._reference_frames_written = 0
        self._last_error = ""
        self._reference_last_error = ""

    @property
    def active(self) -> bool:
        return bool(self.config.remote_audio_playback and self.config.audio_output_validated)

    @property
    def reference_active(self) -> bool:
        return bool(self.active and self.config.echo_reference_enabled)

    def status(self) -> AudioPlaybackStatus:
        running = self._process is not None and self._process.poll() is None
        reference_running = (
            self._reference_process is not None and self._reference_process.poll() is None
        )
        return AudioPlaybackStatus(
            enabled=self.config.remote_audio_playback,
            validated=self.config.audio_output_validated,
            device=self.config.audio_output_device,
            running=running,
            frames_written=self._frames_written,
            last_error=self._last_error,
            echo_management_mode=self.config.echo_management_mode,
            echo_reference_enabled=self.config.echo_reference_enabled,
            echo_reference_device=self.config.echo_reference_device,
            echo_reference_running=reference_running,
            echo_reference_frames_written=self._reference_frames_written,
            echo_reference_last_error=self._reference_last_error,
            echo_reference_validated=self.config.echo_reference_validated,
        )

    def _aplay_process(self, *, device: str, channels: int) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                "aplay",
                "-q",
                "-D",
                device,
                "-f",
                "S16_LE",
                "-c",
                str(channels),
                "-r",
                str(self.config.remote_audio_sample_rate),
                "-t",
                "raw",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def _start_process(self) -> None:
        if not self.active:
            raise RuntimeError("Remote audio playback is not validated and enabled")
        if self._process is None or self._process.poll() is not None:
            self._process = self._aplay_process(
                device=self.config.audio_output_device,
                channels=self.config.remote_audio_channels,
            )

        if self.reference_active and (
            self._reference_process is None or self._reference_process.poll() is not None
        ):
            try:
                self._reference_process = self._aplay_process(
                    device=self.config.echo_reference_device,
                    channels=2,
                )
            except Exception as exc:  # noqa: BLE001 - reference is separately gated
                self._reference_last_error = str(exc)
                self._reference_process = None
                if self.config.echo_management_mode == "aec_reference":
                    raise RuntimeError(f"AEC reference playback failed to start: {exc}") from exc

    @staticmethod
    def _write_payload(process: subprocess.Popen[bytes], payload: bytes) -> None:
        if process.stdin is None:
            raise RuntimeError("aplay stdin is unavailable")
        if process.poll() is not None:
            raise RuntimeError(f"aplay exited with status {process.returncode}")
        process.stdin.write(payload)
        process.stdin.flush()

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

        try:
            while True:
                frame = await track.recv()
                converted = resampler.resample(frame)
                for output in converted:
                    # PyAV planes may include alignment padding beyond the audio samples.
                    sample_bytes = output.samples * len(output.layout.channels) * 2
                    payload = bytes(output.planes[0])[:sample_bytes]
                    if self._reference_process is None:
                        await asyncio.to_thread(self._write_payload, self._process, payload)
                        self._frames_written += 1
                        continue

                    reference_payload = mono_s16le_to_reference_stereo(payload)
                    speaker_result, reference_result = await asyncio.gather(
                        asyncio.to_thread(self._write_payload, self._process, payload),
                        asyncio.to_thread(
                            self._write_payload,
                            self._reference_process,
                            reference_payload,
                        ),
                        return_exceptions=True,
                    )
                    if isinstance(speaker_result, BaseException):
                        raise speaker_result
                    self._frames_written += 1

                    if isinstance(reference_result, BaseException):
                        self._reference_last_error = str(reference_result)
                        self._stop_reference_process()
                        if self.config.echo_management_mode == "aec_reference":
                            raise RuntimeError(
                                f"AEC reference playback failed: {reference_result}"
                            ) from reference_result
                    else:
                        self._reference_frames_written += 1
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

    @staticmethod
    def _stop_aplay(process: subprocess.Popen[bytes] | None) -> None:
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

    def _stop_reference_process(self) -> None:
        process = self._reference_process
        self._reference_process = None
        self._stop_aplay(process)

    def stop(self) -> None:
        process = self._process
        self._process = None
        reference_process = self._reference_process
        self._reference_process = None
        self._stop_aplay(reference_process)
        self._stop_aplay(process)
