"""Mock-only verification of the command-line operator's transport and stop path."""
import importlib.util
import io
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("operator_motion_client", ROOT / "scripts/operator_motion_client.py")
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", lambda *a, **kw: None)
    return operator.ControlClient(operator.BASE_URL, Path("unused-test-ca"), "synthetic-control-token")


def test_client_verifies_tls_and_authenticates_without_redirects(client):
    handlers = client.opener.handlers
    https = next(h for h in handlers if isinstance(h, urllib.request.HTTPSHandler))
    assert https._context.check_hostname
    assert https._context.verify_mode == ssl.CERT_REQUIRED
    redirect = next(h for h in handlers if isinstance(h, operator.NoRedirect))
    assert redirect.redirect_request(None, None, 302, "", {}, "https://elsewhere/") is None
    requests = []

    class FakeOpener:
        def open(self, request, timeout):
            requests.append(request)
            return io.BytesIO(json.dumps({"token": "synthetic-lease-token"}).encode())

    client.opener = FakeOpener()
    client.request_json("POST", "/api/control/lease", {"owner": "test"})
    request = requests[0]
    assert request.get_header("Authorization") == "Bearer synthetic-control-token"
    assert request.full_url == operator.BASE_URL + "/api/control/lease"
    with pytest.raises(ValueError, match="Unsupported"):
        client.request_json("POST", "https://elsewhere/")


def test_http_failure_does_not_print_response_or_token(client):
    class FakeOpener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "private-detail", {},
                                         io.BytesIO(b"synthetic-control-token"))

    client.opener = FakeOpener()
    with pytest.raises(RuntimeError, match=r"^Operator request failed \(HTTP 401\)$"):
        client.request_json("POST", "/api/control/lease", {"owner": "test"})


@pytest.mark.parametrize("stop_fails", [False, True])
def test_lost_motion_ack_always_attempts_stop(monkeypatch, stop_fails):
    calls = []

    class FakeClient:
        def __init__(self, *args):
            pass

        def request_json(self, method, path, payload=None):
            calls.append(path)
            if path == "/api/safety":
                return {"state": "idle", "motion_enabled": True,
                        "watchdog_running": True, "motion_active": False}
            if path == "/api/control/lease":
                return {"token": "synthetic-lease-token"}
            if path == "/api/control/motion":
                raise RuntimeError("Lost motion acknowledgement")
            return {}

        def heartbeat_loop(self, *args):
            pytest.fail("Heartbeat thread must not start after failed motion acknowledgement")

        def send_stop(self):
            calls.append("STOP")
            if stop_fails:
                raise RuntimeError("Synthetic STOP failure")

    monkeypatch.setattr(operator, "ControlClient", FakeClient)
    monkeypatch.setattr(sys, "argv", ["operator_motion_client.py", "--direction", "forward"])
    with pytest.raises(RuntimeError, match="STOP was not confirmed" if stop_fails else "Lost motion"):
        operator.main()
    assert calls[-1] == "STOP"


def test_unsafe_origin_rejected_before_ca_load():
    with pytest.raises(ValueError, match="HTTPS origin"):
        operator.ControlClient("http://localhost:8000", Path("unused"))
