"""Fail-closed did:web resolution against administrator-approved key snapshots.

The enterprise registry is supplied by a trusted caller. DID documents can
confirm an approved key and purpose, but can never self-register a new key.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from tongsuopy.crypto.asymciphers.ec import EllipticCurvePublicKey

from agent_guard.contracts.encoding import EncodingError, b64url_decode, load_strict_json
from agent_guard.crypto.sm import load_sm2_public_key, sm3_b64url

METHOD_TYPE = "https://github.com/Qdcchh/agent-guard#Sm2VerificationKeyV1"
SPKI_PROPERTY = "https://github.com/Qdcchh/agent-guard#publicKeySpki"
_DID_RE = re.compile(r"did:web:([a-z0-9.-]+)((?::[A-Za-z0-9_-]+)*)\Z", re.ASCII)
_PURPOSES = frozenset({"authentication", "capabilityInvocation", "capabilityDelegation"})
MAX_DOCUMENT_BYTES = 65536


class IdentityError(ValueError):
    """The approved key cannot be confirmed as active in its DID document."""


@dataclass(frozen=True)
class RegisteredIdentity:
    tenant_id: str
    client_id: str
    did: str
    kid: str
    spki_der: bytes
    active: bool = True

    @property
    def spki_sm3(self) -> str:
        return sm3_b64url(self.spki_der)


@dataclass(frozen=True)
class ResolvedIdentity:
    registration: RegisteredIdentity
    public_key: EllipticCurvePublicKey


def did_web_url(did: str) -> str:
    """Map a deliberately restricted did:web identifier to one HTTPS URL."""
    match = _DID_RE.fullmatch(did)
    if match is None:
        raise IdentityError("unsupported did:web identifier")
    host, path = match.groups()
    if host.startswith(".") or host.endswith(".") or ".." in host or "." not in host:
        raise IdentityError("invalid did:web host")
    segments = path.split(":")[1:] if path else []
    suffix = "/".join(segments) + "/" if segments else ".well-known/"
    return f"https://{host}/{suffix}did.json"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise IdentityError("DID redirects are not allowed")


def _fetch_document(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/did+json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=5) as response:
            if response.headers.get_content_type() != "application/did+json":
                raise IdentityError("DID document has the wrong media type")
            raw = response.read(MAX_DOCUMENT_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise IdentityError("DID document unavailable") from exc
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise IdentityError("DID document too large")
    return raw


class IdentityResolver:
    """Resolve only an exact tenant/client entry from a trusted registry.

    ``fetch_document`` is injectable for offline unit tests. Production uses
    HTTPS with system TLS validation and redirects disabled. Registry loading
    and administrator approval are outside this read-only class.
    """

    def __init__(
        self,
        registrations: Mapping[tuple[str, str], RegisteredIdentity],
        *,
        allowed_hosts: frozenset[str],
        fetch_document: Callable[[str], bytes] = _fetch_document,
    ) -> None:
        self._registrations = dict(registrations)
        self._allowed_hosts = allowed_hosts
        self._fetch_document = fetch_document

    def resolve_registered(self, client_id: str, tenant_id: str, purpose: str) -> ResolvedIdentity:
        if purpose not in _PURPOSES:
            raise IdentityError("unsupported verification purpose")
        entry = self._registrations.get((tenant_id, client_id))
        if entry is None or not entry.active:
            raise IdentityError("client is not registered and active")
        if entry.tenant_id != tenant_id or entry.client_id != client_id:
            raise IdentityError("registry key mismatch")
        url = did_web_url(entry.did)
        host = url.split("/", 3)[2]
        if host not in self._allowed_hosts:
            raise IdentityError("DID host is not approved")
        if not entry.kid.startswith(entry.did + "#"):
            raise IdentityError("key is not scoped to its DID")
        try:
            document = load_strict_json(self._fetch_document(url))
        except (EncodingError, UnicodeError) as exc:
            raise IdentityError("invalid DID document JSON") from exc
        required = {"id", "verificationMethod", "authentication", "capabilityInvocation"}
        if (
            type(document) is not dict
            or not required <= set(document)
            or not set(document) <= (required | {"capabilityDelegation"})
        ):
            raise IdentityError("DID document fields do not match the profile")
        if document["id"] != entry.did:
            raise IdentityError("DID document id mismatch")
        methods = document["verificationMethod"]
        if type(methods) is not list or len(methods) != 1:
            raise IdentityError("expected one approved verification method")
        method = methods[0]
        if type(method) is not dict or set(method) != {"id", "type", "controller", SPKI_PROPERTY}:
            raise IdentityError("invalid verification method")
        if (
            method["id"] != entry.kid
            or method["type"] != METHOD_TYPE
            or method["controller"] != entry.did
        ):
            raise IdentityError("verification method does not match registry")
        try:
            spki = b64url_decode(method[SPKI_PROPERTY])
            public_key = load_sm2_public_key(spki)
        except (EncodingError, TypeError, ValueError) as exc:
            raise IdentityError("invalid DID SM2 public key") from exc
        if spki != entry.spki_der:
            raise IdentityError("DID key changed without administrator approval")
        for name in _PURPOSES:
            refs = document.get(name, [])
            if type(refs) is not list or len(refs) != len(set(map(str, refs))):
                raise IdentityError("invalid DID purpose references")
            if any(type(ref) is not str or ref != entry.kid for ref in refs):
                raise IdentityError("unknown DID purpose key")
        if entry.kid not in document.get(purpose, []):
            raise IdentityError("key is not authorized for this purpose")
        return ResolvedIdentity(entry, public_key)
