# Remote fixed input consumer — STOP

2026-10-18. Shared source, tests, CI, original110, user CSS/DOCX/PDF were read-only. This proof concerns this worker's source snapshot (manifest SHA256 `a5f8154ca2b46c92908644b286abeb413311adc504440d31575130e9756c8d34`), not candidate1 or a later amended full candidate. No commit, push, upload, repository Secret operation or shared source mutation was performed.

## Actual downloaded input

Consumed controller/fixed-asset-fetch/ciphertext.aesgcm and fetch-receipt.json: fixed GitHub asset ID 653345275, 107401523 bytes, SHA256 `fb5cf3fc1b0158568c726ca3afced324c6a9c18712dae0ab0beaa6a63d5a8975`. This worker validated those actual downloaded bytes against frozen transport metadata; it did not redo HTTP fetching or prove Actions Secret delivery. Authenticated unpack used the retained original private key via stdin into a child-only AG32_CAPACITY_KEY env, `--key-env`; no key argv value/file/GITHUB_ENV/Docker-config env was created. Host secret reference was cleared; physical memory erasure is not claimed.

`actual-download-input.json`, `restored110-sha.json`, and `actual-installation-binding.json` show authenticated unpack, independent original110 length/SHA validation, prepare and actual139 installed binding all succeeded. Original archive SHA256 remains `9eafeecc22541229d5c3ccc9cc0d033f5a4d89497e51e45282fe8255501a4358`. No old historical bytes were changed. CAPSEC01 remains applicable: two original rejection logs contain password-bearing libpq DSNs; liveness UNKNOWN_NOT_PROBED. This run grants no permission to publish plaintext, historical logs or database data.

## Real current installation

Image full ID `sha256:fc9134fe1a2c90c52998c6f44f49e77e1a08faba95a58d7acf78985dd8e4fa1f`; Linux x86_64 Python 3.11.17 (Docker Desktop Linux on Apple arm64 host). A new `/work/venv` was created, all21 requirements-ci.lock wheels installed with --require-hashes, current snapshot package installed noneditable with --no-deps/--no-build-isolation, pip check passed. Total install 13.225s. Actual imported module was `/work/venv/lib/python3.11/site-packages/agent_guard/__init__.py`; include-system-site-packages=false, no PYTHONPATH, direct_url dir_info={}. All139 current business Python files matched source SHA before capacity execution. Image's previous installed package was not used.

Snapshot copied Git tracked/public candidate sources and materials plus precisely the three authorized local user CSS/03-DOCX/main.pdf files (recorded in explicit-user-readonly-copies.json); it excluded private artifacts, .git, nonGit historical secrets and generated aux/out/synctex. It did not copy the entire user report folder. See source-snapshot-sha256.json and read-only-source-fingerprints.json.

## Original fixed capacity counter

Original `test_real_fixed_10000_capacity_preflight`: native exit0, 1 PASS, 0 failures/errors/skips, 399.370879s, peak child RSS1714788 KiB. Original test/counter assertions unchanged. Exact values: native operations10000; journal30009; legal batches668; objects203285; raw291623992 bytes; wire439169636 bytes. First raw cap crossing object165414, raw268436418, journal23963 TERMINAL. First object cap crossing200001, raw291137960. Acceptance remains NOT_ASSERTED; footer roots remain length-only placeholders and terminal material original row arithmetic. This is counter execution, not a new10000-business run or project acceptance. Evidence: capacity-run-summary.json and counter-aggregate.json; native JUnit/logs retained0600 privately.

## Complete nonintegration execution

Actual x402 dependencies were required. Initial Docker wheel download failed TLS EOF, exit2 with0 wheels; failure log retained. Host Python3.14 was used only to download explicitly targeted Linux cp311/abi3 wheels, not test execution. All41 requirements-x402.lock wheel hashes verified, then installed offline into this same fresh3.11 environment with --require-hashes; pip check exit0. CI/x402 lock overlap had no version conflicts.

First full `tests --ignore=tests/integration`: 2195 nodes, 2188 PASS, 6 FAIL, 1 SKIP, 489.45s; native exit1 retained. Six failures exposed root identity/host bind permission semantics (including mandatory euid!=0); no source fix was made. Raw logs/JUnit remain private-native/nonintegration-run.

Correction: copied the same newly installed noneditable environment/source byte-for-byte at the same `/work` path into this worker's own native Linux named volume, chowned to UID/GID1000, and reran the entire unmodified command via tools/pr9_ci_run.py, no Docker socket. Native exit0, 2195 nodes: **2194 PASS, 0 FAIL, 0 ERROR, 1 SKIP**; summed native testcase time465.621s. Includes test_pr9_ci_run7 nodes and test_pr9_capacity_fetch14 nodes. This was a migrated copy of this run's current installation, not the image installation. Original skip is RealCliTests requiring Docker daemon. `nonroot-summary.json` and private-native/nonintegration-nonroot preserve evidence.

After explicit additional root authorization, a separate trusted controller alone received Docker.sock and an exact host absolute-path snapshot mount; ordinary full-test role had no socket. Ran original `RealCliTests::test_actual_cli_run_in_docker` unchanged with --require-no-skips: native exit0, **1 PASS,0 SKIP**,6.495s. Runner image full ID `sha256:997ccb375167a46fb019795a3a59da2d9bc59778b1027e8da85c4f603e8ec567`. Original launcher created fresh owned PG/network/runner; original demo six cases passed, resources_remaining=[] and docker_cleanup_ok=true. Exact resource-name absence independently checked. This is a separate successful node, not a fictional same-round2195-pass/zero-skip claim. See realcli-summary.json, realcli-cleanup-summary.json and private launcher receipt.

## Cleanup and limitations

resources.json confirms own containers0, own Linux volumes0, own private root removed, generated plaintext0, copied/new keyfiles0; original candidate key and controller downloaded cipher preserved outside this worker root for final review. Native logs/JUnit are the explicit retained private evidence exception, files0600/directories0700. Private copied source, user files, venv, wheels, unpacked originals, prepared binding, test scratch, ephemeral signing/PG credentials and own volume were removed. Cleanup corrected a resource_names list shape and chmod-denied temporary directories before final success; no unrelated resources touched. No production services/database were used. Network was disabled for actual consumers except original authorized nested Docker fresh test network.

This local target-runtime proof does not establish final-candidate all-files identity, full integration suite, GitHub Actions execution, repository Secret delivery, production acceptance or performance. Parent's fresh final review must use its final frozen candidate and own qualification gates. STOP; no work remains in this worker resource scope.
