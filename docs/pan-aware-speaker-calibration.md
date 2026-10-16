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
