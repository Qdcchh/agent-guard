"""SM2 second-implementation interoperability against the OpenSSL CLI.

The OpenSSL command-line tool is an implementation independent of Tongsuo.
Both directions are exercised over the same fixed key and message: Tongsuo
signature -> OpenSSL verify, and OpenSSL signature -> Tongsuo verify, plus a
JWS whose signature segment was produced by OpenSSL. OpenSSL applies the
default SM2 user identifier ``1234567812345678``, matching GM-MVP-1. This is a
development-vector check on the CI runner, not a claim about all OpenSSL
builds or algorithm suites.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from tongsuopy.crypto import serialization

from agent_guard.contracts.encoding import b64url_encode
from agent_guard.crypto.sm import (
    InvalidSm2Signature,
    _der_to_jws_signature,
    generate_sm2_private_key,
    sign_compact_jws,
    sign_sm2_message,
    verify_compact_jws,
    verify_sm2_message,
)

pytestmark = pytest.mark.integration

MESSAGE = b"agent-guard GM-MVP-1 SM2 independent interop vector v1"


def _openssl(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["openssl", *args], capture_output=True, text=True, timeout=60)


def _require_openssl() -> None:
    if shutil.which("openssl") is None:
        pytest.fail("openssl CLI is required for the SM2 interop test", pytrace=False)


def _write_keypair(tmp_path):
    key = generate_sm2_private_key()
    private_path = tmp_path / "sm2-private.pem"
    public_path = tmp_path / "sm2-public.pem"
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return key, private_path, public_path


def test_sm2_signatures_interoperate_in_both_directions(tmp_path):
    _require_openssl()
    key, private_path, public_path = _write_keypair(tmp_path)
    message_path = tmp_path / "message.bin"
    message_path.write_bytes(MESSAGE)

    tongsuo_signature = tmp_path / "tongsuo.der"
    tongsuo_signature.write_bytes(sign_sm2_message(key, MESSAGE))
    verified = _openssl(
        [
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_path),
            "-in",
            str(message_path),
            "-rawin",
            "-digest",
            "sm3",
            "-sigfile",
            str(tongsuo_signature),
        ]
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr

    openssl_signature = tmp_path / "openssl.der"
    signed = _openssl(
        [
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private_path),
            "-in",
            str(message_path),
            "-rawin",
            "-digest",
            "sm3",
            "-out",
            str(openssl_signature),
        ]
    )
    assert signed.returncode == 0, signed.stdout + signed.stderr
    verify_sm2_message(key.public_key(), MESSAGE, openssl_signature.read_bytes())

    with pytest.raises(InvalidSm2Signature):
        verify_sm2_message(key.public_key(), MESSAGE + b"!", openssl_signature.read_bytes())


def test_openssl_jws_segment_verifies_through_b_verifier(tmp_path):
    _require_openssl()
    key, private_path, _ = _write_keypair(tmp_path)
    payload = {
        "iss": "https://auth.agent-guard.test",
        "sub": "user-001",
        "client_id": "agent-planner",
    }
    token = sign_compact_jws(key, payload, key_id="as-sign-1", token_type="ag-at+jwt")
    signing_input = token.rsplit(".", 1)[0]

    signing_path = tmp_path / "signing-input.bin"
    signing_path.write_bytes(signing_input.encode("ascii"))
    der_path = tmp_path / "openssl.der"
    signed = _openssl(
        [
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private_path),
            "-in",
            str(signing_path),
            "-rawin",
            "-digest",
            "sm3",
            "-out",
            str(der_path),
        ]
    )
    assert signed.returncode == 0, signed.stdout + signed.stderr

    # B's strict DER -> fixed 64-byte r||s conversion must accept OpenSSL's DER.
    segment = b64url_encode(_der_to_jws_signature(der_path.read_bytes()))
    independently_signed = signing_input + "." + segment
    assert (
        verify_compact_jws(
            independently_signed,
            expected_type="ag-at+jwt",
            trusted_keys={"as-sign-1": key.public_key()},
        )
        == payload
    )
