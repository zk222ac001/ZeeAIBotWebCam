(() => {
  'use strict';
  const Z = window.Zee;
  let cameraSequence = null, seenAt = 0;
  function emptyPreview(message) {
    Z.$('roomPreview').hidden = true; Z.$('previewEmpty').hidden = false;
    Z.text('previewMessage', message); Z.badge('previewBadge', 'Unavailable', 'neutral');
  }
  Z.poll(async () => {
    try {
      const [room, sensors, plan, readiness] = await Promise.all([
        Z.api('/api/operator/status'), Z.api('/api/sensors'),
        Z.api('/api/pan-tilt/plan'), Z.api('/api/readiness'),
      ]);
      Z.clearNotice();
      Z.text('cameraMetric', room.camera.running && room.camera.connected ? 'Online' : 'Offline');
      Z.text('cameraCaption', room.camera.backend === 'mock' ? 'Simulated camera' : 'IMX500 classroom camera');
      Z.text('batteryMetric', Z.finite(sensors.battery_voltage) ? `${sensors.battery_voltage.toFixed(2)} V` : '—');
      Z.text('batteryCaption', Z.health?.hardware?.backend === 'mock' ? 'Simulated voltage reading' : 'Live voltage reading');
      Z.text('peopleMetric', room.camera.people_count ?? '—');
      Z.text('sessionsMetric', room.conference.active_sessions ?? '—');
      Z.text('sessionsCaption', room.conference.backend === 'mock' ? 'Simulated conference service' : 'Active conference sessions');
      Z.text('audioState', room.audio.connected ? Z.human(room.audio.speech_state) : 'Unavailable');
      Z.text('speakerState', Z.human(room.active_speaker.state));
      Z.text('trackingState', plan.mode !== 'execute' ? 'Preview only' : plan.center_hold ? 'Center hold' : Z.human(plan.state));
      Z.text('safetyState', Z.human(room.safety.state));
      Z.text('roomNote', plan.mode !== 'execute' ? 'Camera planning is in preview mode. Physical following is disabled.' : plan.center_hold ? 'Camera is held at center. Resume following in Camera & tracking.' : 'Camera following is enabled. Chassis autonomy remains separately controlled.');
      const categories = Object.keys(Z.categoryNames).map(key => readiness.categories[key]);
      const passed = categories.filter(category => category.ready).length;
      Z.text('releaseTitle', readiness.production_ready ? 'Production checks complete' : 'A few checks to finish.');
      Z.text('releaseSummary', `${passed} of ${categories.length} production categories are ready. Review the remaining checks before release.`);
    } catch (error) {
      for (const id of ['cameraMetric', 'batteryMetric', 'peopleMetric', 'sessionsMetric']) Z.text(id, '—');
      for (const id of ['audioState', 'speakerState', 'trackingState', 'safetyState']) Z.text(id, 'Unavailable');
      Z.text('releaseTitle', 'Readiness unavailable'); Z.text('releaseSummary', 'Reconnect to the device to review its checks.');
      Z.errorNotice(error);
    }
  }, 2000);
  Z.poll(async () => {
    try {
      const camera = await Z.api('/api/camera/status');
      if (camera.backend === 'mock') { emptyPreview('This workspace uses a simulated camera. Connect real hardware for a live room preview.'); return; }
      if (!camera.connected || !camera.running) throw new Error('The classroom camera is unavailable.');
      if (camera.sequence !== cameraSequence) { cameraSequence = camera.sequence; seenAt = performance.now(); }
      if (performance.now() - seenAt > 1500) throw new Error('The camera preview has stopped updating.');
      const frame = await createImageBitmap(await Z.api('/api/camera/frame.jpg', {responseType: 'blob'}));
      try {
        const canvas = Z.$('roomPreview'); canvas.width = frame.width; canvas.height = frame.height;
        canvas.getContext('2d').drawImage(frame, 0, 0); canvas.hidden = false;
      } finally { frame.close(); }
      Z.$('previewEmpty').hidden = true; Z.badge('previewBadge', 'Camera preview', 'success');
    } catch (error) {
      emptyPreview(error.status === 401 ? 'Enter your conference token in Access settings to view the room.' : error.message);
    }
  }, 1200);
})();
