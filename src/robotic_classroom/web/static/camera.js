(() => {
  'use strict';
  const Z = window.Zee, canvas = Z.$('preview'), context = canvas.getContext('2d');
  const deadZoneX = Number(document.body.dataset.deadZoneX), deadZoneY = Number(document.body.dataset.deadZoneY);
  const observationTimeoutMs = Number(document.body.dataset.observationTimeoutMs);
  let cameraSequence = null, cameraSeenAt = 0, refreshing = false;
  function drawPreview(frame, camera, tracking) {
    canvas.width = frame.width; canvas.height = frame.height; context.drawImage(frame, 0, 0);
    const w = canvas.width, h = canvas.height, left = (.5 - deadZoneX) * w, top = (.5 - deadZoneY) * h;
    context.fillStyle = 'rgba(34,197,94,.15)'; context.fillRect(left, top, 2 * deadZoneX * w, 2 * deadZoneY * h);
    context.strokeStyle = '#22c55e'; context.lineWidth = 3; context.strokeRect(left, top, 2 * deadZoneX * w, 2 * deadZoneY * h);
    context.strokeStyle = '#fff'; context.beginPath();
    context.moveTo(w / 2 - 16, h / 2); context.lineTo(w / 2 + 16, h / 2);
    context.moveTo(w / 2, h / 2 - 16); context.lineTo(w / 2, h / 2 + 16); context.stroke();
    context.strokeStyle = '#38bdf8';
    for (const person of camera.people) { const b = person.box;
      context.strokeRect(b.x / camera.frame.width * w, b.y / camera.frame.height * h,
        b.width / camera.frame.width * w, b.height / camera.frame.height * h);
    }
    if (tracking.state === 'tracking' && tracking.center && Z.finite(tracking.center.x) && Z.finite(tracking.center.y)) {
      context.beginPath(); context.arc(tracking.center.x * w, tracking.center.y * h, 10, 0, Math.PI * 2);
      context.fillStyle = tracking.in_dead_zone ? '#22c55e' : '#fbbf24'; context.fill(); context.strokeStyle = '#fff'; context.stroke();
    }
  }
  function describe(plan, tracking) {
    if (plan.mode !== 'execute') return 'Preview only. Camera execution is disabled.';
    if (plan.center_hold) return 'Following paused. Select Resume tracking when you are in position.';
    if (plan.execution?.last_error) return `Camera command blocked: ${plan.execution.last_error}`;
    if (!plan.execution?.executed) return 'Camera command has not been executed.';
    if (tracking.state !== 'tracking' || !tracking.center) return 'No fresh tracking position. Camera is holding or returning to center.';
    const panLimit = [plan.pan.minimum, plan.pan.maximum].includes(plan.pan.planned_pulse);
    const tiltLimit = [plan.tilt.minimum, plan.tilt.maximum].includes(plan.tilt.planned_pulse);
    if ((panLimit && Math.abs(tracking.error?.x) > deadZoneX) || (tiltLimit && Math.abs(tracking.error?.y) > deadZoneY)) {
      return 'At a movement limit. Move closer to the middle of the picture.';
    }
    return tracking.in_dead_zone ? 'Person inside the center guide. The camera should hold this frame.' : 'Target outside the center guide.';
  }
  function empty(message) {
    context.clearRect(0, 0, canvas.width, canvas.height); canvas.hidden = true; Z.$('cameraEmpty').hidden = false;
    Z.text('cameraEmptyMessage', message);
  }
  async function refresh() {
    if (refreshing) return; refreshing = true;
    try {
      const [plan, camera, tracking] = await Promise.all([
        Z.api('/api/pan-tilt/plan'), Z.api('/api/camera/detections'), Z.api('/api/tracking/status'),
      ]);
      Z.clearNotice();
      const now = performance.now();
      if (camera.sequence !== cameraSequence) { cameraSequence = camera.sequence; cameraSeenAt = now; }
      if (!camera.connected || now - cameraSeenAt > observationTimeoutMs) throw new Error('Camera observations are stale or disconnected.');
      Z.text('cameraPeople', camera.people.length);
      Z.text('cameraPan', `${plan.pan.planned_pulse} / ${plan.pan.center} center`);
      Z.text('cameraTilt', `${plan.tilt.planned_pulse} / ${plan.tilt.center} center`);
      Z.text('cameraPosition', tracking.state === 'tracking' && tracking.center ? `${Math.round(tracking.center.x * 100)}% across` : 'Unavailable');
      Z.badge('trackingBadge', plan.center_hold ? 'Center hold' : Z.human(plan.state), plan.center_hold ? 'neutral' : tracking.in_dead_zone ? 'success' : 'warning');
      Z.text('message', plan.center_hold ? 'Camera held at calibrated center.' : 'Automatic following enabled.');
      Z.text('status', [plan.message, `Source: ${tracking.source}`, `Mode: ${plan.mode}`,
        `Execution: ${plan.execution?.executed ? 'submitted' : 'not executed'}`,
        plan.execution?.last_error || '', 'Commands do not measure physical servo position.'].filter(Boolean).join('\n'));
      if (camera.backend === 'mock') {
        empty('A simulated camera is configured. Real camera hardware is needed for a live preview.');
        Z.text('trackingFeedback', 'Simulated tracking data. Physical following cannot be checked in this workspace.');
        Z.text('framing', ''); return;
      }
      const frame = await createImageBitmap(await Z.api('/api/camera/frame.jpg', {responseType: 'blob'}));
      try { drawPreview(frame, camera, tracking); } finally { frame.close(); }
      canvas.hidden = false; Z.$('cameraEmpty').hidden = true;
      Z.text('trackingFeedback', describe(plan, tracking));
      const clipped = camera.people.some(({box: b}) => b.x <= .01 * camera.frame.width || b.x + b.width >= .99 * camera.frame.width || b.y <= .01 * camera.frame.height);
      Z.text('framing', clipped ? 'Person box touches the top or side. Step farther back for a steadier test.' : '');
    } catch (error) {
      empty(error.status === 401 ? 'Enter a conference token in Access settings to view the camera.' : 'Camera preview unavailable.');
      Z.text('trackingFeedback', 'A fresh preview is needed to judge framing.'); Z.text('framing', '');
      Z.badge('trackingBadge', 'Unavailable', 'neutral');
      for (const id of ['cameraPeople', 'cameraPosition', 'cameraPan', 'cameraTilt']) Z.text(id, '—');
      Z.errorNotice(error);
    } finally { refreshing = false; }
  }
  async function requestMode(mode) {
    Z.$('center').disabled = true; Z.$('resume').disabled = true;
    try {
      const data = await Z.api(`/api/pan-tilt/${mode}`, {method: 'POST', scope: 'control'});
      Z.text('message', data.message); await refresh();
    } catch (error) { Z.text('message', error.message); Z.errorNotice(error); }
    finally { Z.$('center').disabled = false; Z.$('resume').disabled = false; }
  }
  Z.$('center').onclick = () => requestMode('center'); Z.$('resume').onclick = () => requestMode('resume');
  Z.poll(refresh, 500);
})();
