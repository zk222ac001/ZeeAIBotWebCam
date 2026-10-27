#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CERT_DIR="$ROOT_DIR/.local-certs"
mkdir -p "$CERT_DIR"

if ! command -v openssl >/dev/null 2>&1; then
  echo "OpenSSL is required. Install it with: sudo apt update && sudo apt install -y openssl"
  exit 1
fi

PI_IP="$(hostname -I | awk '{print $1}')"
if [ -z "$PI_IP" ]; then
  echo "Could not determine Raspberry Pi IP address."
  exit 1
fi

HOSTNAME_VALUE="$(hostname)"
CA_KEY="$CERT_DIR/zee-local-ca.key"
CA_CERT="$CERT_DIR/zee-local-ca.crt"
SERVER_KEY="$CERT_DIR/zee-server.key"
SERVER_CSR="$CERT_DIR/zee-server.csr"
SERVER_CERT="$CERT_DIR/zee-server.crt"
EXTFILE="$CERT_DIR/zee-server.ext"

if [ ! -f "$CA_KEY" ] || [ ! -f "$CA_CERT" ]; then
  openssl genrsa -out "$CA_KEY" 2048
  openssl req -x509 -new -nodes -key "$CA_KEY" -sha256 -days 1825     -out "$CA_CERT" -subj "/CN=ZeeAIBotWebCam Local CA"
fi

openssl genrsa -out "$SERVER_KEY" 2048
openssl req -new -key "$SERVER_KEY" -out "$SERVER_CSR"   -subj "/CN=$PI_IP"

cat > "$EXTFILE" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=@alt_names

[alt_names]
IP.1=$PI_IP
DNS.1=localhost
DNS.2=$HOSTNAME_VALUE
EOF

openssl x509 -req -in "$SERVER_CSR" -CA "$CA_CERT" -CAkey "$CA_KEY"   -CAcreateserial -out "$SERVER_CERT" -days 825 -sha256 -extfile "$EXTFILE"

chmod 600 "$CA_KEY" "$SERVER_KEY"
chmod 644 "$CA_CERT" "$SERVER_CERT"

echo
echo "HTTPS certificates created."
echo "Pi IP: $PI_IP"
echo "CA certificate to install/trust on the phone:"
echo "  $CA_CERT"
echo
echo "After trusting that CA certificate on the phone, start with:"
echo "  ./scripts/run_pi_https.sh"
echo
echo "Then open:"
echo "  https://$PI_IP:8000/conference"
