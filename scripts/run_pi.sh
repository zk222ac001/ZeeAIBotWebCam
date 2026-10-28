#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

# Local operator credentials for manual launches (ignored by Git). The systemd
# deployment continues to use its root-managed EnvironmentFile.
# systemd owns the deployment environment; local manual-launch settings must
# never override its managed credentials or validation settings.
if [ -z "${INVOCATION_ID:-}" ] && [ -f .env ]; then
  if [ ! -f .env ] || [ -L .env ] || [ "$(stat -c '%u' .env)" != "$UID" ] \
      || [ "$(stat -c '%a' .env)" != 600 ]; then
    echo 'Refusing .env: it must be a regular file owned by this user with mode 600.'
    exit 1
  fi
  set -a
  . ./.env
  set +a
fi

# A managed deployment must not fall back to unauthenticated access when a
# local .env previously supplied credentials that EnvironmentFile lacks.
if [ -n "${INVOCATION_ID:-}" ]; then
  case "${CONFERENCE_AUTH_REQUIRED:-}" in
    true|True|TRUE|1|yes|YES|on|ON) ;;
    *) echo 'Configure conference authentication in /etc/zee-robot/zee-robot.env before starting systemd.'; exit 1 ;;
  esac
  case "${CONTROL_AUTH_REQUIRED:-}" in
    true|True|TRUE|1|yes|YES|on|ON) ;;
    *) echo 'Configure control authentication in /etc/zee-robot/zee-robot.env before starting systemd.'; exit 1 ;;
  esac
  if [ -z "${CONFERENCE_ACCESS_TOKEN:-}" ] || [ -z "${CONTROL_ACCESS_TOKEN:-}" ]; then
    echo 'Managed deployment credentials are missing; run scripts/setup_studio_access.py with sudo.'
    exit 1
  fi
  if [ "${#CONFERENCE_ACCESS_TOKEN}" -lt 16 ] || [ "${#CONTROL_ACCESS_TOKEN}" -lt 16 ] \
      || [ "$CONFERENCE_ACCESS_TOKEN" = "$CONTROL_ACCESS_TOKEN" ]; then
    echo 'Managed deployment requires separate conference and control credentials of at least 16 characters.'
    exit 1
  fi
fi

# PyAV's bundled ALSA library may point to a build-time /tmp/vendor path.
# Use the Pi's installed ALSA definitions, preserving explicit overrides.
export ALSA_CONFIG_PATH="${ALSA_CONFIG_PATH:-/usr/share/alsa/alsa.conf}"
export ALSA_CONFIG_DIR="${ALSA_CONFIG_DIR:-/usr/share/alsa}"

# Serialize launches and keep the lock while the app owns the hardware.
# Existing instances started before this lock was added are handled below.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/zee-ai-bot-webcam-${UID}.lock"
if ! flock -n 9; then
  printf '%s\n' 'ZeeAIBotWebCam is already running. Stop it with Ctrl+C before restarting.'
  exit 1
fi

# Restart only app processes launched from this checkout, waiting for cleanup.
python - <<'PYTHON'
from pathlib import Path
import sys
import psutil

root = Path.cwd()
previous = []
for process in psutil.process_iter(["pid", "cmdline", "cwd"]):
    try:
        args = process.info["cmdline"] or []
        if (len(args) == 3 and args[1:] == ["-m", "robotic_classroom.main"]
                and Path(args[0]).name.startswith("python")
                and process.info["cwd"] == str(root)):
            print(f"Stopping previous ZeeAIBotWebCam process: {process.pid}", flush=True)
            process.terminate()
            previous.append(process)
    except psutil.NoSuchProcess:
        continue
    except psutil.AccessDenied as exc:
        sys.exit(f"Cannot inspect or stop an existing app process: {exc}")
_, alive = psutil.wait_procs(previous, timeout=20)
if alive:
    sys.exit("Previous app still owns hardware; stop it before retrying. PIDs: "
             + ", ".join(str(process.pid) for process in alive))
PYTHON

# Refuse to continue if another process still owns the application port.
if command -v ss >/dev/null 2>&1 && ss -ltnp 2>/dev/null | grep -q ':8000 '; then
  printf '%s\n' 'Port 8000 is still in use. Stop the process shown below before starting:'
  ss -ltnp 2>/dev/null | grep ':8000 ' || true
  exit 1
fi

# Clear stale overrides from earlier development/testing sessions.
unset HARDWARE_MODE
unset CAMERA_MODE
unset TRACKING_ENABLED
unset PAN_TILT_HARDWARE_ENABLED
unset PAN_TILT_CALIBRATION_VALIDATED
unset PAN_TILT_CONTROL_ENABLED
unset PAN_TILT_CONTROL_MODE

# Force the validated Raspberry Pi hardware profile.
export APP_CONFIG=config.pi.yaml
export HARDWARE_MODE=real
export CAMERA_MODE=imx500
export TRACKING_ENABLED=true
export PAN_TILT_HARDWARE_ENABLED=true
export PAN_TILT_CALIBRATION_VALIDATED=true
export PAN_TILT_CONTROL_ENABLED=true
export PAN_TILT_CONTROL_MODE=execute

printf '%s\n' 'Starting ZeeAIBotWebCam with Raspberry Pi hardware profile...'
printf '%s\n' 'PAN:  channel 1, 1350 left, 1500 center, 1650 right'
printf '%s\n' 'TILT: channel 2, 1350 up,   1500 center, 1650 down'
printf '%s\n' 'Autonomous chassis execution remains gated by config.pi.yaml.'

exec python -m robotic_classroom.main
