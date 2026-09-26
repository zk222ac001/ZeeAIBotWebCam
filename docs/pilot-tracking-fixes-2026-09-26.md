# Classroom pilot tracking fixes - 2026-09-26

This patch addresses three reproducible software defects. It does not validate
physical motion, echo cancellation, media quality, or autonomous operation.

## Changes

1. **Independent axis dead zones.** Both visual and active-speaker tracking now
   publish `in_dead_zone_x` and `in_dead_zone_y` using the existing TrackingConfig.
   PanTiltController holds the current pulse of an axis inside its dead zone while
   correcting the other axis. It does not return that axis to mechanical center.
   Combined `in_dead_zone` remains available. Missing per-axis flags retain the old
   behavior for direct planner callers; both production tracking sources provide
   the flags. Missing or non-finite errors hold the current plan.
2. **Separate publication and source counters.** TrackingService publishes its own
   increasing `sequence`, with the producer's counter retained as `source_sequence`.
   `source` is `visual`, `active_speaker`, or `active_speaker_hold`. Changing producer
   no longer masquerades as a tracking restart. Repeated reads of identical source
   data return the same publication, so polling cannot manufacture freshness.
   These are metadata counters, not measured frame rates or position feedback.
3. **Hard angular eligibility gate.** Fusion discards candidates whose angular error
   is larger than the existing `max_match_error_degrees`, or whose score/error is
   not finite, before ranking. Confidence, size, and continuity cannot override this
   gate. If no candidate remains, the result is `ambiguous` with no selected target.
   Exactly-at-limit matches remain eligible, subject to the existing score threshold.

The existing `/api/tracking/status` route adds the four fields above: `source`,
`source_sequence`, `in_dead_zone_x`, and `in_dead_zone_y`. Old fields remain.
The classroom pilot helper uses the corrected service sequence without needing a
change. Its existing camera/audio/fusion freshness checks remain in place. Older
reports are not rewritten. Inspect the tracking API when source details are needed.

## Unchanged

No configuration files, servo channels, pulse limits, gains, inversion settings,
microphone orientation offset, firmware, wheel wiring, motor mixer, safety policy,
authentication, HTTPS setup, WebRTC routing, or startup scripts are modified.
Chassis movement has not been newly enabled or authorized by this patch.

## Software validation

Six reproducer cases failed against the pre-patch source: four cross-axis drift
cases, the counter-domain switch, and the out-of-angle continuity match.
After the patch, 52 focused cases passed: 45 new regression cases and seven existing
controller/fusion cases. Python compilation also passed. The test environment used
Python 3.13.5, pytest 9.0.2, and pydantic 2.13.4.

The tests use synthetic camera/speaker observations, real project control/fusion
classes, and an isolated tracking-status serializer. They include both tracking
sources, positive/negative small errors, custom dead-zone boundaries, hold-at-current
behavior, bounded slew, inversion, lost-target hold, non-finite error rejection,
concurrent metadata readers, unchanged-source staleness, source transitions, angular
boundaries, wraparound, and rejection despite a high continuity/confidence score.
No robot SDK, live camera, live microphone, or hardware startup is called.

Run the same focused tests from the checkout:

```bash
python -m pytest -q tests/unit/test_pilot_tracking_regressions.py \
  tests/unit/test_pan_tilt_controller.py tests/unit/test_active_speaker_fusion.py
```

This is not a full repository integration test, a live Pi test, or a classroom PASS.

## Apply and restart on the Pi

Disconnect the conference and stop the pilot helper. In the separate main-server
terminal, press Ctrl+C and wait for application shutdown. Keep the chassis stationary;
these instructions do not acquire a driving lease. Then:

```bash
cd ~/ZeeAIBotWebCam
git status --short
git pull --ff-only origin main
source .venv/bin/activate
python -m pytest -q tests/unit/test_pilot_tracking_regressions.py \
  tests/unit/test_pan_tilt_controller.py tests/unit/test_active_speaker_fusion.py
bash scripts/run_pi_https.sh
```

If the pull reports local changes/conflicts, do not discard them. If tests fail, do not
start the hardware application with the changed code. A server restart is required;
an already running process continues using its previously loaded Python modules.

## First supervised check

Use one stationary visible participant before attempting another ten-minute pilot.
Observe moving video in the existing trusted browser setup. In another Pi terminal:

```bash
cd ~/ZeeAIBotWebCam
curl --fail --silent --show-error --cacert .local-certs/zee-local-ca.crt \
  https://localhost:8000/api/tracking/status | python3 -m json.tool
```

When only horizontal error needs correction, `in_dead_zone_y` should be true and tilt
should hold while pan corrects. Repeat for vertical error and `in_dead_zone_x`.
The corrected sequence must not decrease merely when `source` switches. Stop for
unexpected chassis movement, grinding, heat, or camera-ribbon strain. The pilot
helper is not a stop controller. Do not widen the pulse limits to make this test pass.

Observe the actual image/physical camera as well as telemetry. A pulse limit is a
configured command boundary, not proof of a mechanical stop. `executed` is a command
result, not a position measurement.

## Still unresolved by this patch

A target may remain off-center at a pulse limit because of physical orientation,
mounting, available travel, or other control behavior. The microphone/camera reference
frame when pan changes still needs measured calibration and a separate design change.
The angular gate can intentionally produce MORE `ambiguous` samples rather than
incorrectly selecting a person. The existing lost-target/visual-fallback policy remains;
rejecting a speaker does not disable ordinary visual tracking. This patch does not
add echo-reference validation, shared ALSA capture, access control, stale-actuator-data
protection, or autonomous chassis movement. Physical acceptance checks remain required.
