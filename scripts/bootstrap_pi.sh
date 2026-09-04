#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "[1/6] Updating apt metadata"
sudo apt update

echo "[2/6] Installing system packages"
sudo apt install -y \
  git \
  build-essential \
  python3 \
  python3-dev \
  python3-venv \
  python3-pip \
  python3-serial \
  python3-smbus \
  python3-smbus2 \
  python3-numpy \
  python3-opencv \
  python3-picamera2 \
  python3-munkres \
  ffmpeg \
  alsa-utils \
  libusb-1.0-0 \
  i2c-tools \
  usbutils \
  curl

echo "[3/6] Installing IMX500 support when available"
if apt-cache show imx500-all >/dev/null 2>&1; then
  sudo apt install -y imx500-all
else
  echo "imx500-all is not available from the configured apt sources; skipping."
fi

echo "[4/6] Creating Python virtual environment"
if [[ ! -d .venv ]]; then
  python3 -m venv --system-site-packages .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

echo "[5/6] Cloning Hiwonder TurboPi vendor repository"
mkdir -p vendor
if [[ ! -d vendor/TurboPi/.git ]]; then
  git clone https://github.com/Hiwonder/TurboPi.git vendor/TurboPi
else
  echo "vendor/TurboPi already exists; leaving it unchanged."
fi

echo "[6/6] Running tests in mock mode"
export HARDWARE_MODE=mock
export CAMERA_MODE=mock
export AUDIO_MODE=mock
pytest -v

echo
echo "Bootstrap complete."
echo "Activate with: source .venv/bin/activate"
echo "Run app with:  python -m robotic_classroom.main"
echo "Phase 2 read-only checks: python scripts/phase2_readonly_check.py --system"
echo "Phase 7 audio check: python scripts/phase7_audio_check.py"
echo "Motion remains disabled in the application by default."
