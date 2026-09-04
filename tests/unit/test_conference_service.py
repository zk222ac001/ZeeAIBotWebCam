import pytest

from robotic_classroom.conference.mock import MockConferenceBackend
from robotic_classroom.conference.models import SessionDescription
from robotic_classroom.conference.service import ConferenceService
from robotic_classroom.core.config import ConferenceConfig


@pytest.mark.asyncio
async def test_mock_conference_lifecycle() -> None:
    config = ConferenceConfig(mode="mock", max_sessions=2)
    service = ConferenceService(MockConferenceBackend(config))

    await service.start()
    answer = await service.create_answer(
        SessionDescription(type="offer", sdp="v=0\r\ns=mock offer\r\n")
    )

    assert answer.description.type == "answer"
    assert answer.session_id

    status = await service.status()
    assert status.running is True
    assert status.active_sessions == 1
    assert status.sessions[0].video_published is True
    assert status.sessions[0].audio_published is False

    assert await service.close_session(answer.session_id) is True
    assert (await service.status()).active_sessions == 0

    await service.stop()


@pytest.mark.asyncio
async def test_mock_conference_enforces_session_limit() -> None:
    config = ConferenceConfig(mode="mock", max_sessions=1)
    service = ConferenceService(MockConferenceBackend(config))
    await service.start()

    offer = SessionDescription(type="offer", sdp="v=0\r\ns=mock offer\r\n")
    await service.create_answer(offer)

    with pytest.raises(RuntimeError, match="Maximum conference session count reached"):
        await service.create_answer(offer)

    await service.stop()
