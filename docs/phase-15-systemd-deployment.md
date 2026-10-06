# Phase 15 - Raspberry Pi deployment and systemd

## Goal

Run the validated Raspberry Pi application as a supervised operating-system service instead of
depending on an interactive SSH terminal.

Phase 15 does **not** unlock autonomous chassis motion. The committed Raspberry Pi profile remains:

```yaml
autonomy:
  mode: plan_only
  execution_policy: rotation_only
  require_pilot_validation: true
  pilot_validated: false
```

## Deployment components

- `deploy/systemd/zee-robot.service.in` - systemd unit template.
- `deploy/systemd/zee-robot.env.example` - optional root-owned environment overrides.
- `scripts/install_systemd_service.sh` - renders, installs, and enables the unit.
- `scripts/uninstall_systemd_service.sh` - removes the unit without deleting environment secrets by default.
- `scripts/service_healthcheck.py` - trusted-HTTPS startup verification.

The service reuses `scripts/run_pi_https.sh`, so manual and systemd startup share one application
entry path.

## Startup health gate

After starting the application, systemd runs a read-only local HTTPS health check. It verifies:

1. `/ready` returns ready;
2. the Safety Supervisor watchdog is running;
3. chassis motion is definitely inactive;
4. the autonomy service is running;
5. autonomy did not start armed.

The health check does not acquire a lease, send movement commands, arm autonomy, or disable TLS
verification.

A failed startup health check causes systemd to treat the service start as failed. The unit uses
`Restart=on-failure` with a short delay and systemd start-rate limiting.

## Prerequisites

From the repository root, make sure the existing Raspberry Pi setup works first:

```bash
cd ~/ZeeAIBotWebCam
source .venv/bin/activate
python -m robotic_classroom.main
```

For the HTTPS deployment path, these files must already exist:

```text
.local-certs/zee-server.crt
.local-certs/zee-server.key
.local-certs/zee-local-ca.crt
```

If needed:

```bash
bash scripts/setup_https.sh
```

The installer also requires the project virtual environment at `.venv/bin/python`.

## Install without interrupting the current session

The default installer enables the service for boot but deliberately does not start it:

```bash
cd ~/ZeeAIBotWebCam
bash scripts/install_systemd_service.sh
```

Then stop any manually launched application with Ctrl+C and start the service:

```bash
sudo systemctl start zee-robot.service
```

To install and start in one operation after manual sessions are already stopped:

```bash
bash scripts/install_systemd_service.sh --start
```

## Status and logs

```bash
sudo systemctl status zee-robot.service
journalctl -u zee-robot.service -f
```

Read-only application checks remain available:

```bash
curl -sk https://127.0.0.1:8000/api/safety | python -m json.tool
curl -sk https://127.0.0.1:8000/api/autonomy/status | python -m json.tool
```

The standalone trusted health check is:

```bash
python scripts/service_healthcheck.py --wait 5
```

## Optional deployment environment

The installer creates, only when absent:

```text
/etc/zee-robot/zee-robot.env
```

with root-only permissions.

This is intended for deployment values such as conference authentication or TURN credentials.
Do not commit secrets to the repository.

For example:

```text
CONFERENCE_AUTH_REQUIRED=true
CONFERENCE_ACCESS_TOKEN=<long-random-secret>
WEBRTC_ICE_SERVERS=turn:turn.example.edu:3478
WEBRTC_ICE_USERNAME=<username>
WEBRTC_ICE_CREDENTIAL=<credential>
```

After changing the environment file:

```bash
sudo systemctl restart zee-robot.service
```

## Stop, disable, or remove

Temporary stop:

```bash
sudo systemctl stop zee-robot.service
```

Disable boot startup:

```bash
sudo systemctl disable zee-robot.service
```

Remove the systemd unit while preserving the optional environment file:

```bash
bash scripts/uninstall_systemd_service.sh
```

Remove the unit and deployment environment:

```bash
bash scripts/uninstall_systemd_service.sh --purge-env
```

## Definition of done

Phase 15 software is complete when CI validates the deployment files and, on the Raspberry Pi:

- installation succeeds;
- `systemctl start zee-robot.service` reaches `active (running)`;
- startup health check reports `HEALTHY`;
- HTTPS conference/status endpoints are reachable;
- safety watchdog is running;
- chassis is inactive after startup;
- autonomy starts unarmed and remains behind the Phase 13/14 validation gates;
- reboot starts the service successfully.

Physical reboot validation remains an operator test on the real Raspberry Pi.
