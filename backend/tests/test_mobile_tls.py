"""Exercise the LAN receiver over real TLS using only private, disposable test data."""

import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import HealthObservation, HealthSyncCursor

BACKEND = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.name != "posix" or not shutil.which("openssl"),
    reason="the loopback receiver test uses POSIX descriptor passing and openssl",
)


def _issue_certificate(directory):
    # The CA exists only for this receiver and is trusted only by this client's SSLContext.
    (directory / "issuer.cnf").write_text(
        "[req]\ndistinguished_name=dn\n[dn]\n"
        "[ca]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n"
        "subjectKeyIdentifier=hash\n"
        "[server]\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\n"
        "subjectAltName=IP:127.0.0.1\nauthorityKeyIdentifier=keyid:always\n"
    )
    commands = [
        ["req", "-new", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=Compi test CA", "-keyout", "ca.key", "-out", "ca.pem",
         "-config", "issuer.cnf", "-extensions", "ca"],
        ["req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=Compi test receiver",
         "-keyout", "receiver.key", "-out", "receiver.csr", "-config", "issuer.cnf"],
        ["x509", "-req", "-in", "receiver.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
         "-set_serial", "2", "-days", "1", "-out", "receiver.pem", "-extfile", "issuer.cnf",
         "-extensions", "server"],
    ]
    for command in commands:
        subprocess.run(["openssl", *command], cwd=directory, check=True, capture_output=True, timeout=30)


@contextmanager
def _receiver(directory, database_url, token):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.mobile:app", "--fd", str(listener.fileno()),
             "--loop", "asyncio", "--ssl-certfile", "receiver.pem", "--ssl-keyfile", "receiver.key",
             "--no-proxy-headers", "--no-access-log", "--log-level", "warning"],
            cwd=directory,
            env={"PATH": os.defpath, "PYTHONPATH": str(BACKEND), "DATABASE_URL": database_url,
                 "HEALTHKIT_SYNC_TOKEN": token.get_secret_value()},
            pass_fds=(listener.fileno(),),
        )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"Receiver exited during startup (status {process.returncode})")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except (ConnectionRefusedError, TimeoutError):
                time.sleep(0.05)
        else:
            pytest.fail("Receiver did not start accepting connections")
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture
def receiver():
    with TemporaryDirectory(prefix="compi-receiver-") as temporary:
        directory = Path(temporary)
        _issue_certificate(directory)
        database_url = f"sqlite:///{directory / 'test.sqlite'}"
        engine = create_engine(database_url)
        SQLModel.metadata.create_all(engine)
        token = SecretStr(secrets.token_hex(32))
        try:
            with _receiver(directory, database_url, token) as port:
                trusted = ssl.create_default_context(cafile=str(directory / "ca.pem"))
                yield port, trusted, token, engine
        finally:
            engine.dispose()


def test_authenticated_probe_and_idempotent_batch_over_tls(receiver):
    port, trusted, token, engine = receiver
    untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for context, hostname in [(untrusted, "127.0.0.1"), (trusted, "wrong.example")]:
        with (
            socket.create_connection(("127.0.0.1", port), timeout=3) as connection,
            pytest.raises(ssl.SSLCertVerificationError),
        ):
            context.wrap_socket(connection, server_hostname=hostname)

    with httpx.Client(base_url=f"https://127.0.0.1:{port}", verify=trusted, trust_env=False) as client:
        assert client.get("/api/healthkit/connection").status_code == 401
        client.headers["Authorization"] = f"Bearer {token.get_secret_value()}"
        probe = client.get("/api/healthkit/connection")
        assert probe.status_code == 200
        assert probe.json() == {"status": "ready", "protocol_version": 1}
        with Session(engine) as session:
            assert session.exec(select(HealthObservation)).all() == []
            assert session.exec(select(HealthSyncCursor)).all() == []

        sample_id = uuid4()
        batch = {
            "kind": "heart_rate",
            "stream_id": str(uuid4()),
            "sequence": 1,
            "upserts": [{
                "sample_id": str(sample_id),
                "source_bundle": "com.example.synthetic",
                "start": "2026-01-03T17:00:00Z",
                "end": "2026-01-03T17:00:00Z",
                "value": 80,
            }],
            "deletions": [],
        }
        for applied in (True, False):
            ack = client.post("/api/healthkit/batches", json=batch)
            assert ack.status_code == 200
            assert ack.json() == {"sequence": 1, "applied": applied}
    with Session(engine) as session:
        assert session.exec(select(HealthObservation)).one().sample_id == sample_id
        assert session.exec(select(HealthSyncCursor)).one().last_sequence == 1
