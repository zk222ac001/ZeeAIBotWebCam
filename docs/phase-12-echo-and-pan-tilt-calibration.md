# Phase 12 — Echo Validation and Safe Physical Pan/Tilt Calibration

Phase 12 prepares the first real camera-servo movement without unlocking chassis motion.

## Safety goals

Physical pan/tilt execution is permitted only when all three gates are true:

```text
PAN_TILT_CONTROL_MODE=execute
PAN_TILT_HARDWARE_ENABLED=true
PAN_TILT_CALIBRATION_VALIDATED=true
```

If any gate is false, tracking remains plan-only.

Chassis motion remains locked independently.

## Servo calibration sequence

The TurboPi SDK supports PWM servo channels 1 through 4. Phase 12 therefore extends the guarded calibration script to test all four channels.

Power off before moving servo plugs. Confirm signal, 5 V and ground orientation before applying power.

Start at the neutral pulse:

```bash
python scripts/phase2_actuator_test.py servo --id 1 --pulse 1500 --confirm-motion
python scripts/phase2_actuator_test.py servo --id 2 --pulse 1500 --confirm-motion
python scripts/phase2_actuator_test.py servo --id 3 --pulse 1500 --confirm-motion
python scripts/phase2_actuator_test.py servo --id 4 --pulse 1500 --confirm-motion
```

Record which channel moves which axis.

For a responding channel, test only narrow offsets first:

```bash
python scripts/phase2_actuator_test.py servo --id X --pulse 1450 --confirm-motion
python scripts/phase2_actuator_test.py servo --id X --pulse 1550 --confirm-motion
python scripts/phase2_actuator_test.py servo --id X --pulse 1500 --confirm-motion
```

Observe whether the axis moves left/right or up/down and whether the direction must be inverted.

Do not increase the range until camera ribbon clearance and mechanical stops are visually confirmed.

## Calibration fields

After physical validation, configure the actual values:

```yaml
hardware:
  pan_tilt:
    enabled: true
    calibration_validated: true
    pan:
      channel: 1
      center: 1500
      minimum: 1400
      maximum: 1600
      inverted: false
    tilt:
      channel: 2
      center: 1500
      minimum: 1400
      maximum: 1600
      inverted: true
```

The example channel numbers and pulse ranges above are placeholders. Use only values measured on the real robot.

## Runtime execution gate

The new `PanTiltExecutor` receives bounded plans from the existing planner. It cannot execute unless configuration requests `execute`, hardware pan/tilt is enabled, and calibration is marked validated.

The status endpoint remains:

```text
GET /api/pan-tilt/plan
```

It now reports whether execution was requested, whether calibration is validated, the latest physical pulse values, and any hardware error.

## Echo validation

Keep audio in monitor mode during physical calibration:

```bash
export CONFERENCE_ECHO_MANAGEMENT_MODE=monitor
export CONFERENCE_ECHO_REFERENCE_VALIDATED=false
```

During a full-duplex WebRTC call, check whether sound from the robot speaker re-enters the ReSpeaker microphones and returns to the remote participant. Also observe VAD and DoA while the robot speaker is playing.

Do not claim AEC validation until the actual playback/reference path is proven.

## Chassis remains locked

Phase 12 changes only camera pan/tilt execution. It does not validate motor numbering, direction, power, battery behavior, or chassis dead-man behavior. Real chassis movement remains disabled.
