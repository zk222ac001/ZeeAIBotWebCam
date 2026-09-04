# Phase 5 — Person Tracking and Target Selection

Phase 5 builds on the anonymous `person` detections produced by the Sony IMX500 camera service. It selects one person to follow, keeps continuity across frames, smooths image-space target motion, calculates tracking error relative to the image centre, and handles temporary target loss.

## Safety boundary

Phase 5 performs **tracking math only**.

It does not import or call:

```python
board.set_motor_duty(...)
board.pwm_servo_set_position(...)
```

It also does not bypass the Phase 3 Safety Supervisor. The output of Phase 5 is only a tracking observation that future phases may convert into a *movement request*.

## Architecture

```mermaid
flowchart LR
    IMX[IMX500] --> CAM[CameraService]
    CAM --> DET[Anonymous person detections]
    DET --> TRACK[PersonTracker]
    TRACK --> SMOOTH[Temporal smoothing]
    SMOOTH --> ERR[Image centre error]
    ERR --> API[/api/tracking/status]
    ERR -. future request only .-> SAFE[Safety Supervisor]
    SAFE -. later .-> PT[Pan / Tilt]
```

## Anonymous target identity

The tracker uses temporary session-local identifiers such as:

```text
Person-01
Person-02
```

These are not face identities, names, biometric identifiers, or persistent records. They exist only to help the software maintain continuity while a person is visible.

## Target acquisition

When no target is currently active, detections are scored using three configurable factors:

- closeness to the image centre;
- detection confidence;
- bounding-box size.

Default weights:

```yaml
tracking:
  center_weight: 0.45
  confidence_weight: 0.35
  size_weight: 0.20
```

The goal is to favour a visible, confident, prominent person near the current classroom camera view without identifying who that person is.

## Continuity and reacquisition

Once a target has been acquired, the tracker prefers a detection close to the previous target centre rather than immediately switching to another high-confidence person.

```yaml
tracking:
  reacquire_distance_ratio: 0.30
```

The value is expressed as a normalized image-space distance.

## Temporal smoothing

Person detections can jitter from frame to frame. The tracker therefore uses exponential smoothing:

```text
smoothed = alpha * measured + (1 - alpha) * previous
```

Default:

```yaml
tracking:
  smoothing_alpha: 0.35
```

A lower value produces steadier but slower tracking. A higher value reacts faster but can look more nervous.

## Tracking error

The target centre is normalized to the range `0.0 .. 1.0`.

The image centre is:

```text
x = 0.5
y = 0.5
```

The tracker publishes:

```text
error_x = target_center_x - 0.5
error_y = target_center_y - 0.5
```

Interpretation:

```text
error_x < 0  -> target is left of centre
error_x > 0  -> target is right of centre
error_y < 0  -> target is above centre
error_y > 0  -> target is below centre
```

No actuator direction is assumed yet. Servo inversion and mechanical direction remain calibration parameters for a later phase.

## Dead zone

Small tracking errors should not cause constant servo corrections. Phase 5 therefore defines an image-space dead zone:

```yaml
tracking:
  dead_zone_x: 0.08
  dead_zone_y: 0.10
```

When both absolute errors are within those limits, `in_dead_zone` becomes `true`.

## Lost-target behaviour

A target that disappears briefly is not immediately discarded.

```yaml
tracking:
  lost_target_timeout_ms: 1200
```

State transitions are:

```text
SEARCHING
   |
   v
TRACKING
   |
   | no detection
   v
LOST
   |
   | target returns before timeout
   +------> TRACKING
   |
   | timeout expires
   v
SEARCHING
```

This reduces rapid target switching caused by momentary detector misses or partial occlusion.

## Configuration

```yaml
tracking:
  enabled: true
  poll_interval_ms: 50
  smoothing_alpha: 0.35
  lost_target_timeout_ms: 1200
  reacquire_distance_ratio: 0.30
  dead_zone_x: 0.08
  dead_zone_y: 0.10
  center_weight: 0.45
  confidence_weight: 0.35
  size_weight: 0.20
```

## API

```text
GET /api/tracking/status
```

Example while tracking:

```json
{
  "state": "tracking",
  "sequence": 203,
  "target_id": "Person-01",
  "confidence": 0.92,
  "center": {
    "x": 0.63,
    "y": 0.47
  },
  "error": {
    "x": 0.13,
    "y": -0.03
  },
  "in_dead_zone": false,
  "message": "Tracking target in image space"
}
```

Example when target is centered:

```json
{
  "state": "tracking",
  "target_id": "Person-01",
  "in_dead_zone": true,
  "message": "Target centered"
}
```

## Raspberry Pi validation

Pull and test:

```bash
cd ~/ZeeAIBotWebCam
git pull
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -v
```

Test the tracker first with the mock camera:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=mock
python -m robotic_classroom.main
```

Open:

```text
http://localhost:8000/api/tracking/status
```

Then isolate the real Sony IMX500 while keeping robot hardware mocked:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=imx500
python -m robotic_classroom.main
```

Stand in different parts of the camera frame and observe `center`, `error`, and `in_dead_zone`.

No motor or servo should move during Phase 5.

## Definition of done

Phase 5 is complete when:

- person detections can produce an anonymous target;
- target continuity survives normal small frame-to-frame movement;
- position smoothing reduces detector jitter;
- normalized X/Y errors are exposed;
- dead-zone state is exposed;
- a temporarily lost target enters `lost` before returning to `searching`;
- no biometric identity is created;
- no vision code directly commands actuators;
- motion remains disabled by default.

The next phase can safely convert image-space tracking error into **pan/tilt movement requests** routed through the Safety Supervisor, but only after the physical servo channels and mechanical limits are fully calibrated.
