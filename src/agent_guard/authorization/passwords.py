"""Password hashing for synthetic local accounts using the stdlib scrypt KDF.

A password is never stored or compared as a bare SHA-256/SM3 digest. The
encoded form carries the scheme and parameters so a future parameter change can
be versioned without an ambiguous silent upgrade. Trusted provisioning and
tests only; no HTTP body writes this table directly.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from functools import lru_cache

from agent_guard.contracts.encoding import EncodingError, b64url_decode, b64url_encode

_N = 1 << 14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16
_MAX_PASSWORD = 1024
_MAX_MEM = 64 * 1024 * 1024
_MAX_N = 1 << 20
_MAX_R = 32
_MAX_P = 16
_ENCODED = re.compile(
    r"scrypt\$(\d{1,8})\$(\d{1,4})\$(\d{1,4})\$([A-Za-z0-9_-]{16,64})\$([A-Za-z0-9_-]{16,64})\Z",
    re.ASCII,
)


class PasswordError(ValueError):
    """A password input or encoded hash violates the local account profile."""


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=_DKLEN, maxmem=_MAX_MEM
    )


def hash_password(password: str) -> str:
    """Return a salted scrypt encoding of ``password`` (never a bare digest)."""
    if type(password) is not str or not password or len(password) > _MAX_PASSWORD:
        raise PasswordError("password must be a nonempty bounded string")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = _derive(password, salt, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${b64url_encode(salt)}${b64url_encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time comparison of ``password`` against one stored encoding."""
    if type(password) is not str or not password or len(password) > _MAX_PASSWORD:
        return False
    if type(encoded) is not str:
        return False
    match = _ENCODED.fullmatch(encoded)
    if match is None:
        return False
    raw_n, raw_r, raw_p, salt_s, hash_s = match.groups()
    n, r, p = int(raw_n), int(raw_r), int(raw_p)
    if not (1 < n <= _MAX_N and 0 < r <= _MAX_R and 0 < p <= _MAX_P):
        return False
    try:
        salt = b64url_decode(salt_s)
        expected = b64url_decode(hash_s)
    except (EncodingError, TypeError):
        return False
    if len(salt) != _SALT_BYTES or len(expected) != _DKLEN:
        return False
    try:
        derived = _derive(password, salt, n, r, p)
    except (ValueError, MemoryError, OverflowError):
        return False
    return hmac.compare_digest(derived, expected)


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A well-formed hash used to equalize unknown-user login timing."""
    return hash_password(secrets.token_urlsafe(32))
