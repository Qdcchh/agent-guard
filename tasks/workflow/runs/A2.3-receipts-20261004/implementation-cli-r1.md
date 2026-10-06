# A2.3 CLI/config consumer r1 implementation

Status: **READY_FOR_INTEGRATION / native FINAL STOP**; this is local self-check evidence, **not full A2 ACCEPTED**. Complete119/112 and G1/G2, sole29 integration and NEW independent acceptance remain required. Latest human scope is complete A2 acceptance plus A3 planning then STOP; no A3 implementation.

Task/session `/root/a23_cli_worker_r1`, owner `a23-cli-r1-20261005`; requested sol/medium, effective backend model/effort **UNKNOWN**. Same reviewed task-v3/task-cli-v1 and PACKAGE_READY consumer-r1; main HEAD `138c08a3496eefb6ef2ceca0d694290dcb95c642`, branch `codex/a2.3-receipts`. Current authorizations and pre-consumers-full-freeze govern; historical common control documents do not replace them. Source-read-manifest binds original A2, interface/security/acceptance, contracts/workflow/history, all v3 JSON, latest consumer review and actual core15 source SHA. No children, Git mutation, formal document, migration, dependency, CI or peer-source edit.

## Final change and caller behavior

Exactly four new untracked files: `src/agent_guard/gateway/receipt_config.py`, `src/agent_guard/gateway/receipt_worker.py`, `tests/unit/test_receipt_worker_config.py`, `tests/integration/test_receipt_worker_process.py`. No deletion, tracked baseline edit or shared API change. All preexisting work remains preserved. `scope-final.json` checks every frozen non-peer member, HEAD, index and staged diff; errors=[]; peer3 activity is an explicit exclusion. `baseline-copies.json` checks complete340 common members and exact4 overlays in source and wheel-build trees, never copying concurrent main peer products.

Actual CLI:

```sh
python -m agent_guard.gateway.receipt_worker init --gateway-config OLD --out NEW --signing-kid NEWKID
python -m agent_guard.gateway.receipt_worker check --config NEW/config.json
AG_RECEIPT_DATABASE_URL="$OWNED_TEST_DSN" python -m agent_guard.gateway.receipt_worker run --config NEW/config.json
```

`--kid` aliases `--signing-kid`. `init` exclusively creates the new0700 directory and 0600 receipt-key.pem/config.json/gateway-public.json. It uses existing CSPRNG SM2 backend and descriptor-bound private_files primitives. Historical GW public keys remain; occupied/new kid colliding with AS/holder/GW fails. The original private gateway config bytes never change. Relative downstream-secret reference is validated without opening/copying secret contents and made absolute in the public copy; unsafe metadata/ancestors reject. Extreme umask0777 safely leaves an empty mode000 leaf and returns2; no permission-repair bypass.

Signer config has exact issuer/as_keys/identities/receipt_keys/signing_kid/private_key_path plus connect_timeout/lock_timeout_ms/statement_timeout_ms/batch_size/poll_interval_ms. Only public exact(tenant,client,kid) registrations and receipt private signer are loaded; no catalog, AS/holder private key or downstream secret. Canonical SPKI and kid roles are distinct; same holder DID/kid/SPKI under legal different tenant/client tuples remains admitted, duplicate exact tuple fails. Missing/mismatched/unknown signer rejects. Check and run share strict loader and builder; check opens no DB. Run only uses AG_RECEIPT_DATABASE_URL, with no ordinary fallback or provision/migrate/reset. Exact integer bounds are connect1..30, SQL waits1..60000, batch1..256, poll100..60000; bool, zero, negative, below-min, overmax and float reject.

Run calls frozen InternalPublisher directly. Per-row failure advances the keyset; batch1 corrupt first plus two legal pending rows reaches both valid rows, then wraps. It publishes already-terminal facts only; no business execution. `--once` handles one page; `--operation-id` returns one persisted publication. Parser/config/DB error output is bounded and does not echo raw arguments, DSN, PEM, secrets or stack. No production environment fault/skip hook or public management route.

## Actual local bindings and verification

`local-node-bindings.json`: **7 nodes /15 local atoms**, each original atom/finite contract preserved and bound to actual source symbols/line/assert segments, collected nodeids and final source/wheel JUnit. `actual-source-assertions.json` includes extra strict-schema, bounds, unsafe config/key/secret-reference and lifecycle functions, plus complete full_state/publication_only oracle source. This local union does not prove complete parent119/112. N009 local config proves role separation and legal exact-tuple admission; deeper cross-operation query/offline/race alias controls remain shared core/G1 integration responsibilities, not newly claimed local reruns. N034.A2/N036.A2 explicitly retain whole-regression/global-freeze responsibilities.

| Node | Actual behavior evidence |
| --- | --- |
| N005 | Actual `python -m ...receipt_worker` child executes real SM2 sign/verify, then PG backend exact outbox UPDATE waits on owned trigger/advisory lock; real SIGKILL -9 before commit, full ag/DS rows equal PENDING baseline, distinct new PID publishes same immutable id/material/iat; real verify_tx and three-field publication oracle. |
| N006 | Full actual stdout pipe prevents CLI reply delivery; independent connection first sees committed READY, real child pipe_write/anon_pipe_write wait is observed, then SIGKILL. Drained pipe contains only prefilled bytes; distinct PID returns identical saved JWS/signed_at/receipt_id and final all-row state equals committed snapshot. |
| N009 | AS/holder SPKI reuse, new kid roles, wrong private/public, unknown kid and duplicate exact tuple reject; distinct key and legal tuple alias controls pass; config/public copy contain no other-role secrets. |
| N010 | Occupied file/link/parent link/FIFO/socket/directory/unsafe ancestor reject, old bytes preserved; new modes/key uniqueness, public history preservation and safe relative secret reference pass. Real Linux CLI four umasks and safe partial failure covered separately. |
| N027 | Same offline loader/builder, missing explicit receipt DSN with ordinary poison DSNs fails; all finite numeric boundaries plus float reject. Bad-row rotation has three actual signed accepted/terminal operations, all three ancestors exactly (reserved_amount0,settled70000,reserved_calls0,settled_calls3); complete ag/DS row oracle preserves every fact except three publication fields. Actual two gate-synchronized init PIDs yield one0/one2, old bytes stable; restart succeeds. |
| N034 | Actual source and noneditable-wheel parent and CLI child module file/SHA/metadata, including actual main-call profiler attestation, no wheel src shadow or editable install. New init/check/run fragment executed in both modes. Profiler is test-only observational sitecustomize; product contains no hook. |
| N036 | Explicit namespace ownership marker and database/schema target verified; owned CLI children reaped/absent from procfs, ordinary DSN poison not used; final process/client-backend and fullID/double-owner cleanup evidence below. |

| Actual run label | Exit | P/F/E/S |
| --- | --- | --- |
| local-source-r1 | 1 | 70/2/0/0 |
| local-source-r2 | 0 | 82/0/0/0 |
| local-source-final-r1 | 0 | 101/0/0/0 |
| local-wheel-final-r1 | 0 | 101/0/0/0 |
| local-source-final-r2 | 1 | 100/1/0/0 |
| local-wheel-final-r2 | 1 | 100/1/0/0 |
| **local-source-final-r3** | **0** | **101/0/0/0** |
| **local-wheel-final-r3** | **0** | **101/0/0/0** |
| affected-source-r1 | 0 | 255/0/0/0 |
| affected-wheel-r1 | 0 | 255/0/0/0 |

Final local101 =91unit+10integration, collected101 independently in each mode; results named per actual XML, not inferred counts. Final commands/log/XML/SHA are individually indexed in junit-case-results.json and evidence-manifest.json. Affected255 covers old gateway config/receipt publication unit, private-file primitives/AS private paths/config, original receipt paths, both original core real-PID crash tests and HTTP public-key-only factory isolation. Full core late-window882, whole A1/B/full A2 suites and TLS closure are NOT_RUN by this consumer; prior results are dependencies, not local PASS or exemption.

Exact final ruff check . exit0; format --check . exit0/250files; git diff --check exit0. Earlier lint failures28/2/1 retained. A final owned Linux quality-only container ran lint/format on exact final source after test synchronization, then exited/was removed. No global regression was repeated merely to improve a count.

## Failures and preserved correction evidence

First72 local failures were unchanged real budget rejecting a second70000 order in the fairness fixture and current Linux kernel naming the genuine stdout wait anon_pipe_write. Fairness now uses one order plus two valid zero-amount reads while preserving cumulative calls and all-row oracle; both actual pipe-wait names are accepted without removing the positive wait assertion. Final-r2 failures were procfs cmdline transiently empty during exec startup; observer now first waits for complete JSON attestation emitted at actual receipt_worker.main, then checks real -m command, live PID and SHA. No product security/permission/budget expectation was weakened. First FAIL logs/XML and sealed0600 original XML with exact credential-redaction SHA pairs remain in first-failure-redaction.json/exec-observer-first-failure-redaction.json; failed XML never serves as PASS.

Setup's combined docker pull output originally contaminated its captured PG ID; actual last fullID was independently compared to name/double labels, original create-pg.log and first private state retained. After successful exact removals, the first zero-inventory query used an invalid docker filter syntax; corrected read-only label=owner/label=agent-guard.owner returned0, without another removal. finish_resources-first.py and cleanup-post-remove-inventory-first-failure.md preserve this failure. These are harness failures, not waived product tests.

## Environment, isolation and stop

Fresh Linux Python3.11.17/euid501, PostgreSQL16.15, independent source/wheel HOME/cache/venv/native0700 TMPDIR and separate cli_source/cli_wheel databases. Existing locked requirements-dev/requirements.lock plus PEP517 setuptools80.9.0 used; no main dependency edit. Actual installs/build/pip check/freeze and environment-source/wheel.log are retained. Noneditable wheel SHA `82229a67caa75da4051a29cb8185d50975894557fcd5401f270c7bd77617b153`; wheel-source-and-sql.json compares every production Python member and14 historical SQL to actual immutable-baseline+own4 build source. Wheel parent/children resolve site-packages, source parent/children resolve owned candidate/src. Ordinary DSN/PG defaults removed. Each pytest session owns and verifies a random schema marker plus a separate randomly created downstream database/connection/transaction domain.

Owned fullIDs: main Python `8f3591586a729361bb81e86ac5719fbbdd49ff49e09c69f74998d75d2746f4c8`; PG `8121f7e3f452b1f180fbf7507d1074b6c51b5ea9a3e4d0cb4d7e6d1106aa28cf`; network `d60d8b2cb34167911cfc0b97ccb548e7d3b9b943e7603a7f6bf91a86a9db2299`; final quality container `e1725676007ada270aaf6ce1de6ef0ba6b10cffe4e7939fd55dc33a905e8b8b8`. Before each removal actual fullID/name/owner and agent-guard.owner verified. Process inventory after all test/collect wrappers completed contained only container init sleep; PG other client backends0. All owned CLI child/wrapper PIDs ended. Final both-label container/network inventory0; cleanup-final.json. No host ports/listeners/TLS resources needed or claimed for this internal CLI scope. HTTPS/TLS belongs peer and final integration. Foreign agent-guard-a2-pg/verivote-web/verivote-api fullID/name match controller's predispatched facts, read-only inspect only, never connected or modified; foreign-resource-final.json.

Reproducible owned environment/command orchestration: **manage.py**, **finish_resources.py**, **audit.py**, **final_bindings.py**; all under this evidence directory, never imported old helpers. Integrator must use a new owner/token/password/resource set and the stopped combined baseline; these scripts/command manifests are executable design references, not permission to reuse old private state/fullIDs or stale consumer-only baseline for final integration. README-fragment.md gives the proven init/check/run text for the integrator-owned README. Runtime CA/full TLS and complete119/112 remain sole integrator/fresh reviewer work.

Final scope/errors=[], full source/wheel copy binding and evidence readback complete. Native FINAL STOP after resource0 and all wrappers ended; no further writing. No ACCEPTED/state/Git/report-index update performed by this worker. Hand back exact4 for sole integration only after peer STOP.
