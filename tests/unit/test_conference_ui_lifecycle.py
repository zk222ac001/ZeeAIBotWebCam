"""Run the browser controller against synthetic DOM/RTC objects with Node."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "src/robotic_classroom/web/static/conference.js"
HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const nodes = new Map();
function node(id) {
  if (!nodes.has(id)) nodes.set(id, {textContent:'', disabled:false, hidden:false, checked:false});
  return nodes.get(id);
}
const timers = new Map(); let timerId = 0;
globalThis.setTimeout = fn => { timers.set(++timerId, fn); return timerId; };
globalThis.clearTimeout = id => timers.delete(id);
globalThis.window = globalThis;
window.isSecureContext = true;
window.addEventListener = () => {};
Object.defineProperty(globalThis, 'navigator', {value: {
  userAgent:'Firefox/155.0', mediaDevices: {getUserMedia: async () => {throw new Error('Unexpected microphone access');}},
}, configurable:true});
globalThis.MediaStream = class {};
let peer, offers = 0, closes = [];
globalThis.RTCPeerConnection = class {
  constructor() { peer = this; this.iceGatheringState = 'complete'; this.connectionState = 'new'; }
  addTransceiver() {}
  async createOffer() { return {type:'offer', sdp:process.argv[2] === 'no_candidates' ? 'v=0' : 'v=0\r\na=candidate:1 1 udp 100 192.0.2.1 5000 typ host\r\n'}; }
  async setLocalDescription(value) { this.localDescription = value; }
  async setRemoteDescription() { this.connectionState = 'connecting'; }
  close() { this.connectionState = 'closed'; this.closed = true; }
};
window.Zee = {
  $:node, text:(id,value) => {node(id).textContent = value;},
  human:value => value[0].toUpperCase()+value.slice(1), badge:()=>{},
  clearNotice:()=>{}, errorNotice:()=>{}, headers:()=>({}),
  api:async (path, options={}) => {
    if (path.endsWith('client-config')) return {backend:'aiortc',running:true,enabled:true,iceServers:[],publish_audio:true};
    if (path.endsWith('/offer')) return {session_id:'synthetic-session-'+(++offers),type:'answer',sdp:'synthetic-answer'};
    if (options.method === 'DELETE') { closes.push(path); return {}; }
    throw new Error('Unexpected API request');
  },
};
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
  await node('connect').onclick();
  if (process.argv[2] === 'no_candidates') {
    assert.equal(offers, 0);
    assert.equal(peer.closed, true);
    assert.equal(node('connect').disabled, false);
    assert.match(node('status').textContent, /no network addresses/);
    assert.match(node('iceDetails').textContent, /0 browser addresses/);
    return;
  }
  assert.equal(node('connect').disabled, true);
  if (process.argv[2] === 'failed') {
    peer.connectionState = 'failed'; peer.onconnectionstatechange();
  } else {
    assert.equal(timers.size, 1); [...timers.values()][0]();
  }
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(peer.closed, true);
  assert.equal(timers.size, 0);
  assert.equal(node('connect').disabled, false);
  assert.equal(node('connect').textContent, 'Connect');
  assert.equal(node('disconnect').disabled, true);
  assert.equal(node('localMicState').textContent, 'Off');
  assert.equal(node('videoState').textContent, 'Connection failed');
  assert.match(node('status').textContent, /No working media route/);
  assert.equal(closes.length, 1);
  await node('connect').onclick();
  assert.equal(offers, 2);
  await node('disconnect').onclick();
  assert.equal(closes.length, 2);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


@pytest.mark.parametrize("failure", ["failed", "timeout", "no_candidates"])
def test_failed_media_releases_session_and_allows_retry(failure):
    node = os.environ.get("ZEE_TEST_NODE") or shutil.which("node")
    if not node:
        pytest.skip("Node is needed for JavaScript controller verification")
    result = subprocess.run([node, "-e", HARNESS, str(SCRIPT), failure],
                            check=False, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
