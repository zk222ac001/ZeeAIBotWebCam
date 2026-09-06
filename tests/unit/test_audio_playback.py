import asyncio
from io import BytesIO
from unittest.mock import Mock

import pytest

from robotic_classroom.conference.audio_playback import RemoteAudioPlayback
from robotic_classroom.core.config import ConferenceConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("channels", [1, 2])
async def test_playback_excludes_resampler_padding(monkeypatch, channels):
    av = pytest.importorskip("av")
    frame = av.AudioFrame(format="s16", layout="stereo", samples=960)
    frame.sample_rate = 48000
    for plane in frame.planes:
        plane.update(bytes(plane.buffer_size))

    class Track:
        sent = False

        async def recv(self):
            if self.sent:
                raise asyncio.CancelledError
            self.sent = True
            return frame

    sink = BytesIO()
    process = Mock(stdin=sink)
    process.poll.return_value = None
    monkeypatch.setattr(
        "robotic_classroom.conference.audio_playback.subprocess.Popen",
        Mock(return_value=process),
    )
    playback = RemoteAudioPlayback(ConferenceConfig(
        remote_audio_playback=True,
        audio_output_validated=True,
        remote_audio_channels=channels,
    ))
    captured = []

    def stop():
        captured.append(sink.getvalue())

    monkeypatch.setattr(playback, "stop", stop)
    with pytest.raises(asyncio.CancelledError):
        await playback.render(Track())

    assert captured == [bytes(960 * channels * 2)]
    assert playback.status().frames_written == 1
