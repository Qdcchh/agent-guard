# dependencies/x402-20261017

Pinned inputs for the x402 runtime (`agent-guard-x402-runner:20261017`). Local
test-chain use only; not production deployment material.

## Layout

| Path | Content |
|---|---|
| `FiatTokenV2_2.json` | compiled Circle FiatTokenV2_2 ABI + bytecode + link references + provenance |
| `stablecoin-evm/` | exact `circlefin/stablecoin-evm` v2.2.0 sources for the FiatTokenV2_2 import closure (19 files) + `LICENSE` (Apache-2.0) |
| `openzeppelin-contracts-3.4.2/` | `@openzeppelin/contracts` 3.4.2 files needed by the closure (4 files) + `LICENSE` (MIT) |
| `SOURCES.lock.json` | per-file identity manifest (git blob SHA-1 for Circle, SHA-256 for OZ) |
| `vendor/anvil` | Foundry v1.8.5 anvil, linux/amd64 (sha256 `00f97668...`) |
| `vendor/solc-0.6.12` | official solc 0.6.12 linux/amd64 (sha256 `f6cb519b...`) |
| `vendor/SHA256SUMS` | vendor binary hashes |
| `vendor/licenses/` | upstream license texts (Foundry MIT/Apache-2.0, solc GPL-3.0, x402 spec Apache-2.0) |
| `tools/compile_fiattoken_v2_2.sh` | reproducible compile recipe |
| `tools/verify_sources.py` | source identity check against `SOURCES.lock.json` |
| `tools/render_fiattoken_artifact.py` | renders the final artifact JSON from solc output |
| `.build/` | last compile outputs (combined + standard JSON) |

No source file needed editing: the vendored files are byte-identical to
upstream (verified below), and `@openzeppelin/...` imports are resolved by
compiling inside a symlink farm so source unit names stay canonical.

## Provenance pins

| Input | Pin | Verification |
|---|---|---|
| Circle stablecoin-evm | tag `v2.2.0`, commit `405efc100c016ed1a437063b6274b4e24ea7b8b1` (2023-11-09, "Merge pull request #425 ... release_v2_2") | all 19 files match the GitHub tree blob SHA-1s at that commit; `LICENSE` Apache-2.0 |
| OpenZeppelin Contracts | npm `@openzeppelin/contracts@3.4.2`, tarball sha256 `72f4176e8d4db8825a6161a7663061f3c3d3f2f6e14c7d5357bec6bd1dd9c7bd` | tarball SHA-512 equals the npm registry `dist.integrity`; 4 files match the npm package; MIT |
| solc | `0.6.12+commit.27d51765` linux/amd64, official static binary | sha256 `f6cb519b01dabc61cab4c184a3db11aa591d18151e362fcae850e42cffdfb09a` equals the `binaries.soliditylang.org` list entry (`solc-list.json` in the worker scratch) |
| Foundry / Anvil | release `v1.8.5` (2026-10-05) asset `foundry_v1.8.5_linux_amd64.tar.gz` | official release `.sha256` file equals the local tarball sha256 `6c66ffcc55fa4249197721baa3098bc208014ea1d8aa04b2ed50ac6bccffb226`; extracted `anvil` sha256 `00f97668e1ae0fcca118fd7d2d1b6d25c0496447a523ca6bc2dfd10958c99604`; `anvil --version` -> 1.8.5, commit `51a52c59cffd940f76eddd0b4bb1791aa4b5ac7f`; MIT OR Apache-2.0 |
| x402 Python SDK | PyPI `x402==2.25.0` (wheel sha256 `ce813932133db263fb8501d4aafedc9fd665dfbc67a9e98a5dc86acb79da9485`) | PyPI metadata: MIT, requires-python >=3.10; hash-pinned in `/requirements-x402.lock` |
| x402 specification | `x402-foundation/x402@faa1c694c66a3732aaabbce93bdae140e521a67d` (2026-10-15) | commit confirmed via GitHub API; repository LICENSE Apache-2.0 |

## Reproducible compile

```sh
# linux/amd64 required (solc binary is linux-amd64); from the repository root:
docker run --rm -v "/ABS/PATH/agent-guard-handoff":/work -w /work \
  agent-guard-threshold-gateway-runner:20261017 \
  bash dependencies/x402-20261017/tools/compile_fiattoken_v2_2.sh
```

The script (1) re-verifies the solc sha256, (2) re-verifies all 23 sources
against `SOURCES.lock.json`, (3) compiles
`contracts/v2/FiatTokenV2_2.sol` with `--optimize --optimize-runs 10000000`
(Circle's own `truffle-config.js` settings at the pinned commit; solc 0.6.12
default `evmVersion` istanbul) through a symlink farm so source unit names are
canonical, and (4) runs a standard-JSON pass to capture library link
references.

Observed output (deterministic): `abi=72`, creation 23567 bytes, runtime 23464
bytes; combined-JSON sha256 `300db30383ee55a7014c923edf24dca163a3d3a0ef741d70ac33af5a09d6f2e5`
(re-running produced a byte-identical artifact). The only compile diagnostic is
the upstream warning "Function state mutability can be restricted to pure" at
`FiatTokenV2_2.sol:71`.

## Artifact schema

`FiatTokenV2_2.json`: `contractName`, `compilerVersion`, `compiler`,
`settings`, `abi`, `bytecode`/`bytecodeHex`, `deployedBytecode`/
`deployedBytecodeHex`, `linkReferences` (byte offset of the 20-byte
`SignatureChecker` placeholders), `libraries` (library ABI+bytecode to deploy
first), `metadata`, `sourceKeccak256`, `provenance`, `license`, `notes`.

`bytecode` is intentionally unlinked (contains `__$...$__` placeholders), as in
standard Solidity artifacts. The linked deployment procedure and the initialize
V1 -> V2 -> V2.1 -> V2.2 order are documented in
`deploy/x402-runner/README.md` and exercised by
`deploy/x402-runner/verify_runtime.py`.

## License summary

- Circle stablecoin-evm: Apache-2.0 (`stablecoin-evm/LICENSE`).
- OpenZeppelin Contracts 3.4.2: MIT (`openzeppelin-contracts-3.4.2/LICENSE`).
- x402 Python SDK 2.25.0: MIT (PyPI metadata; no LICENSE file in the wheel).
- x402 specification repository: Apache-2.0 (`vendor/licenses/x402-spec-LICENSE-APACHE.txt`).
- Foundry v1.8.5 (anvil): MIT OR Apache-2.0 (`vendor/licenses/foundry-LICENSE-*.txt`).
- solc 0.6.12: GPL-3.0 (`vendor/licenses/solc-LICENSE-GPL-3.0.txt`).
- Python dependencies in `/requirements-x402.lock`: licenses are recorded in
  each wheel's `dist-info` metadata inside the image (all permissive; see the
  lock for exact versions).
