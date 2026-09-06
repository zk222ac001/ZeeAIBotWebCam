#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

# Stop only stale instances of this project before opening the camera/UART again.
# Duplicate app instances can lock both the IMX500 camera and /dev/ttyAMA0.
OLD_PIDS="$(pgrep -f 'python(3)? -m robotic_classroom\.main' || true)"
if [ -n "$OLD_PIDS" ]; then
  printf '%s\n' "Stopping previous ZeeAIBotWebCam process(es): $OLD_PIDS"
  kill $OLD_PIDS 2>/dev/null || true
  sleep 2
fi

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
printf '%s\n' 'Chassis motion remains disabled.'

exec python -m robotic_classroom.main
