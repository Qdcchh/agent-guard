# A2.3 core-r1 implementation / native STOP — NEEDS_REPLAN

Owner: `a23-core-r1-20261005`. Generated UTC: 2026-10-04T23:40:50.130443+00:00. Requested worker sol/medium; effective model UNKNOWN. Sole core14 writer; no subagents; no Git changes.

**Outcome: NEEDS_REPLAN. Core is not READY and is not released to consumers.** The conditional SDK gate was triggered by two actual legal 256-SKU AS/public/PG pipelines. Candidate writes stopped immediately; the SDK path was never written. The final complete source/wheel core and inherited regression checks were not run after this trigger. Root must freeze/review a new precise package before any fix or resumed implementation.

## Actual blocking evidence

Each SKU quantity is `35184372088831 = floor((2**53-1)/256)`, unit price is 1, total is `9007199254740736 <= 9007199254740991`. Task policy is registered at the real safe maximum before consent/login; the real authorization-code root and both real exchanges sign their own exact maximum limits and max_quantity. No signed chain, production bound, clock, or verifier DTO is modified. Supplier/quote/256 unique plain identifiers are real catalog/downstream inputs.

| Actual candidate | Source bytes | Ancestor JWS bytes | Request | Result | Ledger | SDK nonledger aggregate | Outcome |
|---|---:|---|---:|---:|---:|---:|---|
| SKU 16 bytes | 62583 | 8002/8130/8218 | 13818 | 18645 | 1186 | 67058 | real original aggregate rejection |
| SKU 17 bytes | 65145 | 8344/8472/8560 | 14074 | 18901 | 1186 | 68938 | real original aggregate rejection |

The first native probe was **1 PASS / 2 FAIL, exit 1** (`real-capacity-bounded-probe-r1`): width12 completed real accept/terminal/publication/current query/offline verification; widths16/17 completed public HTTP202 and independent downstream SUCCEEDED before the first failing SDK aggregate codec. The original `canonical_json_bytes` guard raises `EncodingError: canonical JSON exceeds the byte limit` at `verify_receipt_bundle` nonledger aggregation, wrapped as `ReceiptVerificationError`. Every independently measured component remains within the original limits; this is a legal-combination aggregate defect, not a padded DTO/arithmetic-only sample or a precondition rejection.

After candidate STOP, an ignored evidence-only script repeated widths16/17 and directly called the current `InternalPublisher.publish`. Its **2 PASS, exit0** means it confirmed the expected real failure, not publication acceptance. Both causes are exactly `EvidenceError -> ReceiptVerificationError -> EncodingError`. Full persisted `ag_*` and `ds_*` rows match byte-for-byte before/after (all family counts and SHA256 recorded). Outbox remains PENDING, receipt_jws null, signed_at null; three ancestors remain `(amount_reserved=0, amount_settled=9007199254740736, calls_reserved=0, calls_settled=1)` with exactly one downstream order. There was no cancellation, second terminal effect, release, re-execution, SDK patch, or expanded file scope.

Primary trigger artifacts: `real-capacity-bounded-probe-r1.{log,xml,command.json}`, each `real-capacity-bounded-probe-r1-capacity-width-{12,16,17}.json`, `conditional_trigger_replay_r1.py`, `conditional-trigger-replay-r1.{log,xml,command.json}`, and `conditional-trigger-replay-r1-width-{16,17}.json`. Source references are content SHA-bound in each replay record.

## Implemented frozen production interface (not consumer-released)

| API | Behavior/call order |
|---|---|
| `PermissionSnapshotProvider.load_tx(conn, token, *, grant_id, now)` | Same caller connection, original full chain-row validation through the one `_from_records` body. `load` owns and closes its connection before validation. |
| `scoped_trust_tx(conn, operation_id, *, issuer, as_keys, gateway_keys, registrations, permission_provider)` | Original real AS signatures -> original DB exact tenant/client/kid tuple and SPKI -> common historical window -> same-connection load_tx -> original full first-context/proof -> fresh immutable per-operation ReceiptTrust. Legal cross-operation holder kid/DID aliasing remains valid. |
| `ReceiptVerifier(*, issuer, as_keys, gateway_keys, registrations, permission_provider)` | Public trust only; GW kid/SPKI independent from AS and holders. `verify_tx(conn, operation_id, receipt_jws)` uses original SDK, then all17 decoded claims equal exact immutable DB projection. `read_tx(conn, operation_id)` validates state/timestamp and returns original READY bytes/date. |
| `ReceiptPublication(operation_id, receipt_id, receipt_status, receipt_jws, signed_at)` | Frozen dataclass. Nonterminal PENDING has no receipt id/JWS/time. Terminal fields come from immutable outbox; old READY values remain original. |
| `InternalPublisher(dsn, *, private_key, signing_kid, verifier, connect_timeout=5, lock_timeout_ms=10000, statement_timeout_ms=15000)` | Outbox-only FOR UPDATE -> same-connection projection/source -> actual SM2 sign -> original SDK self-verification and exact17 projection -> only3 publication columns atomic update -> immediate constraints -> commit. Already READY validates original bytes/time and does not sign again. `pending_page(*, after_operation_id, limit)` is bounded keyset read. |
| `VerifiedExecution.accept_response(bundle, *, receipt_verifier)` | Per-call closure reset on each attempt; original EvidenceStore binding -> same-connection publication capture -> original proof/link/final DBclock -> commit; return captured3fields with no postcommit SQL. Existing accept and AcceptResult defaults unchanged. |
| `AuthorizedQuery(dsn, *, evidence_store, receipt_verifier=None)` | Absent public verifier preserves original PENDING compatibility and rejects READY. Optional READY trust runs original SDK before final DBclock. Typed bad trusted material503/proof rollback; unknown runtime500. |
| `GatewayEndpoint(..., receipt_verifier=None)` / `build_app` | Optional `receipt_keys` contains public PEM only; public factory constructs tuple-preserving verifier and never uses signing PEM. HTTP invoke captures publication inside acceptance transaction. |

Exact signatures, source SHA256, symbol start/end and assertion lines are in `stop-source-scope-r1.json` and `core29-local-bindings-stop-r1.json`. The current production10 files exactly match the already-built r2 noneditable wheel10/10 SHA256; the wheel has all14 SQL files (`sourcewheel-content-stop-r1.json`). Four owned fixture/test files changed after that wheel copy; their latest cases are not falsely treated as wheel-validated.

## Actual self-checks and preserved failures

| Native run | PASS | FAIL | Meaning |
|---|---:|---:|---|
| aliases-r1 | 40 | 0 | Earlier incremental self-check; exact nodeids/outcomes retained. |
| capacity-r1 | 1 | 0 | Earlier incremental self-check; exact nodeids/outcomes retained. |
| conditional-trigger-replay-r1 | 2 | 0 | Evidence-only expected-failure assertions; no core acceptance. |
| core-full-r1 | 721 | 6 | Source 500 deadline cases plus core; 2 missing-import failures, 4 unreached target gates. No retroactive cause claim for the old unrecorded futures. |
| core-full-wheel-r2 | 727 | 0 | Original wheel snapshot, all500 real deadline cases pass; distinct wheel_core DB. |
| core-latest-nondeadline-r1 | 286 | 70 | New test oracle assembly failures (ag_proof_replays typo and proof/retry-link accounting), preserved. |
| core-latest-nondeadline-r2 | 356 | 0 | Corrected356 cases all pass,500 excluded; direct SM2 backend unsupported native digest lookup, PG faults, PID/SIGKILL, retry SQL40001,1s accept waits, recovery/fencing/revoke/disable races. |
| core-tests-r1 | 19 | 3 | Earlier incremental self-check; exact nodeids/outcomes retained. |
| core-tests-r2 | 49 | 24 | Earlier incremental self-check; exact nodeids/outcomes retained. |
| core-tests-r3 | 145 | 0 | Earlier incremental self-check; exact nodeids/outcomes retained. |
| core-tests-r4 | 309 | 0 | Earlier incremental self-check; exact nodeids/outcomes retained. |
| late-corrections-smoke-r1 | 88 | 0 | Source target correction88 cases including original4 failed deadline IDs and actual two publisher FOR UPDATE/PID waits; all future exceptions drained. |
| ordinary-r1 | 1046 | 1 | Source missing distribution metadata only; preserve first failure. |
| ordinary-r2 | 1051 | 0 | Source metadata installed via PEP517; ordinary full unit pass. |
| real-capacity-bounded-probe-r1 | 1 | 2 | Width12 legal pass, widths16/17 genuine blocking failure. |

The interrupted initial wheel batch `core-full-wheel-r1` exited143 after an owned-process stop because it originally used the source DB; it is explicitly invalid for acceptance. Its log/command and stop evidence remain. The subsequent complete wheel batch used its own wheel_core DB and passed. Source and wheel HOME/TMP/cache/test DSN were separated for later runs; ordinary deployment/PG environment names were blanked. Final deadline suites were planned to run serially but stopped before that final execution because of the genuine conditional gate.

Real signing fault description is precise: the test retains an actual SM2 key and existing `sign_compact_jws` call, redirects its real Tongsuo sign digest operation to a deliberately unavailable native EVP digest name, and receives backend UnsupportedAlgorithm; restoring the same key/path succeeds. Earlier object-TypeError fixture results are not claimed as real backend fault proof. A separate private-handle backend debug probe segfaulted139 and is marked debug-only/no obligation acceptance (`backend-probe-debug-r1.json`); no unsafe key-handle experiment was used as a passing test.

Every old failure and command exit remains; raw original JUnit is preserved0600 under0700 `private-original-junit`, with only exact synthetic password/compact-JWS masking in public XML. `junit-redaction-manifest-r1.json` binds both originals and masked XML SHA; nodeids/outcomes/assertion text remain parseable.

The stopped current tree has **861 actual collected nodes**, of which the formal core29 binding matrix (26 planned test functions +3 static inspection nodes) is bound to actual functions, assertions and run labels. This is a collection/binding record, not a claim all861 or all29 latest finite obligations passed. `core29-local-bindings-stop-r1.json` deliberately labels every binding PARTIAL/NEEDS_REPLAN and final latest source/wheel NOT_RUN.

Known pending finite cases include latest unit all3 wrong-typ/one actual signature-byte-flip additions, latest actual signer.pem creation sentinel, complete latest codec/probe/group lint and source/wheel rerun, all original affected PG/CTX/8wait/4short-window regressions, explicit missing-case expansion of historical disjoint windows/cross-owner/old self-key/UNKNOWN invoke as required by the next reviewed package. No full119/112 integrator acceptance or independent review has occurred. Latest probe test local imports may still require routine lint cleanup; candidate STOP prevented editing them merely to obtain green output.

## N021/N031 bounds: preserved rules, explicit premises

The old READY aggregation gate provides a cancellation proof: identical canonical result and receipt_jws bytes cancel; verified SM2 JWS has raw64-byte signature ->86 base64url bytes plus2 dots, yielding at least88 JWS bytes. SDK additional nonledger fields require minimum397 bytes; the public five-field response adds maximum96 bytes using actual UUID4.hex32 operation ID and longest allowed statuses. Therefore old-SDK-accepted READY public envelope is <=65235. Source references now include query5field construction, read_tx->verify_tx->SDK, actual operation UUID generation, and raw signature conversion/validation (`public-envelope-bounds-r2.json`). **This proof depends on the old SDK aggregate64K premise and must not be applied unchanged after any conditional aggregate codec fix. It does not prove all individually legal calls can publish; the actual16/17 defect disproves that claim.**

Separately, strict four-tool result shapes with256 items, plain128-byte resource identifiers, safe16-digit integers, actual operationid32 and escaped128-byte receipt IDs/metadata/kid produce a conservative over-approximation: order public envelope54873B, notification3359B, request-read2948B, document-read2949B. Independently maximizing quantity and unit price is explicitly an over-approximation, not an admissible quote total. Refusal512 astral/fullwidth/backslash strings were actually original-canonicalized and parse_result-validated: reason2050/1538/1026 bytes respectively; ensure_ascii encodings are6146/3074/1026 and are not RFC8785 canonical output. Source literal/reference premises and exact arithmetic are retained for fresh review.

Original source/component64K/depth64/node4096/JWS16K/ancestor1..3 and external public64K limits remain unchanged. The original SDK nonledger aggregate64K plus ledger64K makes the later1MiB guard unreachable at its exact positive boundary; unit arithmetic is not reachability. N031 conditional outer acceptance was never enabled. The original N021 oversized trusted-projection public503/proof-rollback guard was not rerun in this worker before STOP; retain it in the next final regression package. Root fresh package/reviewer must decide concrete case rebinding and the precise conditional SDK path; this worker does not approve or self-close it.

## Scope, environment, cleanup and native STOP

Baseline checked: `305` paths; `297` outside the existing owned8 remain identical (kind/mode/SHA). Exactly6 newly created paths are all within the authorized14. Current HEAD `138c08a3496eefb6ef2ceca0d694290dcb95c642` and physical/stage index hashes unchanged. Full scope/source manifest: `stop-source-scope-r1.json`.

The own Linux Python3.11 source-copy environment and noneditable PEP517 wheel environment used exact locks and no foreign venv/default DSN. Source and wheel module import witnesses reject source shadowing and include actual executable/PID/PPID/module SHA; direct publisher child records additionally include Python version and frozen module entry. Creation/PEP517/lock logs and wheel inventories are retained. Cached images were python:3.11-slim amd64 and postgres:16-alpine; no image prune or unrelated container/DB action occurred. Only successful-create fullID plus exact owner labels were used for cleanup.

All own native test/command processes finished. Exact owner containers and network were native stopped and removed; own container/network resource count0; all three unrelated original fullIDs remain. Saved inactive source/wheel copies/venvs are evidence files, not running resources. `native-processes-prestop-r1.json`, `python-native-stopped-r1.json`, `pg-native-stopped-r1.json`, and `resources-final-zero-r1.json` contain the exact process/resource facts.

| Removed resource | Full ID |
|---|---|
| python | `dcc91e85c0f2472cc707a683db511ba8b156ad9e6c106d0fafec5c645d732275` |
| pg | `3e11aa0814a87281e74e79d83ae71100ec233535bcbd77052e801869d3928de1` |
| network | `e1f17dec9ca0e884a59d81ed2ae76c7d8fb0bb7d363dcadfbed14b896ec2564b` |

Disposition: **native STOP / NEEDS_REPLAN**. Candidate and interface freeze remain available for root review, but no CLI/HTTPS consumer dispatch should use them as an accepted core baseline. Resume only under the newly frozen, independently reviewed precise package.
