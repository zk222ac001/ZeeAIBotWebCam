# Phase 13 - Supervised classroom pilot evidence

This adds an optional read-only test helper, not autonomous robot behavior.
It does not change configuration, calibration, firmware, motor mixing, pan/tilt,
conference routing, or application startup. It does not certify a completed pilot.

## Purpose

The operator reported that basic video and both audio directions work. The next
step is to observe the existing system during a longer real conversation and
record remaining issues before changing safety or adding speaker reacquisition.

`scripts/classroom_pilot_check.py` polls existing status APIs using HTTPS GET only.
It never imports the robot SDK, opens the camera/microphone, acquires a control
lease, sends a heartbeat, or submits motion. It does not fetch images or media.

The helper is NOT a safety controller. It cannot stop a motor. If the API reports
chassis motion or does not provide a definite stopped state, the helper stops
collecting and tells the operator to stop the pilot. Use the existing STOP control
or physical power switch as appropriate. Stopping this helper does not stop the app.

## Before starting

Keep one existing HTTPS application running and one working Chrome conference.
Use the current calibrated wiring and mounting. Do not acquire driving control.
Keep the chassis stationary on a stable surface, camera ribbon clear, speaker volume
low, and an operator close enough to intervene. Use headphones at the remote end.
Do not allow unattended testing or publish the application on the public internet.

Have two willing local participants initially visible in the camera, and one remote
participant. Telemetry is not raw media, but still describes activity; obtain their
agreement and keep reports private. For speaker switching, watch the actual selected
person: candidate indices and temporary Speaker IDs are not identity measurements.

## Run on the Raspberry Pi

No new dependencies are needed; the helper uses the Python standard library.
Open a second terminal, leaving the application running:

```bash
cd ~/ZeeAIBotWebCam
git pull --ff-only origin main
source .venv/bin/activate
python scripts/classroom_pilot_check.py --duration 600
```

If the Git update is refused because of local changes or divergence, stop and resolve
that without discarding local work. Do not start a second application instance.
These additions do not need an application restart.

The default origin is `https://localhost:8000`. The default trust certificate is
`.local-certs/zee-local-ca.crt`, resolved from the checkout rather than the current
working directory. Certificate chain and hostname verification remain enabled.
There is no insecure mode. The helper blocks redirects and does not use an HTTP proxy.

A different HTTPS origin or CA can be selected explicitly:

```bash
python scripts/classroom_pilot_check.py --duration 600 \
  --base-url https://localhost:8000 \
  --ca .local-certs/zee-local-ca.crt
```

The CA is public certificate material. Never distribute either private `.key` file.
If a read returns HTTP 401/403 and conference authentication has been enabled,
set `ZEE_CONFERENCE_TOKEN` locally to the existing authorized conference token.
The helper reads this environment variable; it does not print or retain it. Do not
put secrets in the URL or publish them in reports. This helper does not create tokens
or change authentication. Only the fixed status paths are requested.

## Guided ten-minute protocol

Instructions print as each phase begins. At the default duration each phase is two
minutes. Shorter durations scale these phases: a short run is only a software smoke
test, not equivalent to completing the ten-minute protocol.

| Time | Phase | Operator task |
|---|---|---|
| 0-2 minutes | Speaker switch | Local A and B alternate speech roughly every five seconds. |
| 2-4 minutes | Slow tracking | One local speaker moves slowly inside the camera view. |
| 4-6 minutes | Remote only | Local people remain quiet; remote participant speaks. |
| 6-8 minutes | Overlap | Briefly overlap local and remote speech, then take turns. |
| 8-10 minutes | Reconnect | Disconnect once, wait a few seconds, reconnect and continue. |

Stop immediately for unexpected chassis movement, loud feedback, grinding, heat,
or cable strain. Ctrl+C in the helper terminal writes a partial report; it is NOT
an emergency-stop command for the application. Do not increase servo range to pass
this test. No threshold in this helper is a robot safety limit.

## Output and interpretation

Reports are written under the existing Git-ignored directory:

```text
logs/classroom-pilot/<UTC-run-timestamp>/
    telemetry.jsonl
    report.json
    report.md
```

The telemetry retains a fixed allowlist of status fields, counts, angles, image-space
errors and commanded pulses. It omits API messages, bearer tokens, session IDs, SDP,
identity labels, images and audio. The files are local; nothing is uploaded by the
helper. Review and share only the smallest necessary report. Delete reports when no
longer needed.

`report.md` includes review counts and a human checklist. Counts are numbers of sampled
observations, NOT distinct incidents or time durations.

- `NO_TELEMETRY_ALERTS`: no automatic alerts in the samples, NOT an overall PASS.
- `REVIEW`: check the flagged observations alongside the real behavior.
- `INCOMPLETE`: the helper stopped early, was interrupted or obtained no samples.
- Exit code 0 means no telemetry alerts; 1 means review/incomplete; 2 is a local setup/report error.

Manual checks always start NOT TESTED. A person must confirm moving video, audible
speech in each direction, correct speaker framing, echo behavior, smooth physical
motion, reconnect recovery and a stationary chassis. Even a complete run is not
formal safety certification or approval for autonomous movement.

A configured pulse limit is a review observation, not necessarily a mechanical stop
or fault. `executed=true` reports a command result, not measured servo motion. Metadata
sequence advancement does not prove that video pixels are changing. An active-speaker
selection during the remote-only phase needs inspection; it does not prove echo.

Requests are sequential, not synchronized snapshots. Polling every two seconds can
miss brief events. The report includes request span and sample gap; slow samples
reduce coverage. Heartbeat expiry is not flagged during this stationary test because
no driving lease is needed. An intentional disconnected sample in the reconnect phase
is not automatically a connection failure; successful recovery needs human confirmation.

## Tests and next development gate

Run the isolated tests without attaching hardware:

```bash
python -m pytest -q tests/unit/test_classroom_pilot_check.py
```

The tests include a temporary simulated HTTPS server, trusted certificate validation,
hostname mismatch rejection, allowlisted GET requests, report generation, partial-run
handling, redaction, telemetry staleness and review classification. They do not test
real Raspberry Pi audio/video, robot movement or a real classroom.

Do not use the older `final_system_validation.py` as a substitute for this pilot:
that script uses an HTTP origin, snapshot checks and configuration flags. In particular,
configuration flags alone are not end-to-end media-quality or safety evidence.

After reviewing the pilot, strengthen server-side access control, continuous motion
safety and microphone/camera reference-frame handling. Then consider a separate,
plan-only speaker-reacquisition module. None of those changes is enabled by this helper.

## Source basis

Status field names come from `src/robotic_classroom/web/app.py` and
`src/robotic_classroom/conference/router.py` in this repository. The phase timing,
review observations and human criteria above are a proposed engineering test protocol.
