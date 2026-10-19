# PR9 candidate5 independent implementation acceptance r2 — STOP_NOT_ACCEPTED

2026-10-18 UTC. Fresh independent reviewer, requested gpt-6.1-sol/high; backend effective model/effort metadata UNKNOWN. Root is the sole Git/remote writer. This review did not modify candidate source, tests, fixtures, Git, remote state, releases or Secrets.

## Decision

**STOP_NOT_ACCEPTED. Candidate5 cannot be accepted locally or published as locally implementation-accepted.** Independent real execution confirmed three original inherited-test failures and two missing physical prerequisites. Root then invalidated C5 and explicitly ordered STOP. The required full nonintegration, original6839 integration, source/wheel20-group runs and security negative matrix are NOT_RUN. Partial quality passes and targeted probes cannot offset these failures. P9-09 is a later root gate after a future complete local acceptance; its not-yet-occurring publication/CI/merge is not the cause of this rejection.

## Candidate and independent identity

C5 manifest SHA256 `104c061d99a0b0ca72dc8a87cdd92930280a8acd3ac96690379f7906c733a9e5`, base commit `eafb6f28aa87a041e149c0190b76054424f1c9cf`. All1212 manifest members independently recomputed at start2026-10-18T13:20:38.427663Z and end2026-10-18T13:25:33.693029Z: zero mismatches both times, symlinks hashed as link-target bytes without dereferencing. Actual business source/migration bytes compared with the base: zero changes. HEAD alone is not represented as the uncommitted implementation identity.

Read AGENTS/AGENT/current-policy, package/C5, all current addenda and original r1 rejection; relevant README/protocol/security/acceptance/review-contract sections, workflow/helper/materializer/controller paths and original inherited files. Some lengthy combined document output was truncated; this is not a claim every line of all documentation or affected deployment code received complete semantic review. The static compatibility audit independently SHA-checked all196 curated legacy originals plus8 sidecar provenance entries =204 originals, parsed all196 Python originals, and inventoried residual paths/migration/database assertions after actual source materialization. This established blockers before spending time on the known-incompatible long matrix.

## Actual independent runtime and preserved failures

Used the immutable trusted tools image fullID `sha256:fc9134fe1a2c90c52998c6f44f49e77e1a08faba95a58d7acf78985dd8e4fa1f`; image inspect reports linux/amd64. The actual process reports Python3.11.17/GCC12.2.0 and nonrootUID501. Created a fresh venv, installed all21 requirements-ci hash-locked wheels using --require-hashes/--only-binary and an immutable local wheelhouse, built the actual candidate project wheel with --no-build-isolation/--no-deps, installed noneditable and ran pip check successfully. Actual package import came from this fresh venv site-packages, not image installation. The probe did not perform complete139-module bind_installed, x40241-wheel qualification, Linux threshold vectors or full source/wheel image qualification, so those remain NOT_RUN.

Created one fresh reviewer-owned PG16 container and network per probe attempt; only the successful attempt ran tests. Its generated credentials lived in0600 env files, not argv/public output. PG was an independent disposable PostgreSQL instance, not a fake DB or reused worker domain. This short compatibility probe does not claim the later required full three-domain TLS topology. The target runs under Docker Desktop on Apple arm64 with an amd64 image; this is emulated execution and is not a native performance result.

Actual current `materialize_legacy` ran for source and wheel. Calling each materialized original A2 `observe` failed with FileNotFoundError/errno2 because `/evidence/probe-observations.jsonl` has no producer/mapping. Each original A2 standalone migration directory remained `/e/s2-legacy-standalone`, absent; actual migration discovery rejected it with MigrationError.

Three unchanged original pytest nodes executed against the fresh noneditable install and real PG, each native exit1, testcase1/failure1/errors0/skips0:

|Probe|Original node/stage|Actual failure|
|---|---|---|
|a1|historical-adapted/a1/test_upgrade_nonzero.py::test_upgrade_preserves_nonzero_reservation_and_all_evidence, line38|Real current_database `review_r2` differs from required `ag_review_upgrade_adapted`; current inherited runner similarly has no dedicated DB routing.|
|a2migration|historical-original/a2/test_review.py::test_legacy_upgrade_must_auto_quarantine_before_worker[extra-params], line97|Actual apply_migrations returns004,005,006,008,009 while original expects004,005,006. It reached the real upgrade after inserting the original legacy state; this is not merely grep inference.|
|a2standalone|historical-original/a2/test_upgrade.py::test_full_seven_and_full_registry_upgrade[False-001], line27|Absent standalone directory yields empty copied subset and real MigrationError: no migrations found.|

Native XMLs, SHA/counts and private raw logs retained, including all failed preparation attempts. Reviewer preparation attempt1 explicitly requested platform linux/amd64 and Docker daemon refused the image even though image metadata saysamd64; attempt2 had a reviewer-generated nested-string SyntaxError. Both were cleaned and preserved, then corrected in the private runner. These are reviewer setup failures, not candidate source defects. Final probe driver exit0 means it successfully captured the intended failures; each original pytest native exit remains1. Nothing treats a probe-driver exit0 as original-suite PASS.

## Required compatibility closure before refreezing

The following inventory is based on the actual C5 materialized source; wheel originals have the corresponding same gaps. Preserve original fixtures and record precise physical adaptations/current-append qualifications. Do not turn the observed actual list/database into a dynamically generated expected value, drop assertions or bypass negative controls.

1. **PR9-C5-R2-001 — original A1 DB identities are not assembled.** `a1-original-controls` runs original `test_missing_invariants.py` and `test_root_rebuild.py` in one group, but their own code independently insists on DB names `ag_review_probe` (line24) and `ag_review_f2` (line19). A single unchanged env DSN cannot satisfy both. `a1-upgrade-equivalent` requires `ag_review_upgrade_adapted` (line38) and an empty initial DB. Current group runner copies the same three connection DSNs to every group and never creates/routes these DBs. Require explicit exclusive per-file DB/connection assembly and original-node coverage, preserving real identity guards and independent run ownership. The unexecuted original A1 upgrade file also requires `ag_review_upgrade` and expects only002, but it is not selected by these20 commands; do not confuse it with the selected adapted upgrade.
2. **PR9-C5-R2-002 — A1 current-append qualification missing.** Selected adapted A1 upgrade line46 expects exactly002,003,004,005,006. Once initial DB identity is fixed, current default migration set appends008/009. Preserve exact historical prefix, full original business/evidence snapshot and no-op checks, and explicitly bind expected appendices with fixed filename/rawSHA/installedSHA/registry metadata. A dedicated original six-migration directory may be appropriate only for tests explicitly proving that historical scope; do not silently reclassify a current-default test.
3. **PR9-C5-R2-003 — A2 observations path absent.** Selected original A2 `test_review.py:26` has `OBS=Path('/evidence/probe-observations.jsonl')`, reused by other A2 modules. Current helper maps only `/evidence/logs`, not this file/root. Both materialized modes demonstrably fail their observation function. Map this public physical path into the current consumer's0700 private result tree (files0600), retaining original observation content and assertions. Do not open `/evidence` broadly or give normal roles a new mount. Adapted A2's same path is also present in the curated inventory but is not the A2-original command's selected tree.
4. **PR9-C5-R2-004 — original standalone001–006 migration input absent.** Selected original A2 `test_upgrade.py:5` explicitly wraps apply_migrations with `/e/s2-legacy-standalone`. No producer/mapping exists in C5. Require an explicitly owned installed/source-verified old standalone001–006 set and physical mapping, without mutating historical SQL or accidentally including audit007/new008009. Preserve all six legal/illegal upgrade variants, old full seven-table snapshot, full registry prefix, illegal rollback and idempotence assertions.
5. **PR9-C5-R2-005 — remaining original A2 current-default migration assertions are incompatible.** `test_review.py:97` and `test_r2_variants.py:32` expect004,005,006; `test_r3_independent.py:121` and `test_r4_boundaries.py:147` expect005,006; `test_r4_boundaries.py:134` expects006. These direct current-default calls need precise current-append qualification, not an arbitrary range change. Importantly `test_r4_boundaries.py:135` also asserts `after[1][:-1]==before[1]`, assuming exactly one appended registry row; preserving only its migration-return list misses this second failure. Require the original exact prefix plus exact fixed new registry rows/filename/checksums and unchanged seven business tables. The line126 custom pre005 equality004005 remains valid and must remain; the illegal `006 pre-check`/absence ofag_event_seals/full rollback and no-op assertions remain essential. The corresponding adapted A2 copies contain the same old fixed-list assumptions, although this20-group A2 command selects original A2.
6. **PR9-C5-R2-006 — B-equivalent legacy subdirectory is not assembled.** The command selects the entire historical-adapted/b directory, including `legacy/test_history1.py:19` and `legacy/test_history4.py:24`. Both require real `history_b_adapted`, with no dedicated env/database producer in C5. They must be routed to a current-owned disposable DB while retaining real root rebuild/subject/call/root-constraint assertions. The earlier three-file B4 smoke did not cover this directory. Original B legacy copies instead requireag_review_f2/ag_review_probe, but that original B tree is not selected by b-equivalent. Existing adapted B `test_r2_migrations` qualification is not a substitute for these omitted legacy nodes.

Adjacent/inventory checks: no additional unhandled `/e/...` or `/evidence/...` absolute file literals were found in the actual materialized Python inventory beyond the above A2 standalone/observation paths and the intentionally retained environment-observer `/e/` absence guard. URL route literals and certificate subject strings are not filesystem omissions. `/private/runtime.json` is explicitly produced by _environment_gate and the trusted nested tmpfs; `/bin/busybox` is the authorized mapped executable. Current actual source139 binding, noneditable import origin, actual UID/modes and original source-absence guard have different meanings and must all remain. Full original semantic/static/runtime acceptance is still required after refreezing; this bounded path/assertion inventory is not a guarantee no other bug exists.

## All20 inherited commands, both modes

This table distinguishes audited routing from actual execution. Every group below remains NOT_RUN as a complete source/wheel group in this review. No old XML or worker result is substituted.

|Group suffix (source/wheel)|Static compatibility observation at STOP|
|---|---|
|ordinary|Uses fixed original file inventory/current install; full current nonintegration not run.|
|current-pg-nonclock|Original fixed inventory avoids recursive A33; current three domains/A31/A32 prerequisites not independently qualified here.|
|current-clock1000|Original1000-clock obligation retained; not run.|
|a1-original-controls|Known conflicting original fixed DB identities, R2-001.|
|a1-upgrade-equivalent|Known missing dedicated empty DB and current-append qualification, R2-001/002; one original node actually failed.|
|a2-original|Known observation/standalone/current-append/registry gaps, R2-003/004/005; two original nodes actually failed.|
|b-equivalent|Whole adapted B includes missing legacy DB identity, R2-006; existing B4 qualification does not cover all nodes.|
|enhanced-original-remainder|Physical paths inventoried; original exclusion list retained; runtime/child observers not independently executed.|
|independent-original-probes|Physical paths inventoried; real independence assertion remains; runtime not qualified.|
|oracle60|Original assert=plain wrapper/observer semantics remain; not run.|
|independent-capacity-domain|Physical sourcecopy mapping present; actual validator-domain proof not run.|
|readme-AS-literal|Mapped private output andbusybox; internally creates mode-specific empty DB; real TLS/permissions/drain not run.|
|readme-old-two-flows|Runner uses fresh randomized DB prefix; script creates/drops its two DBs per flow; full literal flow not run.|
|readme-publisher-literal|Mapped private evidence andbusybox; actual publication/kill/drain not run.|
|receipt-demo|Physical inherited path mapped; not run.|
|AS-demo|Uses installed interpreter/current tests; not run.|
|ruff-check|Command wrapper retains actual module invocation; inherited wrapper not run (host global quality independently passed).|
|ruff-format|Same distinction; inherited wrapper not run.|
|readme-gateway|Mapped paths; script owns two mode-specific fresh DBs; original literal TLS/drain not run.|
|environment|Dynamic installed lib/share prefixes and current17 gateway lineage count mapped; private gate/migration/UID/current139 predicates not independently runtime-qualified. Old `/e/{mode}-tests/src` absence remains an old-path guard only.|

## P9 matrix at STOP

|ID|Actual status|
|---|---|
|P9-01|NOT_RUN full independent nonintegration/current6839 integration; no fresh full collection count asserted. Three original inherited nodes actually failed.|
|P9-02|STATIC_ONLY signature/approval=None repair and query test change read; full real-PG query file not run.|
|P9-03|PARTIAL runtime: reviewer fresh actual PG only for compatibility; required full independent authority/downstream/audit TLS topology/denial roles not run.|
|P9-04|NOT_RUN public fetch/AEAD110SHA/current139bind/original counter. No capacity key read or historical original copied. Original10000/30009/668/203285/raw291623992/wire439169636/NOT_ASSERTED requirements are not reviewer results.|
|P9-05|BLOCKED by selected original inherited paths/DB/migration semantics above; full source/wheel12roles/20groups/negative controls not run.|
|P9-06|PASS unchanged business/migration bytes relative base, but compatibility defects require new authorized candidate; no source repair here.|
|P9-07|PARTIAL_PASS freshPy3.11/21locks/project noneditable/pipcheck and host Ruff/Node; x402 locks/binary vectors/full CI runtime not run.|
|P9-08|PARTIAL independent204 originalSHA and1212 begin/endSHA plus real short failures; complete fresh runtime missing; NOT_ACCEPTED.|
|P9-09|PENDING_ROOT_AFTER_FUTURE_FULL_LOCAL_ACCEPTANCE. Exact-head GitHub all-CI-green/expectedSHA ordinary squash remains mandatory. No publication/merge claim.|
|P9-10|PASS reviewer isolation/cleanup only: candidate untouched, all actual own containers/networks0, private root deleted, no volume/newimage/key/decoded input. Raw failure evidence private0600.|
|P9-11|UserCSS/DOCX/PDF bytes match requestedSHA; actual Node behavior passed. No independent Word/PDF/UI rerender before STOP; root readability evidence not relabeled as this reviewer's execution.|

Actual host quality commands: `/tmp/cosm2-a1-a2-tools-20261017/bin/python -m ruff check .` exit0; same `-m ruff format --check .` exit0,365 files; `node --check web/teacher-demo/app.js` exit0; `node tests/test_teacher_demo_frontend_logic.cjs` exit0. HostPython was used for hashes/preparation only, never target pytest.

User byte identities: CSS `88e88bccb6c4be276b54b1ef1e27866c4ab1f9fe46f55c667d1a382397a6ca91`; DOCX `0205832f0aac3accef0017ec18f56fd779293101fe7d132572968de2b519ddb9`; PDF `1eef31d123c2d2589e862a39d512397c7b9deaf6cc8ed1d520cdeba9bc31dad4`. No user content edits. Aux/out/synctex are not approved publication artifacts.

## Evidence and cleanup

All files under this report's own artifacts directory are0600, directory0700. Preserved: source-begin/end, original provenance check, full original/static/residual inventories, three originalXMLs and raw private logs, native failure counts, private reproducible reviewer scripts, runtime summary, initial setup failures and full own-resource cleanup evidence. Raw logs may contain generated disposable test credentials and are local-only; no excerpt with credentials was published. No historical capacity credentials/password activity was probed. No claim of physical memory wipe.

All three attempted owner labels were independently queried after cleanup using label-scoped Docker ps/network ls: containers0/networks0 for each. Every removed resource was first matched to its recorded fullID and owner. No volume/newimage was created; no unrelated resource inspected/deleted and no prune. UUID-only private root removed. Capacity key read0/copied0, decrypted inputs0, temporary env files0. Original worker failures/cancellations, r1 report and original capacity/user files unchanged.

Earlier COSM2 acceptance remains background only. Semi-honestn=2, same-host/non-OS-strong-isolation prototype and unproven physical wipe boundaries remain. No40000 business experiment was launched.

**STOP. Root must close the enumerated inherited prerequisites/qualifications, refreeze a new full candidate and appoint a new independent full reviewer.**
