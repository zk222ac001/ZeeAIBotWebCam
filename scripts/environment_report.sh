#!/usr/bin/env bash
set -u

echo "=== ZeeAIBotWebCam Environment Report ==="
echo

echo "-- OS --"
cat /etc/os-release 2>/dev/null || true

echo
echo "-- Kernel / Architecture --"
uname -a || true
uname -m || true

echo
echo "-- Python --"
python3 --version || true
which python3 || true

echo
echo "-- Memory --"
free -h || true

echo
echo "-- Storage --"
df -h / || true

echo
echo "-- Serial controller --"
ls -l /dev/ttyAMA0 2>/dev/null || echo "/dev/ttyAMA0 not found"

echo
echo "-- USB --"
lsusb 2>/dev/null || true

echo
echo "-- Camera tools --"
command -v rpicam-hello || true
python3 -c "from picamera2 import Picamera2; print('Picamera2: OK')" 2>/dev/null || echo "Picamera2: unavailable"

echo
echo "-- IMX500 Python support --"
python3 -c "from picamera2.devices.imx500 import IMX500; print('IMX500 import: OK')" 2>/dev/null || echo "IMX500 import: unavailable"

echo
echo "-- Audio devices --"
arecord -l 2>/dev/null || true
aplay -l 2>/dev/null || true

echo
echo "-- Temperature --"
vcgencmd measure_temp 2>/dev/null || true
