# Affordable autonomous classroom telepresence: development roadmap

Project objective: **Development of an Affordable AI-Powered Autonomous Robotic Video Conferencing System Using Raspberry Pi and Python for Hybrid Active Learning Classrooms.**

The first useful autonomous classroom behavior is to frame a local speaker while a remote participant can hear, see and contribute. Chassis rotation supports camera framing. Person following and room navigation are later, separately validated capabilities.

## Stage 1: reliable motion supervision — this change

- Preserve producer timestamps through visual tracking, speaker selection and pan/tilt plans. Reject expired, future or non-finite timestamps. Defaults: 1000 ms for tracking, fusion and safety sensor observations; these are configurable time limits, not measured braking guarantees.
- Repeated fusion or consumer polling cannot refresh the underlying observation time or satisfy the autonomy target-stability gate. Stability now covers both tracking and following, and resets when execute mode is armed.
- Sample chassis sensors in a background reader. The watchdog examines the latest immutable sample without waiting for sensor I/O. Missing, invalid, stale or nearby ultrasonic returns block all non-zero chassis commands conservatively. This does not provide rear/side obstacle coverage.
- While chassis motion is active, heartbeat expiry or a sensor/obstacle blocker stops motion, clears the lease and latches a fault. The operator must inspect the cause, acquire a new lease and reset the fault. The control UI exposes this reset.
- Normal chassis STOP also disarms autonomy. It does not turn off stationary camera framing. Emergency stop inhibits new pan/tilt commands as well as chassis commands; reset requires a new valid lease.
- Pan/tilt execution goes through the same supervisor lock and checks calibration, bounds, observation age and emergency/fault state. It does not require a chassis lease, so stationary classroom framing still works.
- Execute-mode autonomy disarms on stale observations or unavailable/mismatched pan/tilt execution. A successful servo submission is not measured physical position.
- A failed autonomy worker requests STOP, disarms and reports a fault. Running status reflects whether the worker is alive.

The Pi configuration, servo calibration, motor mapping, gains and deployment scripts are unchanged. Autonomous chassis motion remains plan-only, unarmed at startup, rotation-only, with search/forward motion disabled and pilot validation incomplete.

### Software acceptance

Run `python -m ruff check src tests` and `python -m pytest -q` with mock backends. Failure-injection coverage includes frozen/disconnected cameras, stale audio, invalid range, obstacles appearing after a command, a blocked sensor reader, emergency-stop servo inhibition, repeated-observation stability and the public Stop endpoints.

### Physical acceptance still required

Keep chassis execution disabled for the initial stationary pilot. Observe camera framing, speech switching, remote-only speech, double-talk and reconnection using `scripts/classroom_pilot_check.py --duration 600`. The helper is read-only and is not an emergency stop.

Then validate stop timing, range failure behavior and servo inhibition in a controlled hardware test. An already-issued servo move may finish; the software inhibits subsequent writes and does not implement servo power removal. A blocked controller write, crashed Python process or power fault still requires independent hardware protection. Verify controller timeout support or a physical motor inhibit before unattended mobility.

## Stage 2: dependable stationary speaker framing

1. Measure the microphone/camera mounting relationship and pan pulse-to-angle conversion. Transform microphone and visual directions into the same frame as the camera pans.
2. Improve anonymous target association and speaker-switch hysteresis. Existing labels are not proof that the same person remains selected; nearby people crossing can confuse them.
3. Validate AEC with remote-only and simultaneous speech so the robot does not follow its own loudspeaker.
4. Add a bounded plan-only reacquisition behavior for a speaker leaving the camera view.

## Stage 3: supervised chassis recentering

Validate slow rotation only, with fresh stable observations, finite turn duration, clear surroundings, a local operator and explicit arming. Measure motor response and stopping distance before choosing operating thresholds. Define operator presence separately from the autonomy worker heartbeat: the current service renews its own lease and browser disconnection is not an autonomy stop guarantee.

## Stage 4: optional person following

Establish distance to the selected person, not just an arbitrary ultrasonic return. Evaluate additional ranging only after measuring the limitations of current hardware. Add target-loss cancellation, speed/acceleration limits and protection appropriate to the whole chassis footprint. Keep translation disabled until that evidence exists.

## Stage 5: optional navigation and docking

Room-scale mobility requires robot pose estimation, obstacle geometry, route planning, recovery behavior and a docking strategy. Determine the available encoder/IMU interfaces and sensing coverage before selecting hardware or a navigation framework. This repository does not yet implement those capabilities.

## Classroom evaluation and affordability

Record results rather than inferring success from configuration flags:

| Outcome | Measurement |
|---|---|
| Speaker framing | Correct-speaker fraction, image-center error, switch latency |
| Participation | Remote/local conversational turn success and teacher feedback |
| Audio/video | End-to-end latency, intelligibility, echo and reconnect recovery |
| Motion | Stop latency, target-loss response, false turns and interventions |
| Reliability | Session duration without restart, service faults and dropped observations |
| Compute/power | Pi CPU, memory, temperature and battery runtime |
| Affordability | Itemized hardware cost, added sensor cost and maintenance time |

Agree acceptance targets before trials. Do not claim learning improvement without a study design and collected evidence. Prefer anonymous telemetry over stored classroom audio/video.
