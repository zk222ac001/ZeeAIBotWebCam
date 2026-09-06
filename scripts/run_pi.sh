#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
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
