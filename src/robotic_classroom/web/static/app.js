/* Shared UI: explicit access, bounded requests, and read-only device status. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const dialog = $('accessDialog');
  const key = 'zeeai-tab-access-v1';
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (saved) {
      $('token').value = saved.media || '';
      $('controlToken').value = saved.control || '';
      $('rememberAccess').checked = true;
    }
  } catch (_) { /* Storage can be disabled by the browser. */ }
  document.querySelectorAll('.access-trigger').forEach(button => {
    button.addEventListener('click', () => dialog.showModal());
  });
  $('closeAccess').onclick = () => dialog.close();
  $('accessForm').onsubmit = event => {
    event.preventDefault();
    try {
      if ($('rememberAccess').checked) {
        sessionStorage.setItem(key, JSON.stringify({
          media: $('token').value.trim(), control: $('controlToken').value.trim(),
        }));
      } else sessionStorage.removeItem(key);
    } catch (_) { notice('Access applied for this page. Tab storage is unavailable.', 'warning'); }
    dialog.close();
    document.dispatchEvent(new Event('accesschanged'));
  };
  $('clearAccess').onclick = () => {
    $('token').value = '';
    $('controlToken').value = '';
    $('rememberAccess').checked = false;
    try { sessionStorage.removeItem(key); } catch (_) { /* Memory-only access. */ }
    dialog.close();
    document.dispatchEvent(new Event('accesschanged'));
  };
  function headers(scope = 'media') {
    const token = $(scope === 'control' ? 'controlToken' : 'token').value.trim();
    return token ? {Authorization: `Bearer ${token}`} : {};
  }
  async function api(path, options = {}) {
    const {scope = 'media', timeout = 4500, responseType = 'json', ...init} = options;
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (init.signal?.aborted) controller.abort();
    else init.signal?.addEventListener('abort', abort, {once: true});
    const timer = setTimeout(abort, timeout);
    const requestHeaders = new Headers({...headers(scope), ...init.headers});
    if (init.body && !requestHeaders.has('Content-Type')) requestHeaders.set('Content-Type', 'application/json');
    try {
      const response = await fetch(path, {...init, headers: requestHeaders,
        signal: controller.signal, cache: 'no-store'});
      if (!response.ok) {
        let detail;
        try { detail = (await response.json()).detail; } catch (_) { /* Generic HTTP error. */ }
        const error = new Error(typeof detail === 'string' ? detail : `Request failed (${response.status}).`);
        error.status = response.status;
        throw error;
      }
      return responseType === 'blob' ? await response.blob() : await response.json();
    } finally {
      clearTimeout(timer);
      init.signal?.removeEventListener('abort', abort);
    }
  }
  function notice(message, kind = 'warning') {
    const box = $('globalNotice');
    box.className = `notice ${kind}`;
    box.replaceChildren();
    const text = document.createElement('span');
    text.textContent = message;
    box.append(text);
    if (kind === 'auth') {
      const button = document.createElement('button');
      button.className = 'button secondary';
      button.textContent = 'Access settings';
      button.onclick = () => dialog.showModal();
      box.append(button);
    }
    box.hidden = false;
  }
  function clearNotice() { $('globalNotice').hidden = true; }
  function errorNotice(error) {
    if (error.status === 401) notice('This workspace requires an access token. Open access settings to continue.', 'auth');
    else notice(error.name === 'AbortError' ? 'The device took too long to respond. Retrying automatically.' : error.message, 'error');
  }
  function text(id, value) { if ($(id)) $(id).textContent = value; }
  function badge(id, label, kind = 'neutral') {
    const node = $(id);
    if (node) { node.textContent = label; node.className = `badge ${kind}`; }
  }
  function human(value) { return typeof value === 'string' ? value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()) : 'Unavailable'; }
  function finite(value) { return typeof value === 'number' && Number.isFinite(value); }
  function poll(callback, interval = 2000) {
    let stopped = false, running = false, timer;
    async function run() {
      clearTimeout(timer);
      if (stopped || running) return;
      if (!document.hidden) {
        running = true;
        try { await callback(); } catch (error) { errorNotice(error); }
        finally { running = false; }
      }
      if (!stopped) timer = setTimeout(run, interval);
    }
    const refresh = () => { if (!document.hidden) run(); };
    document.addEventListener('visibilitychange', refresh);
    document.addEventListener('accesschanged', refresh);
    run();
    return () => { stopped = true; clearTimeout(timer);
      document.removeEventListener('visibilitychange', refresh);
      document.removeEventListener('accesschanged', refresh); };
  }
  const openSession = document.createElement('a');
  if (document.body.dataset.page === 'overview') {
    openSession.href = '/conference'; openSession.className = 'button primary';
    openSession.textContent = 'Open live session ↗'; $('headingActions').append(openSession);
  }
  const categoryNames = {runtime: 'Device & services', telepresence: 'Video & audio', safety: 'Safety supervision',
    privacy_security: 'Privacy & access', aec: 'Echo cancellation', classroom_pilot: 'Classroom pilot'};
  window.Zee = {$, api, headers, notice, errorNotice, clearNotice, text, badge, human, finite, poll, categoryNames};
  poll(async () => {
    try {
      const health = await api('/health');
      window.Zee.health = health;
      const simulated = health.hardware?.backend === 'mock';
      $('deviceConnection').querySelector('.small-dot').className = `small-dot ${simulated ? 'amber' : 'green'}`;
      text('deviceConnectionText', simulated ? 'Simulated device' : 'Device online');
      text('privacyNote', `${health.recording_enabled ? 'Recording enabled' : 'Recording off'} · ${health.face_recognition_enabled ? 'Face recognition enabled' : 'Anonymous detections'}`);
      document.dispatchEvent(new CustomEvent('devicehealth', {detail: health}));
    } catch (_) {
      $('deviceConnection').querySelector('.small-dot').className = 'small-dot red';
      text('deviceConnectionText', 'Device unavailable'); text('privacyNote', 'Privacy status unavailable');
    }
  }, 5000);
})();
