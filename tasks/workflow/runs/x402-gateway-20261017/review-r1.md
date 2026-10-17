# x402 X1–X8 — independent implementation acceptance r1

**Result: NOT_ACCEPTED.** Three demonstrated defects block this frozen candidate. The normal local test-chain flow and desktop demonstration work; this is not approval of production payments or of the whole project.

Requested reviewer: fresh `gpt-6-astra/high`; effective model/effort metadata **UNKNOWN**. Authorization: current human request “把x402也做了吧”, current-policy and package-v1 X1–X8, as supplied by the controller. No real assets, user wallet, Git changes, external deployment, old long experiments, source edits or delegated reviewer were used.

## Candidate, independence and resources

The controller reported all writers STOP before dispatch. Independently hashed all **820 candidate files** at start and end: **zero mismatches**, manifest SHA-256 `8679619f3e3b3448b4906a4f68d8a6144bcf855a4a44f9638e8c56a0af26724f`. See `fingerprint-start.json` and `fingerprint-end.json`. Source was mounted `/work:ro`; only this review's `/evidence` and container temporary directories were writable. No candidate changes were made.

Read the complete X1–X8 package, package review, current policy, AGENT/AGENTS, review contract, previous threshold acceptance, worker REPORT, relevant interface/security/acceptance documentation, actual x402 modules, gateway/verified-accept/ledger/worker call sites, migration009, threshold V3 contracts and real integration fixtures/assertions, dependency provenance and desktop/public evidence. Existing worker/historical results are not relabelled independent execution.

Created dedicated PostgreSQL16 and runner containers plus a private network with exact owner `6a0cdfd131f6478988761720dad2fb04`, label `agent-guard.x402-acceptance`; no published host ports. Full IDs and mount/ownership records are in `resources.json`/`cleanup.json`. The first private DB had the wrong locale; recreated only that owned database with `template0`, `C`, UTF8. No foreign containers were inspected or connected. Test schemas/downstream databases were independently owned through the normal fixture. Anvil remained alive across crash/recovery subprocesses.

**STOP: owned containers/networks remaining 0.** Owned anonymous PG volume removed with its owned container. Private DSN environment files removed. Sensitive raw logs/XML are mode0600 inside the mode0700 review directory. Docker image caches and the controller's separately owned desktop service are retained.

## Demonstrated blocking findings

### X402-R1-01 — P1: released authorization remains spendable

Location: `src/agent_guard/x402/gate.py:260–264`, `chain.py:238–244`; resource handler also permits persisted material after FAILED.

A transient facilitator verification outage is mapped by `LocalFacilitator.verify` to `is_valid=False`; the real resource server returns402. The gateway sees an unused nonce and calls `mark_failed`, releasing this operation's250000 asset reservation, even though its EIP-3009 signature remains valid. After the verifier recovers, replaying the **identical persisted payload** over real HTTP returns200 and the real chain transfers250000. Payment state/budget remain at FAILED/released. “Not used yet” is not proof that a live authorization cannot later settle.

Independent probe `test_live_authorization_not_released_after_transient_402` fails its safety assertion. `released-live-authorization.json` records operation UNKNOWN, payment FAILED, replay200, actual chain settled, balance delta250000 and unchanged post-release budget. Other reservations from preceding tests remain in the shared test namespace, so the recorded absolute balance is not zero; the probe asserts that this operation's precise250000 reservation was removed. Only the transient verifier return is injected; HTTP, signature, PG state, replay and EVM transfer are real.

Minimal correction: a valid persisted authorization exposed to another component must retain reservation/uncertainty across transient402/4xx or RPC verification failures while it can still execute. Release only with a defensible terminal no-future-transfer condition and no pending payment; distinguish invalid/unavailable/uncertain. Reject resource execution of terminal FAILED records as defense in depth, but that alone cannot revoke an already disclosed chain signature. Regression: transient outage→same nonce recovery, pending/late settlement after error, reservation not freed early, exactly one final transfer/order and correct budget settlement. Do not fix by merely changing the probe or treating unused nonce as irreversible failure.

### X402-R1-02 — P1: unrelated transaction can confirm an unused nonce

Location: `src/agent_guard/x402/chain.py:203–235` (`tx_hash = used_tx or candidate_tx`).

After one genuine payment settles, call `ChainReader.confirm` with the same payer/payee/amount but a fresh **unused nonce**, supplying the genuine earlier transaction as `candidate_tx`. `authorizationState(fresh_nonce)` is false, yet confirmation returns `settled=True`, `authorization_used=True`, `nonce_consumed=True`. The fallback verifies a Transfer/receipt but never requires the candidate transaction's AuthorizationUsed event to bind the requested nonce. This breaks the stated untrusted settlement-response boundary and can falsely mark another payment paid.

Independent failing probe: `test_candidate_transaction_cannot_confirm_unused_nonce`; direct real-chain evidence `wrong-nonce-confirmation.json` includes unused chain state false and false-positive confirmation true. No chain/mock/cryptographic substitution.

Minimal correction: confirm only when a successful receipt contains the correct token's AuthorizationUsed(payer, persisted nonce) and exact Transfer in the same transaction on the configured chain. A candidate hash is a lookup hint, never a substitute for nonce evidence; failed/unavailable log lookup stays uncertain. Regression: unrelated valid tx, no event, log lookup failure, wrong nonce/chain and genuine matching tx.

### X402-R1-03 — P2: idempotent gateway acceptance reserves twice

Location: `src/agent_guard/x402/state.py:184–195`; payment accept callback ignores `disposition`.

Two valid gateway invocations with the **same approved action, business key and payment digest**, using fresh AGPoP, return202 and the same operation. The existing intent is validated but `_reserve_budget_tx` still runs. The independent asset reservation increases250000→500000 while there remains exactly one operation/intent and every CNY ancestor still reserves70000/1call. Repeated retries burn additional available budget and leave a stranded reservation after the one legitimate settlement.

Independent failing probe: `test_retry_does_not_reserve_asset_twice`; `retry-reservation.json` records both responses, counts and budgets. The same genuine FROST signature is reused; only the fresh request proof changes. The probe reuses its saved signature to respect the Rust signer's create-new output-file behavior.

Minimal correction: reserve once only when this intent is newly inserted/operation created, in the existing acceptance transaction. EXISTING must validate the immutable binding and existing payment record without incrementing budget. Regression: sequential and concurrent fresh-proof retries before and after settlement, a tight asset limit, unchanged approval/operation counts, once-only reserve/settle accounting and rollback safety.

## Complete X1–X8 matrix

| Requirement | Disposition and evidence |
|---|---|
| X1 real pinned protocol | Normal path PASS independently: actual HTTP402/signature/response, official SDK EIP-712/3009 signing/verification, real Anvil Circle token receipt/nonce/Transfer and one order. Fixed verify→resource→settle. False terminal confirmation remains blocked by R1-02. |
| X2 trusted intent/budget | V3 payment digest, immutable operation/action/FK linkage, fixed recipient/network/asset/amount/resource/expiry and preserved ancestor CNY checks inspected. Five independent hostile402 fact mutations refuse before signing. Wrong-digest rollback, over-budget and revocation original tests pass. Budget correctness blocked by R1-01/R1-03. |
| X3 persistence/atomicity | Payload+nonce persisted before network, immutable state guards, same-transaction acceptance rollback and same-operation execution race pass. Atomic reserve is present but idempotent acceptance double-reserves: R1-03. Live released signature violates durable budget accounting: R1-01. |
| X4 recovery | Original response-loss/UNKNOWN/server restart/fresh-process tests pass. Additional actual child `os._exit(17)` immediately after persisted authorization, then fresh child native0 using surviving PG/Anvil: same nonce/payload, one transfer/order, SETTLED. Paid-but-unavailable resource independently stays operation UNKNOWN/payment SETTLED with asset settled. Expired approval/authorization tests pass. Unknown/no-transfer terminal logic blocked by R1-01/R1-02. |
| X5 HTTP/wallet safety | Strict duplicate/unknown/type/size/base64 parser tests pass; fixed loopback endpoints, no redirects/proxy-derived URL, separated payer/FROST material inspected. Five actual hostile402 recipient/network/asset/amount/resource cases produce no authorization/order and preserve budget. Untrusted candidate receipt boundary fails R1-02. |
| X6 necessary security tests | Independent focused72 pass, threshold regression24 pass. Ten reviewer probes:7pass/3fail; all three failures are demonstrated blockers above. Required negative-path claims cannot be accepted on the existing normal-case suite alone. No325/1800/40000 suites run. |
| X7 desktop/page/public | Controller independently clicked actual local page button, native0,6/6 cases,3payment records/2transactions/2orders, resources0; read back `../desktop-button-result.json`. Public root/state200, read_onlytrue, empty control/session tokens, POST403 in `../public-check.json`; controller screenshot `../desktop-success.png`. This is controller UI evidence reviewed here, not a second reviewer UI click. Twelve server tests independently pass in focused72. |
| X8 docs/dependencies/STOP | Scope, local testchain, non-SM2 chain signature, same-host trust and PARTIAL boundaries documented. New009 migration applied in every integration fixture; pins/licenses/lock/build inspected. Python3.11 runtime and installed SDK checked; offline hash-required pip install exits0 with already-installed requirements. Worker claims X2–X6 “DONE” require correction alongside the three fixes. Reviewer resources0/source unchanged. |

## Executed commands and actual results

Commands below ran via `docker exec <exact own runner ID>`; full argv/native exits in `*-command.json`. Runtime metadata is in `runtime-metadata.json`. All pytest used `-p no:cacheprovider`, independent `/tmp` basetemp and `/evidence` XML.

| Command/check | Actual result |
|---|---|
| `python -m pytest tests/integration/test_x402_gateway.py tests/unit/test_x402_contracts.py tests/unit/test_threshold_contracts.py tests/unit/test_gateway_errors.py tests/test_teacher_demo_server.py -q` after C-locale setup | **72passed,0failed/errors/skipped**,27.531s,native0; `focused-c-locale.xml` |
| `python -m pytest /evidence/test_probe.py -q` final reviewer probes | **7passed,3failed,0errors/skipped**,12.929s,native1; `probes.xml` and named sanitized JSON |
| `python -m pytest tests/integration/test_threshold_gateway.py -q` | **24passed**,native0; `threshold-regression.xml` |
| `python -m pip install --no-index --require-hashes -r requirements-x402.lock` | native0; already-installed locked dependencies satisfied. This was not a clean-network reinstall/rebuild. |
| `python -m ruff check src tests tools` | native0 |
| `python -m ruff format --check src tests tools` | native0 |

Preserved initial failures: first focused run **64pass/8fail** (all eight successful-accept paths hit the pre-existing audit SQL C-collation requirement on this review's initially misconfigured DB); direct diagnostic **1fail** proved `strict record keys`; neither is an x402 defect. Fixed only owned DB locale and reran same source. Initial reviewer probe run **2pass/8fail** includes signer output-file reuse and my incorrect absolute-budget assumptions: fixtures intentionally leave the independent budget table across cases, so corrected probes use deltas. Original probe source/log/XML remain as `test_probe-r1.py`/`initial-probes-*`; corrected run is authoritative. No test expectation was weakened against the three product safety invariants.

No unrelated old documentation failures or absent A31 audit DSN checks were rerun. Prior worker migration285pass/2environment failures, Rust13pass and wheel content checks remain prior evidence, not independent reruns. No clean runtime image rebuild or production-network test is claimed. Those limitations do not excuse the three directly proven blockers.

## Handoff

Return this candidate for one focused correction batch covering R1-01–03 and corresponding regression tests/report updates. Keep old failure evidence. Freeze corrected source after writers STOP, then commission a **fresh** complete X1–X8 acceptance with these probes and existing normal/negative paths. Do not rerun unrelated long experiments or polish the UI. This reviewer is STOP with no further source/evidence writes planned.
