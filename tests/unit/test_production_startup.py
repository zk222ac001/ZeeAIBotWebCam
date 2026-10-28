"""Production startup checks run before a server or hardware is started."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from robotic_classroom import main


@pytest.fixture
def production_startup(monkeypatch):
    cfg = SimpleNamespace(application=SimpleNamespace(environment="production"),
                          web=SimpleNamespace(host="127.0.0.1", port=8000))
    monkeypatch.setattr(main, "load_settings", lambda: cfg)
    monkeypatch.delenv("UVICORN_SSL_CERTFILE", raising=False)
    monkeypatch.delenv("UVICORN_SSL_KEYFILE", raising=False)
    server = Mock()
    monkeypatch.setattr(main.uvicorn, "run", server)
    return server


def test_production_refuses_plain_http_before_server_start(production_startup):
    with pytest.raises(RuntimeError, match="Production startup requires HTTPS"):
        main.run()
    production_startup.assert_not_called()


def test_incomplete_tls_pair_refused_before_server_start(production_startup, monkeypatch):
    monkeypatch.setenv("UVICORN_SSL_CERTFILE", "synthetic-cert.pem")
    with pytest.raises(RuntimeError, match="Both UVICORN"):
        main.run()
    production_startup.assert_not_called()


def test_production_forwards_complete_tls_pair(production_startup, monkeypatch):
    monkeypatch.setenv("UVICORN_SSL_CERTFILE", "synthetic-cert.pem")
    monkeypatch.setenv("UVICORN_SSL_KEYFILE", "synthetic-key.pem")
    main.run()
    assert production_startup.call_args.kwargs["ssl_certfile"] == "synthetic-cert.pem"
    assert production_startup.call_args.kwargs["ssl_keyfile"] == "synthetic-key.pem"
    assert production_startup.call_args.kwargs["reload"] is False
