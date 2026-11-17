"""Generate disposable local EA-28 test PKI. Not suitable for production use.

Run from security/live-sandbox/: python bootstrap_pki.py
Never commit the generated CA private key or client private keys.
"""
from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

OUT = Path(__file__).resolve().parent / "generated"


def new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def write_key(path, key):
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))


def write_cert(path, cert):
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def sign_cert(cn, subject_key, issuer_cert, issuer_key, *, is_ca=False, server=False):
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder()
               .subject_name(name(cn))
               .issuer_name(issuer_cert.subject if issuer_cert else name(cn))
               .public_key(subject_key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(minutes=5))
               .not_valid_after(now + timedelta(days=2 if is_ca else 1))
               .add_extension(x509.BasicConstraints(ca=is_ca, path_length=0 if is_ca else None),
                              critical=True))
    if server:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]), critical=False)
    if not is_ca:
        usage = [x509.oid.ExtendedKeyUsageOID.SERVER_AUTH if server
                 else x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]
        builder = builder.add_extension(x509.ExtendedKeyUsage(usage), critical=False)
    return builder.sign(issuer_key or subject_key, hashes.SHA256())


def main():
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("generated/ already contains files: remove only disposable sandbox keys before regeneration.")
    OUT.mkdir(parents=True, exist_ok=True)
    ca_key = new_key()
    ca_cert = sign_cert("edgeops-local-test-ca", ca_key, None, None, is_ca=True)
    write_key(OUT / "ca.key", ca_key)
    write_cert(OUT / "ca.crt", ca_cert)
    for cn, is_server in (("localhost", True), ("device-a", False),
                          ("gateway-a", False), ("rogue", False)):
        key = new_key()
        cert = sign_cert(cn, key, ca_cert, ca_key, server=is_server)
        prefix = "server" if is_server else cn
        write_key(OUT / (prefix + ".key"), key)
        write_cert(OUT / (prefix + ".crt"), cert)
    if os.name != "nt":
        for key_path in OUT.glob("*.key"):
            key_path.chmod(0o600)
        # mosquitto container may not read server.key as an unprivileged user
        # if host permissions are restrictive. Document permissions explicitly
        # rather than weakening keys on a shared host.
    print("Generated disposable local CA and mTLS certificates in ignored generated/.")


if __name__ == "__main__":
    main()
