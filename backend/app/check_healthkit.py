"""Comprueba desde el Mac el emparejamiento HTTPS de Compi."""

import argparse
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import SettingsError

from app.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
CA = BACKEND.parent / ".compi-local" / "tls" / "rootCA.pem"
LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


class ProbeError(Exception):
    """Diagnóstico apto para mostrar sin datos del receptor ni credenciales."""


def _local_ip(host: str) -> bool:
    ip = ipaddress.ip_address(host)
    return ip.is_loopback or any(ip in network for network in LOCAL_NETWORKS)


def _origin(url: str) -> tuple[str, int]:
    match = re.fullmatch(r"https://(\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::([0-9]{1,5}))?/?", url, re.I | re.ASCII)
    error = argparse.ArgumentTypeError("Usa un origen HTTPS con IP privada, loopback o nombre .local.")
    if not match:
        raise error
    host = match[1].strip("[]").lower()
    port = int(match[2] or 443)
    if not 1 <= port <= 65535:
        raise error
    try:
        local = _local_ip(host)
    except ValueError:
        local = bool(re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+local", host))
    if not local or len(host) > 253:
        raise error
    return host, port


def _connect(host: str, port: int) -> socket.socket:
    # Select the exact numeric destination before sending anything to a .local name.
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    for family, socktype, proto, _, address in addresses:
        if not _local_ip(address[0]):
            continue
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(5)
            sock.connect(address)
            return sock
        except OSError:
            sock.close()
    raise ProbeError("Red: comprueba la IP Wi-Fi, el puerto y que el receptor esté activo.")


def _check_response(response: http.client.HTTPResponse) -> None:
    if response.status == 401:
        raise ProbeError("Token rechazado (HTTP 401). Comprueba el secreto que está usando el receptor.")
    if response.status == 403:
        raise ProbeError("Acceso denegado (HTTP 403). Comprueba la configuración HTTPS del receptor.")
    if response.status not in (200, 503):
        raise ProbeError(
            f"Respuesta inesperada (HTTP {response.status}). Comprueba la dirección del receptor."
        )
    data = response.read(513)
    try:
        payload = json.loads(data) if len(data) <= 512 else None
    except (ValueError, UnicodeError):
        payload = None
    if response.status == 503:
        if isinstance(payload, dict) and payload.get("detail") == "storage unavailable":
            raise ProbeError("Almacenamiento (HTTP 503). Comprueba PostgreSQL y sus migraciones.")
        if isinstance(payload, dict) and payload.get("detail") == "pairing unavailable":
            raise ProbeError("Emparejamiento (HTTP 503). Configura el token en el receptor y reinícialo.")
        raise ProbeError("Receptor indisponible (HTTP 503).")
    if not isinstance(payload, dict) or type(payload.get("protocol_version")) is not int:
        raise ProbeError(
            "Protocolo incompatible. Comprueba que la dirección corresponda al receptor de Compi."
        )
    if payload["protocol_version"] != 1 or payload.get("status") != "ready":
        raise ProbeError("El receptor no confirmó que está listo con el protocolo 1.")


def check(origin: tuple[str, int], context: ssl.SSLContext, token: str) -> None:
    host, port = origin
    try:
        sock = _connect(host, port)
    except socket.gaierror:
        raise ProbeError(
            "DNS: comprueba el nombre Bonjour o usa la IP privada incluida en el certificado."
        ) from None
    except OSError:
        raise ProbeError("Red: no se pudo abrir una conexión TCP con el receptor.") from None

    with sock, closing(http.client.HTTPSConnection(host, port, context=context)) as connection:
        try:
            connection.sock = context.wrap_socket(sock, server_hostname=host)
        except ssl.SSLCertVerificationError:
            raise ProbeError(
                "Certificado TLS inválido. Comprueba la CA, la dirección y la vigencia."
            ) from None
        except OSError:
            raise ProbeError("La negociación TLS se interrumpió antes de enviar el token.") from None
        try:
            connection.request(
                "GET", "/api/healthkit/connection", headers={"Authorization": f"Bearer {token}"}
            )
            with connection.getresponse() as response:
                _check_response(response)
        except (http.client.HTTPException, OSError):
            raise ProbeError(
                "La conexión HTTPS se interrumpió al consultar el estado del receptor."
            ) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origen", type=_origin, help="p. ej. https://mi-mac.local:8443")
    args = parser.parse_args()
    try:
        settings = Settings(_env_file=BACKEND / ".env")
        secret = settings.healthkit_sync_token
        token = secret.get_secret_value() if secret else ""
        if len(token) < 32 or not token.isascii() or not all("!" <= char <= "~" for char in token):
            raise ProbeError("Configuración: revisa HEALTHKIT_SYNC_TOKEN en backend/.env.")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=CA)
        check(args.origen, context, token)
    except ProbeError as error:
        print(error, file=sys.stderr)
        return 1
    except (SettingsError, ValidationError):
        print("Configuración inválida. Revisa backend/.env.", file=sys.stderr)
        return 1
    except OSError:
        print(
            "Comprueba los permisos de backend/.env y el certificado .compi-local/tls/rootCA.pem.",
            file=sys.stderr,
        )
        return 1
    print("Conexión verificada desde el Mac (HTTP 200, protocolo 1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
