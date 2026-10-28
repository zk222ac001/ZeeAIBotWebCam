#!/usr/bin/env bash
# Read the managed environment through systemd without exposing or sourcing it.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$(id -un)}"
if [ "$SERVICE_USER" = root ]; then
  echo 'Run from the normal Pi account so checks use its filesystem permissions.' >&2
  exit 1
fi
sudo systemd-run --quiet --wait --pipe --collect \
  --unit="zee-preflight-$$" \
  --property="User=$SERVICE_USER" \
  --property="WorkingDirectory=$ROOT_DIR" \
  --property=EnvironmentFile=/etc/zee-robot/zee-robot.env \
  "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/deployment_preflight.py" "$@"
