# A2.3 capacity core r1 implementation — NEEDS_REPLAN / native STOP

Requested gpt-6.1-sol / medium; effective metadata UNKNOWN. Owner `a23-core-capacity-r1-20261005`. This is a partial implementation/selfcheck handoff, not READY_FOR_CONSUMERS, core acceptance, full A2 acceptance or A3 completion.

The new independent capacity PACKAGE_READY and controller dispatch authorized exactly five candidate paths. All five changed; the other 314 of the 319 frozen candidate paths, all 266 original stopped raw artifacts and 23 capacity-review raw artifacts remain byte/mode identical. No pathset addition/deletion, HEAD/index or Git mutation. HEAD remains `138c08a3496eefb6ef2ceca0d694290dcb95c642`. Evidence: `baseline-readback.json`, `source-manifest-stop-r1.json`.

SDK correction preserves the exact nine-field AG-EVIDENCE-1 / UNANCHORED manifest, public function signature, cryptographic inputs and all existing signature/17-claim/chain/history checks. It encodes ledger_changes with the unchanged dedicated signed-delta codec; independently encodes each other component with the unchanged default canonical_json_bytes; computes exact outer size as two braces plus encoded key/colon/value lengths plus eight commas. The private `_outer_encoded_size` helper only measures already encoded components. No default codec, crypto, ledger codec, SQL, dependency, HTTP limit or other production core file changed. Every component retains original 65536-byte, depth64, nodes4096, cumulative-string65536, Unicode and integer rules; each JWS remains ASCII<=16384, ancestors1..3, outer<=1048576. Negative deltas remain confined to the original four named ledger fields.

Owned tests retain original negative obligations and distinguish canonical component boundaries from outer helper arithmetic and legal pipeline reachability. Empty and four-token ancestor paths refuse; real three-token chains are exercised in capacity pipelines, and the existing unit root chain succeeds. The one-MiB arithmetic tests measure exact complete envelopes and preserve oversized illegal-component refusal; they do not claim an admissible manifest reaches that boundary. Owned lint fixes sort imports, wrap SQL strings without changing their bytes, remove an unused import, bind per-loop fixture selectors as defaults and narrow the previous blind Exception assertion to its intended typed rejection classes. The complete latest core remains pending; the latter fixture/assertion changes must be exercised in the next complete source/wheel run.

Actual finite runs:

| Run | PASS | FAIL | ERROR | SKIP | Native exit |
|---|---:|---:|---:|---:|---:|
| capacity-source-r1 | 1 | 3 | 0 | 0 | 1 |
| capacity-source-r2 | 4 | 0 | 0 | 0 | 0 |
| capacity-wheel-r1 | 4 | 0 | 0 | 0 | 0 |
| capacity-source-final-r1 | 4 | 0 | 0 | 0 | 0 |
| capacity-wheel-final-r1 | 4 | 0 | 0 | 0 | 0 |
| unit-sdk-r1 | 61 | 0 | 0 | 0 | 0 |
| unit-final-r1 | 61 | 0 | 0 | 0 | 0 |
| unit-wheel-final-r1 | 61 | 0 | 0 | 0 | 0 |

The initial 3 capacity failures occurred after real SDK verification, publication READY and HTTP200: the new test oracle erroneously compared the pre-staged evidence reference with the HTTP verifier's newly staged reference. Corrected oracle resolves the actual result-read proof association, independently compares its token/proof/body bytes with the original submitted bytes, and permits exactly one new STAGED material and one result-read proof, preserving every other ag_* and independent ds_* row. First failures and original XML remain preserved privately; public copies redact secrets/compact or long hex evidence. `actual-test-runs-stop-r1.json`, `JUnit-redaction-r1.json` and `log-redaction-r1.json` bind counts, nodes, command exits and originals. A prior progress message incorrectly said unit70; actual XML/logs show 61 throughout. No 70-PASS claim is made here.

Both final environments really run original short256 qty1 plus width12/16/17 with quantity35184372088831, unit1, budgetMAX_SAFE and total9007199254740736. Each uses actual AS login/consent/code/root, two real exchanges, public202, independently committed downstream SUCCEEDED, publisher READY, current public HTTP200 and independently trusted SDK verification. All three ancestor four-counter tuples equal (0,total,0,1); exactly two events/six event nodes/one outbox/one DS order; repeat publication returns exact original JWS/signed_at and every full-state row unchanged. Publication permits only three fields; query permits only exact evidence/proof additions. All JWS/source/request/result/quote/ledger components satisfy original limits.

| Width | Old nonledger aggregate bytes | Exact new outer bytes | Public READY bytes | Source/wheel |
|---|---:|---:|---:|---|
|12|59550|60754|18892|PASS / PASS|
|16|67058|68262|19916|PASS / PASS|
|17|68938|70142|20172|PASS / PASS|

Width16/17 are now successful real pipelines, while the old conditional-trigger failures remain unchanged in the original stopped owner's raw evidence. This does not retroactively relabel those failures.

Fresh `bounds_afterfix.py` and `public-envelope-bounds-afterfix-r1.json` bind all actual current15 sources and the production strict-result/codec/ledger/UUID/SM2/projection/query/SDK sources. Kind is CONSERVATIVE_UNREACHABILITY_BOUND_NOT_LEGAL_PIPELINE_MAXIMUM. READY strict-schema bounds: order54872, notification3361, request-read2947, document-read2949; PENDING maximum52155. Each tool's FAILED refusal is independently bounded for 512 astral/fullwidth/escaped characters; noncanonical ensure_ascii sizes are explicitly separate. The conservative order estimate allows independently maximal quantity/price that cannot form a legal quote total. It is not called a legal business maximum. The old global54873 estimate remains conservative; the old notification3359 estimate is corrected. The old READY65235 cancellation proof is not used after the fix. Public65536/65537 legal-domain reachability is excluded by the fresh schema bound; original exact codec and public oversize fault-injection/rollback must still be rerun in the next full stage. Nine component lengths each<=65536 plus exact overhead140 give outer589964<1048576; helper boundary arithmetic and illegal-component early rejection are distinct from actual pipeline evidence. The first bounds-script run failed because it asserted the old numerical estimate54873 as exact; its failure log is preserved, and the script now reports actual computed54872 rather than forcing the old value.

New isolated Python3.11 Linux/amd64 and PG16 resources, fresh exact locks, setuptools80.9.0 PEP517 source install/build, fresh noneditable wheel install and separate wheel/GW/downstream DB targets are recorded in native command receipts and resource metadata. Repository mount was read-only. Normal deployment DSNs/PG environment were cleared by run.py; explicit random private TEST DSN only. No prior or foreign environment was reused. `wheel-inventory-r2.json` inventories the real wheel and all14 SQL files. `wheel-current-prod-byte-identity.json` confirms every installed wheel production Python member equals the current candidate source bytes. Wheel test root has no src directory. Import witnesses record actual module paths, content SHAs, interpreter and parent/child PIDs; final API signatures include actual Python3.11 version. `environment-content-manifest-r1.json` binds 9690 source-copy/installed-environment files without exposing secret values.

Latest source and wheel each actually collect 861 core cases and match exactly. The 29 formal local bindings cover 860 collected cases; the additional unknown receipt runtime HTTP500 case is separately included. `core29-local-bindings-stop-r1.json` rebinds actual current functions/lines/assertions/SHA/nodes and finite execution evidence to the unchanged local atom texts. Nodes with no current execution are explicitly NOT_RUN. All500 real deadline cases, original8 wait/4 AS-window groups, ten-round races/SQL40001/real backend/SIGKILL/fencing/current revocation and the remaining core cases are NOT_RUN in this round. No old PASS replaces their current execution. Full ordinary/affected legacy/provider/query/config/SDK regression is also pending. No clock/TTL/grant renewal, skip or deleted group was used.

The reason for this stop is a real scope gap. First full src/tests ruff check found42 errors; owned-only repair reduced this to exactly three frozen read-only production errors: receipt_publication.py:238 E501, verified.py:3 I001, factory.py:3 I001. Format --check passes. No rule ignore or waiver was introduced and those three files remain untouched. Parent explicitly directed native STOP before starting the long complete-core run, followed by a new exact format scope, independent package review, new owner/freeze/environment and one final complete source/wheel run. Required next work includes those three AST-equivalent formatting fixes plus every pending full-core and inherited regression obligation; no parent requirement or local atom is marked closed by this report.

All finite command wrappers/tests/futures completed before cleanup. Python top showed only its owned sleep process; all owned containers and network were removed by verified fullID plus owner label. Both owner and agent-guard.owner postqueries return zero. The three initial unrelated container fullIDs/names remain present and unchanged; no foreign DB/container was accessed or removed. `cleanup-r1.json` and `native-stop-r1.json` record these facts. This writer performs no further candidate changes and returns native FINAL STOP / NEEDS_REPLAN.

Actual API signatures (unchanged consumer-facing SDK/core signatures):

```json
{
  "PermissionSnapshotProvider.load": "(self, token: 'str', *, grant_id: 'str', now: 'int') -> 'PermissionSource'",
  "PermissionSnapshotProvider.load_tx": "(self, conn, token: 'str', *, grant_id: 'str', now: 'int') -> 'PermissionSource'",
  "PermissionSnapshotProvider._from_records": "(self, records, token: 'str', now: 'int') -> 'PermissionSource'",
  "scoped_trust_tx": "(conn, operation_id, *, issuer, as_keys, gateway_keys, registrations, permission_provider)",
  "validate_original_tx": "(conn, op, source)",
  "InternalPublisher.__init__": "(self, dsn, *, private_key, signing_kid, verifier, connect_timeout=5, lock_timeout_ms=10000, statement_timeout_ms=15000)",
  "InternalPublisher.publish": "(self, operation_id) -> agent_guard.execution.receipt_publication.ReceiptPublication",
  "InternalPublisher.pending_page": "(self, *, after_operation_id, limit)",
  "ReceiptVerifier.__init__": "(self, *, issuer, as_keys, gateway_keys, registrations: collections.abc.Mapping[tuple[str, str, str], agent_guard.identity.resolver.RegisteredIdentity], permission_provider: agent_guard.authorization.permission_snapshot.PermissionSnapshotProvider)",
  "ReceiptVerifier.verify_tx": "(self, conn, operation_id, receipt_jws)",
  "ReceiptVerifier.read_tx": "(self, conn, operation_id) -> agent_guard.execution.receipt_publication.ReceiptPublication",
  "evidence_bundle": "(projection, receipt_jws)",
  "verify_receipt_bundle": "(bundle: 'object', *, trust: 'ReceiptTrust') -> 'VerifiedReceipt'",
  "AuthorizedQuery.__init__": "(self, dsn: 'str', *, evidence_store: 'EvidenceStore', receipt_verifier=None)",
  "AuthorizedQuery.query": "(self, bundle)",
  "VerifiedExecution.accept": "(self, bundle: agent_guard.contracts.verification.VerifiedInvocationBundle)",
  "VerifiedExecution.accept_response": "(self, bundle: agent_guard.contracts.verification.VerifiedInvocationBundle, *, receipt_verifier) -> dict"
}
```

Actual current15 source SHA256:

```json
{
  "src/agent_guard/evidence/receipt.py": "50bc7b6aba7a6cb8cc89880dc44ef00d716cea8e8914d6c5bf42195e36868ed5",
  "src/agent_guard/execution/receipt_publication.py": "e0dd03d43cb7a2a89a6ae4ba36b956775f009bfad882c889c178daa0683be906",
  "src/agent_guard/execution/original_material.py": "1c781bd0f6f43855df48214f4859a878a8d2eb17efae1823b62b74355793407f",
  "src/agent_guard/execution/receipts.py": "32367393ac80a9defe222b314710b11987c767aa05bd046180ced7fc9ff61aff",
  "src/agent_guard/execution/query.py": "9763ac130ebd0c7f87130f11be3ec64d3beb5a14edf722879a64d205c0d86ac5",
  "src/agent_guard/execution/verified.py": "96a6c29a3716991ab17956b15e8f2e2d5bae486399eb740c07a06d9f80ee6aa7",
  "src/agent_guard/execution/store.py": "42b95254488b5c43028efd9284a7726dc8589182cdb32e67fbeafd9741d9e504",
  "src/agent_guard/gateway/config.py": "e0a5554d0d7eef8da870528d18278255a7f9e345d486c927725a623060c9dbe9",
  "src/agent_guard/gateway/factory.py": "693ee77387f8174eb3ae7afb2b068c640f40f0547d8f12167cb6b0e4abffd3dc",
  "src/agent_guard/gateway/endpoint.py": "dd14776c3a709138e04fae76611971b6875246267be2965aadc1a5aa3726e403",
  "src/agent_guard/authorization/permission_snapshot.py": "6e0bfb89d0cc460c3d12c1d253a063623d9d843f5acf098873cd2f8443aea3de",
  "tests/fixtures/receipts.py": "30070ba78239ca04873b6d1167356cfd12c99b3cb67920e6fea47add0d0d2b60",
  "tests/unit/test_receipt_publication.py": "efada4e89ce59f6dcc4b1af451d8d29352e24492e8f8065131fa44b027f73c6a",
  "tests/integration/test_receipt_publication.py": "ef978ba9ef0cc6cf449f55525c7819316548003234e8858d9917b480cb64345e",
  "tests/integration/test_gateway_receipt_query.py": "b34b686a41d5a8c00a9c90677277fc8437f9c73935e29b2e165175929b895ba4"
}
```
