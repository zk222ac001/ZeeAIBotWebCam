from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/ui", response_class=HTMLResponse)
def control_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ZeeAIBotWebCam Control</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, sans-serif; max-width: 980px; margin: 1.2rem auto; padding: 0 1rem 2rem; }
    h1 { margin-bottom: .3rem; }
    .hint { opacity: .8; margin-top: 0; }
    .layout { display: grid; grid-template-columns: minmax(310px, 1fr) minmax(280px, .9fr); gap: 1rem; }
    .card { border: 1px solid #8887; border-radius: 14px; padding: 1rem; }
    .status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .55rem; }
    .metric { border: 1px solid #8885; border-radius: 10px; padding: .65rem; }
    .metric strong { display: block; font-size: .78rem; opacity: .7; margin-bottom: .2rem; }
    .controls { display: grid; grid-template-columns: repeat(3, minmax(78px, 1fr)); gap: .55rem; max-width: 430px; margin: .8rem auto; }
    button { min-height: 58px; padding: .7rem; font-size: 1rem; border-radius: 11px; border: 1px solid #8888; cursor: pointer; touch-action: none; }
    button:disabled { opacity: .45; cursor: not-allowed; }
    .move { font-weight: 700; }
    .stop { font-weight: 800; font-size: 1.1rem; }
    .estop { width: 100%; min-height: 68px; font-weight: 900; font-size: 1.15rem; border: 2px solid currentColor; }
    .lease-row { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
    input { padding: .7rem; border-radius: 9px; border: 1px solid #8888; flex: 1; min-width: 180px; }
    #message { white-space: pre-wrap; min-height: 3.2rem; border-radius: 10px; padding: .7rem; background: #8882; }
    .links a { margin-right: 1rem; }
    @media (max-width: 760px) { .layout { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <h1>ZeeAIBotWebCam Robot Control</h1>
  <p class="hint">Press and hold a direction button to move. Releasing it sends STOP. The 750 ms deadman watchdog remains active.</p>

  <div class="layout">
    <section class="card">
      <h2>Operator control</h2>
      <div class="lease-row">
        <input id="owner" value="browser-operator" maxlength="100" aria-label="Operator name">
        <button id="leaseBtn">Acquire Control</button>
      </div>
      <p id="leaseStatus">No control lease</p>

      <div class="controls" aria-label="Robot movement controls">
        <button class="move" data-dir="rotate-left">↶ Rotate</button>
        <button class="move" data-dir="forward">▲ Forward</button>
        <button class="move" data-dir="rotate-right">Rotate ↷</button>
        <button class="move" data-dir="left">◀ Left</button>
        <button class="stop" id="stopBtn">■ STOP</button>
        <button class="move" data-dir="right">Right ▶</button>
        <span></span>
        <button class="move" data-dir="backward">▼ Backward</button>
        <span></span>
      </div>

      <button class="estop" id="estopBtn">EMERGENCY STOP</button>
      <p class="hint">Emergency stop does not require a lease and always overrides movement.</p>
    </section>

    <section class="card">
      <h2>Live safety</h2>
      <div class="status-grid">
        <div class="metric"><strong>Distance</strong><span id="distance">-</span></div>
        <div class="metric"><strong>Robot state</strong><span id="robotState">-</span></div>
        <div class="metric"><strong>Motion enabled</strong><span id="motionEnabled">-</span></div>
        <div class="metric"><strong>Motion active</strong><span id="motionActive">-</span></div>
        <div class="metric"><strong>Heartbeat</strong><span id="heartbeat">-</span></div>
        <div class="metric"><strong>Watchdog</strong><span id="watchdog">-</span></div>
        <div class="metric"><strong>Obstacle limit</strong><span id="obstacleLimit">-</span></div>
        <div class="metric"><strong>Lease</strong><span id="leaseMetric">none</span></div>
      </div>
      <h3>Message</h3>
      <div id="message">Ready. Acquire control before moving.</div>
      <p class="links"><a href="/conference">Conference</a><a href="/operator">System dashboard</a></p>
    </section>
  </div>

<script>
let token = null;
let heartbeatTimer = null;
let moving = false;
let acquiring = false;

const directions = {
  forward:      {forward: 1, sideways: 0, rotation: 0},
  backward:     {forward: -1, sideways: 0, rotation: 0},
  left:         {forward: 0, sideways: -1, rotation: 0},
  right:        {forward: 0, sideways: 1, rotation: 0},
  'rotate-left':  {forward: 0, sideways: 0, rotation: -1},
  'rotate-right': {forward: 0, sideways: 0, rotation: 1},
};

function setMessage(text) {
  document.getElementById('message').textContent = text;
}

function setMoveButtonsEnabled(enabled) {
  document.querySelectorAll('.move').forEach(button => button.disabled = !enabled);
}
setMoveButtonsEnabled(false);

async function api(path, options={}) {
  const response = await fetch(path, options);
  let data = null;
  try { data = await response.json(); } catch (_) { data = {detail: await response.text()}; }
  if (!response.ok) {
    const error = new Error(data.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function acquireLease() {
  if (acquiring) return false;
  acquiring = true;
  try {
    const owner = document.getElementById('owner').value.trim() || 'browser-operator';
    const data = await api('/api/control/lease', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({owner})
    });
    token = data.token;
    document.getElementById('leaseStatus').textContent = `Control acquired for ${data.ttl_seconds}s; auto-renews after expiry.`;
    document.getElementById('leaseMetric').textContent = 'active';
    setMoveButtonsEnabled(true);
    startHeartbeat();
    setMessage('Control lease acquired. Hold a direction button to move.');
    return true;
  } catch (error) {
    setMessage(`Could not acquire control: ${error.message}`);
    return false;
  } finally {
    acquiring = false;
  }
}

document.getElementById('leaseBtn').onclick = acquireLease;

async function heartbeatOnce() {
  if (!token) return;
  try {
    await api('/api/control/heartbeat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token})
    });
  } catch (error) {
    if (error.status === 403) {
      token = null;
      setMoveButtonsEnabled(false);
      document.getElementById('leaseMetric').textContent = 'expired';
      if (moving) await stopMotion();
      await acquireLease();
    } else {
      setMessage(`Heartbeat error: ${error.message}`);
    }
  }
}

function startHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = setInterval(heartbeatOnce, 250);
  heartbeatOnce();
}

async function sendMotion(command) {
  const body = {...command};
  if (token) body.token = token;
  return api('/api/control/motion', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
}

async function startMotion(direction) {
  if (moving) return;
  if (!token) {
    setMessage('Acquire control before moving.');
    return;
  }
  moving = true;
  try {
    const result = await sendMotion(directions[direction]);
    setMessage(`${direction}: ${result.reason}`);
  } catch (error) {
    moving = false;
    setMessage(`Motion refused: ${error.message}`);
  }
}

async function stopMotion() {
  const wasMoving = moving;
  moving = false;
  try {
    await sendMotion({forward: 0, sideways: 0, rotation: 0});
    if (wasMoving) setMessage('STOP sent.');
  } catch (error) {
    setMessage(`STOP request error: ${error.message}`);
  }
}

for (const button of document.querySelectorAll('.move')) {
  const direction = button.dataset.dir;
  button.addEventListener('pointerdown', event => {
    event.preventDefault();
    button.setPointerCapture?.(event.pointerId);
    startMotion(direction);
  });
  for (const eventName of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    button.addEventListener(eventName, event => {
      event.preventDefault();
      stopMotion();
    });
  }
}

document.getElementById('stopBtn').onclick = stopMotion;

document.getElementById('estopBtn').onclick = async () => {
  moving = false;
  try {
    await api('/api/control/emergency-stop', {method: 'POST'});
    setMoveButtonsEnabled(false);
    setMessage('EMERGENCY STOP ACTIVE. Motion is blocked until reset through an authorized control workflow.');
  } catch (error) {
    setMessage(`Emergency-stop request error: ${error.message}`);
  }
};

async function refreshStatus() {
  try {
    const [sensors, safety] = await Promise.all([
      api('/api/sensors'),
      api('/api/safety')
    ]);
    document.getElementById('distance').textContent = sensors.distance_cm == null ? 'unavailable' : `${Number(sensors.distance_cm).toFixed(1)} cm`;
    document.getElementById('robotState').textContent = safety.state;
    document.getElementById('motionEnabled').textContent = String(safety.motion_enabled);
    document.getElementById('motionActive').textContent = String(safety.motion_active);
    document.getElementById('heartbeat').textContent = safety.heartbeat_fresh ? 'fresh' : 'expired';
    document.getElementById('watchdog').textContent = safety.watchdog_running ? 'running' : 'NOT RUNNING';
    document.getElementById('obstacleLimit').textContent = `${Number(safety.minimum_obstacle_distance_cm).toFixed(1)} cm`;

    if (safety.state !== 'idle' || !safety.motion_enabled || !safety.watchdog_running) {
      setMoveButtonsEnabled(false);
    } else if (token) {
      setMoveButtonsEnabled(true);
    }
  } catch (error) {
    setMessage(`Status error: ${error.message}`);
  }
}

setInterval(refreshStatus, 500);
refreshStatus();
window.addEventListener('blur', stopMotion);
</script>
</body>
</html>"""
