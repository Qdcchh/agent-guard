#!/usr/bin/env python3
"""Render the FiatTokenV2_2 deployment artifact from solc output.

Usage: render_fiattoken_artifact.py <combined.json> <standard.json> <out.json>

The artifact carries the ABI plus creation/runtime bytecode for local test
chains, together with the compiler pin, Circle/OpenZeppelin provenance, the
per-source keccak256 hashes taken from the solc metadata, and the Solidity
library link references (SignatureChecker) with the library artifact needed to
deploy the token.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEPS = os.path.dirname(HERE)
MANIFEST = os.path.join(DEPS, "SOURCES.lock.json")

CONTRACT_KEY = "contracts/v2/FiatTokenV2_2.sol:FiatTokenV2_2"
OUTPUT_UNIT = "contracts/v2/FiatTokenV2_2.sol"
SOLC_LONG_VERSION = "0.6.12+commit.27d51765.Linux.g++"
SOLC_SHA256 = "f6cb519b01dabc61cab4c184a3db11aa591d18151e362fcae850e42cffdfb09a"
SOLC_ORIGIN = (
    "https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.6.12+commit.27d51765"
)


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    combined_path, standard_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(combined_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    with open(standard_path, "r", encoding="utf-8") as handle:
        standard = json.load(handle)

    contracts = data["contracts"]
    if CONTRACT_KEY not in contracts:
        print(f"missing contract {CONTRACT_KEY} in {combined_path}", file=sys.stderr)
        return 1
    compiled = contracts[CONTRACT_KEY]
    abi = json.loads(compiled["abi"])
    bytecode = compiled["bin"]
    runtime = compiled["bin-runtime"]
    metadata = json.loads(compiled["metadata"])

    standard_contract = standard["contracts"][OUTPUT_UNIT]["FiatTokenV2_2"]
    link_creation = standard_contract["evm"]["bytecode"]["linkReferences"]
    link_runtime = standard_contract["evm"]["deployedBytecode"]["linkReferences"]

    libraries = {}
    for source, refs in {**link_creation, **link_runtime}.items():
        for library_name in refs:
            library = standard["contracts"][source][library_name]
            libraries[f"{source}:{library_name}"] = {
                "abi": library["abi"],
                "bytecode": "0x" + library["evm"]["bytecode"]["object"],
                "deployedBytecode": "0x" + library["evm"]["deployedBytecode"]["object"],
            }

    with open(MANIFEST, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    artifact = {
        "artifact": "agent-guard-x402/fiattoken-v2_2/compiled",
        "artifactSchema": 1,
        "contractName": "FiatTokenV2_2",
        "compilerVersion": data["version"],
        "compiler": {
            "name": "solc",
            "version": "0.6.12",
            "longVersion": SOLC_LONG_VERSION,
            "sha256": SOLC_SHA256,
            "origin": SOLC_ORIGIN,
        },
        "settings": metadata["settings"],
        "abi": abi,
        "bytecode": "0x" + bytecode,
        "bytecodeHex": bytecode,
        "deployedBytecode": "0x" + runtime,
        "deployedBytecodeHex": runtime,
        "linkReferences": {
            "bytecode": link_creation,
            "deployedBytecode": link_runtime,
        },
        "libraries": libraries,
        "metadata": compiled["metadata"],
        "sourceKeccak256": {
            name: info["keccak256"] for name, info in sorted(metadata["sources"].items())
        },
        "provenance": {
            "circle": {
                "repo": manifest["circle"]["repo"],
                "tag": manifest["circle"]["tag"],
                "commit": manifest["circle"]["commit"],
                "license": manifest["circle"]["license"],
            },
            "openzeppelin": {
                "package": manifest["openzeppelin"]["package"],
                "version": manifest["openzeppelin"]["version"],
                "npmTarballSha256": manifest["openzeppelin"]["npmTarballSha256"],
                "license": manifest["openzeppelin"]["license"],
            },
            "settingsSource": (
                "circlefin/stablecoin-evm truffle-config.js at the pinned commit: "
                "solc 0.6.12, optimizer enabled with runs=10000000; evmVersion "
                "istanbul is the solc 0.6.12 default"
            ),
            "recipe": "dependencies/x402-20261017/tools/compile_fiattoken_v2_2.sh",
            "sourceManifest": "dependencies/x402-20261017/SOURCES.lock.json",
        },
        "license": (
            "Compiled artifact of Apache-2.0 sources (Circle stablecoin-evm) and "
            "MIT sources (OpenZeppelin Contracts 3.4.2); see the LICENSE files "
            "under dependencies/x402-20261017/"
        ),
        "notes": [
            "Local test-chain artifact only; NOT Circle production deployment bytecode.",
            "'bytecode' contains Solidity link placeholders for the SignatureChecker "
            "library. Deploy the artifact in 'libraries' first, replace the 20-byte "
            "placeholders listed in 'linkReferences' with the deployed library address, "
            "then deploy the token (see deploy/x402-runner/verify_runtime.py).",
            "Deploy the implementation directly and call initialize/initializeV2/"
            "initializeV2_1/initializeV2_2 in order (see deploy/x402-runner/README.md).",
            "'bytecode'/'deployedBytecode' are 0x-prefixed; 'bytecodeHex'/"
            "'deployedBytecodeHex' are the raw solc hex without prefix.",
        ],
    }

    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(
        f"wrote {out_path}: abi={len(abi)} entries, "
        f"creation={len(bytecode) // 2} bytes, runtime={len(runtime) // 2} bytes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
