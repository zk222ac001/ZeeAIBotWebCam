# Pan-aware speaker matching: stationary classroom validation

This feature is opt-in. Neither supplied YAML profile enables it, and chassis autonomy remains plan-only. Start with a stationary chassis and a microphone rigidly mounted to that chassis. If the microphone rotates with the camera, leave compensation disabled and calibrate their fixed relative alignment instead.

## Coordinate convention

After the existing audio orientation offset and `doa_inverted` correction, positive angles point right from chassis front. Camera pan is positive right as well:

    pan_degrees = (successful_pan_pulse - pan.center) * pan_degrees_per_us * direction
    direction = -1 if pan.inverted else +1
    camera_relative_doa = wrap_to_minus180_plus180(corrected_doa - pan_degrees)

Both the field-of-view gate and candidate angular comparison use camera-relative direction. `camera_angle_degrees` in the status API retains its existing meaning: the candidate's image-relative angle, not a chassis bearing. Angular error uses circular distance.

## Estimate limitations

The current servo interface provides no encoder feedback. A successful write is only a commanded-position estimate; it cannot detect a stalled, disconnected or manually displaced servo. Pan geometry must be measured on the assembled robot. This is a horizontal approximation, suited to modest tilt and distant classroom participants; it is not full 3D localization or target distance estimation.

The executor exposes a pan estimate only after a successful supervised command and the configured settling interval. Frames older than that interval, future timestamps, missing execution, plan-only execution and failed commands cannot supply a pose. Repeated identical successful pan commands retain the original settle time. A changed command invalidates the estimate before hardware I/O, including during a blocked write. After errors the next successful command starts a new settling interval. No planned pulse is treated as a physical pose.

During continuous panning, speaker fusion may report `calibration_required` with a message requesting a settled estimate. The existing visual tracker can continue framing; speaker association resumes on fresh frames after settling. A current pose is never applied retroactively to older images. This conservative approach may reduce speaker-selection availability during movement.

## Calibration procedure

### Center and hold for setup

The Pi profile now starts with `pan_tilt_control.startup_center_hold: true`. Both
axes request their existing calibrated centers and stay there until the operator
resumes automatic camera tracking. This prevents a visible person from immediately
pulling the camera back toward a limit while participants are being positioned.
The generic mock profile keeps its previous tracking startup behavior.

Open `/api/pan-tilt/ui`, also linked from the conference page. **Center and hold**
disarms chassis autonomy, requests STOP, and pauses camera following while the
planner slews toward the calibrated neutral pulses. **Resume tracking** releases
that hold. Requests use the configured control access token when authentication
is enabled; a conference access token is separate. Endpoints are:

```text
POST /api/pan-tilt/center
POST /api/pan-tilt/resume
GET  /api/pan-tilt/plan
```

The control page also shows a camera preview with person boxes, the tracking
position, and a center guide drawn from the configured tracking dead zones. The
dot uses the selected person's box center, so assess body framing with this
guide. Frames and markers refresh separately and may differ briefly during
movement. A stalled camera sequence or failed refresh clears the preview. Edge
warnings help position participants before a steady test; limit warnings show
when the configured camera travel cannot center the current target. Loading the
page does not resume tracking or move hardware.

The existing maximum step and servo bounds apply. Execution still passes through
the executor and Safety Supervisor; emergency/fault/shutdown states block it.
Plan-only mode remains a preview. While center hold is active, execute-mode chassis
autonomy cannot arm. `center_hold` in the plan status identifies the override.

The page reports submitted commands, not measured servo position. If both submitted
pulses equal their configured centers but the physical camera does not point forward,
inspect the mechanical mounting and neutral calibration. Do not widen limits to
correct that. Missing/stale perception cannot override an explicit center hold;
normal tracking still uses producer freshness checks. A blocked actuator driver can
still delay commands, so this control does not replace independent motor protection.

The stationary-target check on 2026-10-25 found reversed horizontal correction on
this Pi mounting: increasing the pan command from 1500 to 1650 moved the same
visual target from about 58% to 72% of image width, farther from center. The Pi
profile now sets `hardware.pan_tilt.pan.inverted: true`. Restart the service and
repeat the stationary-target check after changing this setting. The first check
after restart reduced the sole person's horizontal box-center offset from about
11% to 4–5% of image width. Both axes remained inside their configured center
zones for six consecutive samples, at pan 1445 and tilt 1580, without reaching
either limit or reporting an execution error. The explicit center request then
returned both commands to 1500. This confirms correction toward that stationary
target; opposite-side correction, moving-target accuracy, pan angle, and usable
travel still require validation. Servo bounds, center pulses, and tilt direction
are unchanged. Speaker selection was not validated by this visual check.

The opposite-side check moved the target toward center but did not hold it there
before reaching the pan limit. Subsequent preparation still included movement
and detections clipped at the image edges, so opposite-side accuracy remains
unconfirmed. Keep the existing bounds and repeat with a stationary, clearly
framed participant; do not widen travel based on this incomplete result.

For a microphone confirmed fixed to the chassis, first verify its front/left/right
direction using the running HTTPS service:

```bash
.venv/bin/python scripts/calibrate_active_speaker.py
```

Pause all playback and use one local speaker 1–2 metres away. Follow the prompts,
using chassis front and chassis left/right rather than the camera's current heading.
The helper uses the checkout's trusted CA, rejects repeated producer sequences and
silent/hangover samples, and withholds a recommendation for weak or scattered readings.
Its 80%-within-15-degrees criterion checks sample consistency, not physical accuracy.
It sends status GETs only and does not change configuration, servo limits, or motion gates.
Review its direction offset and inversion results before applying them. A successful
microphone check does not calibrate the camera's pulse-to-angle relationship.

The centered-speaker diagnostic exposed a separate filter issue: rejection of large
direction jumps could retain an old bearing throughout continuous speech, even after
the raw source returned to a consistent front direction. The filter now confirms a
new bearing using three distinct producer sequences whose angles are within 15 degrees
of the first candidate, then replaces the old bearing using their circular mean. An
isolated jump, inconsistent candidates, or repeated polling of one producer sequence
cannot confirm a new bearing. Normal smoothing and silence clearing remain in place.
This is a software recovery rule, not proof of correct physical speaker selection.

### Direction source is part of calibration

`AUDIO_MGR_SELECTED_AZIMUTHS` returns the speech-processed direction at index 0 and
the auto-selected beam at index 1. The previous backend used index 1 while naming
it processed. XMOS explains that auto-selection may switch rapidly and that index 0
combines beam directions with speech energy; a missing speech direction is NaN.
See [XMOS direction indication](https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/user_guide/03_using_the_host_application.html).

`audio.doa_source` now explicitly selects `processed`, `auto_selected`, or `primary`.
The generic default preserves `auto_selected`; the Pi profile selects `processed`
and marks `orientation_calibrated: false` pending fresh measurements. The previous
offset is retained for reference, not accepted as validated for this source. No
source is silently substituted if its value is unavailable. `/api/audio/status`
exposes the selected source and all three raw direction values for diagnosis.

After restarting the service to load a source change, run the helper above. It expects
`processed` by default (use `--source` to explicitly measure another configured source).
It allows two seconds for settling at each position and prints direction-bin counts
when samples scatter. Keep the consistency check: do not apply only the center offset
or enable pan geometry after failed left/right measurements. A reader correction is
not evidence that real-world localization or pan compensation has been validated.

1. Keep chassis autonomy plan-only and validate emergency stop. Use the existing bounded pan/tilt controls under supervision. Mark the physical camera-forward direction at the configured pan center and calibrate microphone orientation against it.
2. Measure actual camera angle at center and at several safe pulses on each side. Confirm `pan.inverted` agrees with physical rightward motion. Determine positive `pan_degrees_per_us` from angle change divided by pulse change. Do not assume the default 0.09 matches the servo. If a single slope does not fit across the safe range, narrow that range or implement a measured lookup table before proceeding.
3. Measure worst-case time to settle, including command and capture latency. Set `pan_settle_ms` conservatively (default 400 ms, minimum 300 ms, matching the current adapter's 300 ms move duration).
4. With chassis fixed, place speakers at measured left, center and right bearings. Test centered and panned camera poses. Confirm the visible speaker is selected and an off-camera speaker is rejected. Repeat with two people, alternating speech. Check camera mirroring and audio inversion independently.
5. Only after these checks, set the following fields under `active_speaker` in the local Pi profile, replacing the slope and settle time with measured values:

```yaml
pan_compensation_enabled: true
pan_geometry_calibrated: true
pan_degrees_per_us: 0.09  # EXAMPLE ONLY: replace with measured slope
pan_settle_ms: 400       # replace with measured conservative settling time
```

Existing audio orientation, camera geometry and hardware calibration gates must also pass. If compensation is enabled without pan calibration or a usable pose, fusion does not select a speaker.

## Acceptance record

Record pulse, measured pan angle, expected participant, selected candidate, angular error, settling time and selection latency. Exercise camera freeze, denied servo command, partial write failure and process restart. Confirm fusion does not claim a fresh match without valid inputs. Run a ten-minute stationary classroom pilot before considering chassis rotation. Physical validation, acoustic echo cancellation and anonymous participant identity stability remain separate work.
