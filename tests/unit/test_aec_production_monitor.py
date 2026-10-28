import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/aec_production_monitor.py"
SPEC = importlib.util.spec_from_file_location("aec_production_monitor", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


@pytest.fixture(autouse=True)
def mock_ca_loading(monkeypatch):
    # CI has no Pi-local CA. Network calls below use fake openers; retain the
    # real TLS context so verification mode and hostname checks can be asserted.
    monkeypatch.setattr(monitor.ssl.SSLContext, "load_verify_locations", lambda *a, **kw: None)


def test_snapshot_maps_audio_pipeline_payload() -> None:
    # Mirrors the fields exposed by /api/conference/audio-pipeline.
    payload = {
        "speaker_playback_running": True,
        "speaker_frames_written": 123,
        "speaker_last_error": "",
        "echo_reference_enabled": True,
        "echo_reference_running": True,
        "echo_reference_frames_written": 123,
        "echo_reference_last_error": "",
        "echo_reference_validated": False,
        "echo_management_mode": "monitor",
    }

    snapshot = monitor.Snapshot.from_payload(payload)

    assert snapshot.speaker_running is True
    assert snapshot.speaker_frames == 123
    assert snapshot.reference_enabled is True
    assert snapshot.reference_running is True
    assert snapshot.reference_frames == 123
    assert snapshot.reference_validated is False
    assert snapshot.echo_management_mode == "monitor"


def test_fetch_uses_verified_tls_and_bearer_without_redirects(monkeypatch) -> None:
    import io
    import json
    import ssl
    import urllib.request

    observed = {}

    class Opener:
        def open(self, request, timeout):
            observed["request"] = request
            observed["timeout"] = timeout
            return io.BytesIO(json.dumps({"speaker_frames_written": 12}).encode())

    def build_opener(*handlers):
        observed["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(monitor.urllib.request, "build_opener", build_opener)
    result = monitor.fetch_snapshot(monitor.DEFAULT_URL, 2, token="local-secret")
    assert result.speaker_frames == 12
    assert observed["request"].get_header("Authorization") == "Bearer local-secret"
    handlers = observed["handlers"]
    https = next(h for h in handlers if isinstance(h, urllib.request.HTTPSHandler))
    assert https._context.verify_mode == ssl.CERT_REQUIRED
    assert https._context.check_hostname
    redirect = next(h for h in handlers if isinstance(h, monitor.NoRedirect))
    assert redirect.redirect_request(None, None, 302, "", {}, "https://elsewhere/") is None


def test_fetch_redacts_http_error_details(monkeypatch) -> None:
    import urllib.error

    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "sensitive-detail", {}, None)

    monkeypatch.setattr(monitor.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(RuntimeError, match=r"^Audio-pipeline request failed \(HTTP 401\)$"):
        monitor.fetch_snapshot(monitor.DEFAULT_URL, 2)


def test_fetch_rejects_unsafe_urls_and_token_headers() -> None:
    import argparse

    for url in (
        "http://localhost:8000/api/conference/audio-pipeline",
        "https://secret@localhost:8000/api/conference/audio-pipeline",
        "https://localhost:8000/api/conference/audio-pipeline?token=secret",
        "https://localhost:8000/api/control/reset",
    ):
        with pytest.raises(argparse.ArgumentTypeError):
            monitor.fetch_snapshot(url, 2)
    with pytest.raises(ValueError, match="printable ASCII"):
        monitor.fetch_snapshot(monitor.DEFAULT_URL, 2, token="secret\nInjected: yes")


def test_fetch_rejects_oversized_response(monkeypatch) -> None:
    import io

    class Opener:
        def open(self, request, timeout):
            return io.BytesIO(b" " * 262145)

    monkeypatch.setattr(monitor.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(RuntimeError, match="trusted audio-pipeline JSON"):
        monitor.fetch_snapshot(monitor.DEFAULT_URL, 2)


@pytest.mark.parametrize("failure", ["transient_error", "counter_reset"])
def test_monitor_retains_failures_after_stream_recovers(monkeypatch, capsys, failure):
    from dataclasses import replace

    baseline = monitor.Snapshot(True, 100, "", True, True, 100, "", False, "monitor")
    bad = (replace(baseline, speaker_error="private-driver-detail")
           if failure == "transient_error" else replace(baseline, speaker_frames=0, reference_frames=0))
    snapshots = iter([baseline, bad, replace(baseline, speaker_frames=200, reference_frames=200)])
    clock = iter([0, 0, 0, 1, 1, 2, 2, 4])
    monkeypatch.setattr(monitor, "fetch_snapshot", lambda *args, **kwargs: next(snapshots))
    monkeypatch.setattr(monitor.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(monitor.time, "sleep", lambda duration: None)
    monkeypatch.setattr(sys, "argv", ["aec_production_monitor.py", "--seconds", "3"])
    assert monitor.main() == 1
    output = capsys.readouterr().out
    assert "RESULT: FAIL" in output
    assert "private-driver-detail" not in output
