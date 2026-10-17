#!/usr/bin/env python3
"""Private-chain runtime smoke test for agent-guard-x402-runner:20261017.

Runs entirely inside the container: starts a private Anvil process bound to
127.0.0.1 (no host ports are published), deploys the compiled Circle
FiatTokenV2_2 artifact, initializes V1 -> V2 -> V2.1 -> V2.2, configures a
minter, mints, and settles one real EIP-3009 transferWithAuthorization whose
signature is produced by the pinned x402 SDK ExactEvmScheme. Also checks the
main SDK imports/constructors.

No private keys are stored: the payer is a fresh in-memory eth_account account
created per run and funded from the standard Anvil dev account.

Exit code 0 only if every check passes. Summary JSON is printed to stdout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

ARTIFACT_PATH = os.environ.get("X402_FIATTOKEN_ARTIFACT", "/opt/x402/FiatTokenV2_2.json")
PORT = int(os.environ.get("X402_SMOKE_PORT", "18545"))
RPC_URL = f"http://127.0.0.1:{PORT}"

CHECKS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    CHECKS.append(name)
    if not condition:
        raise AssertionError(f"{name} failed {detail}".strip())
    print(f"ok: {name} {detail}".rstrip())


def main() -> int:
    from eth_account import Account
    from web3 import Web3

    from x402 import x402ClientSync, x402Facilitator, x402ResourceServer
    from x402.mechanisms.evm.exact import (
        ExactEvmClientScheme,
        ExactEvmFacilitatorScheme,
        ExactEvmServerScheme,
    )
    from x402.schemas import PaymentRequirements

    # ---- SDK surface (construction only) -------------------------------
    client = x402ClientSync()
    server = x402ResourceServer()
    facilitator = x402Facilitator()
    ExactEvmServerScheme()
    check("sdk_construction", client is not None and server is not None and facilitator is not None)
    check("sdk_facilitator_scheme_symbol", ExactEvmFacilitatorScheme is not None)

    # ---- private Anvil --------------------------------------------------
    anvil = subprocess.Popen(
        ["anvil", "--host", "127.0.0.1", "--port", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        deadline = time.time() + 30
        while time.time() < deadline and not w3.is_connected():
            time.sleep(0.2)
        check("anvil_rpc_connected", w3.is_connected(), RPC_URL)
        chain_id = w3.eth.chain_id
        check("anvil_chain_id", chain_id == 31337, str(chain_id))

        accounts = w3.eth.accounts
        owner, merchant = accounts[0], accounts[2]

        artifact = json.load(open(ARTIFACT_PATH, "r", encoding="utf-8"))
        abi = artifact["abi"]
        check("artifact_contract", artifact["contractName"] == "FiatTokenV2_2")

        # ---- deploy + link the Solidity library --------------------------
        library_addresses = {}
        for fqn, library in artifact["libraries"].items():
            library_factory = w3.eth.contract(
                abi=library["abi"], bytecode=library["bytecode"]
            )
            library_hash = library_factory.constructor().transact({"from": owner})
            library_receipt = w3.eth.wait_for_transaction_receipt(library_hash, timeout=120)
            library_addresses[fqn] = library_receipt.contractAddress
            check("library_deployed", library_receipt.status == 1, fqn)

        def link(hex_bytecode: str, references: dict) -> str:
            linked = hex_bytecode
            for source, refs in references.items():
                for library_name, positions in refs.items():
                    address = library_addresses[f"{source}:{library_name}"][2:].lower()
                    for position in positions:
                        start = position["start"] * 2
                        linked = linked[:start] + address + linked[start + 40 :]
            return linked

        creation = link(artifact["bytecodeHex"], artifact["linkReferences"]["bytecode"])
        check("bytecode_linked", "__$" not in creation)

        # ---- deploy + initialize ---------------------------------------
        factory = w3.eth.contract(abi=abi, bytecode="0x" + creation)
        deploy_hash = factory.constructor().transact({"from": owner})
        deploy_receipt = w3.eth.wait_for_transaction_receipt(deploy_hash, timeout=120)
        check("deploy_status", deploy_receipt.status == 1)
        token = w3.eth.contract(address=deploy_receipt.contractAddress, abi=abi)

        expected_runtime = link(
            artifact["deployedBytecodeHex"],
            artifact["linkReferences"]["deployedBytecode"],
        )
        on_chain_runtime = w3.eth.get_code(deploy_receipt.contractAddress).hex()
        check(
            "runtime_code_matches_artifact",
            on_chain_runtime.removeprefix("0x").lower() == expected_runtime.lower(),
        )

        tx = token.functions.initialize(
            "USD Coin", "USDC", "USD", 6, owner, owner, owner, owner
        ).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)

        tx = token.functions.initializeV2("USD Coin").transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)

        tx = token.functions.initializeV2_1(owner).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)

        tx = token.functions.initializeV2_2([], "USDC").transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)
        check("initialize_v1_v2_v2_1_v2_2", token.functions.symbol().call() == "USDC")

        # ---- minter + mint ---------------------------------------------
        tx = token.functions.updateMasterMinter(owner).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)
        tx = token.functions.configureMinter(owner, 2**256 - 1).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)
        tx = token.functions.mint(merchant, 1_000_000).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)
        check("mint", token.functions.balanceOf(merchant).call() == 1_000_000)

        # ---- SDK-signed EIP-3009 transfer ---------------------------------
        payer = Account.create()
        amount = 250_000
        fund = w3.eth.send_transaction(
            {"from": owner, "to": payer.address, "value": Web3.to_wei(1, "ether")}
        )
        w3.eth.wait_for_transaction_receipt(fund, timeout=120)
        tx = token.functions.mint(payer.address, amount).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx, timeout=120)

        requirements = PaymentRequirements(
            scheme="exact",
            network=f"eip155:{chain_id}",
            asset=Web3.to_checksum_address(token.address),
            amount=str(amount),
            pay_to=Web3.to_checksum_address(merchant),
            max_timeout_seconds=3600,
            extra={"name": "USD Coin", "version": "2"},
        )
        scheme = ExactEvmClientScheme(signer=payer)
        payload = scheme.create_payment_payload(requirements)
        auth = payload["authorization"]
        signature = bytes.fromhex(payload["signature"].removeprefix("0x"))
        check("sdk_signed_payload", len(signature) == 65 and auth["to"].lower() == merchant.lower())

        signature_r = int.from_bytes(signature[0:32], "big")
        signature_s = int.from_bytes(signature[32:64], "big")
        signature_v = signature[64]
        if signature_v < 27:
            signature_v += 27
        tx = token.functions.transferWithAuthorization(
            auth["from"],
            auth["to"],
            int(auth["value"]),
            int(auth["validAfter"]),
            int(auth["validBefore"]),
            bytes.fromhex(auth["nonce"].removeprefix("0x")),
            signature_v,
            signature_r.to_bytes(32, "big"),
            signature_s.to_bytes(32, "big"),
        ).transact({"from": owner})
        receipt = w3.eth.wait_for_transaction_receipt(tx, timeout=120)
        check("eip3009_settle_status", receipt.status == 1)
        check("eip3009_authorization_consumed",
              token.functions.authorizationState(auth["from"], auth["nonce"]).call() is True)
        check("eip3009_balances",
              token.functions.balanceOf(auth["from"]).call() == 0
              and token.functions.balanceOf(merchant).call() == 1_000_000 + amount)

        print(json.dumps({"status": "PASS", "checks": CHECKS, "chainId": chain_id}))
        return 0
    finally:
        anvil.terminate()
        try:
            anvil.wait(timeout=10)
        except subprocess.TimeoutExpired:
            anvil.kill()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - report and fail
        print(json.dumps({"status": "FAIL", "checks": CHECKS, "error": str(error)}))
        sys.exit(1)
