# Documentation

[← Project home](../README.md)

## Start here

1. **Develop without hardware:** use the [README quick start](../README.md#quick-start--no-robot-required), then [development environment](phase-01-development-environment.md).
2. **Prepare a robot:** review [safety](safety.md) and complete [hardware validation](phase-02-hardware-validation.md).
3. **Operate Studio:** follow [deployment and access setup](studio-deployment.md).
4. **Validate a classroom session:** use [stationary validation](stationary-classroom-validation.md), then [production readiness](phase-16-production-readiness.md).
5. **Contribute:** read [contributing](../CONTRIBUTING.md), [privacy](privacy.md) and [security](../SECURITY.md).

## Current guides

| Guide | What it covers |
| --- | --- |
| [Architecture](architecture.md) | Service boundaries and integration |
| [Hardware API inventory](hardware-api-inventory.md) | Hardware integration references |
| [Safety](safety.md) | Motion supervision and staged testing |
| [Studio deployment](studio-deployment.md) | Interface, tokens, HTTPS and private access |
| [Speaker switching](speaker-switching.md) | Speaker-selection behavior |
| [Pan-aware speaker calibration](pan-aware-speaker-calibration.md) | Audio/camera geometry and calibration |
| [Stationary classroom validation](stationary-classroom-validation.md) | Supervised acceptance procedure |
| [Classroom autonomy roadmap](classroom-autonomy-roadmap.md) | Implemented scope, blockers and future stages |
| [Privacy](privacy.md) | Media, observations, credentials and sharing |
| [Repository security review](repository-security-review.md) | Dated GitHub settings findings and next actions |

## Engineering phase archive

These documents record staged implementation and validation. Historical examples may describe earlier defaults. For current behavior, compare the current source, configuration and deployment environment; do not treat a completed software phase as physical acceptance.

| Phase | Guide |
| --- | --- |
| 00 | [engineering analysis](phase-00-engineering-analysis.md) |
| 01 | [development environment](phase-01-development-environment.md) |
| 02 | [hardware validation](phase-02-hardware-validation.md) |
| 03 | [hardware adapter safety](phase-03-hardware-adapter-safety.md) |
| 04 | [imx500 camera service](phase-04-imx500-camera-service.md) |
| 05 | [person tracking](phase-05-person-tracking.md) |
| 06 | [pan tilt planning](phase-06-pan-tilt-planning.md) |
| 07 | [respeaker audio service](phase-07-respeaker-audio-service.md) |
| 08 | [active speaker fusion](phase-08-active-speaker-fusion.md) |
| 09 | [webrtc telepresence](phase-09-webrtc-telepresence.md) |
| 10 | [production telepresence controls](phase-10-production-telepresence-controls.md) |
| 11 | [full duplex audio](phase-11-full-duplex-audio.md) |
| 12 | [echo and pan tilt calibration](phase-12-echo-and-pan-tilt-calibration.md) |
| 13 | [classroom pilot](phase-13-classroom-pilot.md) |
| 14 | [supervised autonomy](phase-14-supervised-autonomy.md) |
| 15 | [systemd deployment](phase-15-systemd-deployment.md) |
| 16 | [production readiness](phase-16-production-readiness.md) |

## Diagnostic history

- [Pilot tracking fixes, 2026-09-26](pilot-tracking-fixes-2026-09-26.md)

Diagnostic history explains earlier changes; it is not a current health report for your Pi.
