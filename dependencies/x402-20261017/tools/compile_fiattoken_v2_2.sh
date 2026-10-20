#!/usr/bin/env bash
# Reproducible compile of the Circle FiatTokenV2_2 test contract.
#
# Pins:
#   - solc 0.6.12+commit.27d51765, sha256 f6cb519b01dabc61cab4c184a3db11aa
#     591d18151e362fcae850e42cffdfb09a (official linux-amd64 static binary)
#   - circlefin/stablecoin-evm tag v2.2.0, commit
#     405efc100c016ed1a437063b6274b4e24ea7b8b1 (Apache-2.0)
#   - @openzeppelin/contracts 3.4.2 npm package (MIT)
# Settings mirror Circle's truffle-config.js at the pinned commit:
# optimizer enabled, runs=10000000; evmVersion istanbul is the solc default.
#
# The solc binary is linux/amd64, so on macOS arm64 run this inside an amd64
# Linux container with the repository mounted (the project runner image):
#
#   docker run --rm \
#     -v "/absolute/path/to/agent-guard-handoff":/work -w /work \
#     agent-guard-threshold-gateway-runner:20261017 \
#     bash dependencies/x402-20261017/tools/compile_fiattoken_v2_2.sh
#
# Outputs (defaults):
#   dependencies/x402-20261017/FiatTokenV2_2.json
#   dependencies/x402-20261017/.build/FiatTokenV2_2.solc-combined.json
#   dependencies/x402-20261017/.build/FiatTokenV2_2.standard-output.json
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS="$(cd "$HERE/.." && pwd)"
SOLC="$DEPS/vendor/solc-0.6.12"
BUILD="$DEPS/.build"
FARM="$BUILD/farm"
COMBINED="$BUILD/FiatTokenV2_2.solc-combined.json"
STANDARD_INPUT="$BUILD/FiatTokenV2_2.standard-input.json"
STANDARD_OUTPUT="$BUILD/FiatTokenV2_2.standard-output.json"
OUT="${1:-$DEPS/FiatTokenV2_2.json}"

case "$FARM" in
  */dependencies/x402-20261017/.build/farm) ;;
  *) echo "refusing to clean unexpected build dir: $FARM" >&2; exit 1 ;;
esac

if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x /opt/venv/bin/python ]; then
  PY=/opt/venv/bin/python
else
  PY=python3
fi

EXPECTED_SOLC_SHA256=f6cb519b01dabc61cab4c184a3db11aa591d18151e362fcae850e42cffdfb09a
ACTUAL_SOLC_SHA256="$("$PY" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$SOLC")"
if [ "$ACTUAL_SOLC_SHA256" != "$EXPECTED_SOLC_SHA256" ]; then
  echo "solc 0.6.12 hash mismatch: $ACTUAL_SOLC_SHA256" >&2
  exit 1
fi

"$PY" "$HERE/verify_sources.py"

rm -rf "$FARM"
mkdir -p "$FARM"
ln -s ../../stablecoin-evm/contracts "$FARM/contracts"
ln -s ../../openzeppelin-contracts-3.4.2 "$FARM/@openzeppelin"

(
  cd "$FARM"
  "$SOLC" \
    --optimize --optimize-runs 10000000 \
    --combined-json abi,bin,bin-runtime,metadata,hashes \
    --allow-paths "$DEPS" \
    contracts/v2/FiatTokenV2_2.sol > "$COMBINED"
)

# Second pass with standard JSON to capture library link references.
cat > "$STANDARD_INPUT" <<'JSON'
{
  "language": "Solidity",
  "sources": {
    "contracts/v2/FiatTokenV2_2.sol": {"urls": ["contracts/v2/FiatTokenV2_2.sol"]}
  },
  "settings": {
    "optimizer": {"enabled": true, "runs": 10000000},
    "outputSelection": {
      "*": {
        "*": [
          "abi",
          "evm.bytecode.object",
          "evm.bytecode.linkReferences",
          "evm.deployedBytecode.object",
          "evm.deployedBytecode.linkReferences",
          "metadata"
        ]
      }
    }
  }
}
JSON
(
  cd "$FARM"
  "$SOLC" --standard-json --base-path "$FARM" --allow-paths "$DEPS" \
    < "$STANDARD_INPUT" > "$STANDARD_OUTPUT"
)

"$PY" "$HERE/render_fiattoken_artifact.py" "$COMBINED" "$STANDARD_OUTPUT" "$OUT"

echo "combined output: $COMBINED"
echo "standard output: $STANDARD_OUTPUT"
"$PY" -c 'import hashlib,sys;print("combined sha256:",hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$COMBINED"
