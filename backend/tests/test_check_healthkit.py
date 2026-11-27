"""The Mac pairing check only sends its bearer to a verified local receiver."""

import argparse
import os
import secrets
import shutil
import socket
import sys
from unittest.mock import Mock

import pytest
from pydantic import SecretStr
from sqlmodel import SQLModel, create_engine

from app import check_healthkit as probe
from tests.test_mobile_tls import _issue_certificate, _receiver


@pytest.mark.parametrize("url", [
    "http://mi-mac.local:8443", "https://example.org", "https://169.254.169.254",
    "https://mi-mac.local@1.1.1.1", "https://user:pass@mi-mac.local", "https://8.8.8.8",
    "https://mi-mac.local/?token=private", "https://mi-mac.local:0", "https://[::ffff:0808:0808]",
    "https://127.0.0.1:8443/api/healthkit/batches", "https://[::1]public", "https://mi-mac.local/#",
])
def test_reject_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(argparse.ArgumentTypeError):
        probe._origin(url)


def test_dns_cannot_redirect_a_local_name_to_a_public_address(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 8443)),
    ])
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: pytest.fail("unexpected connection"))
    with pytest.raises(probe.ProbeError, match="Red"):
        probe._connect("mi-mac.local", 8443)


@pytest.mark.parametrize(("status", "body", "diagnostic"), [
    (302, b"", "302"), (403, b"", "403"),
    (503, b'{"detail":"pairing unavailable"}', "Emparejamiento"),
    (200, b'{"status":"ready","protocol_version":true}', "Protocolo"),
    (200, b'{"status":"ready","protocol_version":2}', "protocolo 1"),
    (200, b"secret-response", "Protocolo"),
])
def test_only_recognized_ready_response_passes(status, body, diagnostic):
    response = Mock(status=status)
    response.read.return_value = body
    with pytest.raises(probe.ProbeError, match=diagnostic) as exc:
        probe._check_response(response)
    assert "secret-response" not in str(exc.value)


@pytest.mark.skipif(os.name != "posix" or not shutil.which("openssl"), reason="POSIX TLS fixture")
def test_cli_identifies_tls_storage_and_token_before_confirming_pairing(tmp_path, monkeypatch, capsys):
    _issue_certificate(tmp_path)
    token = SecretStr(secrets.token_hex(32))
    database = f"sqlite:///{tmp_path}/test.sqlite"
    monkeypatch.setattr(probe, "BACKEND", tmp_path)
    monkeypatch.setattr(probe, "CA", tmp_path / "ca.pem")
    monkeypatch.delenv("HEALTHKIT_SYNC_TOKEN", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"HEALTHKIT_SYNC_TOKEN={token.get_secret_value()}\n")
    with _receiver(tmp_path, database, token) as port:
        monkeypatch.setattr(sys, "argv", ["check_healthkit", f"https://127.0.0.1:{port}"])
        with monkeypatch.context() as bad_ca:
            # This valid PEM is not the issuer of the receiver certificate.
            other = tmp_path / "other"
            other.mkdir()
            _issue_certificate(other)
            bad_ca.setattr(probe, "CA", other / "ca.pem")
            assert probe.main() == 1
            assert "Certificado TLS inválido" in capsys.readouterr().err
        assert probe.main() == 1
        assert "Almacenamiento (HTTP 503)" in capsys.readouterr().err
        engine = create_engine(database)
        try:
            SQLModel.metadata.create_all(engine)
        finally:
            engine.dispose()
        assert probe.main() == 0
        assert "HTTP 200" in capsys.readouterr().out
        wrong_token = secrets.token_hex(32)
        env.write_text(f"HEALTHKIT_SYNC_TOKEN={wrong_token}\n")
        assert probe.main() == 1
        error = capsys.readouterr().err
        assert "Token rechazado (HTTP 401)" in error
        assert wrong_token not in error
