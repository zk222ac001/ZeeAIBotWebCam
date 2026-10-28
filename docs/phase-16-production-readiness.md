# Phase 16 - Validation and production readiness

## Goal

Phase 16 turns the completed Raspberry Pi deployment into an auditable production-readiness
workflow. It does not unlock chassis autonomy.

The phase adds:

- a runtime `GET /api/readiness` endpoint;
- a trusted HTTPS `scripts/production_readiness.py` reporter;
- optional bearer authentication for control-lease acquisition;
- an explicit production environment promotion flag;
- tests that ensure readiness output never exposes secrets.

## Readiness categories

The runtime endpoint separates readiness into categories so a working telepresence prototype is
not confused with a fully validated production deployment.

### Runtime

Requires real hardware, camera and audio services to be connected and running.

### Telepresence

Requires the conference service, video publishing, robot microphone publishing and remote speaker
playback to be configured and validated.

### Safety

Requires the Safety Supervisor watchdog, inactive chassis at the time of the check, control leases,
and validated motor mapping.

### Privacy and security

Requires:

- recording disabled;
- face recognition disabled;
- conference bearer authentication enabled;
- control-lease bearer authentication enabled;
- application environment promoted to `production`.

### AEC

Requires the echo-reference path to be enabled and physically/acoustically validated.

A software frame-counter synchronization PASS alone is not enough.

### Classroom pilot

Requires the supervised classroom pilot gate to be explicitly validated after the complete
operator-observed test.

### Autonomous motion

Reported separately from production telepresence readiness. It remains blocked while:

- autonomy is `plan_only`;
- pilot validation is incomplete;
- execution policy is `rotation_only`;
- control authentication is disabled.

Phase 16 does not automatically remove any of these gates.

## Runtime endpoint

```bash
curl -sk https://127.0.0.1:8000/api/readiness | python -m json.tool
```

The endpoint returns no access tokens, TURN credentials, SDP, media or identity data.

## Trusted operator report

```bash
cd ~/ZeeAIBotWebCam
source .venv/bin/activate
python scripts/production_readiness.py
```

A non-production-ready system returns exit code 1 and prints each blocker. Endpoint/network setup
errors return exit code 2.

For machine-readable output:

```bash
python scripts/production_readiness.py --json
```

## Production authentication

Conference authentication already uses:

```text
CONFERENCE_AUTH_REQUIRED=true
CONFERENCE_ACCESS_TOKEN=<long-random-secret>
```

Phase 16 adds a separate gate for obtaining a motion control lease:

```text
CONTROL_AUTH_REQUIRED=true
CONTROL_ACCESS_TOKEN=<different-long-random-secret>
```

The emergency-stop endpoint remains independently available. A valid lease token is still required
by normal motion, heartbeat and reset paths.

Do not use the same secret for conference and control access.

For the systemd deployment, store these only in:

```text
/etc/zee-robot/zee-robot.env
```

which the Phase 15 installer creates with root-only permissions.

## Production environment promotion

After the remaining Phase 16 gates are genuinely complete, set:

```text
APPLICATION_ENVIRONMENT=production
```

in `/etc/zee-robot/zee-robot.env` and restart:

```bash
sudo systemctl restart zee-robot.service
```

The environment label is not itself evidence of readiness. It is intentionally a separate final
promotion step.

## Current Raspberry Pi gate status

Based on the real-hardware Phase 15 evidence collected before this phase:

- systemd service: validated;
- trusted HTTPS health check: validated;
- safety watchdog: validated running;
- chassis inactive after startup: validated;
- autonomy startup: validated unarmed;
- autonomy execution: intentionally `plan_only`;
- full 600-second classroom pilot: not yet validated;
- acoustic AEC/double-talk validation: not yet validated;
- production conference authentication: not yet enabled;
- production control authentication: not yet enabled;
- production environment promotion: not yet enabled.

Therefore Phase 16 software can be complete while the deployment still correctly reports
`production_ready: false`.

## Definition of done

Phase 16 software is complete when CI passes and the readiness endpoint/reporter correctly identify
all open gates without changing robot state.

The physical production-validation phase is complete only after:

1. the full supervised classroom pilot completes and the human checklist is reviewed;
2. acoustic echo/double-talk validation is completed;
3. conference and control bearer authentication are enabled with strong separate secrets;
4. a production environment promotion is deliberate;
5. the readiness report returns `production_ready: true`;
6. autonomous motion remains separately gated until its own physical validation is complete.

Production readiness is not equivalent to autonomous-motion readiness.

## Runtime safety checks added after the initial readiness implementation

Readiness now rejects mocked hardware/media backends, stale camera/audio observations,
unavailable or unsafe range data, and emergency-stop/fault/shutdown states. Autonomous-motion
readiness also requires the production categories, enabled motion and tracking, a running autonomy
worker, configured battery cutoff, and available calibrated pan/tilt execution. These are runtime
prerequisites for supervised target tracking, not proof of navigation or physical safety.

The response includes `autonomous_motion_scope` and `unattended_navigation_ready: false`.
Room navigation and docking are not implemented. Arming and control leases remain separate
from readiness; this read-only endpoint never authorizes movement.

### Battery cutoff

Configure `safety.minimum_battery_voltage` in YAML or `SAFETY_MINIMUM_BATTERY_VOLTAGE`
in the deployment environment after determining the safe threshold for the actual pack under
load. No voltage is guessed: the default is `null`, preserving existing operation while reporting
a blocker for autonomous-motion readiness. When configured, unavailable, non-finite, non-positive
or below-threshold readings block movement. A drop during movement triggers the watchdog stop,
revokes control and latches a fault. Reset requires inspection and a new valid lease.

### Controller write failures

Emergency stop latches its state and revokes the lease/heartbeat before attempting the motor
write. A raised stop-write error preserves the latch, leaves `motion_active: true` conservatively
(physical motion is unknown), and makes stop endpoints return HTTP 503. Autonomy is disarmed
even on stop failure. Failed drive writes latch a fault and attempt STOP. Failed reset writes
cannot clear the latch. Successful writes indicate submission, not measured motor stopping.

These changes handle raised I/O errors. The actuator lock is still shared with the watchdog:
a driver that blocks indefinitely can delay stopping. A Python crash or controller fault can also
prevent STOP. Independent motor inhibition/controller timeout and physical stop-timing tests
remain necessary before unattended mobility. No live service restart or physical validation is
performed by the software tests.

## Preparing the remaining acceptance checks

The read-only AEC monitor supports the protected conference endpoint with trusted
HTTPS. Provide `CONFERENCE_ACCESS_TOKEN` in the local environment (never as a
command-line argument). It uses `.local-certs/zee-local-ca.crt` by default; use
`--ca` for a different CA and `--url` for a certificate-covered HTTPS endpoint.
With one call connected and browser audio being sent to the Pi, run:

```bash
.venv/bin/python scripts/aec_production_monitor.py --seconds 20
```

Exit codes are 0 for synchronized software counters, 1 for failed path checks,
and 2 when the protected endpoint cannot be verified or read. This never marks
acoustic acceptance complete. Follow it with remote-only speech and double-talk
listening checks, and record the observed result.

For the supervised pilot, use the same environment token:

```bash
.venv/bin/python scripts/classroom_pilot_check.py --duration 600 --interval 0.5 \
  --token-env CONFERENCE_ACCESS_TOKEN
```

Arrange two local participants and one remote participant first. An operator must
inspect the stationary robot before deliberately clearing an emergency-stop latch
using the existing control UI. Keep autonomy unarmed and plan-only. A failed
preflight or a short software check does not complete the pilot. Review all eight
human checks in [stationary-classroom-validation.md](stationary-classroom-validation.md).
Only record validated acceptance settings after those observations pass, then
perform the documented production promotion and recheck `/api/readiness`.

## Software preparation checked on 2026-10-28

The current checkout includes these production-preparation fixes:

- systemd ignores a manual-launch `.env` and refuses startup without both
  authentication gates and separate credentials in its managed environment;
- readiness rejects missing or shared conference/control credentials;
- operator motion uses verified HTTPS, an environment-supplied control token,
  and nonzero failure on an unconfirmed STOP;
- read-only tracking diagnostics use verified HTTPS and the conference token;
- exclusive audio testing refuses an occupied application port, including HTTPS;
- watchdog diagnostics attempt every cleanup step even when STOP raises;
- the AEC monitor retains transient stream errors and counter resets;
- `final_system_validation.py` delegates to the authoritative readiness reporter;
- CI lints source, tests and scripts, runs mock tests, and builds a wheel.

For older read-only tracking diagnostics, `ZEE_BASE_URL` and `ZEE_CA` can override
`https://localhost:8000` and `.local-certs/zee-local-ca.crt`. Run them from the
checkout with `CONFERENCE_ACCESS_TOKEN` in the environment. The motion client
uses `CONTROL_ACCESS_TOKEN`, `--base-url` and `--ca`. Do not run automated motion
checks against the live Pi.

These source changes are not evidence that the running service has loaded them.
The live service needs an operator-controlled restart after local inspection;
restarting must not be used to bypass an emergency-stop inspection. Applying
systemd changes requires administrator access. Retain the current preview
application environment until acceptance is complete.

The remaining release sequence is:

1. Inspect the stationary robot and resolve the emergency-stop condition through
   the existing operator controls. Keep chassis autonomy unarmed and plan-only.
2. Connect a real call and verify moving video, microphone publishing and speaker
   playback in both directions. Validate camera framing and physical travel.
3. Run the AEC monitor with remote audio playing; separately listen for echo and
   check intelligibility during remote-only speech and overlapping speech.
4. Run the complete 600-second pilot and review all eight human observations.
5. Only after successful review, record `CONFERENCE_ECHO_REFERENCE_VALIDATED=true`
   in the managed environment and `autonomy.pilot_validated: true` in the deployed
   YAML configuration. Keep `autonomy.mode: plan_only` and `forward_enabled: false`.
   These settings represent observed acceptance; they must not be inferred from
   unit tests or counters.
6. Promote `APPLICATION_ENVIRONMENT=production`, restart under operator supervision,
   and require `production_readiness.py` to return exit code 0 with all six
   production categories ready. Inspect post-restart service logs and repeat a call.

Unattended movement, navigation and docking remain outside this release. No
production promotion or physical acceptance was performed during software work.
