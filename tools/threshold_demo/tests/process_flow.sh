#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/agent-guard-threshold-target}"
cargo build --locked --quiet
bin="$CARGO_TARGET_DIR/debug/agent-guard-threshold-demo"
scratch="$(mktemp -d /tmp/agent-guard-threshold-flow.XXXXXXXX)"
trap 'case "$scratch" in /tmp/agent-guard-threshold-flow.*) rm -rf -- "$scratch";; esac' EXIT
mkdir "$scratch/session-a" "$scratch/session-b" "$scratch/session-c" "$scratch/session-d" "$scratch/session-e" "$scratch/session-f"

python3 - "$scratch/action.json" <<'PY'
import hashlib
import json
import sys

params = {
    "request_id": "req-001",
    "quote_id": "quote-001",
    "quote_version": "1",
    "items": [{"sku": "sku-001", "quantity": 1}],
    "delivery_id": "office-001",
}
digest = hashlib.sha256(json.dumps(params, separators=(",", ":")).encode()).hexdigest()
action = {
    "version": 1,
    "tenant_id": "tenant-demo",
    "task_id": "task-001",
    "root_grant_id": "grant-root",
    "grant_id": "grant-leaf",
    "holder_client_id": "agent-executor",
    "holder_kid": "kid-exec",
    "audience": "gateway-demo",
    "tool_id": "procurement.order.create",
    "currency": "CNY",
    "policy_version": 1,
    "key_epoch": 1,
    "action_id": "order-001",
    "idempotency_key": "idem-001",
    **params,
    "amount_fen": 70000,
    "canonical_params_sha256": digest,
    "expires_at": 4102444800,
}
with open(sys.argv[1], "w", encoding="utf-8") as output:
    json.dump(action, output, separators=(",", ":"))
PY

must_reject() {
    if "$bin" "$@" >/dev/null 2>&1; then
        printf 'unexpected acceptance: %s\n' "$*" >&2
        exit 1
    fi
}

"$bin" setup "$scratch/dealer" "$scratch/action.json"
test -f "$scratch/dealer/public.json"
test -f "$scratch/dealer/signer-1/share.json"
test -f "$scratch/dealer/signer-2/share.json"
test -f "$scratch/dealer/signer-3/share.json"
test -f "$scratch/dealer/signer-1/policy.json"
test -f "$scratch/dealer/signer-2/policy.json"
test -f "$scratch/dealer/signer-3/policy.json"
test ! -f "$scratch/dealer/share.json"
test "$(stat -c %a "$scratch/dealer")" = 700
test "$(stat -c %a "$scratch/dealer/signer-1")" = 700
test "$(stat -c %a "$scratch/dealer/signer-1/share.json")" = 600
test "$(stat -c %a "$scratch/dealer/signer-1/policy.json")" = 600

"$bin" round1 "$scratch/dealer/signer-1" 1 "$scratch/session-a"
"$bin" round1 "$scratch/dealer/signer-3" 3 "$scratch/session-a"
must_reject prepare "$scratch/action.json" "$scratch/session-a" 1 1
"$bin" prepare "$scratch/action.json" "$scratch/session-a" 1 3
"$bin" round2 "$scratch/dealer/signer-1" 1 "$scratch/action.json" "$scratch/session-a"
must_reject round2 "$scratch/dealer/signer-1" 1 "$scratch/action.json" "$scratch/session-a"
"$bin" round2 "$scratch/dealer/signer-3" 3 "$scratch/action.json" "$scratch/session-a"
must_reject aggregate "$scratch/action.json" "$scratch/dealer/public.json" "$scratch/session-a" 1 1
"$bin" aggregate "$scratch/action.json" "$scratch/dealer/public.json" "$scratch/session-a" 1 3
"$bin" verify "$scratch/action.json" "$scratch/dealer/public.json" "$scratch/session-a/signature.json"
"$bin" export-vector "$scratch/action.json" "$scratch/dealer/public.json" "$scratch/session-a/signature.json" "$scratch/vector.json"
if [[ -n "${AG_THRESHOLD_VECTOR_OUT:-}" ]]; then
    cp "$scratch/vector.json" "$AG_THRESHOLD_VECTOR_OUT"
fi

python3 - "$scratch/action.json" "$scratch/tampered.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as source:
    action = json.load(source)
action["amount_fen"] += 1
with open(sys.argv[2], "w", encoding="utf-8") as output:
    json.dump(action, output)
PY
must_reject verify "$scratch/tampered.json" "$scratch/dealer/public.json" "$scratch/session-a/signature.json"

"$bin" round1 "$scratch/dealer/signer-1" 1 "$scratch/session-c"
if policy_result=$("$bin" round2 "$scratch/dealer/signer-1" 1 "$scratch/tampered.json" "$scratch/session-c" 2>&1); then
    printf 'unexpected signer policy acceptance\n' >&2
    exit 1
fi
[[ "$policy_result" == *"authenticated local approval"* ]]
must_reject round2 "$scratch/dealer/signer-1" 1 "$scratch/action.json" "$scratch/session-c"

for spec in '1 session-d grant_id other-grant' '2 session-e max_amount_fen 69999' '3 session-f canonical_params_sha256 bad-digest'; do
    read -r signer session field value <<< "$spec"
    "$bin" round1 "$scratch/dealer/signer-$signer" "$signer" "$scratch/$session"
    python3 - "$scratch/dealer/signer-$signer/policy.json" "$field" "$value" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
policy = json.loads(path.read_text(encoding="utf-8"))
policy[sys.argv[2]] = int(sys.argv[3]) if sys.argv[2] == "max_amount_fen" else sys.argv[3]
path.write_text(json.dumps(policy), encoding="utf-8")
PY
    if domain_result=$("$bin" round2 "$scratch/dealer/signer-$signer" "$signer" "$scratch/action.json" "$scratch/$session" 2>&1); then
        printf 'unexpected signer domain policy acceptance\n' >&2
        exit 1
    fi
    [[ "$domain_result" == *"domain policy denied action"* ]]
done

"$bin" round1 "$scratch/dealer/signer-2" 2 "$scratch/session-b"
"$bin" abort "$scratch/dealer/signer-2" 2 "$scratch/session-b"
must_reject round2 "$scratch/dealer/signer-2" 2 "$scratch/action.json" "$scratch/session-b"
printf 'process-separated FROST flow and rejection probes passed\n'
