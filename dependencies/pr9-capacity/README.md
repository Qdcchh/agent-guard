# PR9 historical capacity input

Only this safe allowlist, transport metadata, and source/verification code belong in Git. The 110 original files include a database row snapshot, expired synthetic authorization/proof material, dormant lease handles, and two original failure logs with libpq keyword DSNs/passwords. Those passwords have verified historical isolated-test provenance but current liveness is **UNKNOWN_NOT_PROBED**. Neither raw inputs nor encrypted payloads nor keys belong in Git/LFS. Earlier URI-only safety summaries were incomplete; see the separate CAPSEC-01 correction in the transport worker report.

`source-manifest.json` fixes all 110 roles, safe relative paths, exact byte lengths/SHA256 and the original binding SHA. It carries only the minimum safe historical binding metadata needed by the existing `prepare` tool. It does not certify current business semantics or grant publication permission. `transport.json` binds the complete source manifest, fixed framed stream, gzip stream and ciphertext by length/SHA; its nonce is public. After independent transport review, the controller published only the ciphertext as GitHub release asset **653345275** in `Qdcchh/agent-guard` release `ci-capacity-inputs-20261018-r6-v1`. `transport.json` fixes this asset ID and the unchanged cipher length/SHA. This publication alone does not establish full same-head CI acceptance. The key remains separate from public metadata.

The content stream is a fixed magic header plus the 32-byte canonical manifest digest, followed by the exact 110 files in manifest order and lengths. It contains no filenames, link records, executable extraction metadata, or tar/zip structure. Compression is gzip level 6. One mature `cryptography` AESGCM operation uses a fresh CSPRNG 256-bit key and independent 96-bit nonce for every package. AAD binds format, dataset, canonical manifest SHA, framed and compressed lengths/SHA, compressor metadata, and nonce. The external asset location is a locator, not an authenticated content identity; fixed ciphertext length/SHA and GCM authentication remain mandatory after any locator change.

## Local packing and review

Run with the existing locked Python/cryptography environment. `pack` takes the original historical binding and root, verifies every original member, and creates a **new** mode-0700 output directory containing mode-0600 ciphertext, key, safe source manifest and transport metadata. The real dataset name additionally requires the exact original 110-member binding SHA. No existing output is overwritten. The compression temporary file is removed after successful encryption; failure removes only the new output tree.

```sh
python tools/pr9_capacity_transport.py pack \
  --historical-binding "$ORIGINAL_BINDING" \
  --historical-root "$HISTORICAL_ROOT" \
  --output-root "$NEW_PRIVATE_PACKAGE"
```

Do not publish the whole output directory. The controller receives only the private key-file location through a mode-0600 handoff file, never a key value in argv/logs. No key is generated from the fixture's SM2 keys or historical database password.

## Verified consumer interface

`python -m tools.pr9_capacity_fetch` resolves the exact frozen asset ID, requires its expected release/name/size, follows only HTTPS for public ciphertext without any Authorization header, and checks cipher length/SHA into a fresh private output. The controller fails if the asset or Secret is missing. The decoder also requires the local cipher file, exact ciphertext length/SHA, and one private key source; it has no download fallback, fabricated input, skip, or built-in key. CI supplies the base64-encoded 32-byte key only in the necessary step environment, not CLI values, `GITHUB_ENV`, a key file, artifacts, or caches.

```sh
python tools/pr9_capacity_transport.py unpack \
  --manifest dependencies/pr9-capacity/source-manifest.json \
  --metadata dependencies/pr9-capacity/transport.json \
  --ciphertext "$CIPHER_FILE" \
  --output-root "$NEW_PRIVATE_DECODED" \
  --key-env AG32_CAPACITY_KEY
```

For authorized local review only, `--key-file /private/owner/bundle/key.bin` is available; it must be a single-link mode-0600 regular file inside a private directory. Paths must be real paths without symbolic links, traversal or hard links. The decoder fully authenticates the approximately 107 MB compressed message before creating the private partial plaintext tree; then it bounds decompression, rejects extra gzip streams/tails/overlong output and checks every member's original SHA. Only after the complete stream and every original match does it rename the tree to `$NEW_PRIVATE_DECODED/historical-root` and expose `source-binding.json`. All failures return nonzero, emit only a fixed safe CLI error, and remove their own partial plaintext tree. Existing destinations and original sources are never removed.

Feed that returned root and `source-binding.json` to the frozen `tools/pr9_capacity_inputs.py prepare` interface. Preparation accepts the actual original raw binding identity, or the exact canonical reconstructed binding generated from the pinned public manifest and transport metadata. It records the trusted original binding SHA, the actual received binding SHA and the manifest SHA separately. Removing or forging transport markers cannot fall back to a legacy branch; the whole reconstructed document and all original member bytes must match before output is created. Every source/wheel consumer must then run `bind-installed` under its own real noneditable Python 3.11 installation against current source SHA/spec origins, followed by the unchanged original capacity test. The historical classification and reconstructed safe binding are provenance, not an automatic approval of source semantics. All original object/raw/wire limits, boundary assertions and `NOT_ASSERTED` remain unchanged.

## CI trust and retention gates

All code that can access the step key or later plaintext—including workflow, decoder, dependency installation/build hooks, source, tests and tools—must be the same reviewed frozen same-repository head on a fresh ephemeral runner. A step-only Secret does not protect later plaintext from malicious code. Pin third-party Actions by full commit SHA, use checkout `persist-credentials: false` and hashed dependency locks. Do not expose the Secret via `pull_request_target`/`workflow_run` to fork code. Fork/Dependabot missing Secrets must fail explicitly rather than skip the original test or relax Secret policy.

Only ciphertext may be uploaded externally after controller authorization and fresh independent implementation review. A public Release ciphertext is publicly retainable; it is not private object storage. Key deletion/rotation cannot retract copies of an old key plus ciphertext. A mutable latest tag or expiring Actions artifact alone is not a reproducible source: freeze the actual asset ID/length/SHA and describe persistence/resupply. No external upload, Actions Secret setup, download verification, full CI acceptance or merge is performed by these tools.

Public/CI evidence must use an explicit allowlist of sanitized aggregates, exit codes, JUnit statistics and source/install SHA. Never upload whole evidence/temp roots or raw failure traces, which can contain DSNs. Use `finally`/trap/always cleanup on success, failure and cancellation for each owned private tree, temporary environment and resources; never shared prune/down. Runner recycling is not proof of physical memory erasure. Preserve original historical failures and bytes.

The C6 clean-path rejection and remediation are retained in `tasks/workflow/runs/pr9-historical-ci-20261018/candidate6-rejected.md`. The original transport review and its151-file map are preserved as a historical snapshot. The current source map explicitly binds the four remediation files and requires a new full-head acceptance; it does not retroactively claim the old review accepted new source. The fixed manifest, transport metadata, external ciphertext and managed Secret remain unchanged.
