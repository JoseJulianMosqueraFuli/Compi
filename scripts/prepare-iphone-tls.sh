#!/usr/bin/env bash
# Create a local server identity. Trust on the iPhone is a separate, manual step.
set -euo pipefail
umask 077

host=${1:?Uso: bash scripts/prepare-iphone-tls.sh nombre-del-mac.local [IPv4-Wi-Fi]}
if [[ ! $host =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.local$ ]]; then
  echo "Se requiere el nombre Bonjour del Mac, por ejemplo mi-mac.local." >&2
  exit 2
fi
san="DNS:$host"
if [[ $# -gt 2 ]]; then
  echo "Se acepta un nombre Bonjour y una dirección IPv4 opcional." >&2
  exit 2
fi
if [[ $# -eq 2 ]]; then
  python3 - "$2" <<'PY'
import ipaddress
import sys

try:
    ip = ipaddress.IPv4Address(sys.argv[1])
    if not any(ip in ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise ValueError
except ValueError:
    sys.exit("La dirección debe ser la IPv4 privada de la interfaz Wi-Fi del Mac.")
PY
  san+=",IP:$2"
fi
root=$(cd "$(dirname "$0")/.." && pwd)
local_dir="$root/.compi-local"
mkdir -p "$local_dir"
dest="$local_dir/tls"
if [[ -e $dest ]]; then
  echo "El directorio TLS ya existe. Se conservan sus certificados y claves." >&2
  exit 1
fi

# Stage on the same filesystem. Remove the signing key before publishing the directory.
stage=$(mktemp -d "$local_dir/.tls.XXXXXX")
trap 'rm -rf "$stage"' EXIT
cat > "$stage/ca.cnf" <<'EOF'
[req]
distinguished_name = dn
x509_extensions = ca
prompt = no
[dn]
CN = Compi local pairing
[ca]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF
cat > "$stage/server.cnf" <<EOF
[server]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = $san
authorityKeyIdentifier = keyid
EOF
openssl req -newkey rsa:3072 -nodes -x509 -sha256 -days 365 -config "$stage/ca.cnf" \
  -keyout "$stage/issuer.key" -out "$stage/rootCA.pem" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -sha256 -subj "/CN=$host" \
  -keyout "$stage/server-key.pem" -out "$stage/server.csr" 2>/dev/null
openssl x509 -req -in "$stage/server.csr" -CA "$stage/rootCA.pem" -CAkey "$stage/issuer.key" \
  -CAcreateserial -days 90 -sha256 -extfile "$stage/server.cnf" -extensions server -out "$stage/server.pem"
openssl verify -CAfile "$stage/rootCA.pem" -purpose sslserver "$stage/server.pem"
openssl x509 -in "$stage/rootCA.pem" -outform DER -out "$stage/Compi-CA.cer"
rm "$stage/issuer.key" "$stage/server.csr" "$stage/server.cnf" "$stage/ca.cnf" "$stage/rootCA.srl"
# mkdir is exclusive: two runs cannot replace an existing pairing.
mkdir "$dest"
mv "$stage"/{rootCA.pem,server-key.pem,server.pem,Compi-CA.cer} "$dest/"
echo "Certificado público para el iPhone: $dest/Compi-CA.cer"
openssl x509 -in "$dest/rootCA.pem" -noout -fingerprint -sha256
