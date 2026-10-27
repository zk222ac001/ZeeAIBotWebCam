(() => {
  'use strict';
  const Z = window.Zee;
  let latest = null;
  const descriptions = {
    runtime: 'Real camera, microphone and hardware services.', telepresence: 'Conference video and both audio directions.',
    safety: 'Watchdog, sensor checks and stationary chassis.', privacy_security: 'Access tokens, privacy and production settings.',
    aec: 'Validated returning-echo and double-talk performance.', classroom_pilot: 'The complete supervised classroom acceptance test.',
  };
  function blockers(container, reasons) {
    container.replaceChildren();
    for (const reason of reasons || []) {
      const paragraph = document.createElement('p'); paragraph.textContent = Z.human(reason); container.append(paragraph);
    }
  }
  Z.poll(async () => {
    try {
      const data = await Z.api('/api/readiness'); latest = data; Z.clearNotice();
      const grid = Z.$('readinessGrid'); grid.replaceChildren(); let passed = 0;
      for (const [key, name] of Object.entries(Z.categoryNames)) {
        const category = data.categories[key]; if (!category) continue;
        if (category.ready) passed++;
        const card = document.createElement('article'); card.className = 'readiness-card';
        const top = document.createElement('div'); top.className = 'readiness-card-top';
        const heading = document.createElement('h3'); heading.textContent = name;
        const badge = document.createElement('span'); badge.className = `badge ${category.ready ? 'success' : 'warning'}`;
        badge.textContent = category.ready ? 'Ready' : 'Pending'; top.append(heading, badge);
        const description = document.createElement('p'); description.className = 'muted'; description.textContent = descriptions[key];
        const list = document.createElement('div'); list.className = 'blocker-list'; blockers(list, category.blockers);
        if (category.ready) { const note = document.createElement('p'); note.className = 'check-note'; note.textContent = '✓ Current checks passed'; list.append(note); }
        card.append(top, description, list); grid.append(card);
      }
      Z.text('readinessTitle', data.production_ready ? 'Production checks complete' : 'Supervised preview');
      Z.text('readinessSubtitle', data.production_ready ? 'Runtime production prerequisites are satisfied. Physical operation remains supervised.' : 'Your workspace is running. Complete the pending checks before calling it a final release.');
      Z.badge('readinessCount', `${passed} / 6 ready`, data.production_ready ? 'success' : 'warning');
      Z.text('autonomySummary', `${Z.human(data.autonomy.mode)} · ${data.autonomy.armed ? 'Armed' : 'Unarmed'}`);
      blockers(Z.$('autonomyBlockers'), data.categories.autonomous_motion?.blockers);
    } catch (error) {
      latest = null; Z.text('readinessTitle', 'Status unavailable'); Z.text('readinessSubtitle', 'Reconnect to the device before assessing release readiness.');
      Z.badge('readinessCount', 'Unavailable', 'neutral'); Z.$('readinessGrid').replaceChildren();
      Z.text('autonomySummary', 'Unavailable'); Z.$('autonomyBlockers').replaceChildren(); Z.errorNotice(error);
    }
  }, 5000);
  const download = document.createElement('button'); download.className = 'button secondary'; download.textContent = 'Download report ↓';
  download.onclick = () => {
    if (!latest) { Z.notice('A fresh readiness report is needed before downloading.'); return; }
    const blob = new Blob([JSON.stringify({captured_at: new Date().toISOString(), ...latest}, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url;
    link.download = `zeeai-readiness-${new Date().toISOString().slice(0, 10)}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  Z.$('headingActions').append(download);
})();
