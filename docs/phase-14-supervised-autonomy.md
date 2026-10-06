# Phase 14 — Supervised Autonomy

## Goal

Add autonomous chassis decisions without allowing perception code to bypass the existing safety
architecture.

The autonomy layer consumes:

- anonymous person / active-speaker tracking;
- calibrated pan position;
- ultrasonic range;
- the existing chassis safety supervisor.

It never calls TurboPi motor APIs directly.

## Safety architecture

```text
Camera + XVF3800
       |
       v
Tracking / active speaker
       |
       v
Pan/tilt plan + ultrasonic range
       |
       v
AutonomyController
       |
       v
AutonomyService
       |
       v
SafetySupervisor
  - control lease
  - heartbeat
  - obstacle threshold
  - command bounds
  - emergency stop
  - dead-man watchdog
       |
       v
TurboPiAdapter
       |
       v
Motors
```

STOP and emergency-stop remain available independently of autonomy.

## Modes

### plan_only

The controller generates decisions but never sends chassis commands. This is the Raspberry Pi
default while autonomy behavior is being physically validated.

### execute

The autonomy service may submit its planned chassis command through the SafetySupervisor.

Execute mode:

1. requires a valid control lease before arming;
2. renews the normal heartbeat while armed;
3. stops and disarms if the lease/heartbeat is lost;
4. remains subject to obstacle and dead-man protection;
5. blocks simultaneous non-zero manual chassis commands.

## Initial autonomous behaviors

The first implementation supports:

- stop when an obstacle is inside the safety distance;
- stop when ultrasonic range is required but unavailable;
- stop when the tracked target is temporarily lost;
- use calibrated pan displacement to request slow chassis rotation toward a tracked target;
- optionally perform a slow search rotation when no target is visible;
- optionally move forward toward a centered target using ultrasonic range.

Search rotation and forward following are disabled by default.

## Important ranging limitation

The TurboPi ultrasonic sensor measures whatever lies in its acoustic beam. It does not prove that
the measured object is the same person selected by the camera tracker.

For that reason, autonomous forward following stays disabled until physical validation establishes
a trustworthy target/range relationship or a better ranging/localization source is added.

Recommended upgrades for higher autonomy:

- depth camera or stereo/depth ranging;
- wheel encoders / odometry;
- IMU;
- 2D lidar for room-scale obstacle geometry;
- mapped navigation and localization;
- docking / charging marker or beacon.

## Raspberry Pi safe defaults

```yaml
autonomy:
  enabled: true
  mode: plan_only
  search_enabled: false
  forward_enabled: false
```

This allows live autonomy-decision inspection without autonomous chassis movement.

## API

Read the current decision:

```bash
curl -sk https://127.0.0.1:8000/api/autonomy/status | python -m json.tool
```

Arm plan-only preview:

```bash
curl -sk -X POST https://127.0.0.1:8000/api/autonomy/arm \
  -H 'Content-Type: application/json' \
  -d '{}'
```

Stop/disarm at any time:

```bash
curl -sk -X POST https://127.0.0.1:8000/api/autonomy/stop
```

Do not change `mode` to `execute` until the plan-only decisions have been observed and physically
validated with the chassis secured and sufficient clearance around the robot.
