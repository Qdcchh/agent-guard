# x402 runtime runner image

`agent-guard-x402-runner:20261017` is the pinned runtime for the local
test-chain x402 exact/EVM stage. It extends the unchanged threshold gateway
runner image (amd64, Python 3.11.17; the base's stale signer is replaced by a
reproducible V3 build) with:

| Adds | Location | Pin |
|---|---|---|
| Official Anvil | `/usr/local/bin/anvil` | Foundry v1.8.5; official release tarball sha256 `6c66ffcc55fa4249197721baa3098bc208014ea1d8aa04b2ed50ac6bccffb226`, extracted binary sha256 `00f97668e1ae0fcca118fd7d2d1b6d25c0496447a523ca6bc2dfd10958c99604` |
| x402 Python SDK + EVM stack | `/opt/venv` | `x402[evm]==2.25.0`, hash-pinned full closure in `requirements-x402.lock` (web3 8.0.0, eth-account 0.14.0, pydantic 2.14.1, pycryptodome 3.24.1, ...) |
| Compiled Circle test token | `/opt/x402/FiatTokenV2_2.json` | circlefin/stablecoin-evm v2.2.0 (`405efc100c016ed1a437063b6274b4e24ea7b8b1`), solc 0.6.12, OZ 3.4.2; see `dependencies/x402-20261017/README.md` |
| Runtime smoke test | `/opt/x402/verify_runtime.py` | starts its own private Anvil on 127.0.0.1, no host ports |
| Reproducible V3 FROST signer | `/usr/local/bin/threshold-demo` | rebuilt during the image build from `tools/threshold_demo` source + `Cargo.lock` (stage `rust:1.99.1-slim-bookworm`, `cargo build --locked --release`); replaces the base image's stale V2-era binary |

The old threshold image (`agent-guard-threshold-gateway-runner:20261017`,
`sha256:997ccb375167...`) is only used as build base and is not modified.

## Build

The base image is a cached single-platform amd64 image. On arm64 Docker Desktop
an explicit `--platform` on *build* makes BuildKit try to resolve the base from
the registry and fail, and `docker run/create --platform` is likewise
unnecessary; the image itself is amd64 and Docker selects it. Build with
absolute in-repo paths:

```sh
docker build \
  -f "/ABS/PATH/agent-guard-handoff/deploy/x402-runner/Dockerfile" \
  --build-arg HTTP_PROXY=http://host.docker.internal:7897 \
  --build-arg HTTPS_PROXY=http://host.docker.internal:7897 \
  -t agent-guard-x402-runner:20261017 \
  "/ABS/PATH/agent-guard-handoff"
```

The proxy arguments are build-time only (offline hash-pinned `pip install
--require-hashes`); nothing is persisted. Expected build warnings:

- `FromPlatformFlagConstDisallowed` (the stages pin a constant `--platform`;
  required so the amd64 base is used as-is) and `InvalidBaseImagePlatform`
  (base is amd64, host is arm64) - both harmless.
- Pulling `agent-guard-threshold-gateway-runner:20261017` is not a rebuild;
  that image stays byte-identical.

The base image ships a stale V2-era `threshold-demo`; stage (1) rebuilds the
current V3 signer from this repository's pinned Rust source and `Cargo.lock`
and stage (3) copies it over `/usr/local/bin/threshold-demo`. Verify the
executable without running a full demo:

```sh
docker run --rm agent-guard-x402-runner:20261017 \
  sh -c '/usr/local/bin/threshold-demo 2>&1 | head -1'
# -> threshold demo rejected: missing argument
```

Verify architecture afterwards:

```sh
docker image inspect agent-guard-x402-runner:20261017 \
  --format '{{.Architecture}} {{.Os}} {{.Id}}'
```

## Run

No host ports are needed and none are published. On arm64 hosts omit
`--platform` (a platform-mismatch warning is expected under emulation):

```sh
# Full private-chain smoke: SDK imports, library link, deploy, initialize
# V1/V2/V2.1/V2.2, mint, SDK-signed EIP-3009 settle. Prints {"status": "PASS"}.
docker run --rm agent-guard-x402-runner:20261017 \
  /opt/venv/bin/python /opt/x402/verify_runtime.py

# Interactive shell with the repository mounted (business tests):
docker run --rm -it -v "/ABS/PATH/agent-guard-handoff":/work -w /work \
  agent-guard-x402-runner:20261017 bash
```

Environment: `X402_FIATTOKEN_ARTIFACT` (default `/opt/x402/FiatTokenV2_2.json`),
`AGENT_GUARD_X402_ANVIL=/usr/local/bin/anvil`, `X402_SMOKE_PORT` (default 18545,
loopback only).

## Compiled artifact interface

`FiatTokenV2_2.json` top-level keys (the same file is in the image at
`/opt/x402/FiatTokenV2_2.json` and in the repository under
`dependencies/x402-20261017/`):

- `abi`: 72-entry ABI array for `w3.eth.contract(abi=...)`.
- `bytecode` / `bytecodeHex`: creation bytecode, 0x-prefixed / raw hex. It is
  **unlinked**: it contains Solidity library placeholders.
- `deployedBytecode` / `deployedBytecodeHex`: runtime bytecode.
- `linkReferences`: `{"bytecode": {...}, "deployedBytecode": {...}}`, source ->
  library -> `[{start, length}]` byte offsets of the 20-byte placeholders.
- `libraries`: `{"contracts/util/SignatureChecker.sol:SignatureChecker":
  {abi, bytecode, deployedBytecode}}` - deploy these before the token.
- `compilerVersion`, `compiler` (solc 0.6.12 sha256), `settings` (optimizer
  enabled, runs 10000000, evmVersion istanbul), `metadata`, `sourceKeccak256`,
  `provenance`, `license`, `notes`.

### Deploy procedure (verified by `verify_runtime.py`)

Circle's FiatTokenV2_2 calls an external `SignatureChecker` library function, so
the library must be deployed and linked first (this mirrors Circle's official
`migrations/versioned/7_deploy_v2_2.js`):

```python
artifact = json.load(open("/opt/x402/FiatTokenV2_2.json"))
lib = artifact["libraries"]["contracts/util/SignatureChecker.sol:SignatureChecker"]
lib_addr = deploy(w3.eth.contract(abi=lib["abi"], bytecode=lib["bytecode"]))  # from any account

def link(hex_no_0x, refs):
    out = hex_no_0x
    for source, libs in refs.items():
        for name, positions in libs.items():
            addr = lib_addr[2:].lower()
            for pos in positions:
                s = pos["start"] * 2
                out = out[:s] + addr + out[s + 40:]
    return out

creation = link(artifact["bytecodeHex"], artifact["linkReferences"]["bytecode"])
token = w3.eth.contract(abi=artifact["abi"], bytecode="0x" + creation)
impl = deploy(token)  # then initialize; see below
```

Check `w3.eth.get_code(impl).hex() == "0x" + link(deployedBytecodeHex, linkReferences["deployedBytecode"])`
to prove the runtime matches the artifact (done in the smoke test).

### Initialize order (exact signatures)

Direct implementation deployment can be initialized for local tests (no proxy):

1. `initialize(string tokenName, string tokenSymbol, string tokenCurrency,
   uint8 tokenDecimals, address newMasterMinter, address newPauser,
   address newBlacklister, address newOwner)`
2. `initializeV2(string newName)` - requires step 1; sets name and EIP-712
   domain version "2".
3. `initializeV2_1(address lostAndFound)` - requires step 2; blacklists the
   implementation address itself.
4. `initializeV2_2(address[] accountsToBlacklist, string newSymbol)` - requires
   step 3; pass `[]` for a fresh token.

Then (local test only) `updateMasterMinter(owner)`,
`configureMinter(minter, 2**256-1)`, `mint(to, amount)`. Production uses the
versioned proxy flow and initializes the implementation with throwaway values.

## SDK construction (x402 2.25.0)

```python
from x402 import x402ClientSync, x402ResourceServerSync, x402FacilitatorSync
from x402.mechanisms.evm.exact import (
    ExactEvmClientScheme,       # signer=LocalAccount (auto-wrapped) for payer
    ExactEvmServerScheme,       # server-side price parsing / requirements
    ExactEvmFacilitatorScheme,  # signer=FacilitatorEvmSigner, verify/settle
)

client = x402ClientSync()
client.register("eip155:*", ExactEvmClientScheme(signer=payer_account))
# client.create_payment_payload(payment_required) -> full PaymentPayload

# Scheme-level EIP-3009 signing used by the smoke test:
from x402.schemas import PaymentRequirements
requirements = PaymentRequirements(
    scheme="exact",
    network=f"eip155:{chain_id}",
    asset=token_address, amount=str(amount), pay_to=payee,
    max_timeout_seconds=3600,
    extra={"name": "USD Coin", "version": "2"},  # EIP-712 domain
)
payload = ExactEvmClientScheme(signer=payer_account).create_payment_payload(requirements)
# payload == {"authorization": {from,to,value,validAfter,validBefore,nonce}, "signature": "0x.."}
# then settle with token.transferWithAuthorization(...) v/r/s split.
```

`x402FacilitatorSync().register([...networks], ExactEvmFacilitatorScheme(signer=<FacilitatorEvmSigner>))`
for verify/settle; `x402ResourceServerSync(facilitator_clients)` for HTTP
middleware. Business-side policy (trusted intent parsing, reservation, state
machine) stays in `src/`; this image only provides the pinned runtime.

## Limitations

- Local test chain only. No production network, real funds, user keys or
  deployment claim; anvil dev accounts and a fresh in-memory payer are used.
- No gateway/backend tests run here; those are the main worker's scope.
- amd64 image on arm64 Docker Desktop runs under emulation (slower but
  functional; the full smoke test passed).
- `eth-tester`/`py-evm` are intentionally absent (Anvil is the local EVM).
