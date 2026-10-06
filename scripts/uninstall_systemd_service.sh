#!/usr/bin/env bash
set -eu

UNIT_NAME="zee-robot.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
ENV_DIR="/etc/zee-robot"
PURGE_ENV=false

case "${1:-}" in
  "") ;;
  --purge-env) PURGE_ENV=true ;;
  -h|--help)
    echo "Usage: ./scripts/uninstall_systemd_service.sh [--purge-env]"
    exit 0
    ;;
  *)
    echo "Usage: ./scripts/uninstall_systemd_service.sh [--purge-env]" >&2
    exit 2
    ;;
esac

sudo systemctl disable --now "$UNIT_NAME" 2>/dev/null || true
sudo rm -f "$UNIT_PATH"
sudo systemctl daemon-reload

if [ "$PURGE_ENV" = true ]; then
  sudo rm -rf "$ENV_DIR"
  echo "Removed $ENV_DIR"
else
  echo "Preserved optional deployment environment under $ENV_DIR"
fi

echo "Removed $UNIT_NAME"
