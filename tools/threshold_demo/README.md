# 2-of-3 FROST action authorization prototype

This is an **independent teaching prototype**, not wired into the Agent Guard gateway. It does not change the existing SM2 token, AGPoP, budget, revocation, or execution protocol. The result is a FROST-Ed25519 group signature, **not an SM2 signature**. No business operation is executed by this crate.

## Gateway integration decision for this demo

The 2026-10-16 decision is **No-Go for enabling threshold acceptance in the existing gateway**. The current [`GatewayEndpoint`](../../src/agent_guard/gateway/endpoint.py) and [`InvocationVerifier`](../../src/agent_guard/authorization/verifier.py) require the exact six-field `GM-MVP-1` invocation body and the existing `/v1/invocations` AGPoP proof. This prototype signs a separate `AGENT-GUARD-THRESHOLD-ACTION-V1` message. The gateway has no trusted group-key epoch or threshold-required policy configuration, and its acceptance transaction has no persistent action-ID binding for this signature. Adding an optional client-controlled threshold field to the current request would not enforce a required second approval. Treating the FROST result as an SM2 signature would be incorrect.

Integration requires a versioned request and proof binding, trusted policy and group-key distribution, a verifier with independently checked wire encoding, and atomic replay/authorization/budget checks in the existing acceptance path. Then test a valid 2-of-3 signature followed by ancestor revocation, same-intent retry, changed-intent reuse, crash recovery, and actual downstream effects. Until those tests pass, the demo presents this crate as a separate signing experiment and marks the execution binding as unimplemented.

## What it demonstrates

`trusted_dealer_setup()` creates one 2-of-3 group key using the Zcash Foundation FROST implementation. A trusted dealer exists only during setup and returns three distinct `Signer` values, each holding one verified share. The CLI `setup` writes the shares into three separate signer directories. Each `round1` and `round2` command starts a fresh process and opens only its named owner's `share.json`; `prepare`, `aggregate`, and `verify` open public artifacts only. The dealer must deliver each share to its owner over a confidential authenticated channel and erase its own material. The included CLI runs all processes under one OS user for a local demo; separate OS identities or hardware-backed storage and dealer erasure are **not implemented**.

The CLI's trusted `setup DIR ACTION.json` also writes an owner-local `policy.json` for each signer. The three deterministic domains are authorization (tenant, task, grant path, holder, audience, tool, policy version, key epoch), finance (CNY and maximum amount), and procurement (full parameter digest). All three policies bind the exact approved action message hash and action ID. A signer checks its local policy before producing a round-two share; a denial burns that round's nonce. There is no browser policy switch. This demonstrates owner-local approval, but **the current same-user file permissions do not authenticate a separate administrator or prevent that user from editing policy and shares**. A real deployment needs separate signer identities and an authenticated policy distribution and approval channel.

Each signer produces a fresh round-one nonce and commitment. The coordinator builds a signing package for a validated, domain-separated `OrderAction`, obtains two distinct round-two signature shares, and aggregates them with the library's verified `aggregate` function. Neither the coordinator nor verifier reconstructs the group secret. The signer API only accepts the structured action and checks the signing package message against that action; it offers no arbitrary digest signing endpoint. The CLI moves a round-one nonce file to a `.spent` path before round two, so a failed or interrupted round cannot reuse that nonce via the normal command. `abort` burns an unused nonce. This is a demo file protocol, not crash-safe durable nonce accounting; abandoned `.spent` files retain sensitive nonce material until the owner removes the entire test directory.

`DemoActionGate::accept(action, signature, now)` verifies the group signature against the exact action fields, checks expiration, and rejects a second acceptance of the same tenant/task/action ID. This is an in-memory demonstration of an execution-entry check. An actual gateway integration must place verification, **current grant and ancestor revocation**, trusted quote/cost checks, idempotency, and budget reservation in its existing atomic acceptance path. It must persist replay state; this crate's `HashSet` does not survive restart or protect concurrent processes. No existing Agent Guard route calls this API yet.

The encoded action includes tenant, task, root and leaf grant IDs, holder and key ID, audience, exact tool ID, policy version, key epoch, action and business idempotency IDs, request, quote and version, all order items and quantities, delivery, amount in integer CNY fen, currency, full fixed parameter-structure SHA-256 digest, and expiry. The signer recomputes the parameter digest from the typed parameter fields before signing. The message is `AGENT-GUARD-THRESHOLD-ACTION-V1\n` followed by deterministic JSON of the fixed Rust struct. That encoding is local to this prototype and is **not** the repo's GM-MVP-1/JWS encoding. Any gateway integration must version and review the exact wire format, align its parameter canonicalization, and compare these claims with authoritative token, identity, quote and policy data before using it.

## Dependencies and reproducibility

- [`frost-ed25519` 3.0.0](https://docs.rs/frost-ed25519/3.0.0/frost_ed25519/) is the mature FROST ciphersuite implementation. Its [upstream repository](https://github.com/ZcashFoundation/frost) states stable, feature-complete status and documents an NCC audit of **v0.6.0**, not of this pinned v3.0.0. The [workspace manifest](https://github.com/ZcashFoundation/frost/blob/main/Cargo.toml) declares `MIT OR Apache-2.0` and Rust 1.86.
- `rand` 0.8.5 supplies OS randomness compatible with this FROST release's `rand_core` 0.6 API. `serde` 1.0.228 and `serde_json` 1.0.149 encode the closed action schema. `sha2` 0.10.9 and `hex` 0.4.3 encode the full parameter digest.
- `Cargo.toml` pins direct versions; `Cargo.lock` fixes the transitive graph. The crate is not added to Python runtime dependencies.

Run in a Rust 1.86+ environment:

```sh
cd tools/threshold_demo
cargo test --locked
cargo fmt --check
bash tests/process_flow.sh
python3 tests/verify_vector.py tests/public-vector.json
```

Run the shell flow in WSL/Linux, where it creates and removes a private `/tmp` tree. The focused tests cover all three two-person pairs, one signer, duplicate identity, signer refusal of a different action's signing package, changed amount/delivery/action ID and holder/policy, unknown fields and invalid quantity, expiry before signing and acceptance, and repeat acceptance. The process flow additionally checks signer-owned files, owner-local policy denial, nonce reuse/abort, coordinator duplicate rejection, and changed-amount verification failure. [`tests/public-vector.json`](tests/public-vector.json) is a synthetic, public, test-only group key and signature with no shares. The independent Python/OpenSSL check recomputes the message digest, verifies the signature against the group Ed25519 public key, and rejects a tampered message.
