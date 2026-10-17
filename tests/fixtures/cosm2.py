"""Real policy-gated two-domain signing fixture; no raw-share policy bypass."""

from pathlib import Path

from agent_guard.authorization.permission_snapshot import PermissionSnapshotProvider
from agent_guard.contracts.encoding import b64url_decode
from agent_guard.cosign.authz_cli import SubprocessAuthzClient, write_public_trust
from agent_guard.cosign.authz_domain import AuthorizationDomainSigner, CosignRefused
from agent_guard.cosign.exec_domain import ExecutionDomainSigner
from agent_guard.cosign.shares import generate_shares
from agent_guard.threshold.codec import build_envelope, decode_header, encode_header, parse_envelope
from agent_guard.threshold.contracts import COSM2_PROFILE, ThresholdApprovalPolicy
from tests.fixtures.cosm2_readonly import readonly_role
from tests.fixtures.threshold import approval_action

__all__ = ["CosignSigner", "approval_action", "readonly_role"]


class CosignSigner:
    def __init__(
        self,
        directory,
        *,
        dsn_readonly,
        snapshot_provider,
        token_provider,
        catalog,
        policy=None,
        bundle_provider=None,
        process=False,
        payment_digest_provider=None,
        clock=None,
    ):
        self.directory = Path(directory)
        self._dsn = dsn_readonly
        self._provider = snapshot_provider
        self.policy = policy
        self._token_provider = token_provider
        self._catalog = catalog
        self._bundle_provider = bundle_provider
        self._process = process
        self._payment_provider = payment_digest_provider
        self._clock = clock
        self.last_timing_ms = {}

    def enroll(self):
        metadata = generate_shares(
            self.directory, key_epoch=self.policy.key_epoch if self.policy else 1
        )
        if self.policy is None:
            self.policy = ThresholdApprovalPolicy(
                group_public_key=b64url_decode(metadata["public_key_spki_b64url"]),
                policy_version=1,
                key_epoch=metadata["key_epoch"],
                scheme="sm2-2p",
            )
        if self.policy.group_public_key != b64url_decode(metadata["public_key_spki_b64url"]):
            raise ValueError("policy public key differs from newly enrolled shares")
        self.exec_signer = ExecutionDomainSigner(
            share_dir=self.directory / "exec",
            token_provider=self._token_provider,
            catalog=self._catalog,
            clock=self._clock,
            payment_digest_provider=self._payment_provider,
        )
        self.authz_signer = None
        if self._process:
            trust_file = self.directory / "public-trust.json"
            write_public_trust(self._provider, self.policy, trust_file)
            self._client = SubprocessAuthzClient(
                share_dir=self.directory / "authz", trust_file=trust_file, dsn_readonly=self._dsn
            )
        else:
            self.authz_signer = AuthorizationDomainSigner(
                share_dir=self.directory / "authz",
                dsn_readonly=self._dsn,
                snapshot_provider=self._provider,
                policy=self.policy,
            )
            self._client = self.authz_signer
        return metadata["public_key_spki_b64url"]

    def sign(self, action, *, bundle=None):
        if bundle is None:
            if self._bundle_provider is None:
                raise ValueError("actual verified bundle required")
            bundle = self._bundle_provider(action)
        header = self.exec_signer.approve(bundle, action, self._client)
        self.last_timing_ms = dict(self.exec_signer.last_timing_ms)
        return parse_envelope(decode_header(header), profile=COSM2_PROFILE)[1]

    def sign_refused(self, action, *, bundle=None):
        try:
            self.sign(action, bundle=bundle)
        except CosignRefused as exc:
            return exc
        raise AssertionError("expected genuine signing refusal")

    def header_for(self, action, signature):
        return encode_header(build_envelope(action, signature, profile=COSM2_PROFILE))


def readonly_provider(provider, dsn):
    return PermissionSnapshotProvider(
        dsn,
        issuer=provider._issuer,
        as_keys=provider._as_keys,
        registrations=provider._registrations,
    )
