# PR9 candidate6 independent implementation acceptance r3 — STOP_NOT_ACCEPTED

2026-10-19 UTC. Fresh independent implementation reviewer r3, requested gpt-6.1-sol/high; effective backend metadata UNKNOWN. Root is the sole Git, shared-source and remote writer. This reviewer wrote only its private `artifacts/pr9-historical-ci-20261018/implementation-review-r3/` evidence tree. No candidate source, formal test, original fixture, workflow, user document, Git state, remote state, release or Secret was modified.

## Decision

**STOP_NOT_ACCEPTED. Candidate6 has a confirmed clean-checkout capacity provenance incompatibility, PR9-C6-R3-001.** After the reviewer reported the real failure, root explicitly invalidated C6 and ordered STOP. Complete independent nonintegration, complete original6839 integration, both source/wheel original20 inherited groups, three-domain/12-role acceptance and runtime security controls are NOT_RUN. Preparatory passes and the earlier worker diagnostic do not replace them. This review grants no local acceptance, CI acceptance or merge approval.

P9-09 remains a later root gate after a future complete local acceptance. Its future publication/CI/merge has not occurred in this review and is not the reason for this rejection.

## Frozen identity and independent integrity checks

Manifest: `tasks/workflow/runs/pr9-historical-ci-20261018/candidate6-manifest.json`, SHA256 `33ca1d70464fb63b0481c957352bea21d5a5cad2bdd34639d8395adbad6ef6e1`, base commit `eafb6f28aa87a041e149c0190b76054424f1c9cf`. The actual reviewed checkout was the byte-identical read-only snapshot `/private/tmp/pr9-public-snapshot-c6-20261019/checkout`.

Independently recomputed all1220 manifest members at the beginning and end, separately against both the read-only snapshot and the shared checkout: zero mismatches in all four passes. Symlinks were hashed as link-target text bytes, without dereferencing. The beginning/end manifest digest is identical. `source-begin.json` and `source-end.json` retain actual timestamps and results; they attest C6 before any later authorized remediation, not a future candidate.

Compared every139 business source file and18 SQL migration with the base commit using actual bytes: no differences. Independently verified all196 curated Python originals and8 sidecar provenance inputs against both their recorded SHA and the actual retained historical source files, with no missing/mismatching originals; all196 Python originals parse. These results are in `business-migration-base-comparison.json` and `original-provenance-check.json`.

Read AGENTS→AGENT/current-policy, the review contract, current package and package review, original r1/r2 rejections, C5 rejection and every current addendum, current workflow and relevant deployment/capacity/helper/test paths. Inspected the exact C5 compatibility corrections: fixed real DB routing and owner/TLS/system-ID guards; original six SQL materialization; exact historical migration prefix plus008009/current registry metadata; current41 gateway and4 downstream inventory qualification with added snapshot mutation controls; and current test-only query expiry/receipt inventory changes. This is a substantial but incomplete static review stopped by the confirmed defect. It is not a claim every frozen file or every affected security assertion received complete semantic review.

## PR9-C6-R3-001 — reconstructed binding identity is rejected by the deployment consumer

Severity: blocking. Trigger: execute the frozen CI's documented public fetch→authenticated unpack→prepare sequence, then validate the prepared capacity root for the required nested inherited deployment tests.

The reviewer independently performed that real public path, using a fresh Python3.11 noneditable installation and the fixed public release asset. No old worker input root was used:

1. Public asset653345275 fetched by HTTPS requests without an Authorization header:107401523 bytes, SHA256 `fb5cf3fc1b0158568c726ca3afced324c6a9c18712dae0ab0beaa6a63d5a8975`.
2. The fixed metadata and AES-GCM authenticated unpack succeeded. All110 original members were reconstructed and SHA-checked. The secret was supplied only to this decoder container through its process environment, never a CLI value, output or environment dump. The original key file was not copied or modified. This reviewer preparation combined fetch and unpack in the same short-lived container, whose environment already held the decoder key; it therefore does not independently demonstrate the CI workflow's separate fetch/secret-step process isolation. The HTTP request itself carried no key or authorization credential.
3. `tools/pr9_capacity_transport.py:508–526` intentionally reconstructs a safe new `source-binding.json` from the authenticated public manifest. It records `original_binding_sha256=4509d6f5620634104d51a682a58aacd7e6bff48c7939142f699600b31a9e2a45` and the authenticated manifest SHA. The reconstructed file's actual raw SHA is `ff7d0dd3d60857f7d7caf98a7a9b017d8b1ec50c4b134e58a4c66d3a7470eba9`.
4. The frozen CI invokes `tools/pr9_capacity_inputs.py prepare` on precisely this reconstructed file. At `tools/pr9_capacity_inputs.py:110–112`, prepare writes its actual file SHA into `relocation_run.historical_binding_sha256`. Consequently the prepared binding records `ff7d…eba9`, while retaining the correct `/capacity/inputs` mapping. Preparation and subsequent actual139-module installed binding both succeeded.
5. `tools/pr9_deploy_inputs.py:1612–1617` demands that this relocation field equal the old original binding SHA `4509…2a45` from `tests/fixtures/pr9_legacy/trusted-capacity-members.json`. It raises `ValueError: capacity source or container prefix mismatch` before the member-validation loop. `tests/integration/test_a33_clean_deploy.py:263–266` calls this exact validator before mounting capacity inputs into every required inherited consumer.

Thus the producer and consumer disagree about which object's identity the same field represents. This is a source incompatibility in the fresh public CI path, not a bad key, failed public download, SHA corruption, Python version, permissions, original member mismatch or source drift. Reusing the old raw historical binding would avoid the trigger but would fail the authorized clean-checkout/public-fetch obligation and was not used as a workaround.

Actual independent Python3.11 minimal native repro: `capacity-clean-path-failure.xml`, native pytest exit1, one executed testcase/one failure/zero errors/zero skips. The test directly asserts that the valid freshly prepared root is accepted, and fails at the real validator with the above ValueError. `capacity-probe-native-exit.json` distinguishes that native failure from the outer diagnostic wrapper's exit0 confirming the expected reproduction. Neither is represented as an original integration pass. `capacity-source-blocker.json` retains the exact safe SHA/provenance chain, actual target Python/UID and both lock-version inventories; `capacity-native-summary.json` binds the native XML SHA.

The first three planned domain drivers also independently rejected the prepared input in their host preflight before creating any PG/deployment/controller owner. These are preflight rejections, not source/wheel/ordinary matrix executions. They did not produce a full integration XML and are not counted as three original test failures.

Required correction boundary: qualify and preserve the two separate identities—the actual reconstructed binding SHA and the trusted original historical binding SHA—and prove their precise relation to the authenticated, fixed public source manifest/transport metadata. Do not simply overwrite the field with4509, accept an arbitrary self-declared `original_binding_sha256`, skip validation, change the110-member role/SHA inventory or relax current139/source/import binding. Preserve the original-binding path where legitimately required. Add meaningful positive coverage of the actual fetch/unpack/preparation handoff plus negatives for forged/missing/wrong original identity, altered reconstructed binding or manifest linkage, changed/missing member and invalid mapping/permissions. Production business/SQL semantics and original capacity counters/limits must remain unchanged. Root must authorize implementation, stop all writers, freeze a new complete candidate and appoint a new independent reviewer for the entire acceptance matrix.

## Actual preparation and collection results

Target tools image independently inspected as linux/amd64, fullID `sha256:fc9134fe1a2c90c52998c6f44f49e77e1a08faba95a58d7acf78985dd8e4fa1f`. Actual Python3.11.17/GCC12.2.0, x86_64, nonrootUID501 with mode0700 HOME. Execution used Docker Desktop on Apple arm64 with amd64 emulation; no native performance claim is made.

A fresh venv installed all21 CI-lock wheels with `--require-hashes --only-binary=:all: --no-index` from the immutable supplied wheelhouse. The actual C6 project was wheel-built without dependency resolution/build isolation, then installed noneditable. The41 x402-lock wheels were freshly downloaded with all hashes required, installed from the resulting local wheelhouse, and pip check passed. The final direct target probe checked the actual installed version of each entry in both locks. Actual139 current source bytes and module import origins were bound by `bind_installed`, under the new installation rather than the image's package. This supports the observed preparation scope, not full source/wheel deployment acceptance.

Fresh complete collection succeeded, actual native exit0:

|Inventory|Collected|Unique|Execution status|
|---|---:|---:|---|
|All original current integration|6839|6839|Complete execution NOT_RUN|
|All nonintegration, including top-level B tests|2255|2255|Complete execution NOT_RUN|

`integration-collect.json` raw SHA256 `dce5b42a0cb5da81b789b79c5ecbfa3471a7a66df306de1c90980c5fcc407017`. Planned explicit complete node partition: ordinary6821, source9, wheel9; the source/wheel9 each are exactly the parameterized role/clean-deployment nodes requiring a33_install, and ordinary includes every scenario/registration node. The unique union equals6839 with zero overlap. `partition.json` and the three exact node lists retain this plan. No partition was actually run. Consequently no full native-XML union is claimed. Source/wheel all20 groups each remain NOT_RUN.

Preparatory mistakes were preserved and corrected only inside reviewer-owned drivers: first collection lacked x402/web3 and reported two import errors/6819 collected; after installing the full x402 lock, a reviewer driver string-slicing error raised AttributeError after a successful6839 collection. The final clean collection completed both inventories with native exit0. `attempt1-*`, `prepare*.private.log`, `collect.private.log` and exit files preserve this history. These setup mistakes are not candidate test failures and do not erase the confirmed source failure.

Independently fresh-built the actual C6 threshold crate with `cargo build --locked --release` using rust:1.99.1-slim-bookworm. Actual `rustc -vV` reports1.99.1/host x86_64-unknown-linux-gnu; cargo1.99.1, uname x86_64. The resulting binary is Linux ELF64/e_machine62, with source and binary SHAs in `rust-independent-build.json`. The current compiled source includes V3, but V3 vectors, runtime threshold/Anvil/x402 behavior and the required COSM2/payment test counts were NOT_RUN. No host Mach-O or image's old threshold binary was used as acceptance evidence. The Anvil file's frozen source bytes are covered by the candidate manifest; its runtime qualification was not completed.

## P9-01..11 matrix at STOP

|ID|Actual evidence and remaining obligation|
|---|---|
|P9-01|PARTIAL: independent complete6839/2255 collection and original204 fixture provenance pass; full execution and zero-skip/native-XML union NOT_RUN. No deletions/relaxations were made by reviewer.|
|P9-02|STATIC_ONLY: fifth optional approval with explicit None rejection retained; real full inherited trusted-material file NOT_RUN.|
|P9-03|NOT_RUN: fresh complete three-domain TLS/independent transactions, denial role and real12-role setup. No domain owner was created because capacity preflight rejected.|
|P9-04|BLOCKED_CONFIRMED: actual fixed public fetch, AES-GCM110 unpack, original memberSHA and current139 installed binding pass; clean producer→nested validator incompatibility confirmed. Original counter and its10000/30009/668/203285/raw291623992/wire439169636/boundary/NOT_ASSERTED assertions NOT_RUN. No new10000 business experiment or40000 experiment was launched.|
|P9-05|NOT_RUN full source/wheel installations,12 roles, all20 inherited groups per mode and real scenario/fault/registration matrix. The planned9+9 nodes were never executed.|
|P9-06|PASS byte-integrity boundary for139 business/18 SQL versus base; blocking source qualification issue must be corrected in a new candidate. Reviewer made no fix.|
|P9-07|PARTIAL_PASS fresh target3.11/21+41 locks/noneditable/pipcheck/current139 and fresh locked LinuxRust1.99.1 build. Independent global Ruff/format/Node/browser, binary vectors, x402142 and COSM2 complete behavior NOT_RUN. Root's checks are not relabeled reviewer runs.|
|P9-08|PARTIAL: fresh independent beginning/end1220 checks, original204 checks, complete collection and real minimal failure retained; full independent acceptance missing and C6 invalidated.|
|P9-09|PENDING_ROOT_AFTER_FUTURE_FULL_LOCAL_ACCEPTANCE: latest-head all-GitHub-CI-green plus expectedSHA ordinary squash remain mandatory. No remote success or merge claim.|
|P9-10|PASS reviewer-scope isolation and exact cleanup: candidate unchanged, six recorded own owners' containers/networks/volumes/images all0; decoder/relocation/plaintext/temporary-secret inputs removed. Historical unknown-volume attribution remains UNKNOWN.|
|P9-11|PARTIAL: all three authorized user file byte identities match; DOCX ZIP structure/text parse passes. Independent browser/Word/PDF rendering and behavioral acceptance NOT_RUN. Existing root QA was read as prior evidence, not represented as this reviewer's rerender.|

## User local files

Actual supplied CSS SHA `88e88bccb6c4be276b54b1ef1e27866c4ab1f9fe46f55c667d1a382397a6ca91`; 03-stage-report DOCX SHA `0205832f0aac3accef0017ec18f56fd779293101fe7d132572968de2b519ddb9`; main.pdf SHA `1eef31d123c2d2589e862a39d512397c7b9deaf6cc8ed1d520cdeba9bc31dad4`. All match the manifest. DOCX archive integrity and XML text extraction passed without modifying OOXML. The existing04 planning DOCX was also byte/integrity checked; this is not new publication authorization. No document content or CSS was changed. The root's12 browser views/13 DOCX pages/15 PDF pages and draft/PDF red-placeholder boundary were read as existing QA evidence only; no independent visual rerender occurred before STOP. Aux/out/synctex were not approved publication artifacts or review output.

## Resource, secret and retention boundary

Six short-lived reviewer owner labels were recorded for the preparation/collection, public capacity, Rust builder and minimal probe containers. Every removed container was first matched to its actual fullID and exact owner label. After removal, separately queried containers, networks, volumes and images for every exact owner label: all zero. No PG/network/volume/new image was created by these short tools; no deployment domain owner was created. Public trusted tools/Rust base images were preexisting and retained. No shared down/prune or unknown resource deletion was used.

Original key and old capacity sources remain untouched. The key was read only for the decoder child's environment; no key/env dump was written. Removed only the reviewer's newly decoded historical-root, relocated capacity input tree, temporary current binding, target venv/wheel/cache tree and fresh Rust build tree after preserving safe hashes. `resources-final.json` records actual cleanup and owner inventories. It does not claim physical memory wipe, key rotation or deletion of the retained public ciphertext/remote Secret. Historical anonymous-volume ownership remains UNKNOWN and those volumes were not inspected, mounted or deleted.

All retained own evidence files are0600 and directories0700. Raw logs/XML are local private evidence; only explicitly safe aggregate/SHA data appears in this report. Prior worker/reviewer failures, native old capacity bytes, previous accepted COSM2 scope and original user files were not rewritten. Semi-honestn=2/same-host/non-OS-strong-isolation and unproven physical wipe boundaries remain; this stopped review grants no additional claim.

**STOP. C6 is rejected. A corrected frozen candidate and a new independent full reviewer are required.**
