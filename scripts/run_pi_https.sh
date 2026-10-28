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

# DHCP can change the Pi address while the existing certificate still names
# the previous network. Reissue with the same local CA to preserve client trust.
PI_IP="$(hostname -I | awk '{print $1}')"
if [ -z "$PI_IP" ]; then
  echo "Could not determine Raspberry Pi IP address."
  exit 1
fi
if ! openssl x509 -in "$CERT_FILE" -noout -checkip "$PI_IP" >/dev/null 2>&1 \
    || ! openssl x509 -in "$CERT_FILE" -noout -checkend 86400 >/dev/null 2>&1; then
  echo "Refreshing HTTPS certificate for $PI_IP..."
  "$ROOT_DIR/scripts/setup_https.sh"
fi

export UVICORN_SSL_CERTFILE="$CERT_FILE"
export UVICORN_SSL_KEYFILE="$KEY_FILE"

exec "$ROOT_DIR/scripts/run_pi.sh"
