"""SM2 second-implementation interoperability against the OpenSSL CLI.

OpenSSL is an implementation independent of Tongsuo. The keypair is generated
by OpenSSL as an SM2 key (so OpenSSL applies SM2 semantics) and loaded into
Tongsuo; both directions are then exercised over the same fixed message:
Tongsuo signature -> OpenSSL verify, OpenSSL signature -> Tongsuo verify, and
a JWS whose signature segment was produced by OpenSSL. The OpenSSL commands
pass ``-pkeyopt distid:1234567812345678`` so both sides use the GM-MVP-1 user
identifier explicitly (the OpenSSL 3 provider default distid is not the GB/T
default). This is a development-vector check on the CI runner, not a claim
about every OpenSSL build or algorithm suite.
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
    sign_compact_jws,
    sign_sm2_message,
    verify_compact_jws,
    verify_sm2_message,
)

pytestmark = pytest.mark.integration

MESSAGE = b"agent-guard GM-MVP-1 SM2 independent interop vector v1"
DISTID = "distid:1234567812345678"


def _openssl(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["openssl", *args], capture_output=True, text=True, timeout=60)


def _require_openssl() -> None:
    if shutil.which("openssl") is None:
        pytest.fail("openssl CLI is required for the SM2 interop test", pytrace=False)


def _openssl_keypair(tmp_path):
    """Let OpenSSL generate a genuine SM2 keypair for both sides to use."""
    private_path = tmp_path / "sm2-private.pem"
    public_path = tmp_path / "sm2-public.pem"
    generated = _openssl(["genpkey", "-algorithm", "SM2", "-out", str(private_path)])
    assert generated.returncode == 0, generated.stdout + generated.stderr
    exported = _openssl(["pkey", "-in", str(private_path), "-pubout", "-out", str(public_path)])
    assert exported.returncode == 0, exported.stdout + exported.stderr
    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    public_key = serialization.load_pem_public_key(public_path.read_bytes())
    assert private_key.curve.name == "SM2" and public_key.curve.name == "SM2"
    return private_key, public_key, private_path, public_path


def test_sm2_signatures_interoperate_in_both_directions(tmp_path):
    _require_openssl()
    private_key, public_key, private_path, public_path = _openssl_keypair(tmp_path)
    message_path = tmp_path / "message.bin"
    message_path.write_bytes(MESSAGE)

    tongsuo_signature = tmp_path / "tongsuo.der"
    tongsuo_signature.write_bytes(sign_sm2_message(private_key, MESSAGE))
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
            "-pkeyopt",
            DISTID,
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
            "-pkeyopt",
            DISTID,
            "-out",
            str(openssl_signature),
        ]
    )
    assert signed.returncode == 0, signed.stdout + signed.stderr
    verify_sm2_message(public_key, MESSAGE, openssl_signature.read_bytes())

    with pytest.raises(InvalidSm2Signature):
        verify_sm2_message(public_key, MESSAGE + b"!", openssl_signature.read_bytes())


def test_openssl_jws_segment_verifies_through_b_verifier(tmp_path):
    _require_openssl()
    private_key, public_key, private_path, _ = _openssl_keypair(tmp_path)
    payload = {
        "iss": "https://auth.agent-guard.test",
        "sub": "user-001",
        "client_id": "agent-planner",
    }
    token = sign_compact_jws(private_key, payload, key_id="as-sign-1", token_type="ag-at+jwt")
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
            "-pkeyopt",
            DISTID,
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
            trusted_keys={"as-sign-1": public_key},
        )
        == payload
    )
