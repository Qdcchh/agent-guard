"""Offline verification of one unanchored final receipt evidence bundle.

Trust keys and historical registrations must arrive through an independent
channel, never from fields inside the evidence bundle. This checks one
operation's cryptographic and delta consistency, not completeness of a task
history, current authorization state, or the truth of a downstream result.
"""

from agent_guard.contracts.encoding import canonical_json_bytes
from agent_guard.contracts.ledger_changes import canonical_ledger_changes_bytes
from agent_guard.evidence.receipt_semantics import (
    _BUNDLE_FIELDS,
    ReceiptComponents,
    ReceiptTrust,
    ReceiptVerificationError,
    VerifiedReceipt,
    _object,
    _outer_encoded_size,
    verify_receipt_components,
)
from agent_guard.evidence.receipt_semantics import (
    _RECEIPT_FIELDS as _RECEIPT_FIELDS,
)
from agent_guard.evidence.receipt_semantics import (
    _ascii_jws as _ascii_jws,
)


def verify_receipt_bundle(bundle: object, *, trust: ReceiptTrust) -> VerifiedReceipt:
    """Preserve the strict version-1 wrapper and exact encoded outer limit."""
    data = _object(bundle, _BUNDLE_FIELDS, "evidence bundle")
    if data["manifest_version"] != "AG-EVIDENCE-1" or data["anchoring_status"] != "UNANCHORED":
        raise ReceiptVerificationError("unsupported evidence manifest or anchoring claim")
    try:
        ledger = canonical_ledger_changes_bytes(data["ledger_changes"])
        encoded = {
            name: ledger if name == "ledger_changes" else canonical_json_bytes(value)
            for name, value in data.items()
        }
        if _outer_encoded_size(encoded) > 1048576:
            raise ReceiptVerificationError("evidence bundle too large")
        ancestors = data["ancestor_tokens"]
        if type(ancestors) is not list or not 1 <= len(ancestors) <= 3:
            raise ReceiptVerificationError("invalid ancestor token path")
        components = ReceiptComponents(
            data["token_jws"].encode("ascii"),
            data["proof_jws"].encode("ascii"),
            tuple(token.encode("ascii") for token in ancestors),
            encoded["request"],
            encoded["result"],
            ledger,
            data["receipt_jws"].encode("ascii"),
        )
        return verify_receipt_components(components, trust)
    except (ValueError, TypeError, UnicodeError, AttributeError) as exc:
        if isinstance(exc, ReceiptVerificationError):
            raise
        raise ReceiptVerificationError("invalid signed receipt evidence") from exc
