import importlib.util
import io
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from robotic_classroom.core import status_client


@pytest.fixture
def transport(monkeypatch):
    observed = {}
    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", lambda *a, **kw: None)
    monkeypatch.setenv("CONFERENCE_ACCESS_TOKEN", "synthetic-conference-token")
    monkeypatch.setenv("ZEE_BASE_URL", "https://localhost:8000")

    class FakeOpener:
        def open(self, request, timeout):
            observed["request"] = request
            return io.BytesIO(json.dumps({"running": True}).encode())

    def build_opener(*handlers):
        observed["handlers"] = handlers
        return FakeOpener()

    monkeypatch.setattr(status_client.urllib.request, "build_opener", build_opener)
    return observed


def test_status_transport_verifies_https_and_never_redirects(transport):
    assert status_client.read_status("/api/audio/status") == {"running": True}
    req = transport["request"]
    assert req.get_method() == "GET"
    assert req.get_header("Authorization") == "Bearer synthetic-conference-token"
    https = next(h for h in transport["handlers"] if isinstance(h, urllib.request.HTTPSHandler))
    assert https._context.verify_mode == ssl.CERT_REQUIRED
    assert https._context.check_hostname
    redirect = next(h for h in transport["handlers"] if isinstance(h, status_client.NoRedirect))
    assert redirect.redirect_request(None, None, 302, "", {}, "https://elsewhere/") is None


@pytest.mark.parametrize("base,path", [
    ("http://localhost:8000", "/api/audio/status"),
    ("https://user:password@localhost:8000", "/api/audio/status"),
    ("https://localhost:8000", "/api/control/motion"),
    ("https://localhost:8000", "https://elsewhere/"),
])
def test_unsafe_status_requests_never_reach_transport(transport, base, path):
    with pytest.raises(urllib.error.URLError):
        status_client.read_status(path, base_url=base)
    assert "request" not in transport


def test_exclusive_audio_test_detects_https_listener_without_http(monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/validate_echo_path.py"
    spec = importlib.util.spec_from_file_location("validate_echo_path", script)
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    calls = []

    class Listener:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def connect(address, timeout):
        calls.append(address)
        return Listener()

    monkeypatch.setattr(diagnostic.socket, "create_connection", connect)
    assert diagnostic.app_is_running() is True
    assert calls == [("127.0.0.1", 8000)]
    # A timeout must not be interpreted as exclusive audio access being safe.
    def uncertain(*args, **kwargs):
        raise TimeoutError("synthetic uncertainty")

    monkeypatch.setattr(diagnostic.socket, "create_connection", uncertain)
    with pytest.raises(TimeoutError):
        diagnostic.app_is_running()
