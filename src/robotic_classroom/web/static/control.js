/* Commands are deliberate; polling and page load never acquire control or move. */
(() => {
  'use strict';
  const Z = window.Zee;
  let token = null, heartbeatTimer = null, heartbeatBusy = false, moving = false;
  let acquiring = false, robotState = null, safetyReady = false, epoch = 0, motionOutstanding = false;
  let commandQueue = Promise.resolve();
  const directions = {
    forward: {forward: 1, sideways: 0, rotation: 0}, backward: {forward: -1, sideways: 0, rotation: 0},
    left: {forward: 0, sideways: -1, rotation: 0}, right: {forward: 0, sideways: 1, rotation: 0},
    'rotate-left': {forward: 0, sideways: 0, rotation: -1}, 'rotate-right': {forward: 0, sideways: 0, rotation: 1},
  };
  const setMessage = message => Z.text('message', message);
  function enableMoves() { document.querySelectorAll('.move').forEach(button => { button.disabled = !(token && safetyReady && !acquiring); }); }
  function clearLease() {
    token = null; clearInterval(heartbeatTimer); heartbeatTimer = null; enableMoves();
    Z.badge('leaseMetric', 'No control', 'neutral'); Z.text('leaseStatus', 'No active control lease.');
  }
  async function sendMotion(command) {
    return Z.api('/api/control/motion', {method: 'POST', scope: 'control', body: JSON.stringify({...command, ...(token ? {token} : {})})});
  }
  function enqueue(action) {
    const next = commandQueue.then(action); commandQueue = next.catch(() => {}); return next;
  }
  async function stopMotion() {
    const wasMoving = moving; moving = false; epoch++;
    try { await enqueue(async () => { await sendMotion({forward: 0, sideways: 0, rotation: 0}); motionOutstanding = false; }); if (wasMoving) setMessage('STOP accepted.'); }
    catch (error) { setMessage(`STOP request failed: ${error.message}`); Z.errorNotice(error); }
  }
  async function startMotion(direction) {
    if (moving) return;
    if (!token || !safetyReady) { setMessage('Acquire control and wait for a healthy safety status before moving.'); return; }
    moving = true; const started = ++epoch;
    try {
      await enqueue(async () => {
        if (!moving || started !== epoch || !token || !safetyReady) return;
        motionOutstanding = true;
        const result = await sendMotion(directions[direction]);
        if (started === epoch && moving) setMessage(`${Z.human(direction)}: ${result.reason}`);
      });
    } catch (error) {
      moving = false; epoch++; safetyReady = false; enableMoves(); setMessage(`Motion refused: ${error.message}`);
    }
  }
  async function heartbeatOnce() {
    if (!token || heartbeatBusy) return; heartbeatBusy = true;
    try { await Z.api('/api/control/heartbeat', {method: 'POST', scope: 'control', timeout: 1200, body: JSON.stringify({token})}); }
    catch (error) {
      const wasMoving = moving; clearLease(); safetyReady = false; enableMoves();
      setMessage(`Control heartbeat lost: ${error.message}`); if (wasMoving) await stopMotion();
    } finally { heartbeatBusy = false; }
  }
  async function acquireLease() {
    if (acquiring) return false; acquiring = true; Z.$('leaseBtn').disabled = true; enableMoves();
    try {
      const data = await Z.api('/api/control/lease', {method: 'POST', scope: 'control', body: JSON.stringify({owner: Z.$('owner').value.trim() || 'browser-operator'})});
      token = data.token; clearInterval(heartbeatTimer); heartbeatTimer = setInterval(heartbeatOnce, 250);
      Z.text('leaseStatus', `Control acquired. Heartbeats keep your ${data.ttl_seconds}s lease fresh.`); Z.badge('leaseMetric', 'Control active', 'success');
      setMessage('Control acquired. Press and hold a direction to move.'); await heartbeatOnce(); return Boolean(token);
    } catch (error) { setMessage(`Could not acquire control: ${error.message}`); Z.errorNotice(error); return false; }
    finally { acquiring = false; Z.$('leaseBtn').disabled = false; enableMoves(); }
  }
  for (const button of document.querySelectorAll('.move')) {
    button.addEventListener('pointerdown', event => { event.preventDefault(); button.setPointerCapture?.(event.pointerId); void startMotion(button.dataset.dir); });
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) button.addEventListener(name, event => { event.preventDefault(); if (moving) void stopMotion(); });
    button.addEventListener('keydown', event => { if ([' ', 'Enter'].includes(event.key)) { event.preventDefault(); if (!event.repeat) void startMotion(button.dataset.dir); } });
    button.addEventListener('keyup', event => { if ([' ', 'Enter'].includes(event.key)) { event.preventDefault(); if (moving) void stopMotion(); } });
  }
  Z.$('leaseBtn').onclick = acquireLease; Z.$('stopBtn').onclick = stopMotion;
  Z.$('estopBtn').onclick = async () => {
    moving = false; epoch++; clearLease(); safetyReady = false; enableMoves();
    try { await Z.api('/api/control/emergency-stop', {method: 'POST', scope: 'control'}); motionOutstanding = false;
      setMessage('Emergency stop is active. Acquire fresh control before requesting a reset.'); await refreshStatus(); }
    catch (error) { setMessage(`Emergency-stop request failed: ${error.message}. Physical motion is unconfirmed.`); Z.errorNotice(error); }
  };
  Z.$('resetBtn').onclick = async () => {
    if (!['emergency_stop', 'fault'].includes(robotState)) return;
    Z.$('resetBtn').disabled = true;
    try {
      if (!token && !await acquireLease()) return;
      const result = await Z.api('/api/control/reset-stop', {method: 'POST', scope: 'control', body: JSON.stringify({token})});
      setMessage(`${result.status}. Press a direction deliberately to start movement.`); await refreshStatus();
    } catch (error) { setMessage(`Reset refused: ${error.message}`); Z.errorNotice(error); }
    finally { Z.$('resetBtn').disabled = !['emergency_stop', 'fault'].includes(robotState); }
  };
  async function refreshStatus() {
    try {
      const [sensors, safety] = await Promise.all([Z.api('/api/sensors'), Z.api('/api/safety')]);
      robotState = safety.state; safetyReady = robotState === 'idle' && safety.motion_enabled && safety.watchdog_running && !safety.sensor_blocker;
      Z.text('distance', Z.finite(sensors.distance_cm) ? `${sensors.distance_cm.toFixed(1)} cm` : 'Unavailable');
      Z.text('robotState', Z.human(safety.state)); Z.text('motionEnabled', safety.motion_enabled ? 'Enabled' : 'Disabled');
      Z.text('motionActive', safety.motion_active ? 'Active' : 'Inactive'); Z.text('heartbeat', safety.heartbeat_fresh ? 'Fresh' : 'Expired');
      Z.text('watchdog', safety.watchdog_running ? 'Running' : 'Not running'); Z.text('obstacleLimit', `${safety.minimum_obstacle_distance_cm} cm`);
      Z.$('resetBtn').disabled = !['emergency_stop', 'fault'].includes(safety.state); enableMoves();
      if (!safetyReady && moving) await stopMotion();
    } catch (error) {
      safetyReady = false; robotState = null; enableMoves(); Z.$('resetBtn').disabled = true;
      for (const id of ['distance','robotState','motionEnabled','motionActive','heartbeat','watchdog','obstacleLimit']) Z.text(id, 'Unavailable');
      setMessage(`Safety status unavailable: ${error.message}`); if (moving) await stopMotion();
    }
  }
  enableMoves(); Z.poll(refreshStatus, 500);
  window.addEventListener('blur', () => { if (moving || motionOutstanding) void stopMotion(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden && moving) void stopMotion(); });
  window.addEventListener('pagehide', () => {
    clearInterval(heartbeatTimer);
    if (moving || motionOutstanding) { moving = false; epoch++;
      void fetch('/api/control/motion', {method: 'POST', keepalive: true,
        headers: {...Z.headers('control'), 'Content-Type': 'application/json'},
        body: JSON.stringify({forward: 0, sideways: 0, rotation: 0, ...(token ? {token} : {})})}).catch(() => {});
    }
  });
})();
