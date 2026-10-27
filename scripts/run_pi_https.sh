#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

CERT_DIR="$ROOT_DIR/.local-certs"
CERT_FILE="$CERT_DIR/zee-server.crt"
KEY_FILE="$CERT_DIR/zee-server.key"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
  echo "HTTPS certificate files are missing."
  echo "Run: ./scripts/setup_https.sh"
  exit 1
fi

export UVICORN_SSL_CERTFILE="$CERT_FILE"
export UVICORN_SSL_KEYFILE="$KEY_FILE"

exec "$ROOT_DIR/scripts/run_pi.sh"
