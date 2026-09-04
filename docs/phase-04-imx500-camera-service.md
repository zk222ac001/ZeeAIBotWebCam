# Phase 4 — Sony IMX500 Camera Service and Person Detection

Phase 4 converts the already validated Raspberry Pi AI Camera into a production application service. The camera is now treated as a single-owned resource: only the camera backend may instantiate Picamera2/IMX500. Vision, WebRTC, dashboards and future tracking code consume shared snapshots from `CameraService`.

## Goals

- one camera owner;
- mock camera support for Windows and CI;
- real IMX500 backend on Raspberry Pi;
- continuous frame capture;
- JPEG frame publication for diagnostics;
- person-detection metadata;
- no direct movement from vision code;
- camera failure does not silently crash the application;
- recording and face recognition remain disabled by default.

## Architecture

```mermaid
flowchart LR
    IMX[IMX500 Hardware] --> BACKEND[IMX500Camera]
    MOCK[MockCamera] --> FACTORY[Camera Factory]
    BACKEND --> SERVICE[CameraService]
    FACTORY --> SERVICE
    SERVICE --> FRAME[/api/camera/frame.jpg]
    SERVICE --> META[/api/camera/detections]
    SERVICE --> STATUS[/api/camera/status]
    SERVICE --> FUTURE[Future Tracking / WebRTC]
    FUTURE -. movement request only .-> SAFE[Safety Supervisor]
```

## Single-owner rule

Application modules must not instantiate `Picamera2` themselves. Future consumers obtain frame/detection state only through `CameraService`.

This prevents:

- multiple processes fighting over the CSI camera;
- duplicated inference pipelines;
- inconsistent frame timestamps;
- WebRTC and vision code owning separate camera devices.

## Configuration

Default configuration remains hardware-safe and CI-friendly:

```yaml
camera:
  enabled: true
  mode: mock
  required: false
  model_path: /usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk
  width: 1280
  height: 720
  frame_rate: 20
  confidence_threshold: 0.55
  jpeg_quality: 80
  person_label: person
```

To run the real AI Camera on Raspberry Pi:

```yaml
camera:
  mode: imx500
```

`required: false` means a camera startup failure is surfaced in `/health` and `/api/camera/status`, but does not prevent the safety/hardware API from starting. Production deployments may later set it to `true`.

## IMX500 implementation

The backend follows the Raspberry Pi Picamera2 IMX500 flow:

1. instantiate `IMX500(model_path)` before Picamera2;
2. create `Picamera2(imx500.camera_num)`;
3. start the configured video stream;
4. acquire completed requests;
5. read request metadata;
6. call `imx500.get_outputs(metadata, add_batch=True)`;
7. extract boxes, scores and classes;
8. convert inference coordinates with `convert_inference_coords`;
9. keep only detections whose label is `person` and confidence exceeds the configured threshold;
10. encode the current frame as JPEG for diagnostic consumers.

The real Picamera2/IMX500/OpenCV imports are lazy, so mock mode works on Windows and GitHub Actions without Raspberry Pi packages.

## API

### Camera status

```text
GET /api/camera/status
```

Example:

```json
{
  "backend": "imx500",
  "connected": true,
  "running": true,
  "sequence": 132,
  "people_count": 2,
  "message": "IMX500 camera running"
}
```

### Detection metadata

```text
GET /api/camera/detections
```

Example:

```json
{
  "backend": "imx500",
  "connected": true,
  "sequence": 132,
  "frame": {"width": 1280, "height": 720},
  "people": [
    {
      "label": "person",
      "confidence": 0.91,
      "box": {"x": 320, "y": 110, "width": 240, "height": 520}
    }
  ]
}
```

No identity or face recognition is performed. The detections represent anonymous people only.

### Latest frame

```text
GET /api/camera/frame.jpg
```

The endpoint returns the latest shared JPEG from the single camera owner. It is intended for development/diagnostic viewing, not as the final conference media path. WebRTC will consume the camera service in a later phase.

## Raspberry Pi test procedure

Update the repository:

```bash
cd ~/ZeeAIBotWebCam
git pull
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

Confirm the packaged model exists:

```bash
ls -lh /usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk
```

Set real camera mode in `config.yaml` or temporarily:

```bash
export CAMERA_MODE=imx500
```

Keep chassis motion disabled:

```bash
export HARDWARE_MODE=mock
python -m robotic_classroom.main
```

Using hardware mock mode while camera mode is IMX500 is intentional for the first Phase 4 test. It isolates camera validation from motors and other hardware.

With VS Code port 8000 forwarded, open:

```text
http://localhost:8000/api/camera/status
http://localhost:8000/api/camera/detections
http://localhost:8000/api/camera/frame.jpg
http://localhost:8000/docs
```

Stand in front of the camera and refresh `/api/camera/detections`. The `people` list should become non-empty when the model detects a person above the threshold.

## Safety boundary

Phase 4 does not contain any call to:

```python
board.set_motor_duty(...)
board.pwm_servo_set_position(...)
```

Camera detections are metadata only. Future tracking code may create a pan/tilt or chassis *request*, but only the Safety Supervisor is allowed to authorize movement.

## Definition of done

Phase 4 is considered complete when:

- mock camera tests pass in CI;
- real IMX500 starts through `CameraService`;
- `/api/camera/status` reports healthy operation;
- `/api/camera/frame.jpg` produces a current image;
- `/api/camera/detections` reports person detections;
- only one Picamera2 owner exists;
- vision code has no direct actuator access;
- real chassis motion remains disabled.

After that, Phase 5 will add person selection/tracking logic, smoothing, lost-target handling and tracking requests without bypassing the Safety Supervisor.
