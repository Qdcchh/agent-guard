"""Operator HTTPS retrieval plus independent registry and possession approval."""

from __future__ import annotations

import hashlib
import ssl
import urllib.request
from datetime import datetime, timezone
from types import MappingProxyType
from urllib.parse import urlsplit

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.crypto.sm import load_sm2_public_key, sm3_b64url, verify_sm2_message
from agent_guard.demo.config import (
    ApprovedDIDSnapshot,
    ApprovedRegistry,
    DemoConfigError,
    DemoRunConfig,
)
from agent_guard.identity.resolver import IdentityResolver, did_web_url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise DemoConfigError("DID redirect forbidden")


def possession_message(config: DemoRunConfig, registry: ApprovedRegistry, registration) -> bytes:
    return b"AG-DEMO-DID-APPROVAL-2\x00" + canonical_json_bytes(
        {
            "run_id": config.run_id,
            "tenant_id": registration.tenant_id,
            "client_id": registration.client_id,
            "did": registration.did,
            "kid": registration.kid,
            "spki_sm3": registration.spki_sm3,
            "purposes": list(registry.purposes[registration.client_id]),
            "challenge_sm3": sm3_b64url(registry.challenge),
        }
    )


def approve_dids(
    config: DemoRunConfig, *, registry: ApprovedRegistry, proof_of_possession
) -> ApprovedDIDSnapshot:
    if (
        type(config) is not DemoRunConfig
        or type(registry) is not ApprovedRegistry
        or registry.run_id != config.run_id
        or type(registry.challenge) is not bytes
        or len(registry.challenge) < 32
    ):
        raise DemoConfigError("independent run-bound registry required")
    expected = {"agent-" + h for h in ("planner", "selector", "executor")}
    entries = {r.client_id: r for r in registry.registrations}
    if (
        len(entries) != 3
        or set(entries) != expected
        or set(proof_of_possession) != expected
        or set(registry.purposes) != expected
    ):
        raise DemoConfigError("exact approval registry required")
    context = ssl.create_default_context(cafile=str(registry.ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )
    documents, fingerprints, fetched_at = {}, {}, {}
    for client, registration in entries.items():
        h = client.removeprefix("agent-")
        url = did_web_url(registration.did)
        parsed = urlsplit(url)
        if (
            registration.tenant_id != config.scope["tenant_id"]
            or not registration.active
            or url != config.endpoints["did_urls"][h]
            or parsed.port not in (None, 443)
        ):
            raise DemoConfigError("unapproved DID registration")
        required = (
            ("authentication", "capabilityInvocation", "capabilityDelegation")
            if h != "executor"
            else ("authentication", "capabilityInvocation")
        )
        if registry.purposes[client] != required:
            raise DemoConfigError("approval purpose mismatch")
        request = urllib.request.Request(url, headers={"Accept": "application/did+json"})
        with opener.open(request, timeout=5) as response:
            if (
                response.status != 200
                or response.geturl() != url
                or response.headers.get_content_type() != "application/did+json"
            ):
                raise DemoConfigError("DID transport rejected")
            cert = response.fp.raw._sock.getpeercert(binary_form=True)
            raw = response.read(65537)
        if len(raw) > 65536:
            raise DemoConfigError("DID capacity")
        documents[url] = canonical_json_bytes(load_strict_json(raw))
        fingerprints[url] = hashlib.sha256(cert).hexdigest()
        fetched_at[url] = datetime.now(timezone.utc).isoformat()
    resolver = IdentityResolver(
        {(r.tenant_id, r.client_id): r for r in entries.values()},
        allowed_hosts=frozenset(("identity.agent-guard.test",)),
        fetch_document=lambda url: documents[url],
    )
    for client, registration in entries.items():
        for purpose in registry.purposes[client]:
            resolver.resolve_registered(client, registration.tenant_id, purpose)
        proof = proof_of_possession[client]
        verify_sm2_message(
            load_sm2_public_key(registration.spki_der),
            possession_message(config, registry, registration),
            proof,
        )
    return ApprovedDIDSnapshot(
        config.run_id,
        MappingProxyType(documents),
        MappingProxyType({u: sm3_b64url(b) for u, b in documents.items()}),
        MappingProxyType(fingerprints),
        MappingProxyType(fetched_at),
    )


def save_approved_snapshot(config: DemoRunConfig, *, approved: ApprovedDIDSnapshot):
    """Freeze operator-approved public bytes through an exclusive owned output."""
    import os

    from agent_guard.server.private_files import private_directory

    if os.getuid() != config.roles["operator"].uid or approved.run_id != config.run_id:
        raise DemoConfigError("approval publisher operator required")
    value = {
        "version": "demo-did-approval-2",
        "run_id": config.run_id,
        "owner_id": config.owner_id,
        "documents": {
            url: {
                "canonical": raw.decode("utf-8"),
                "sm3": approved.digests[url],
                "certificate_sha256": approved.certificate_fingerprints[url],
                "fetched_at": approved.fetched_at[url],
            }
            for url, raw in approved.documents.items()
        },
    }
    directory = config.roles["operator"].public_config_file.parent
    with private_directory(directory) as private:
        private.write_file("approved-did-manifest.json", canonical_json_bytes(value))
    path = directory / "approved-did-manifest.json"
    path.chmod(0o444)
    return path


def load_approved_snapshot(config: DemoRunConfig) -> ApprovedDIDSnapshot:
    """Read the explicitly mounted independent operator manifest, never a token."""
    from agent_guard.demo.config import exact

    value = load_strict_json(config.approved_did_manifest.read_bytes())
    exact(value, ("version", "run_id", "owner_id", "documents"))
    if (value["version"], value["run_id"], value["owner_id"]) != (
        "demo-did-approval-2",
        config.run_id,
        config.owner_id,
    ) or set(value["documents"]) != set(config.endpoints["did_urls"].values()):
        raise DemoConfigError("independent approval manifest mismatch")
    documents, digests, fingerprints, fetched_at = {}, {}, {}, {}
    for url, item in value["documents"].items():
        exact(item, ("canonical", "sm3", "certificate_sha256", "fetched_at"))
        raw = item["canonical"].encode("utf-8")
        if (
            len(raw) > 65536
            or canonical_json_bytes(load_strict_json(raw)) != raw
            or sm3_b64url(raw) != item["sm3"]
        ):
            raise DemoConfigError("approved DID bytes/hash mismatch")
        documents[url] = raw
        digests[url] = item["sm3"]
        fingerprints[url] = item["certificate_sha256"]
        fetched_at[url] = item["fetched_at"]
    return ApprovedDIDSnapshot(
        config.run_id,
        MappingProxyType(documents),
        MappingProxyType(digests),
        MappingProxyType(fingerprints),
        MappingProxyType(fetched_at),
    )


def load_registry(config: DemoRunConfig) -> ApprovedRegistry:
    """Read independent operator approval records before fetching any DID."""
    import os

    from agent_guard.contracts.encoding import b64url_decode
    from agent_guard.crypto.sm import serialize_sm2_public_key
    from agent_guard.demo.config import exact
    from agent_guard.identity.resolver import RegisteredIdentity
    from agent_guard.server.factory import _load_public_key
    from agent_guard.server.private_files import read_private_file

    role = config.roles["operator"]
    if os.getuid() != role.uid:
        raise DemoConfigError("operator registry UID required")
    value = load_strict_json(read_private_file(role.private_files["approval_registry"]))
    exact(value, ("run_id", "challenge", "registrations"))
    if value["run_id"] != config.run_id or type(value["registrations"]) is not list:
        raise DemoConfigError("independent registry run mismatch")
    registrations, purposes = [], {}
    for row in value["registrations"]:
        exact(
            row,
            (
                "tenant_id",
                "client_id",
                "did",
                "kid",
                "spki_pem",
                "spki_der",
                "purposes",
            ),
        )
        spki = b64url_decode(row["spki_der"])
        if serialize_sm2_public_key(_load_public_key(row["spki_pem"], "approval registry")) != spki:
            raise DemoConfigError("independent registry SPKI mismatch")
        registrations.append(
            RegisteredIdentity(row["tenant_id"], row["client_id"], row["did"], row["kid"], spki)
        )
        if row["client_id"] in purposes:
            raise DemoConfigError("duplicate approval identity")
        purposes[row["client_id"]] = tuple(row["purposes"])
    return ApprovedRegistry(
        config.run_id,
        tuple(registrations),
        MappingProxyType(purposes),
        role.public_config_file.parent / "ca.pem",
        b64url_decode(value["challenge"]),
    )
