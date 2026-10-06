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
