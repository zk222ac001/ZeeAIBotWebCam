# Phase 10 — Production Telepresence Controls

Phase 10 hardens the Phase 9 WebRTC transport without unlocking robot motion. It adds conference API authentication, ALSA media-device discovery, a read-only operator dashboard, and explicit configuration for future robot-speaker playback.

## Goals

- protect conference signaling/status APIs with an optional Bearer token;
- keep development mode usable with authentication disabled by default;
- keep access tokens outside source control;
- expose ALSA capture and playback device listings;
- make microphone input and speaker output device names explicit configuration;
- keep Raspberry Pi microphone publishing disabled until capture is validated;
- keep remote WebRTC audio playback disabled until the real speaker path is validated;
- provide one read-only operator dashboard for camera, audio, active-speaker, conference, safety, and privacy state;
- expose no motor or servo controls.

## Safe defaults

```yaml
conference:
  mode: mock
  publish_video: true
  publish_audio: false
  allow_remote_audio: true
  remote_audio_playback: false
  audio_input_device: default
  audio_output_device: default
  probe_media_devices: true
  auth_required: false
  access_token: null

safety:
  motion_enabled: false
```

## Production-style authentication

Authentication is intentionally opt-in during local bring-up. For a protected deployment, use environment variables instead of committing a token:

```bash
export CONFERENCE_AUTH_REQUIRED=true
export CONFERENCE_ACCESS_TOKEN='replace-with-a-long-random-secret'
```

Protected endpoints accept:

```text
Authorization: Bearer <token>
```

The token comparison uses a constant-time comparison helper.

## Protected conference endpoints

```text
GET    /api/conference/status
GET    /api/conference/media-devices
GET    /api/operator/status
POST   /api/conference/offer
DELETE /api/conference/sessions/{session_id}
```

The HTML pages remain reachable so an operator can enter the token in the browser, but protected API calls do not return conference state or create sessions without valid credentials when authentication is enabled.

## Media-device probe

```text
GET /api/conference/media-devices
```

On Raspberry Pi this executes read-only device listings equivalent to:

```bash
arecord -l
aplay -l
```

It reports:

- available ALSA capture devices;
- available ALSA playback devices;
- configured conference input device;
- configured conference output device;
- whether Pi microphone publishing is enabled;
- whether remote audio playback is enabled.

The probe does not record or play any audio.

## Operator dashboard

```text
GET /operator
```

The dashboard is read-only and summarizes:

- camera connection and person count;
- ReSpeaker/VAD/DoA state;
- active-speaker fusion state;
- WebRTC session count;
- safety state and motion lock;
- privacy state.

There are deliberately no movement buttons.

## Audio validation sequence

Do not enable conference microphone publishing or remote speaker playback merely because a device appears in `arecord -l` or `aplay -l`.

### 1. Find the actual devices

```bash
arecord -l
aplay -l
```

### 2. Validate microphone capture

Use the exact card/device shown on the Pi, for example:

```bash
arecord -D hw:X,Y -f S16_LE -r 48000 -c 1 -d 5 test-mic.wav
```

Do not copy `X,Y` from this example; use the real values from your hardware.

### 3. Validate speaker playback

After choosing the real playback device:

```bash
aplay -D hw:A,B test-mic.wav
```

Again, `A,B` must come from the Raspberry Pi.

### 4. Enable Pi microphone publishing

Only after a successful capture test:

```bash
export CONFERENCE_PUBLISH_AUDIO=true
export CONFERENCE_AUDIO_INPUT_DEVICE=hw:X,Y
```

### 5. Remote speaker playback remains locked

Phase 10 adds configuration for:

```bash
export CONFERENCE_REMOTE_AUDIO_PLAYBACK=false
export CONFERENCE_AUDIO_OUTPUT_DEVICE=hw:A,B
```

The playback flag remains false by default. Actual remote-track-to-ALSA rendering should only be enabled after the speaker/amplifier path and acoustic echo behavior are verified.

## Why speaker playback remains gated

The project may use either the ReSpeaker playback path or a separate I2S amplifier/speaker. Until the final hardware choice is installed and validated, routing remote browser audio into an arbitrary ALSA device could create feedback, excessive volume, or echo-cancellation problems.

Phase 10 therefore models the output device and reports it, but does not automatically enable remote playback.

## Recommended Raspberry Pi validation

```bash
cd ~/ZeeAIBotWebCam
git pull
source .venv/bin/activate
pip install -e ".[dev,webrtc]"
ruff check src tests
pytest -v
```

Run safely:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=imx500
export AUDIO_MODE=xvf3800_usb
export CONFERENCE_MODE=aiortc
export CONFERENCE_PUBLISH_AUDIO=false
export CONFERENCE_REMOTE_AUDIO_PLAYBACK=false
python -m robotic_classroom.main
```

Then open:

```text
http://localhost:8000/operator
http://localhost:8000/conference
http://localhost:8000/api/conference/media-devices
```

For token-protected testing:

```bash
export CONFERENCE_AUTH_REQUIRED=true
export CONFERENCE_ACCESS_TOKEN='choose-a-long-random-test-token'
python -m robotic_classroom.main
```

Enter the same token into the `/conference` or `/operator` page.

## Safety boundary

Phase 10 does not add a public movement endpoint. The operator UI cannot move motors or servos. `safety.motion_enabled` remains false by default, and the pan/tilt controller remains plan-only.

## Next phase

Phase 11 should focus on **validated full-duplex audio and echo management** after the final microphone/speaker hardware is chosen. Once capture and playback are proven, the remote WebRTC audio track can be rendered through a dedicated playback adapter, and AEC behavior can be measured before any active-speaker-driven physical movement is considered.
