# Phase 1 — Development Environment and Software Foundation

## Goal

Create a reproducible, hardware-safe development foundation that runs on Raspberry Pi and on a normal development workstation without commanding the robot.

## Target environment

Recommended production candidate:

- Raspberry Pi OS 64-bit;
- Debian 13 Trixie where hardware compatibility is confirmed;
- Python 3.11–3.13 supported by this project;
- ARM64 on Raspberry Pi;
- project virtual environment with system site packages so Raspberry Pi camera packages remain visible.

Do not destroy a known-working Hiwonder SD card. Back it up before changing the operating system or controller configuration.

## Install

On Raspberry Pi:

```bash
git clone https://github.com/zk222ac001/ZeeAIBotWebCam.git
cd ZeeAIBotWebCam
chmod +x scripts/bootstrap_pi.sh scripts/environment_report.sh
./scripts/bootstrap_pi.sh
```

Manual environment creation:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Why `--system-site-packages`?

Raspberry Pi camera support is commonly installed through the operating-system package manager. A virtual environment that cannot see system packages may not be able to import Picamera2 or the IMX500 integration.

## Configuration

The default `config.yaml` is intentionally safe:

```yaml
hardware:
  mode: mock

safety:
  motion_enabled: false
```

Environment variables may override the hardware backend:

```bash
export HARDWARE_MODE=mock
```

Real read-only probe mode is selected only for explicit hardware validation:

```bash
export HARDWARE_MODE=real
```

## Critical lazy-import rule

The upstream Hiwonder `Board` constructor opens the serial device during initialization and starts its receive infrastructure. Therefore the real hardware module must not be imported as a normal module-level dependency in mock mode.

`hardware/factory.py` imports the real backend only after configuration explicitly selects `real`.

## Run application

```bash
source .venv/bin/activate
python -m robotic_classroom.main
```

or:

```bash
robotic-classroom
```

Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/docs`

Expected mock health response includes:

```json
{
  "status": "ok",
  "hardware": {
    "backend": "mock",
    "connected": true
  },
  "motion_enabled": false,
  "recording_enabled": false,
  "face_recognition_enabled": false
}
```

## Tests

```bash
pytest -v
ruff check src tests
```

CI also runs in mock mode so GitHub Actions can never contact physical robot hardware.

## Development on Windows

```powershell
git clone https://github.com/zk222ac001/ZeeAIBotWebCam.git
cd ZeeAIBotWebCam
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
$env:HARDWARE_MODE="mock"
python -m robotic_classroom.main
```

Do not use `source .venv/bin/activate` in Windows PowerShell.

## Raspberry Pi environment report

Run:

```bash
./scripts/environment_report.sh
```

Record its output before Phase 2. It checks:

- OS and kernel;
- architecture;
- Python;
- memory/storage;
- `/dev/ttyAMA0`;
- USB devices;
- Picamera2/IMX500 imports;
- microphone/speaker enumeration;
- temperature.

## Phase 1 acceptance criteria

- [ ] Working Hiwonder installation preserved/backed up.
- [ ] Raspberry Pi OS, architecture and Python version recorded.
- [x] Production repository created.
- [x] Python packaging defined in `pyproject.toml`.
- [x] Safe `config.yaml` provided.
- [x] `HARDWARE_MODE=mock` implemented.
- [x] Mock backend implemented.
- [x] Real backend uses lazy vendor import.
- [x] Real Phase 1 probe contains no motor/servo API.
- [x] FastAPI `/health` implemented.
- [x] FastAPI `/ready` implemented.
- [x] Unit/integration tests added.
- [x] CI uses mock mode.
- [x] Bootstrap and environment-report scripts added.
- [x] Motion defaults to disabled.
- [ ] Physical controller and devices validated — Phase 2.

## Next phase

Phase 2 validates physical hardware in a controlled order:

1. Raspberry Pi and OS;
2. controller serial communication;
3. battery telemetry;
4. ultrasonic sensor and units;
5. individual motors at low duty/short duration;
6. Mecanum directions;
7. pan servo;
8. tilt servo;
9. IMX500 detection;
10. microphone;
11. speaker.

Full-chassis movement must not be the first hardware test.
