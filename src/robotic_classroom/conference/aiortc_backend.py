from __future__ import annotations

import asyncio
from dataclasses import dataclass
from fractions import Fraction
from time import monotonic
from typing import Any
from uuid import uuid4

from robotic_classroom.camera.service import CameraService
from robotic_classroom.conference.audio_playback import RemoteAudioPlayback
from robotic_classroom.conference.models import (
    ConferenceAnswer,
    ConferenceSession,
    ConferenceState,
    ConferenceStatus,
    SessionDescription,
)
from robotic_classroom.core.config import ConferenceConfig


@dataclass(slots=True)
class _RuntimeSession:
    session_id: str
    peer_connection: Any
    created_monotonic: float
    last_activity_monotonic: float
    media_player: Any | None = None
    remote_tasks: list[asyncio.Task[None]] | None = None
    playback: RemoteAudioPlayback | None = None


class AiortcConferenceBackend:
    """Optional real WebRTC backend using shared camera and validated ALSA audio."""

    def __init__(
        self,
        config: ConferenceConfig,
        camera: CameraService,
        *,
        frame_rate: int,
    ) -> None:
        self.config = config
        self.camera = camera
        self.frame_rate = max(1, frame_rate)
        self._running = False
        self._sessions: dict[str, _RuntimeSession] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if not self.config.enabled:
            self._running = False
            return
        try:
            import aiortc  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                'Conference mode "aiortc" requires the optional WebRTC dependencies. '
                'Install with: pip install -e ".[webrtc]"'
            ) from exc

        if self.config.publish_audio and not self.config.audio_input_validated:
            raise RuntimeError(
                "Pi microphone publishing is enabled but the configured ALSA input is not validated"
            )
        if self.config.remote_audio_playback and not self.config.audio_output_validated:
            raise RuntimeError(
                "Remote speaker playback is enabled but the configured ALSA output is not validated"
            )
        if (
            self.config.echo_management_mode == "aec_reference"
            and not self.config.echo_reference_validated
        ):
            raise RuntimeError(
                "AEC reference mode is enabled but the echo-reference path is not validated"
            )

        self._running = True

    def _rtc_configuration(self) -> Any:
        from aiortc import RTCConfiguration, RTCIceServer

        servers = []
        for url in self.config.ice_servers:
            servers.append(
                RTCIceServer(
                    urls=url,
                    username=self.config.ice_username,
                    credential=self.config.ice_credential,
                )
            )
        return RTCConfiguration(iceServers=servers)

    def _video_track(self) -> Any:
        import cv2
        import numpy as np
        from aiortc import VideoStreamTrack
        from av import VideoFrame

        camera = self.camera
        frame_rate = self.frame_rate

        class CameraServiceVideoTrack(VideoStreamTrack):
            def __init__(self) -> None:
                super().__init__()
                self._next_frame_at = monotonic()
                self._pts = 0
                self._time_base = Fraction(1, 90000)

            async def recv(self) -> VideoFrame:
                interval = 1.0 / frame_rate
                now = monotonic()
                delay = self._next_frame_at - now
                if delay > 0:
                    await asyncio.sleep(delay)
                self._next_frame_at = max(self._next_frame_at + interval, monotonic())

                jpeg = camera.jpeg()
                if jpeg is None:
                    raise RuntimeError("CameraService has no JPEG frame available")

                encoded = np.frombuffer(jpeg, dtype=np.uint8)
                bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                if bgr is None:
                    raise RuntimeError("Unable to decode CameraService JPEG frame")
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                frame = VideoFrame.from_ndarray(rgb, format="rgb24")
                self._pts += int(90000 / frame_rate)
                frame.pts = self._pts
                frame.time_base = self._time_base
                return frame

        return CameraServiceVideoTrack()

    async def _wait_for_ice_complete(self, pc: Any) -> None:
        deadline = monotonic() + self.config.ice_gathering_timeout_seconds
        while pc.iceGatheringState != "complete" and monotonic() < deadline:
            await asyncio.sleep(0.05)

    async def create_answer(self, offer: SessionDescription) -> ConferenceAnswer:
        if not self._running:
            raise RuntimeError("Conference backend is not running")
        if offer.type != "offer" or not offer.sdp.strip():
            raise ValueError("A non-empty SDP offer is required")

        from aiortc import RTCPeerConnection, RTCSessionDescription
        from aiortc.contrib.media import MediaPlayer

        async with self._lock:
            if len(self._sessions) >= self.config.max_sessions:
                raise RuntimeError("Maximum conference session count reached")

        pc = RTCPeerConnection(configuration=self._rtc_configuration())
        session_id = uuid4().hex
        now = monotonic()
        runtime = _RuntimeSession(
            session_id=session_id,
            peer_connection=pc,
            created_monotonic=now,
            last_activity_monotonic=now,
            remote_tasks=[],
        )

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            runtime.last_activity_monotonic = monotonic()
            if pc.connectionState in {"failed", "closed"}:
                await self.close_session(session_id)

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange() -> None:
            runtime.last_activity_monotonic = monotonic()

        @pc.on("track")
        def on_track(track: Any) -> None:
            runtime.last_activity_monotonic = monotonic()
            if track.kind != "audio" or not self.config.allow_remote_audio:
                return

            assert runtime.remote_tasks is not None
            playback = RemoteAudioPlayback(self.config)
            runtime.playback = playback
            if playback.active:
                task = asyncio.create_task(playback.render(track))
            else:
                task = asyncio.create_task(playback.drain(track))
            runtime.remote_tasks.append(task)

        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer.sdp, type=offer.type))

            if self.config.publish_video:
                pc.addTrack(self._video_track())

            if self.config.publish_audio:
                player = MediaPlayer(self.config.audio_input_device, format="alsa")
                runtime.media_player = player
                if player.audio is None:
                    raise RuntimeError(
                        f"ALSA device {self.config.audio_input_device!r} did not expose an audio track"
                    )
                pc.addTrack(player.audio)

            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await self._wait_for_ice_complete(pc)

            async with self._lock:
                self._sessions[session_id] = runtime

            local = pc.localDescription
            if local is None:
                raise RuntimeError("WebRTC local description was not created")

            return ConferenceAnswer(
                session_id=session_id,
                description=SessionDescription(type=local.type, sdp=local.sdp),
            )
        except Exception:
            if runtime.playback is not None:
                runtime.playback.stop()
            await pc.close()
            runtime.media_player = None
            raise

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            runtime = self._sessions.pop(session_id, None)
        if runtime is None:
            return False

        if runtime.remote_tasks:
            for task in runtime.remote_tasks:
                task.cancel()
            await asyncio.gather(*runtime.remote_tasks, return_exceptions=True)
        if runtime.playback is not None:
            runtime.playback.stop()
        await runtime.peer_connection.close()
        runtime.media_player = None
        return True

    async def _cleanup_stale(self) -> None:
        now = monotonic()
        timeout = float(self.config.session_timeout_seconds)
        async with self._lock:
            stale = [
                session_id
                for session_id, runtime in self._sessions.items()
                if now - runtime.last_activity_monotonic > timeout
            ]
        for session_id in stale:
            await self.close_session(session_id)

    async def status(self) -> ConferenceStatus:
        await self._cleanup_stale()
        async with self._lock:
            sessions = tuple(self._session_model(runtime) for runtime in self._sessions.values())

        return ConferenceStatus(
            backend="aiortc",
            enabled=self.config.enabled,
            running=self._running,
            active_sessions=len(sessions),
            max_sessions=self.config.max_sessions,
            publish_video=self.config.publish_video,
            publish_audio=self.config.publish_audio,
            sessions=sessions,
            message="aiortc WebRTC conference backend",
        )

    def audio_pipeline_status(self) -> dict[str, object]:
        playback_running = False
        playback_frames = 0
        playback_error = ""
        for runtime in self._sessions.values():
            if runtime.playback is None:
                continue
            status = runtime.playback.status()
            playback_running = playback_running or status.running
            playback_frames += status.frames_written
            playback_error = playback_error or status.last_error

        return {
            "microphone_publish_enabled": self.config.publish_audio,
            "microphone_input_validated": self.config.audio_input_validated,
            "microphone_device": self.config.audio_input_device,
            "remote_audio_allowed": self.config.allow_remote_audio,
            "speaker_playback_enabled": self.config.remote_audio_playback,
            "speaker_output_validated": self.config.audio_output_validated,
            "speaker_device": self.config.audio_output_device,
            "speaker_playback_running": playback_running,
            "speaker_frames_written": playback_frames,
            "speaker_last_error": playback_error,
            "echo_management_mode": self.config.echo_management_mode,
            "echo_reference_validated": self.config.echo_reference_validated,
            "full_duplex_requested": bool(
                self.config.publish_audio and self.config.remote_audio_playback
            ),
            "full_duplex_validated": bool(
                self.config.audio_input_validated
                and self.config.audio_output_validated
                and (
                    self.config.echo_management_mode != "aec_reference"
                    or self.config.echo_reference_validated
                )
            ),
        }

    def _session_model(self, runtime: _RuntimeSession) -> ConferenceSession:
        pc = runtime.peer_connection
        connection_state = pc.connectionState
        if connection_state == "connected":
            state = ConferenceState.CONNECTED
        elif connection_state in {"failed", "closed"}:
            state = ConferenceState.FAILED if connection_state == "failed" else ConferenceState.CLOSED
        else:
            state = ConferenceState.NEGOTIATING

        return ConferenceSession(
            session_id=runtime.session_id,
            state=state,
            connection_state=connection_state,
            ice_connection_state=pc.iceConnectionState,
            video_published=self.config.publish_video,
            audio_published=self.config.publish_audio,
            remote_audio_allowed=self.config.allow_remote_audio,
            created_monotonic=runtime.created_monotonic,
            last_activity_monotonic=runtime.last_activity_monotonic,
            message="WebRTC peer session",
        )

    async def stop(self) -> None:
        async with self._lock:
            session_ids = list(self._sessions)
        for session_id in session_ids:
            await self.close_session(session_id)
        self._running = False
