(() => {
  'use strict';
  const Z = window.Zee, video = Z.$('remoteVideo'), connect = Z.$('connect'), disconnect = Z.$('disconnect'), mic = Z.$('sendMic');
  let current = null, generation = 0;
  const micAvailable = () => Boolean(window.isSecureContext && navigator.mediaDevices?.getUserMedia);
  if (!micAvailable()) {
    mic.disabled = true;
    Z.text('micHint', 'Sending your microphone needs trusted HTTPS and browser permission. You can still receive robot audio.');
  }
  function status(message, state = 'idle') {
    Z.text('status', message); Z.text('connectionState', Z.human(state));
    Z.badge('sessionBadge', state === 'connected' ? 'Connected' : state === 'connecting' ? 'Connecting' : state === 'failed' ? 'Connection issue' : 'Not connected',
      state === 'connected' ? 'success' : state === 'failed' ? 'warning' : 'neutral');
  }
  function buttons(active) {
    connect.disabled = active; disconnect.disabled = !active; mic.disabled = active || !micAvailable();
    Z.text('connect', active ? 'Connecting…' : 'Connect');
  }
  function waitForIce(peer) {
    if (peer.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise(resolve => {
      const done = () => { clearTimeout(timer); peer.removeEventListener('icegatheringstatechange', check); resolve(); };
      const check = () => { if (peer.iceGatheringState === 'complete' || peer.signalingState === 'closed') done(); };
      const timer = setTimeout(done, 5500); peer.addEventListener('icegatheringstatechange', check);
    });
  }
  async function closeResources(session, keepalive = false) {
    if (!session) return;
    session.cancelled = true; session.localStream?.getTracks().forEach(track => track.stop());
    session.peer.ontrack = null; session.peer.onconnectionstatechange = null; session.peer.close();
    if (session.id) {
      const id = session.id; session.id = null;
      await Z.api(`/api/conference/sessions/${encodeURIComponent(id)}`, {
        method: 'DELETE', headers: session.headers, keepalive,
      }).catch(() => {});
    }
  }
  async function leave() {
    generation++; const session = current; current = null;
    video.srcObject = null; video.hidden = true; Z.$('sessionEmpty').hidden = false;
    buttons(false); Z.text('videoState', 'Waiting'); Z.text('roomAudioState', 'Waiting'); Z.text('localMicState', 'Off');
    await closeResources(session); status('Session closed. You can reconnect whenever you are ready.');
  }
  connect.onclick = async () => {
    if (current) return;
    const attempt = ++generation; buttons(true); Z.clearNotice(); status('Preparing your classroom connection…', 'connecting');
    let session = null;
    const check = () => { if (attempt !== generation || session?.cancelled) throw new Error('Connection cancelled.'); };
    try {
      const config = await Z.api('/api/conference/client-config'); check();
      if (config.backend === 'mock') throw new Error('This device uses simulated conferencing. Connect the real robot to start live media.');
      if (!config.running || !config.enabled) throw new Error('The conference service is unavailable. Check system readiness.');
      if (!window.RTCPeerConnection) throw new Error('This browser does not support WebRTC. Use a current Chrome, Edge or Firefox browser.');
      const peer = new RTCPeerConnection({iceServers: config.iceServers});
      session = {peer, id: null, localStream: null, cancelled: false, headers: Z.headers()}; current = session;
      const remote = new MediaStream(); video.srcObject = remote;
      peer.addTransceiver('video', {direction: 'recvonly'});
      peer.ontrack = event => {
        if (current !== session || session.cancelled) return;
        if (!remote.getTracks().includes(event.track)) remote.addTrack(event.track);
        if (event.track.kind === 'video') { video.hidden = false; Z.$('sessionEmpty').hidden = true; Z.text('videoState', 'Receiving'); }
        if (event.track.kind === 'audio') Z.text('roomAudioState', 'Receiving');
        video.play().catch(() => status('Connected. Press play on the video to allow room audio.', peer.connectionState));
      };
      peer.onconnectionstatechange = () => {
        if (current !== session || session.cancelled) return;
        const state = peer.connectionState;
        status(state === 'connected' ? 'You are connected to the classroom.' : state === 'failed' ? 'The media connection failed. Leave and reconnect; check private network access if it persists.' : `Connection: ${Z.human(state)}.`, state);
        if (state === 'connected') Z.text('connect', 'Connected');
        if (state === 'failed') { Z.text('videoState', 'Connection failed'); Z.text('roomAudioState', 'Connection failed'); }
      };
      if (mic.checked) {
        if (!micAvailable()) throw new Error('Microphone access requires trusted HTTPS and browser permission.');
        const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}, video: false});
        if (attempt !== generation || session.cancelled) { stream.getTracks().forEach(track => track.stop()); check(); }
        session.localStream = stream; stream.getAudioTracks().forEach(track => peer.addTrack(track, stream)); Z.text('localMicState', 'Sending');
      } else { peer.addTransceiver('audio', {direction: 'recvonly'}); Z.text('localMicState', 'Off'); }
      check(); await peer.setLocalDescription(await peer.createOffer()); await waitForIce(peer); check();
      const answer = await Z.api('/api/conference/offer', {method: 'POST', headers: session.headers,
        body: JSON.stringify({type: peer.localDescription.type, sdp: peer.localDescription.sdp}), timeout: 20000});
      session.id = answer.session_id;
      if (attempt !== generation || session.cancelled) { await closeResources(session); check(); }
      await peer.setRemoteDescription({type: answer.type, sdp: answer.sdp}); check();
      status('Connecting media to the classroom…', peer.connectionState);
      if (!config.publish_audio) Z.text('roomAudioState', 'Disabled on device');
    } catch (error) {
      await closeResources(session);
      if (attempt !== generation) return;
      current = null; video.srcObject = null; video.hidden = true; Z.$('sessionEmpty').hidden = false;
      buttons(false); Z.text('localMicState', 'Off'); status(error.message, 'failed');
      if (error.status === 401) Z.errorNotice(error);
    }
  };
  disconnect.onclick = leave;
  Z.$('fullscreen').onclick = async () => {
    try { if (video.hidden) return; if (document.fullscreenElement) await document.exitFullscreen(); else await video.requestFullscreen(); }
    catch (_) { status('Full screen is unavailable in this browser view. Open the app in a full browser.'); }
  };
  window.addEventListener('pagehide', () => {
    generation++; const session = current; current = null; void closeResources(session, true);
  });
})();
