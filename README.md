# ZeeAIBotWebCam

**Affordable AI-Powered Robotic Video Conferencing System Using Raspberry Pi and Python for Hybrid Active Learning Classrooms**

ZeeAIBotWebCam is a production-oriented research and teaching platform built around **Hiwonder TurboPi + Raspberry Pi + Sony IMX500 AI Camera + Python + Edge AI + WebRTC**.

The repository follows a phased engineering process. The current software includes the production hardware boundary, central safety layer, a single-owner Sony IMX500 camera service, and anonymous person tracking. Real chassis movement remains intentionally locked until physical calibration is complete.

## Project status

| Phase | Scope | Status |
|---|---|---|
| Phase 0 | Engineering analysis and architecture | ✅ Documented |
| Phase 1 | Development environment and software foundation | ✅ Implemented |
| Phase 2 | Physical hardware validation | 🧪 Baseline validated; calibration follow-ups remain |
| Phase 3 | TurboPi production hardware adapter + safety supervisor | ✅ Phase 3A/3B implemented |
| Phase 4 | Sony IMX500 AI Camera service + person-detection metadata | ✅ Implemented; real Pi validation required |
| Phase 5 | Person tracking, target selection, smoothing and lost-target handling | ✅ Implemented |
| Phase 6 | Safety-routed pan/tilt tracking requests | ⏳ Next after servo calibration |
| Phase 7+ | ReSpeaker fusion, WebRTC, active-speaker AI, hardening | ⏳ Planned |

## Current validated hardware baseline

The project has already verified enough real hardware to continue software development:

- Raspberry Pi Remote SSH development;
- project runtime on Raspberry Pi;
- Hiwonder UART on `/dev/ttyAMA0`;
- Hiwonder controller communication;
- I2C bus availability;
- ultrasonic sensor discovery;
- Sony IMX500 AI Camera detection and still capture;
- servo power rail around 4.7–4.97 V;
- at least one PWM servo physically moving.

Open Phase 2 calibration items remain:

- identify and calibrate both pan/tilt servo channels;
- map the four IR channels to physical positions;
- validate ReSpeaker XVF3800 capture/DoA path;
- validate speaker output;
- map all four motor IDs and polarity;
- resolve battery telemetry interpretation before chassis movement.

## Core safety rule

> **AI, web, vision and conference modules must never command motors directly.**
>
> All chassis or pan/tilt movement must pass through the central Safety Supervisor and the TurboPi hardware adapter.

The application defaults to:

```yaml
hardware:
  mode: mock
  motor_mapping_validated: false
  pan_tilt:
    enabled: false

camera:
  mode: mock

tracking:
  enabled: true

safety:
  motion_enabled: false
```

So normal application startup cannot drive the robot.

## Current architecture

```mermaid
flowchart LR
    UI[Remote User / Classroom UI] --> API[FastAPI]
    API --> LEASE[Control Lease]
    LEASE --> HEART[Heartbeat / Dead-man]
    HEART --> SAFE[Safety Supervisor]
    SAFE --> ADAPTER[TurboPi Adapter]
    ADAPTER --> SDK[Hiwonder SDK]
    SDK --> HW[Motors / Servos / Sensors]

    CAM[Sony IMX500] --> CBACK[IMX500Camera]
    MOCK[MockCamera] --> CSVC[CameraService]
    CBACK --> CSVC
    CSVC --> META[Anonymous Person Detections]
    META --> TRACK[PersonTracker]
    TRACK --> SMOOTH[Smoothing + Lost Target]
    SMOOTH --> ERROR[Normalized X/Y Error]
    ERROR --> TAPI[/api/tracking/status]
    ERROR -. future movement request only .-> SAFE

    MIC[ReSpeaker XVF3800] --> AUDIO[Future Audio / VAD / DoA]
```

## Repository layout

```text
ZeeAIBotWebCam/
├── config.yaml
├── pyproject.toml
├── src/robotic_classroom/
│   ├── camera/
│   ├── core/
│   ├── control/
│   ├── hardware/
│   ├── safety/
│   ├── tracking/
│   └── web/
├── tests/
├── scripts/
├── vendor/
└── docs/
```

## Phase documentation

- [`docs/phase-00-engineering-analysis.md`](docs/phase-00-engineering-analysis.md)
- [`docs/phase-01-development-environment.md`](docs/phase-01-development-environment.md)
- [`docs/phase-02-hardware-validation.md`](docs/phase-02-hardware-validation.md)
- [`docs/phase-03-hardware-adapter-safety.md`](docs/phase-03-hardware-adapter-safety.md)
- [`docs/phase-04-imx500-camera-service.md`](docs/phase-04-imx500-camera-service.md)
- [`docs/phase-05-person-tracking.md`](docs/phase-05-person-tracking.md)
- [`docs/hardware-api-inventory.md`](docs/hardware-api-inventory.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/safety.md`](docs/safety.md)

## Pull latest code on Raspberry Pi

```bash
cd ~/ZeeAIBotWebCam
git pull
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -v
```

## Run Phase 5 in fully mocked mode

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=mock
export TRACKING_ENABLED=true
python -m robotic_classroom.main
```

Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/api/camera/status`
- `http://127.0.0.1:8000/api/camera/detections`
- `http://127.0.0.1:8000/api/tracking/status`
- `http://127.0.0.1:8000/api/sensors`
- `http://127.0.0.1:8000/api/safety`
- `http://127.0.0.1:8000/docs`

## Test the real Sony IMX500 while robot movement remains mocked

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=imx500
export TRACKING_ENABLED=true
python -m robotic_classroom.main
```

With VS Code Remote SSH, forward port `8000` and open:

```text
http://localhost:8000/api/camera/status
http://localhost:8000/api/camera/detections
http://localhost:8000/api/tracking/status
http://localhost:8000/api/camera/frame.jpg
```

Stand in different parts of the camera frame and watch the tracking response. The tracker exposes an anonymous temporary target such as `Person-01`, normalized target centre, X/Y error from image centre, dead-zone state, and lost-target state. No face recognition or biometric identity is used.

## Safe API surface

```text
GET  /health
GET  /ready
GET  /api/sensors
GET  /api/safety
GET  /api/camera/status
GET  /api/camera/detections
GET  /api/camera/frame.jpg
GET  /api/tracking/status
POST /api/control/lease
POST /api/control/heartbeat
POST /api/control/emergency-stop
POST /api/control/reset-stop
```

There is deliberately **no public movement endpoint** yet.

## Upstream hardware and camera software

Hiwonder TurboPi:

https://github.com/Hiwonder/TurboPi

Raspberry Pi Picamera2 / IMX500 support:

https://github.com/raspberrypi/picamera2

The project keeps vendor-specific behavior behind adapters and services rather than allowing application modules to open hardware directly.

## Privacy baseline

The design defaults to:

- no face recognition;
- no biometric identity database;
- no recording;
- no cloud upload of raw classroom video by default;
- anonymous on-device person detection;
- temporary tracking labels such as `Person-01` only;
- future camera/microphone/conference indicators.

## Next phase

**Phase 6** will convert Phase 5 image-space errors into bounded pan/tilt *requests* routed through the Safety Supervisor. It will not be enabled on real hardware until both servo channels, direction, centre positions, and mechanical limits have been calibrated.
