from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from robotic_classroom.conference.models import SessionDescription

router = APIRouter()


class OfferRequest(BaseModel):
    type: str = Field(pattern="^offer$")
    sdp: str = Field(min_length=1)


class OfferResponse(BaseModel):
    session_id: str
    type: str
    sdp: str


@router.get("/api/conference/status")
async def conference_status(request: Request) -> dict[str, object]:
    status = await request.app.state.conference.status()
    return {
        "backend": status.backend,
        "enabled": status.enabled,
        "running": status.running,
        "active_sessions": status.active_sessions,
        "max_sessions": status.max_sessions,
        "publish_video": status.publish_video,
        "publish_audio": status.publish_audio,
        "message": request.app.state.conference_start_error or status.message,
        "sessions": [
            {
                "session_id": session.session_id,
                "state": session.state.value,
                "connection_state": session.connection_state,
                "ice_connection_state": session.ice_connection_state,
                "video_published": session.video_published,
                "audio_published": session.audio_published,
                "remote_audio_allowed": session.remote_audio_allowed,
                "message": session.message,
            }
            for session in status.sessions
        ],
    }


@router.post("/api/conference/offer", response_model=OfferResponse)
async def conference_offer(request: Request, offer: OfferRequest) -> OfferResponse:
    try:
        answer = await request.app.state.conference.create_answer(
            SessionDescription(type=offer.type, sdp=offer.sdp)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"WebRTC negotiation failed: {exc}") from exc

    return OfferResponse(
        session_id=answer.session_id,
        type=answer.description.type,
        sdp=answer.description.sdp,
    )


@router.delete("/api/conference/sessions/{session_id}")
async def close_conference_session(request: Request, session_id: str) -> dict[str, str]:
    closed = await request.app.state.conference.close_session(session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Conference session not found")
    return {"status": "closed", "session_id": session_id}


@router.get("/conference", response_class=HTMLResponse)
def conference_test_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ZeeAIBotWebCam Conference Test</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
    video { width: 100%; max-height: 65vh; background: #111; border-radius: 12px; }
    button { margin: .5rem .5rem .5rem 0; padding: .7rem 1rem; }
    pre { background: #f3f3f3; padding: 1rem; white-space: pre-wrap; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>ZeeAIBotWebCam WebRTC Test</h1>
  <p>This page tests telepresence media only. It has no robot movement controls.</p>
  <label><input id="sendMic" type="checkbox"> Send browser microphone to the Pi</label><br>
  <button id="connect">Connect</button>
  <button id="disconnect" disabled>Disconnect</button>
  <video id="remoteVideo" autoplay playsinline controls></video>
  <pre id="status">idle</pre>
<script>
let pc = null;
let sessionId = null;
let localStream = null;
const statusEl = document.getElementById('status');
const videoEl = document.getElementById('remoteVideo');
const connectBtn = document.getElementById('connect');
const disconnectBtn = document.getElementById('disconnect');

function updateStatus(extra='') {
  if (!pc) { statusEl.textContent = extra || 'idle'; return; }
  statusEl.textContent = `connection=${pc.connectionState}\nice=${pc.iceConnectionState}\ngathering=${pc.iceGatheringState}\n${extra}`;
}

async function waitForIceGatheringComplete(peer) {
  if (peer.iceGatheringState === 'complete') return;
  await new Promise(resolve => {
    const check = () => {
      if (peer.iceGatheringState === 'complete') {
        peer.removeEventListener('icegatheringstatechange', check);
        resolve();
      }
    };
    peer.addEventListener('icegatheringstatechange', check);
    setTimeout(resolve, 5000);
  });
}

connectBtn.onclick = async () => {
  connectBtn.disabled = true;
  try {
    pc = new RTCPeerConnection();
    pc.addTransceiver('video', {direction: 'recvonly'});
    pc.ontrack = event => {
      if (event.track.kind === 'video') videoEl.srcObject = event.streams[0] || new MediaStream([event.track]);
    };
    pc.onconnectionstatechange = () => updateStatus();
    pc.oniceconnectionstatechange = () => updateStatus();

    if (document.getElementById('sendMic').checked) {
      localStream = await navigator.mediaDevices.getUserMedia({audio: true, video: false});
      for (const track of localStream.getAudioTracks()) pc.addTrack(track, localStream);
    }

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    await waitForIceGatheringComplete(pc);

    const response = await fetch('/api/conference/offer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type: pc.localDescription.type, sdp: pc.localDescription.sdp})
    });
    if (!response.ok) throw new Error(await response.text());
    const answer = await response.json();
    sessionId = answer.session_id;
    await pc.setRemoteDescription({type: answer.type, sdp: answer.sdp});
    disconnectBtn.disabled = false;
    updateStatus(`session=${sessionId}`);
  } catch (error) {
    updateStatus(`error=${error}`);
    connectBtn.disabled = false;
  }
};

disconnectBtn.onclick = async () => {
  if (sessionId) await fetch(`/api/conference/sessions/${sessionId}`, {method: 'DELETE'}).catch(() => {});
  if (localStream) for (const track of localStream.getTracks()) track.stop();
  if (pc) pc.close();
  pc = null;
  sessionId = null;
  localStream = null;
  videoEl.srcObject = null;
  connectBtn.disabled = false;
  disconnectBtn.disabled = true;
  updateStatus('closed');
};
</script>
</body>
</html>"""
