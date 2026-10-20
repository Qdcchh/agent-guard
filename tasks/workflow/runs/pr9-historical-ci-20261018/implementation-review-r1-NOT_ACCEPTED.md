# PR9 C4 independent implementation review r1 — STOP_NOT_ACCEPTED

2026-10-18 UTC. Role: fresh independent reviewer, requested gpt-6.1-sol/high. Effective backend metadata UNKNOWN. Scope: complete local PR9 IMPLEMENTATION_ACCEPTANCE, not a package review or a partial capacity transport acceptance. Root is the sole Git/remote writer. This reviewer made no candidate, Git, remote, Secret, upload or business database writes.

## Decision and stop condition

**STOP_NOT_ACCEPTED. No local implementation acceptance or CI-publication acceptance is granted.** Root explicitly invalidated C4 and instructed controlled STOP after a new confirmed worker failure. This review was in static/preparation phase. Required complete independent nonintegration, original6839 integration, source/wheel original20 groups and meaningful runtime negative controls were **NOT_RUN**, so neither their completeness nor success is asserted.

The upstream failure is independently checked as an existing log, not represented as this reviewer’s rerun: `a31-tls-worker/private-runtime/export-suffix.xml`, SHA256 `28f4e12af92afaace6ee7d055dce0ffb962c37a88ebd881052cbba726ac831a6`. It contains1284 executed testcase records:1283 pass,1 failure,0 errors,0 skips. Failure node is `tests.integration.test_gateway_query::test_new_query_proof_accepts_expired_original_proof`. Native worker exit and1024.5s were communicated by root; this reviewer did not execute that process. The XML traceback itself confirms failure at initial `accepted = env.adapter.accept(original)` with `STALE_REQUEST` / `proof expired`. Current source lines655–666 create original proof_lifetime=1, accept it, only then wait for original expiry and issue a new query proof. Thus the initial proof expired before acceptance and the intended post-expiry query assertion was not reached. Production expiry rejection is retained; the failure does not demonstrate that query behavior passed or failed.

Blocking issue **PR9-C4-R1-001**: one-second original-proof setup has an unstable pre-acceptance window. Required remediation is a deterministic test-only synchronization/lifetime setup that still proves the originally accepted proof is truly expired before the fresh query, preserving real SQL/time/state/zero-new-effect assertions and production freshness checks. Root must authorize remediation, freeze a new candidate, and assign a fresh full reviewer. This reviewer does not modify or consume unfrozen corrections. A targeted pass must not substitute for the next full required independent matrix.

## Frozen identity and independent source checks

Manifest `tasks/workflow/runs/pr9-historical-ci-20261018/candidate4-manifest.json` SHA256 `48419ff740d6361902e5e5a369b9440a1e9ad5b0ea69d18847f7339a31daaae6`; base HEAD `eafb6f28aa87a041e149c0190b76054424f1c9cf` with uncommitted C4 implementation. Independently recomputed every one of1204 contents at beginning and end, including the two tracked symlinks as link target bytes, without dereferencing them. Both passes:0 mismatches; same manifest digest. See `source-begin.json` and `source-end.json`. End observation2026-10-18T12:54:36.345672+00:00 precedes any permitted future correction and cannot attest a later candidate.

Read repository AGENTS/AGENT/current-policy, task package/C4 and all current addenda, candidate1 blocker/candidate2 probe failure, environment closure analysis, CI inputs documentation, relevant portions of README/protocol/security/acceptance and review contract. Inspected actual workflow, A31 receipt/helper/fixture/query shim/audit-delivery diff, supervisor/controller/cleanup paths and inherited materialization. This was substantial but **incomplete static review**, not a claim all1204 files or every affected assertion received semantic review.

`git diff --numstat -- src migrations` had no changes: the current business source and migration tree were unchanged relative to the review HEAD at observation. Full AST comparison of original tests and original fixture provenance inventory was not completed before STOP. The original6839 count is inherited scope, not a fresh collected count from this reviewer.

## Actual independent executions

All commands ran from candidate repository on the host; these are quality checks only. Native outputs and exits retained in `quality-results.json` and `quality-0.log` through `quality-3.log`.

- `/tmp/cosm2-a1-a2-tools-20261017/bin/python -m ruff check .`: exit0, All checks passed.
- Same Python `-m ruff format --check .`: exit0,365 files already formatted.
- `node --check web/teacher-demo/app.js`: exit0.
- `node tests/test_teacher_demo_frontend_logic.cjs`: exit0, frontend logic passed.

No target Python test, Docker run, PG connection, counter, source/wheel inherited group, fresh native XML or independent runtime negative control was executed. Host Python3.14 was used only for hashes, file preparation, parsing existing XML and cleanup; it was never substituted for Python3.11 tests. Copied host threshold binary was identified by `file` as Mach-O arm64, unsuitable for Linux target, and was never executed. A future reviewer must obtain/build the correct Linux binary and qualify its provenance rather than use this copied binary.

## Static observations and their practical limits

The current A31 branch checks the exact11-field receipt, absolute/no-symlink private material paths, currentUID/modes, full64hex container identity, expected external owner against real Docker labels/running state, bound CA/delivery digests, allowed DNS/host equality and a real libpq verify-full connection followed by pg_stat_ssl. This review read those paths; it did not generate a fresh receipt or independently prove a valid or rejected real connection.

The new ssl.SSLEOFError catch is nested only around completed-response send_response/send_header/end_headers/body writes; request parsing, verification, transaction processing and other exceptions remain outside that catch. Existing broad handler_error semantics remain. AuditClient production source was unchanged. Query shim explicitly accepts the fifth optional approval and asserts it is None; original path/token/proof/body checks remain in the visible diff.

CI declares three distinct PG services, provisions real downstream and denial role, generates A31 receipt and separate A32 export PKI with the original certificates helper. It pins Actions to complete commits, uses same-repository trusted-head checks and noneditable installation with hash-locked wheel dependencies, keeps key scoped to unpack-step env, uses private pytest output and strict cleanup-all before deleting owned directories. Static reading does not establish a successful clean-checkout CI execution, Secret delivery or actual post-cancel cleanup.

Controller code contains the newly authorized A32 export-PKI producer, /evidence/logs relocation and dynamic legacy prefix mappings; /private private tmpfs and trusted-controller socket mounts are explicitly assembled. Supervisor validates closed typed bootstrap/public fields and persists owned identities. Cleanup validates recorded fullID/owner/run/project/image bindings and rejects unknown entries. These observations are not substituted for required nonrootUID1001, wrong-owner/wrongCA/wrongSAN, cancel and unknown-resource runtime controls. Public-control allowlist and bounded private output were read but not fully adversarially exercised.

## P9 matrix at STOP

|ID|Status/evidence|
|---|---|
|P9-01|NOT_RUN complete independent original nonintegration/integration. No fresh collection/XML; no claim of6839 executed. Upstream single failure remains blocking.|
|P9-02|PARTIAL_STATIC: fifth-argument shim/approval=None and original visible checks retained; full real-PG file not run.|
|P9-03|PARTIAL_STATIC: root workflow three PG/downstream/role and current TLS chain read; no reviewer-owned domains provisioned.|
|P9-04|NOT_RUN: frozen capacity metadata/tool paths read only. No independent HTTP fetch, AEAD unpack,110SHA,139 installed binding or original counter. Original numbers10000/30009/668/203285/raw291623992/wire439169636 and NOT_ASSERTED remain requirements, not this reviewer results.|
|P9-05|NOT_RUN runtime source/wheel,12 roles,3PG,21 locks,139 installed bytes, child kills, original20 groups including1000clock. Some static deployment/observer paths read.|
|P9-06|BLOCKED_C4: observed business/migration diff empty; new original-proof test timing failure prevents acceptance. No candidate repair performed.|
|P9-07|PARTIAL_PASS: actual global Ruff365 and Node pass. Target3.11 fresh installation/pipcheck, Rust/Anvil and complete Node/UI/export checks not completed.|
|P9-08|PARTIAL: fresh independent beginning/end1204 content checks pass; full independent runtime/negative matrix missing. Complete acceptance prohibited.|
|P9-09|PENDING_ROOT_AFTER_NEW_LOCAL_ACCEPTANCE: root-only exact published-head all-CI-green and ordinary expectedSHA squash gate. This future gate is not itself the reason for this local rejection. No remote state claimed.|
|P9-10|PASS reviewer-scope cleanup/isolation only: no candidate mutation; own runtime resources/keys/plaintext/env0. User file SHA verified below; readability not independently rerendered.|

## User local files

Independent actual SHA matches all three authorized supplied values (`user-file-sha256.json`): CSS `88e88bccb6c4be276b54b1ef1e27866c4ab1f9fe46f55c667d1a382397a6ca91`; DOCX `0205832f0aac3accef0017ec18f56fd779293101fe7d132572968de2b519ddb9`; main.pdf `1eef31d123c2d2589e862a39d512397c7b9deaf6cc8ed1d520cdeba9bc31dad4`. No content edits or Word/PDF/UI rendering was performed by this reviewer. Root’s prior readability evidence was not claimed as an independent rerender. Generated aux/out/synctex were not included in reviewer snapshot; this reviewer grants no publication authority for them.

## Preparation, safety and actual cleanup

Created one private UUID-only `/private/tmp/pr9-acceptance-r1-461a2e82-5dc3-4378-9007-6933ca9129b4` directory, copied exactly manifest-selected content with original symlinks, immutable CI/x402 wheels and unused host threshold binary. STOP arrived before any target container creation. Entire own UUID root has been removed. `resources-final.json`: containers0,networks0,volumes0,newimages0,private-root absent,keys read/copied0,generated plaintext0,secret env0. No Docker resource ever created; no unknown resource inspected/deleted, no prune. Root original key/cipher/plaintext inputs remain untouched. Retained report/evidence files are0600, own output directory0700. No sensitive original log text was copied into this report; upstream XML was parsed only to public-safe counts/node/stage confirmation.

Expected future target environment is Docker Desktop Linux x86_64 Python3.11.17 on Apple arm64 emulation, not native performance; no target performance measurement occurred here. Original worker failures/cancellations and previous candidate records were not changed or erased. COSM2 previous full acceptance is unaffected and is not treated as PR9 historical-CI acceptance.

**STOP. Root must remediate and refreeze; this reviewer will not continue with unfrozen corrections.**
