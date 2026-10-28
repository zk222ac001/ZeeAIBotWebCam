#!/usr/bin/env bash
# Prepare an extracted release in its own directory; never start robot services.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f release-manifest.json ] || [ ! -f runtime.constraints.txt ]; then
  echo 'Run this installer from an extracted release bundle.' >&2
  exit 1
fi
python3 scripts/verify_release.py "$ROOT_DIR"
if [ -e .venv ]; then
  echo 'Refusing to replace an existing .venv. Use a new release directory.' >&2
  exit 1
fi

# Pi camera and board drivers are provided by Raspberry Pi OS, outside pip.
python3 -m venv --system-site-packages .venv
.venv/bin/python - <<'PY'
from pathlib import Path
import subprocess
import sys

wheels = list(Path('artifacts').glob('*.whl'))
if len(wheels) != 1:
    raise SystemExit('Expected exactly one application wheel')
subprocess.run([sys.executable, '-m', 'pip', 'install', '--constraint',
                'runtime.constraints.txt', f'{wheels[0].resolve()}[webrtc]'], check=True)
PY

echo 'Release environment prepared. No service was installed, restarted or promoted.'
echo 'Prepare the device SDK, local certificates and managed credentials as documented.'
echo 'Then run deployment_preflight.py with the intended service environment before supervised activation.'
