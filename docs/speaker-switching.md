# Stable classroom speaker selection

Fusion now distinguishes a confirmed change of speaker from repeated observations of a nearby target. Labels such as `Speaker-01` describe temporary selection episodes, not recognized identities. No face recognition or audio/video recording is added.

## Behavior

- First acquisition remains immediate once existing freshness, calibration, geometric and confidence gates pass.
- A candidate at a different location needs at least three observations spanning 250 ms by default before replacing the selected speaker. Both camera and audio producer timestamps must advance for each confirmation; polling, sequence changes alone, and only one advancing producer cannot confirm a switch.
- While confirmation is pending, fusion reports `ambiguous` with no selected ID or image center. The downstream tracker uses its existing brief lost-target hold and then visual fallback. Pending confirmation is never published as a fresh active-speaker target.
- A confirmed switch gets a new label, resetting downstream target-stability counting. Detection-list reordering does not change the label.
- Silence, unavailable inputs, invalid geometry, low confidence and near-tied candidates clear pending confirmation. Returning to the incumbent cancels the pending switch.
- An association expires after the configured observation timeout without a confirmed sample. Reacquisition then requires confirmation and receives a new label. Expiry cannot bypass the confirmation gate.
- Two eligible candidates whose scores differ by less than `candidate_score_margin` are ambiguous, even when both pass the individual confidence threshold.

## Configuration

These defaults apply through `ActiveSpeakerConfig`; neither supplied YAML profile is edited:

```yaml
active_speaker:
  switch_confirmations: 3
  switch_dwell_ms: 250
  candidate_score_margin: 0.08
```

The existing `continuity_distance_ratio` (default 0.20) controls association proximity. Horizontal angular difference is normalized by camera field of view and combined with normalized vertical distance. With validated pan compensation enabled, horizontal association uses chassis-relative bearing, so a settled camera pan alone need not imply a new speaker. Without compensation, association is image-relative. Chassis rotation, tilt changes, occlusion and nearby people crossing can still break association or confuse it; this is not multi-person identity tracking.

The dwell time is a minimum evidence span, not a guaranteed end-to-end response time. Camera/audio rate, processing latency, pan settling and ambiguous scenes can increase latency. Initial acquisition remains immediate; the confirmation filter primarily protects switching and reacquisition.

## Stationary acceptance trial

Keep chassis autonomy plan-only. Use two visible participants separated in angle. Record correct-speaker selections and switch latency during alternating turns, brief interjections, pauses and overlapping speech. Reorder mock detections, freeze either input stream and repeat old observations: none should manufacture switch confirmation. Check that a confirmed switch changes the ID and resets autonomy stability. Test close participants and movement across one another; record association failures rather than treating labels as ground truth.

Remote-only speech and simultaneous remote/local speech still require acoustic echo cancellation validation. This filter does not identify loudspeaker echo and cannot substitute for that work. Physical classroom testing has not yet been performed.
