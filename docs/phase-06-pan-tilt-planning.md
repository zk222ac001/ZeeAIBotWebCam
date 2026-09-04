# Phase 6 — Pan/Tilt Tracking Controller (Plan-Only)

Phase 6 converts Phase 5 image-space tracking error into bounded, rate-limited servo pulse requests. It is intentionally implemented in **plan-only mode** because the physical pan/tilt channels are not fully calibrated yet.

## Goals

- consume `TrackingObservation` from Phase 5;
- convert horizontal and vertical image error into desired pan/tilt pulse requests;
- use configured servo centres, limits and inversion;
- clamp every desired pulse to its calibrated minimum/maximum;
- slew-limit each update to avoid large jumps;
- hold position while a target is temporarily lost;
- expose the planned request through the API;
- never write PWM to the physical servo in this phase.

## Architecture

```mermaid
flowchart LR
    CAM[IMX500 Camera] --> TRACK[PersonTracker]
    TRACK --> ERR[error_x / error_y]
    ERR --> PLAN[PanTiltController]
    PLAN --> LIMIT[Clamp + Inversion + Slew Limit]
    LIMIT --> API[/api/pan-tilt/plan]
    API --> REVIEW[Calibration / Validation]
    REVIEW -. future only .-> SAFE[Safety Supervisor]
    SAFE -. future only .-> ADAPTER[TurboPi Adapter]
    ADAPTER -. future only .-> SERVO[Pan/Tilt Servos]
```

## Important safety boundary

`PanTiltController` and `PanTiltPlanningService` have no hardware dependency. Their output always contains:

```json
"apply_to_hardware": false
```

The controller does not import the Hiwonder SDK and contains no call to `pwm_servo_set_position`.

## Planning math

Tracking error is normalized around the image centre:

```text
error_x < 0  -> target left of centre
error_x > 0  -> target right of centre
error_y < 0  -> target above centre
error_y > 0  -> target below centre
```

For each axis:

```text
desired_pulse = centre + signed_error * gain_us
```

If an axis is configured as inverted, the sign is reversed first.

The desired pulse is then clamped to the configured range. The planned pulse approaches it by no more than `max_step_us` per planning cycle.

## Default configuration

```yaml
pan_tilt_control:
  enabled: true
  mode: plan_only
  poll_interval_ms: 50
  pan_gain_us: 400.0
  tilt_gain_us: 300.0
  max_step_us: 15
  hold_on_lost_target: true
```

Physical axis calibration remains separately configured under:

```yaml
hardware:
  pan_tilt:
    enabled: false
    pan:
      channel: null
      center: 1500
      minimum: 1300
      maximum: 1700
      inverted: false
    tilt:
      channel: null
      center: 1500
      minimum: 1300
      maximum: 1700
      inverted: false
```

The `channel` values intentionally remain `null` until both physical servos are identified.

## API

```text
GET /api/pan-tilt/plan
```

Example response:

```json
{
  "state": "tracking",
  "sequence": 42,
  "target_id": "Person-01",
  "mode": "plan_only",
  "apply_to_hardware": false,
  "pan": {
    "desired_pulse": 1580,
    "planned_pulse": 1530,
    "minimum": 1300,
    "center": 1500,
    "maximum": 1700,
    "inverted": false
  },
  "tilt": {
    "desired_pulse": 1470,
    "planned_pulse": 1470,
    "minimum": 1300,
    "center": 1500,
    "maximum": 1700,
    "inverted": false
  },
  "message": "Generated bounded pan/tilt tracking request"
}
```

## Validation procedure

On Raspberry Pi:

```bash
cd ~/ZeeAIBotWebCam
git pull
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -v
```

Run fully mocked first:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=mock
export TRACKING_ENABLED=true
export PAN_TILT_CONTROL_ENABLED=true
python -m robotic_classroom.main
```

Open:

```text
http://localhost:8000/api/tracking/status
http://localhost:8000/api/pan-tilt/plan
```

Then test with the real IMX500 while keeping hardware motion mocked:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=imx500
export TRACKING_ENABLED=true
export PAN_TILT_CONTROL_ENABLED=true
python -m robotic_classroom.main
```

Move left/right/up/down in front of the camera and compare `/api/tracking/status` with `/api/pan-tilt/plan`. The planned pulses should change smoothly but remain inside the configured ranges.

## Definition of done

Phase 6 is complete when:

- unit tests prove clamping, inversion and slew limiting;
- the API always reports `apply_to_hardware: false`;
- real IMX500 movement changes the planned pulse values in the expected direction;
- no actuator API is called;
- both physical servo channels remain uncommitted until calibration.

The next phase can introduce a guarded pan/tilt actuator executor only after both physical channels, directions, centres and safe limits are measured and recorded.
