from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from robotic_classroom.conference.media_probe import probe_alsa_devices
from robotic_classroom.conference.models import SessionDescription
from robotic_classroom.conference.security import require_conference_access

router = APIRouter()


class OfferRequest(BaseModel):
    type: str = Field(pattern="^offer$")
    sdp: str = Field(min_length=1)


class OfferResponse(BaseModel):
    session_id: str
    type: str
    sdp: str


def _protect(request: Request) -> None:
    require_conference_access(request, request.app.state.settings.conference)


@router.get("/api/conference/status")
async def conference_status(request: Request) -> dict[str, object]:
    _protect(request)
    status = await request.app.state.conference.status()
    return {
        "backend": status.backend,
        "enabled": status.enabled,
        "running": status.running,
        "active_sessions": status.active_sessions,
        "max_sessions": status.max_sessions,
        "publish_video": status.publish_video,
        "publish_audio": status.publish_audio,
        "auth_required": request.app.state.settings.conference.auth_required,
        "remote_audio_playback": request.app.state.settings.conference.remote_audio_playback,
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


@router.get("/api/conference/media-devices")
def conference_media_devices(request: Request) -> dict[str, object]:
    _protect(request)
    config = request.app.state.settings.conference
    if not config.probe_media_devices:
        return {
            "enabled": False,
            "capture_devices": [],
            "playback_devices": [],
            "message": "Media-device probing disabled",
        }

    probe = probe_alsa_devices()
    return {
        "enabled": True,
        "available": probe.available,
        "capture_devices": probe.capture_devices,
        "playback_devices": probe.playback_devices,
        "configured_input": config.audio_input_device,
        "configured_output": config.audio_output_device,
        "publish_audio": config.publish_audio,
        "remote_audio_playback": config.remote_audio_playback,
        "message": probe.message,
    }


@router.get("/api/operator/status")
async def operator_status(request: Request) -> dict[str, object]:
    _protect(request)
    camera = request.app.state.camera.status()
    audio = request.app.state.audio.observation()
    active = request.app.state.active_speaker.observation()
    conference = await request.app.state.conference.status()
    safety = request.app.state.safety
    settings = request.app.state.settings

    return {
        "camera": {
            "backend": camera.backend,
            "connected": camera.connected,
            "running": camera.running,
            "people_count": camera.people_count,
        },
        "audio": {
            "backend": audio.backend,
            "connected": audio.connected,
            "running": audio.running,
            "speech_state": audio.speech_state.value,
            "doa_degrees": audio.doa_degrees,
        },
        "active_speaker": {
            "state": active.state.value,
            "speaker_id": active.speaker_id,
            "confidence": active.confidence,
        },
        "conference": {
            "backend": conference.backend,
            "running": conference.running,
            "active_sessions": conference.active_sessions,
            "publish_video": conference.publish_video,
            "publish_audio": conference.publish_audio,
            "remote_audio_playback": settings.conference.remote_audio_playback,
        },
        "safety": {
            "state": safety.state.state.value,
            "motion_enabled": settings.safety.motion_enabled,
        },
        "privacy": {
            "recording_enabled": settings.privacy.recording_enabled,
            "face_recognition_enabled": settings.privacy.face_recognition_enabled,
        },
    }


@router.post("/api/conference/offer", response_model=OfferResponse)
async def conference_offer(request: Request, offer: OfferRequest) -> OfferResponse:
    _protect(request)
    try:
        answer = await request.app.state.conference.create_answer(
            SessionDescription(type=offer.type, sdp=offer.sdp)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - transport errors are normalized for the API
        raise HTTPException(status_code=500, detail=f"WebRTC negotiation failed: {exc}") from exc

    return OfferResponse(
        session_id=answer.session_id,
        type=answer.description.type,
        sdp=answer.description.sdp,
    )


@router.delete("/api/conference/sessions/{session_id}")
async def close_conference_session(request: Request, session_id: str) -> dict[str, str]:
    _protect(request)
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
  <title>ZeeAIBotWebCam Conference</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }
    video { width: 100%; max-height: 65vh; background: #111; border-radius: 12px; }
    button, input { margin: .4rem .4rem .4rem 0; padding: .7rem 1rem; }
    input[type=password] { width: min(500px, 90%); }
    pre { background: #f3f3f3; padding: 1rem; white-space: pre-wrap; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>ZeeAIBotWebCam WebRTC</h1>
  <p>Telepresence media only. This page has no robot movement controls.</p>
  <input id="token" type="password" placeholder="Conference access token (if enabled)"><br>
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

function headers() {
  const token = document.getElementById('token').value.trim();
  const result = {'Content-Type': 'application/json'};
  if (token) result.Authorization = `Bearer ${token}`;
  return result;
}

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
      headers: headers(),
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
  if (sessionId) {
    await fetch(`/api/conference/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: headers()
    }).catch(() => {});
  }
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


@router.get("/operator", response_class=HTMLResponse)
def operator_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ZeeAIBotWebCam Operator</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; }
    .card { border: 1px solid #ccc; border-radius: 12px; padding: 1rem; }
    input, button { padding: .7rem; margin: .3rem 0; }
    input { width: min(500px, 90%); }
    pre { white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>ZeeAIBotWebCam Operator Dashboard</h1>
  <p>Read-only operational status. No motor or servo commands are exposed here.</p>
  <input id="token" type="password" placeholder="Conference access token (if enabled)">
  <button id="refresh">Refresh</button>
  <div class="grid">
    <div class="card"><h2>Camera</h2><pre id="camera">-</pre></div>
    <div class="card"><h2>Audio</h2><pre id="audio">-</pre></div>
    <div class="card"><h2>Active Speaker</h2><pre id="speaker">-</pre></div>
    <div class="card"><h2>Conference</h2><pre id="conference">-</pre></div>
    <div class="card"><h2>Safety</h2><pre id="safety">-</pre></div>
    <div class="card"><h2>Privacy</h2><pre id="privacy">-</pre></div>
  </div>
<script>
function authHeaders() {
  const token = document.getElementById('token').value.trim();
  return token ? {Authorization: `Bearer ${token}`} : {};
}
async function refresh() {
  const response = await fetch('/api/operator/status', {headers: authHeaders()});
  if (!response.ok) { alert(await response.text()); return; }
  const data = await response.json();
  for (const key of ['camera','audio','active_speaker','conference','safety','privacy']) {
    const id = key === 'active_speaker' ? 'speaker' : key;
    document.getElementById(id).textContent = JSON.stringify(data[key], null, 2);
  }
}
document.getElementById('refresh').onclick = refresh;
</script>
</body>
</html>"""
