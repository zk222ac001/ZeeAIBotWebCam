# Safety Baseline

## Non-negotiable rule

AI, vision, audio, WebRTC and web modules must not call Hiwonder motor/servo APIs directly.

All future movement must pass through:

```text
Authorized request
   -> control lease
   -> command validation
   -> safety supervisor
   -> bounded motion controller
   -> TurboPi adapter
   -> Hiwonder SDK
```

## Phase 1 safety state

Current configuration intentionally uses:

```yaml
hardware:
  mode: mock

safety:
  motion_enabled: false
```

There is no movement REST endpoint and no movement WebSocket command in Phase 1.

## Planned stop conditions

The Safety Supervisor introduced in Phase 3 must force or maintain stop when any of these conditions apply:

- physical E-stop active;
- controller/hardware fault;
- obstacle is inside the configured safety threshold;
- ultrasonic data is stale or invalid when required for motion;
- control heartbeat expires;
- network/control lease is lost;
- command is invalid or outside configured limits;
- system is in an incompatible state;
- battery/power state is unsafe;
- shutdown is in progress.

## Control priority

Recommended priority, highest first:

1. emergency stop;
2. hardware fault;
3. collision/obstacle protection;
4. lost heartbeat/network;
5. invalid system state;
6. authorized manual control;
7. bounded autonomous repositioning;
8. visual tracking.

## Dead-man control

A dedicated motion heartbeat should use a short configurable timeout. Initial engineering target: approximately 500–750 ms, subject to Phase 2/3 testing.

The existing upstream application heartbeat is not sufficient as the production motor dead-man mechanism.

## Servo safety

Before enabling pan/tilt movement, Phase 2 must determine:

- actual pan channel;
- actual tilt channel;
- center values;
- minimum safe values;
- maximum safe values;
- direction/sign convention;
- mechanical collision limits.

No guessed servo limit should be committed as a production default.

## Motor safety

Individual motor polarity and chassis direction must be verified with the robot elevated or otherwise secured for controlled low-duty tests.

Full autonomous chassis motion is not a Phase 1 or initial Phase 2 activity.

## Physical recommendation

Add a physical emergency-stop mechanism that removes or safely inhibits motor drive independent of the AI/web application whenever possible.
