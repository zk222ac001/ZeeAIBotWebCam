# Phase 8 — Vision + Audio Active-Speaker Fusion

Phase 8 combines anonymous person detections from the Sony IMX500 with ReSpeaker XVF3800 VAD/DoA metadata to estimate which visible person is most likely speaking.

It is intentionally a decision-only layer. It does not move servos, motors, or the chassis.

## Goals

- combine VAD and DoA with visible anonymous people;
- require physical geometry calibration before using DoA for matching;
- convert visible person horizontal positions into camera-relative angles;
- rank candidates using audio alignment, detector confidence, size, and continuity;
- expose an ephemeral speaker label such as `Speaker-01`;
- reject speech outside the camera field of view;
- expose ambiguous/no-candidate states rather than forcing a match;
- never request physical movement in Phase 8.

## Architecture

```mermaid
flowchart LR
    CAM[Sony IMX500] --> CS[CameraService]
    CS --> PEOPLE[Anonymous person detections]

    MIC[ReSpeaker XVF3800] --> AS[AudioService]
    AS --> VAD[VAD]
    AS --> DOA[Smoothed DoA]

    PEOPLE --> FUSION[ActiveSpeakerFusion]
    VAD --> FUSION
    DOA --> FUSION

    FUSION --> API[/api/active-speaker/status]
    FUSION -. future target recommendation only .-> SAFE[Safety Supervisor]
```

## Calibration gate

The fusion engine will not perform geometric matching unless both are true:

```yaml
audio:
  orientation_calibrated: true

active_speaker:
  geometry_calibrated: true
```

The first flag means the microphone's physical 0° direction has been measured relative to the robot.

The second means the relationship between microphone direction and camera horizontal image angle is known well enough to compare them.

Until then, the API reports:

```json
{
  "state": "calibration_required",
  "speaker_id": null,
  "movement_requested": false
}
```

This is deliberate. A numerically valid DoA is not automatically a valid camera-space angle.

## Camera-space angle model

For the first calibrated model, the horizontal centre of the camera is treated as 0°.

For a configured horizontal field of view of 70°:

```text
left image edge      centre       right image edge
     -35°               0°               +35°
```

For normalized person centre `x` in the range 0–1:

```text
camera_angle = (x - 0.5) × horizontal_fov
```

This simple pinhole-style horizontal mapping is sufficient for the first fusion layer and can later be replaced by a lens-calibrated projection if needed.

## DoA interpretation

The audio service exposes a smoothed angle in the range 0–359°.

Phase 8 converts that into a signed angle:

```text
0°    ->   0°
30°   ->  +30°
330°  ->  -30°
180°  -> -180°
```

If physical calibration shows that microphone left/right is reversed relative to the camera, set:

```yaml
active_speaker:
  doa_inverted: true
```

## Candidate score

Each visible person receives a score from four pieces of evidence:

```text
Audio alignment          65%
Detector confidence      20%
Target continuity        10%
Bounding-box size         5%
```

The defaults are configurable.

Audio alignment is the dominant signal. A person whose camera angle is too far from the current DoA receives little or no audio-alignment score.

## States

The service exposes explicit states instead of forcing a speaker decision:

```text
disabled
waiting_for_speech
calibration_required
no_visible_candidate
speaker_selected
ambiguous
```

Examples:

- no VAD activity → `waiting_for_speech`;
- VAD active but geometry uncalibrated → `calibration_required`;
- VAD active and sound outside camera FOV → `no_visible_candidate`;
- several weak matches → `ambiguous`;
- one strong match → `speaker_selected`.

## API

```text
GET /api/active-speaker/status
```

Example after calibration:

```json
{
  "state": "speaker_selected",
  "sequence": 120,
  "speaker_id": "Speaker-01",
  "confidence": 0.88,
  "candidate_index": 1,
  "center": {
    "x": 0.72,
    "y": 0.48
  },
  "camera_angle_degrees": 15.4,
  "doa_degrees": 17.0,
  "angular_error_degrees": 1.6,
  "audio_orientation_calibrated": true,
  "geometry_calibrated": true,
  "movement_requested": false,
  "message": "Most likely active speaker selected from anonymous visual candidates"
}
```

`candidate_index` is only the index of the current anonymous camera detection list. It is not a persistent identity.

`Speaker-01` is also an ephemeral session label. It is not face recognition, voice recognition, or biometric identification.

## Safe default configuration

```yaml
active_speaker:
  enabled: true
  poll_interval_ms: 100
  geometry_calibrated: false
  camera_horizontal_fov_degrees: 70.0
  doa_inverted: false
  outside_fov_margin_degrees: 5.0
  max_match_error_degrees: 18.0
  minimum_candidate_score: 0.45
  continuity_distance_ratio: 0.20
  audio_alignment_weight: 0.65
  detection_confidence_weight: 0.20
  size_weight: 0.05
  continuity_weight: 0.10
```

## Mock validation

```bash
cd ~/ZeeAIBotWebCam
git pull
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -v
```

Run:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=mock
export AUDIO_MODE=mock
export ACTIVE_SPEAKER_ENABLED=true
export ACTIVE_SPEAKER_GEOMETRY_CALIBRATED=false
python -m robotic_classroom.main
```

Open:

```text
http://localhost:8000/api/active-speaker/status
```

Because geometry is deliberately uncalibrated, speech periods should produce `calibration_required` rather than a speaker match.

## Real-sensor observation before calibration

You may safely run the real camera and real microphone together while robot movement remains mocked:

```bash
export HARDWARE_MODE=mock
export CAMERA_MODE=imx500
export AUDIO_MODE=xvf3800_usb
export ACTIVE_SPEAKER_ENABLED=true
export ACTIVE_SPEAKER_GEOMETRY_CALIBRATED=false
python -m robotic_classroom.main
```

Useful endpoints:

```text
/api/camera/detections
/api/audio/status
/api/active-speaker/status
```

This lets you observe camera positions and microphone angles side-by-side without enabling fusion geometry or movement.

## Required physical calibration before enabling matching

1. Place a speaker directly in front of the robot/camera.
2. Record the stable ReSpeaker DoA value.
3. Repeat at known left and right positions.
4. Determine the microphone orientation offset.
5. Confirm whether increasing DoA corresponds to camera-right or camera-left.
6. Confirm the real camera horizontal FOV or use a measured value.
7. Set `audio.orientation_calibrated: true` only after the microphone orientation offset is correct.
8. Set `active_speaker.geometry_calibrated: true` only after left/centre/right matching is verified.

## Safety and privacy boundary

Phase 8 has no dependency on the Hiwonder motor or servo APIs.

The public result explicitly contains:

```json
"movement_requested": false
```

It also performs no:

- face recognition;
- voice recognition;
- biometric identification;
- persistent identity storage;
- classroom recording.

## Definition of done

Phase 8 software is complete when:

- unit tests verify calibration gating;
- unit tests verify left/right audio-to-vision matching;
- API tests verify that fusion never requests movement;
- the service exposes unambiguous failure states;
- real camera and audio can be observed together;
- physical geometry remains disabled until measured.

The next phase should focus on WebRTC/telepresence media transport or, if the hardware calibration is completed first, a separately gated active-speaker target recommendation into the Safety Supervisor.
