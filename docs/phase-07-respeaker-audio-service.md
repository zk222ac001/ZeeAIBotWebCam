# Phase 7 — ReSpeaker XVF3800 Audio Metadata Service

Phase 7 adds a single-owned ReSpeaker XVF3800 service for voice activity detection (VAD) and direction of arrival (DoA). It intentionally does not use audio to move the robot yet.

## Goals

- keep XVF3800 USB control behind one application service;
- expose VAD state and DoA metadata through FastAPI;
- support mock mode in Windows and CI;
- use circular smoothing for 0/360 degree wrap-around;
- add short VAD hangover to avoid rapid speech on/off flicker;
- keep microphone-array orientation configurable and explicitly uncalibrated by default;
- validate ALSA capture-device visibility separately from USB control metadata;
- keep all actuator paths disabled.

## Architecture

```mermaid
flowchart LR
    MIC[ReSpeaker XVF3800] --> USB[USB vendor control]
    USB --> BACKEND[XVF3800USBBackend]
    MOCK[MockAudioBackend] --> SERVICE[AudioService]
    BACKEND --> SERVICE
    SERVICE --> VAD[VAD state]
    SERVICE --> DOA[Smoothed DoA]
    VAD --> API[/api/audio/status]
    DOA --> API
    API --> FUTURE[Future active-speaker fusion]
    FUTURE -. no direct motion .-> SAFE[Safety Supervisor]
```

## Official USB metadata protocol

The implementation follows Seeed Studio's documented Python protocol for the USB firmware:

- USB VID: `0x2886`
- USB PID: `0x001A`
- `DOA_VALUE`: resource ID 20, command ID 18, 4-byte payload
- response payload: two little-endian unsigned 16-bit words
  - word 0: DoA angle, 0–359 degrees
  - word 1: VAD flag, 1 = speech, 0 = silence

The project performs read-only vendor-control transfers. It does not change LED modes, firmware settings or saved device configuration.

Seeed reference:

https://wiki.seeedstudio.com/respeaker_xvf3800_python_sdk/

## Configuration

```yaml
audio:
  enabled: true
  mode: mock
  required: false
  vendor_id: 10374
  product_id: 26
  poll_interval_ms: 100
  doa_smoothing_alpha: 0.35
  vad_hangover_ms: 350
  orientation_offset_degrees: 0.0
  orientation_calibrated: false
```

`10374` and `26` are the decimal forms of `0x2886` and `0x001A`.

For the real device:

```bash
export AUDIO_MODE=xvf3800_usb
```

## Why orientation is not considered calibrated yet

The XVF3800 reports an angle relative to its own physical coordinate system. The final robot requires a known relationship between:

- 0° reported by the microphone array;
- the front of the robot;
- the camera's image centre;
- pan-servo positive direction.

Until that relationship is physically measured, the API exposes:

```json
"orientation_calibrated": false
```

The `orientation_offset_degrees` setting exists so the measured offset can later be applied without changing code.

## Smoothing

Ordinary numeric averaging fails around the wrap point. For example, averaging 359° and 1° arithmetically gives 180°, which is wrong.

`AudioService` therefore smooths angles as vectors on the unit circle before converting the result back to 0–359°.

## VAD hangover

The raw DSP VAD flag can change quickly between speech frames. Phase 7 applies a short configurable hangover:

```text
raw VAD = 1
    ↓
SPEAKING
    ↓
raw VAD becomes 0
    ↓
HANGOVER for up to 350 ms
    ↓
SILENT
```

This will be useful when Phase 8 combines audio evidence with camera detections.

## API

```text
GET /api/audio/status
```

Example:

```json
{
  "backend": "xvf3800_usb",
  "connected": true,
  "running": true,
  "sequence": 143,
  "speech_state": "speaking",
  "speech_active": true,
  "doa_degrees_raw": 72.0,
  "doa_degrees": 69.4,
  "orientation_calibrated": false,
  "firmware_version": "2.0.10",
  "message": "XVF3800 VAD/DoA metadata available"
}
```

## Raspberry Pi validation

Update the repository:

```bash
cd ~/ZeeAIBotWebCam
git pull
source .venv/bin/activate
pip install -e ".[dev]"
```

First confirm USB enumeration:

```bash
lsusb
```

Look for a device with:

```text
2886:001a
```

Then check ALSA capture devices:

```bash
arecord -l
```

Run the Phase 7 diagnostic:

```bash
python scripts/phase7_audio_check.py
```

Speak from different sides of the microphone array. The output should show changing values similar to:

```text
seq=001 speech=0 doa=42.0 firmware=2.0.10
seq=002 speech=1 doa=75.0 firmware=2.0.10
seq=003 speech=1 doa=82.0 firmware=2.0.10
```

## USB permissions

It is possible for `lsusb` to show `2886:001a` while PyUSB vendor-control reads fail because the current user does not have permission to access the control interface.

If that occurs, configure a udev rule for VID/PID `2886:001a`, reload udev, and reconnect the ReSpeaker. Do not run the entire production application as root as a permanent workaround.

## Application test

Keep all robot hardware mocked while testing the real microphone metadata:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=mock
export AUDIO_MODE=xvf3800_usb
python -m robotic_classroom.main
```

Then open:

```text
http://localhost:8000/api/audio/status
```

This isolates the microphone-array validation from motors, servos and camera inference.

## ALSA audio capture

Phase 7 verifies that an ALSA capture device is visible, but the application does not yet stream PCM into the conference stack. Raw microphone capture, echo cancellation integration and WebRTC audio transport will be added in a later telepresence phase.

## Safety boundary

The audio package does not import the Hiwonder board, motor API or servo API. VAD and DoA are metadata only.

Future audio/vision fusion may select an active-speaker target, but any resulting movement request must still pass through the Safety Supervisor.

## Definition of done

Phase 7 software is complete when:

- mock audio tests pass;
- `/api/audio/status` works in mock mode;
- the Raspberry Pi detects `2886:001a`;
- PyUSB can read firmware version and `DOA_VALUE`;
- VAD changes when someone speaks;
- DoA changes when the sound source moves;
- `arecord -l` shows the capture device;
- array orientation is physically measured and recorded before audio-driven tracking is enabled.

After this, Phase 8 will fuse anonymous vision tracking with VAD/DoA to choose the likely active speaker without using face recognition.
