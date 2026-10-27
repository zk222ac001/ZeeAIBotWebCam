"""Exercise exclusive audio ownership without opening ALSA or a camera."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from robotic_classroom.conference.aiortc_backend import AiortcConferenceBackend
from robotic_classroom.conference.models import SessionDescription
from robotic_classroom.core.config import ConferenceConfig


@pytest.fixture
def conference(monkeypatch):
    state = SimpleNamespace(players=[], peers=[], capture_open=False, fail_answer=False)

    class Track:
        def __init__(self, stop=None):
            self.stops = 0
            self.on_stop = stop

        def stop(self):
            self.stops += 1
            if self.on_stop:
                self.on_stop()

    class Player:
        def __init__(self, *args, **kwargs):
            if state.capture_open:
                raise OSError("exclusive microphone already open")
            state.capture_open = True
            self.audio = Track(lambda: setattr(state, "capture_open", False))
            self.video = None
            state.players.append(self)

    class Relay:
        def subscribe(self, source, buffered=True):
            assert buffered is False
            return Track()

    class Peer:
        def __init__(self, **kwargs):
            self.connectionState = "new"
            self.iceConnectionState = "new"
            self.iceGatheringState = "complete"
            self.callbacks = {}
            self.tracks = []
            state.peers.append(self)

        def on(self, name):
            def register(callback):
                self.callbacks[name] = callback
                return callback
            return register

        async def setRemoteDescription(self, description):
            pass

        def addTrack(self, track):
            self.tracks.append(track)

        async def createAnswer(self):
            await asyncio.sleep(0)
            if state.fail_answer:
                raise RuntimeError("injected negotiation failure")
            return SimpleNamespace(type="answer", sdp="v=0")

        async def setLocalDescription(self, description):
            self.localDescription = description

        async def close(self):
            self.connectionState = "closed"
            await self.callbacks["connectionstatechange"]()

    rtc = ModuleType("aiortc")
    rtc.RTCPeerConnection = Peer
    rtc.RTCSessionDescription = lambda **kwargs: SimpleNamespace(**kwargs)
    media = ModuleType("aiortc.contrib.media")
    media.MediaPlayer = Player
    media.MediaRelay = Relay
    monkeypatch.setitem(sys.modules, "aiortc", rtc)
    monkeypatch.setitem(sys.modules, "aiortc.contrib.media", media)
    backend = AiortcConferenceBackend(ConferenceConfig(
        publish_audio=True, audio_input_validated=True, max_sessions=2),
        None, frame_rate=20)
    monkeypatch.setattr(backend, "_rtc_configuration", lambda: None)
    monkeypatch.setattr(backend, "_video_track", Track)
    return backend, state


OFFER = SessionDescription(type="offer", sdp="v=0")


@pytest.mark.asyncio
async def test_two_sessions_share_capture_and_last_close_releases_it(conference):
    backend, state = conference
    await backend.start()
    first = await backend.create_answer(OFFER)
    second = await backend.create_answer(OFFER)
    assert len(state.players) == 1
    assert await backend.close_session(first.session_id)
    assert state.capture_open
    assert state.players[0].audio.stops == 0
    assert await backend.close_session(second.session_id)
    assert not state.capture_open
    assert state.players[0].audio.stops == 1
    # A fresh call can reopen the exclusive device after complete disconnect.
    await backend.create_answer(OFFER)
    assert len(state.players) == 2
    await backend.stop()
    assert not state.capture_open


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_session", [False, True])
async def test_failed_offer_releases_only_its_microphone_subscription(conference, existing_session):
    backend, state = conference
    await backend.start()
    if existing_session:
        await backend.create_answer(OFFER)
    state.fail_answer = True
    with pytest.raises(RuntimeError, match="injected negotiation failure"):
        await backend.create_answer(OFFER)
    assert state.capture_open is existing_session
    assert len(backend._microphone_tracks) == int(existing_session)
    assert (await backend.status()).active_sessions == int(existing_session)
    state.fail_answer = False
    await backend.create_answer(OFFER)
    await backend.stop()
    assert not state.capture_open


@pytest.mark.asyncio
async def test_cancelled_negotiation_closes_capture(conference, monkeypatch):
    backend, state = conference
    await backend.start()
    waiting = asyncio.Event()

    async def wait_for_ice(peer):
        waiting.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(backend, "_wait_for_ice_complete", wait_for_ice)
    task = asyncio.create_task(backend.create_answer(OFFER))
    await asyncio.wait_for(waiting.wait(), timeout=1)
    assert state.capture_open
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not state.capture_open
    assert not backend._microphone_tracks
    assert (await backend.status()).active_sessions == 0


@pytest.mark.asyncio
async def test_concurrent_offers_obey_session_capacity(conference):
    backend, state = conference
    backend.config.max_sessions = 1
    await backend.start()
    answers = await asyncio.gather(
        backend.create_answer(OFFER), backend.create_answer(OFFER), return_exceptions=True)
    assert sum(isinstance(answer, RuntimeError) for answer in answers) == 1
    assert (await backend.status()).active_sessions == 1
    assert len(state.players) == 1
    await backend.stop()
    assert not state.capture_open
