#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$ROOT_DIR/deploy/systemd/zee-robot.service.in"
ENV_TEMPLATE="$ROOT_DIR/deploy/systemd/zee-robot.env.example"
UNIT_NAME="zee-robot.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
ENV_DIR="/etc/zee-robot"
ENV_PATH="$ENV_DIR/zee-robot.env"
START_NOW=false

usage() {
  cat <<'EOF'
Usage: ./scripts/install_systemd_service.sh [--start]

Installs and enables the ZeeAIBotWebCam systemd service.
By default it does not start the service, so an existing manual robot session
is not interrupted. Pass --start only after stopping any manually launched app.
EOF
}

case "${1:-}" in
  "") ;;
  --start) START_NOW=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd/systemctl is required." >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to install the system service." >&2
  exit 1
fi
if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Missing virtual environment: $ROOT_DIR/.venv/bin/python" >&2
  echo "Create/install the project environment before installing the service." >&2
  exit 1
fi

for required in   "$ROOT_DIR/config.pi.yaml"   "$ROOT_DIR/scripts/run_pi_https.sh"   "$ROOT_DIR/.local-certs/zee-server.crt"   "$ROOT_DIR/.local-certs/zee-server.key"   "$ROOT_DIR/.local-certs/zee-local-ca.crt"
do
  if [ ! -r "$required" ]; then
    echo "Required deployment file is missing or unreadable: $required" >&2
    exit 1
  fi
done

SERVICE_USER="${SUDO_USER:-$(id -un)}"
if [ "$SERVICE_USER" = "root" ]; then
  echo "Run this installer from the normal Raspberry Pi account, not a root login." >&2
  exit 1
fi
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

SUPPLEMENTARY_GROUPS=""
for candidate in dialout audio video render gpio i2c; do
  if getent group "$candidate" >/dev/null 2>&1; then
    if [ -n "$SUPPLEMENTARY_GROUPS" ]; then
      SUPPLEMENTARY_GROUPS="$SUPPLEMENTARY_GROUPS $candidate"
    else
      SUPPLEMENTARY_GROUPS="$candidate"
    fi
  fi
done

TMP_UNIT="$(mktemp)"
trap 'rm -f "$TMP_UNIT"' EXIT

/usr/bin/python3 - "$TEMPLATE" "$TMP_UNIT"   "$SERVICE_USER" "$SERVICE_GROUP" "$SUPPLEMENTARY_GROUPS"   "$ROOT_DIR" "$ROOT_DIR/.venv/bin/python" <<'PY'
from pathlib import Path
import sys

source, destination, user, group, extra_groups, root, python = sys.argv[1:]
text = Path(source).read_text(encoding="utf-8")
replacements = {
    "@USER@": user,
    "@GROUP@": group,
    "@SUPPLEMENTARY_GROUPS@": extra_groups,
    "@ROOT@": root,
    "@PYTHON@": python,
}
for old, new in replacements.items():
    text = text.replace(old, new)
if "@" in text:
    raise SystemExit("Unresolved systemd template placeholder")
Path(destination).write_text(text, encoding="utf-8")
PY

sudo install -d -m 0755 "$ENV_DIR"
if [ ! -e "$ENV_PATH" ]; then
  sudo install -m 0600 "$ENV_TEMPLATE" "$ENV_PATH"
  echo "Created $ENV_PATH"
else
  echo "Keeping existing $ENV_PATH"
fi

sudo install -m 0644 "$TMP_UNIT" "$UNIT_PATH"
sudo systemctl daemon-reload
sudo systemctl enable "$UNIT_NAME"

echo
echo "Installed: $UNIT_PATH"
echo "Enabled at boot: $UNIT_NAME"
echo "Service user: $SERVICE_USER"
echo "Working directory: $ROOT_DIR"
echo

if [ "$START_NOW" = true ]; then
  echo "Starting $UNIT_NAME..."
  sudo systemctl restart "$UNIT_NAME"
  sudo systemctl --no-pager --full status "$UNIT_NAME"
else
  echo "The service was NOT started."
  echo "Stop any manually running app, then start with:"
  echo "  sudo systemctl start $UNIT_NAME"
fi
