# Stationary classroom validation on the Raspberry Pi

This trial evaluates the draft autonomy changes before chassis turning is enabled. It requires the physical Pi, two local participants and one remote participant. The helper does not deploy software, change calibration, arm autonomy, send motor commands or capture audio/video.

## Prepare

Use the reviewed PR branch on the Pi and keep autonomous chassis execution in `plan_only`. Run the existing HTTPS application and open one conference session in Chrome. Complete the pan calibration in [pan-aware-speaker-calibration.md](pan-aware-speaker-calibration.md) before enabling compensation. Keep the chassis stationary with an operator present. The monitor cannot stop the robot.

From the repository root, run:

```bash
python scripts/classroom_pilot_check.py --duration 600 --interval 0.5
```

The default origin is `https://localhost:8000`; the default trusted CA is `.local-certs/zee-local-ca.crt`. If needed, specify `--base-url https://YOUR_PI_HOST:8000 --ca /path/to/zee-local-ca.crt` using a hostname covered by the certificate. For authenticated conference status, provide the configured token through the `ZEE_CONFERENCE_TOKEN` environment variable; do not put it in the command line or report.

The program prints the output directory. It creates `telemetry.jsonl`, `report.json` and `report.md`. Read errors, missing data and interruptions remain visible in the report. A 0.5-second interval improves sampling resolution but cannot measure a 250 ms switch delay reliably; slow requests can further reduce sampling frequency.

Before starting its timer, the helper now checks for readable status endpoints, an
idle chassis with no reported motion, a running watchdog, connected camera/audio,
at least one connected conference, and at least two visible local participants.
If a condition is missing, it writes an `INCOMPLETE` report with
`stop_reason: preflight_failed`, lists the missing conditions, and collects no trial
samples. No service restart is required to use this helper change. Passing this
single snapshot does not validate audio quality or physical safety. Later changes
are recorded as telemetry observations; the starting check is not a safety controller.

## Ten-minute sequence

Each phase lasts two minutes. Follow the terminal prompts.

| Phase | Action | Human evidence to record |
|---|---|---|
| speaker_switch | Two visible participants alternate speech every five seconds | Expected left/right participant, whether the actual speaker was framed, missed switches, visible oscillation |
| slow_tracking | One speaking participant moves slowly left, center and right | Framing quality, smoothness, loss of target, cable or servo limits |
| remote_only | Local participants stay silent while the remote participant speaks | Whether camera follows a silent local person; whether the remote participant hears their voice returned |
| overlap | Brief local and remote speech overlap | Intelligibility in both directions, returning echo, feedback; stop if feedback becomes loud |
| reconnect | Disconnect once, wait a few seconds and reconnect | Moving video and both audio directions recover without restarting the application |

Use anonymous left/right labels in notes. A `Speaker-NN` label describes a selection episode, not a person identity. Do not infer correct-speaker selection from an ID change.

## Interpret the report

Report schema version 2 adds per-phase sample counts and metrics:

- `selected_fraction` and `ambiguous_fraction` divide by samples with a known speaker state. Missing or failed speaker reads are excluded and counted explicitly. An unsampled phase is `null`/`N/A`, not zero or success.
- `mean_selected_abs_center_error` is the mean absolute horizontal displacement from image center, using selected samples with valid normalized centers. Zero means image center; this does not prove the correct person is framed.
- `p95_selected_angular_error_degrees` is the nearest-rank 95th percentile of valid audio/visual matching errors for selected samples. Its sample count is also included. It is not an independently measured bearing error.
- `speaker_state_counts` distinguishes silence, ambiguity, missing candidates and calibration requirements. Review these alongside sequence/freshness flags, sample spans and sample gaps.

These are sample-weighted summaries; repeated polls are included, and samples are not independent trials. They do not measure time spent in each state, switch latency, echo suppression, safety or learning outcomes. Remote-only selection is a reason to investigate echo or false speech detection, not proof of echo. Zero selections during that phase does not prove successful echo cancellation.

For a switch-latency study, separately log the observed start of each real speaking turn and the first correct framing, using a consistent observation method and stating its timing resolution. Record missed turns separately rather than omitting them from the average. No automated accuracy or latency value is fabricated by the helper.

## What to review next

Review the report together with all eight human checks. Record PASS, FAIL or NOT TESTED for each; the program never produces an overall hardware PASS. Repeat failed phases after addressing geometry, microphone orientation, echo or target association issues. Keep chassis autonomy plan-only until stationary framing and two-way audio are dependable and the physical stop tests are complete.

For follow-up analysis, share `report.json` and anonymous manual findings, particularly incorrect framing during remote-only speech or alternating turns. Reports omit raw media, session identifiers and person labels; review manual notes before sharing them.
