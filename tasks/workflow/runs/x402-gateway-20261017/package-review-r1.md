# x402 gateway — independent PACKAGE_REVIEW

- Date: 2026-10-17
- Result: **PACKAGE_READY** for `tasks/workflow/runs/x402-gateway-20261017/package-v1.md`, X1–X8 only.
- Requested reviewer role: fresh gpt-6-astra/high; effective model/effort metadata: **UNKNOWN**.
- This is a package review, not implementation acceptance. No x402 behavior has been run or marked PASS. No Docker, business resource, dependency installation, source edit, Git mutation or subagent was used.
- Authorization basis: current policy and controller-provided current human instruction “把x402也做了吧”; prior “不做x402” is explicitly superseded for this local test-chain stage. No real assets/user wallets, Git publication or old long experiments are authorized here.

## Scope and baseline evidence

Read AGENTS/AGENT, current policy/review contract, complete X1–X8 package, README, security/interface/acceptance documentation, x402 design and threshold integration documentation and previous T1–T8 acceptance. Inspected actual `gateway/{endpoint,factory}.py`, `execution/{verified,service}.py`, `ledger/service.py`, `threshold/binding.py`, `tools/downstream.py`, and threshold integration test coverage. The accepted threshold stage remains a baseline, not proof of new payment behavior.

HEAD: `5c03d47fc19ef331002ad4b428262f4fa4b0a033`; branch: `codex/integrate-a-b-20261016`. Baseline manifest contains **752 files**; direct SHA verification found only `tasks/workflow/current-policy.md` different, consistent with the new phase authorization added after baseline capture. The package is new after that baseline. No implementation source drift was found. Git porcelain has 67 grouped entries (not a count of all constituent files); pre-existing staged/dirty/untracked content is preserved.

Package/contract SHA-256 independently read and rechecked:

| File | SHA-256 |
|---|---|
| package-v1.md | `e26da5e6bec8683356bbf99b54b44c4c1cc4a75666da3c1c198e274250471d9e` |
| AGENT.md | `fd7a38b4ba1e0fe74d52cd77aa4fa6da1ffa9040f6280e8270f5cdc13f160862` |
| current-policy.md | `000fac1d2f3fdd22f60457b3ee9b858364ccbbb2ff2352463f2df7775b46693e` |
| review-contract.md | `1ccdba2d10c3b12abe38c71e8d48eeef8aa40f7d2dad97594c5f4633861aab19` |

## Complete requirements assessment

| ID | Package assessment and required implementation evidence (all runtime checks NOT_RUN) |
|---|---|
| X1 | Complete: pinned v2 exact/EVM EIP-3009, real HTTP challenge/signature/response, official SDK and real local EVM receipt/balance/nonce. Authorization flow is verify→resource→settle→respond; resource execution is not already a successful payment. |
| X2 | Complete: accepted immutable operation, complete authorization/action/business association, all payment facts, unchanged all-ancestor CNY checks and a separate atomic asset budget. Prefer the explicitly permitted V3 payment digest, preserving V1/V2 bytes. If using V2 plus a trusted quote mapping, mapping must already be immutable when approved and cover every payment fact; changing a config dictionary after approval is not that mapping. Show payment facts to the approver. |
| X3 | Complete: acceptance transaction reserves asset funds and binds immutable intent; authorization/nonce/payload persisted before transmission; one operation cannot obtain a different payment. Unique constraints and guarded state transitions must protect concurrency as well as normal requests. |
| X4 | Complete: UNKNOWN retains reservation, real chain reconciliation, separate payment/resource facts, process restart and expiry-safe recovery. Missing receipt/lookup result or an HTTP error is not proof of no payment. |
| X5 | Complete: strict bounded parsing and fixed approved origins/network/asset; reject unsupported methods/flows, redirects and security-field ambiguity. Validate EIP-712 token name/version/domain and authorization payer/to/value/time/nonce as well as the outer accepted/resource fields. Preserve production TLS and current authorization. |
| X6 | Complete and appropriately focused: real PG/SM2/FROST→HTTP→local chain positive case; rejection/mutation/expiry, concurrency/replay, rollback, response-loss and real process recovery; effect and all ledger associations rather than HTTP-only assertions. No need to revive old broad/long matrices. |
| X7 | Complete: fixed native desktop run with dedicated automatic resources, real button success, sanitized local/public display and public POST403. Preserve old threshold entry and Claude layout. |
| X8 | Complete: protocol/dependency/license pins, migration/wheel/lineage, recovery/build/run documentation, truthful stage scope and original failures, STOP and exact-owner cleanup. Python 3.11 dependency resolution/installation is part of implementation validation; package review did not install it. |

## Lean implementation guidance from the actual baseline

These are concrete ways to satisfy the existing package, not new scope or requests for another package iteration.

1. `VerifiedExecution` already composes threshold and evidence callbacks into `TrustedAcceptBinding`; compose payment-intent insertion and asset reservation here, using the same accepted operation and transaction. Do no HTTP/RPC or signing-network work under these locks. Preserve the existing final DB-clock gate, including checks after lock waits. Add root `migrations/009_*.sql`; the unrelated `migrations/b/009_*` already exists and must remain untouched.
2. Use a small downstream adapter implementing existing execute/query contracts, with a separate persisted payment state. `ExecutionService.run_operation` currently queries and may execute again after a missing result; this must never create a fresh payment authorization. More critically, existing `MockDownstream.query` can return a created order before payment is known: the adapter must withhold terminal success until both the bound resource result and confirmed payment are known. A settled payment with failed/missing resource stays recorded as paid; do not translate it to the old zero-effect refusal/release path. Keep uncertain combinations UNKNOWN rather than inventing refunds or distributed atomicity.
3. Prefer one isolated long-lived local EVM service for both initial worker and restarted worker, plus a separate fresh worker process for the crash test. An in-process eth-tester recreated on restart would lose chain state and fail X4; eth-tester is usable if hosted in a surviving service, or use a pinned Anvil process. One local test token with upstream EIP-3009 source/bytecode provenance is sufficient. No multichain support, remote faucet or public testnet is needed.
4. Use the pinned SDK for signing/verification/settlement, but surround it with the strict trusted-intent parser; SDK model parsing alone is not evidence that duplicates, unknown fields or coercion are rejected. EIP-3009 signs transfer parameters, not the resource URL/operation ID: trusted pre-sign checks and immutable server-side operation/payment association remain necessary. One nonce must not acquire a second order/resource association.
5. Reconcile using actual chain receipt status plus correctly bound token events/authorization state and the original payer/payee/amount/network. A tx hash, current balance, or consumed nonce alone does not prove this exact successful transfer. After expiry, query a prior transfer and retain uncertainty; do not renew the authorization or treat expiry alone as permission to release. A repeated byte-identical authorization can be safe against double transfer through EIP-3009 nonce consumption, but resource idempotency and expiry still need enforcement.

## Official-source verification

The pinned [core v2 specification](https://github.com/x402-foundation/x402/blob/faa1c694c66a3732aaabbce93bdae140e521a67d/specs/x402-specification-v2.md) defines the default authorization ordering. The pinned [exact EVM specification](https://github.com/x402-foundation/x402/blob/faa1c694c66a3732aaabbce93bdae140e521a67d/specs/schemes/exact/scheme_exact_evm.md) describes EIP-3009 signature/verification/settlement and pending confirmation with a transaction hash. [PyPI x402 2.25.0](https://pypi.org/project/x402/2.25.0/) exposes the release and artifacts, MIT license and Python >=3.10 metadata, including Python 3.11 classification. This verifies dependency existence and protocol feasibility; it does not claim that the September SDK implements every later feature in the pinned October specification. Worker must exercise the selected narrow profile and lock its actual dependencies.

## Disposition

No blocking package defect found. Proceed once with X1–X8 implementation, targeted self-check and STOP, then freeze the complete candidate for one fresh implementation acceptance. Unimplemented behavior and dependency installation remain NOT_RUN here by design. No cosmetic correction or broad experiment is requested. Project status remains PARTIAL.
