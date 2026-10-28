# Privacy and data handling

[← Documentation](README.md)

This document describes the inspected application and committed profiles. It is not a claim that a particular classroom deployment is compliant or fully secured.

## Data flow

| Data | Processing / destination | Operator responsibility |
| --- | --- | --- |
| Camera frames | Local camera service; JPEG endpoint and WebRTC video to authorized clients when authentication is enabled | Limit access and review what the camera captures |
| Microphone audio | Configured capture device; published to conference participants when enabled | Explain live microphone use and disconnect sessions after use |
| Remote audio | Received from conference clients and played through the configured output | Validate playback and echo behavior |
| Person boxes and speaker direction | Local tracking/fusion services and status APIs | Treat observations as classroom activity data |
| Temporary target labels | Used for tracking continuity rather than identity recognition | Do not describe the video itself as anonymous |
| Logs, reports and screenshots | May be generated during diagnostics and shared manually | Inspect and redact before upload |
| Access tokens | Local deployment environment; Studio page memory or optional tab session storage | Keep secret, use separate tokens and clear them on shared browsers |

## Defaults and boundaries

Both committed YAML profiles disable recording and face recognition. There is no biometric identity database described by the current design. These defaults do not prevent external screen capture, diagnostic tools or conference participants from recording.

The Pi profile publishes real audio/video when sessions are established, and local camera processing can run independently of a conference session. The application is not configured to upload raw classroom media to a cloud service by default; configured remote peers and ICE infrastructure still require deployment review.

## Access limitations to understand

- Conference authentication protects detailed `/health`, camera frames and camera/audio/tracking observation routes when enabled.
- Separate control authentication protects control acquisition and camera control operations; leases and safety checks govern motion.
- Both committed profiles set the two authentication gates to false. Local environment overrides must enable them for shared access.
- The minimal `/ready` probe remains public and contains no classroom observations. Operational routes including `/api/sensors`, `/api/safety` and `/api/readiness` remain public and expose device/release status. Detailed `/health` requires the conference token when authentication is enabled.
- Emergency stop is intentionally reachable without acquiring a lease. Network exposure can therefore permit disruption even where other gates are enabled.

**Use a restricted private network or an access-controlled gateway for the whole application.** Endpoint token settings alone do not hide all operational information. See [Studio deployment](studio-deployment.md) for local token setup.

## Before a classroom session

1. Agree who may access the robot, what will be captured and whether participants permit the planned use under your institution's process.
2. Enable both access gates, use HTTPS and restrict network access to approved devices.
3. Confirm recording/recognition settings and physically check the camera view and microphone behavior.
4. Avoid capturing unrelated people, screens or documents.
5. Disconnect sessions, clear browser tokens on shared devices and remove unneeded diagnostics afterward.

## Before publishing repository content

Use synthetic or explicitly cleared demonstration material. Never commit tokens, environment files, private keys or raw classroom recordings. Review diagnostic reports for device addresses, usernames, observations and other identifying context.

At the review baseline, `imx500_detection.264` is a tracked video-sized binary. Its contents and consent status were **not inspected**. The owner should review it before further sharing. Removing it in a future commit would not remove earlier copies from Git history or existing clones.

See the [dated repository review](repository-security-review.md) for scope and unresolved checks.
