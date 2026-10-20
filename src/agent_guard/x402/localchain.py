"""Long-lived local EVM service and real Circle EIP-3009 token bootstrap.

One Anvil process (pinned v1.8.5, chain id 31337) is owned by this module and
outlives gateway worker restarts: an in-process test chain recreated on restart
would lose receipts and balances, so the chain is a real child process with its
own lifecycle. The deployed token is the compiled Circle
``FiatTokenV2_2`` artifact produced by the pinned runner image; its
``transferWithAuthorization`` enforces the EIP-712 signature and consumes the
nonce on chain, so settlement here is real settlement.

Only synthetic wallets are funded; there are no real assets and no public
network connection.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from eth_account import Account
from web3 import Web3

from agent_guard.x402.contracts import X402Error

DEFAULT_ARTIFACT_PATHS = (
    Path("/opt/x402/FiatTokenV2_2.json"),
    Path("/work/dependencies/x402-20261017/FiatTokenV2_2.json"),
    Path(__file__).resolve().parents[3] / "dependencies/x402-20261017/FiatTokenV2_2.json",
)
ANVIL_BINARIES = (
    os.environ.get("AGENT_GUARD_X402_ANVIL_BIN") or "",
    "/usr/local/bin/anvil",
)
DEFAULT_CHAIN_ID = 31337
START_TIMEOUT = 60.0
STOP_TIMEOUT = 10.0
E18 = 10**18

_REQUIRED_ABI = {
    "initialize",
    "initializeV2",
    "initializeV2_1",
    "initializeV2_2",
    "updateMasterMinter",
    "configureMinter",
    "mint",
    "balanceOf",
    "authorizationState",
    "transferWithAuthorization",
}


@dataclass(frozen=True)
class LibraryArtifact:
    """One linked Solidity library of the compiled token."""

    fqn: str
    abi: list
    bytecode: str


@dataclass(frozen=True)
class TokenArtifact:
    """Compiled FiatTokenV2_2 artifact with its link references and libraries."""

    abi: list
    bytecode: str
    runtime_bytecode: str | None = None
    link_references: dict | None = None
    libraries: tuple[LibraryArtifact, ...] = ()

    def __post_init__(self):
        if not isinstance(self.abi, list) or not self.bytecode.startswith("0x"):
            raise X402Error("invalid compiled token artifact", code="TOKEN_ARTIFACT_INVALID")
        names = {entry.get("name") for entry in self.abi if isinstance(entry, dict)}
        missing = _REQUIRED_ABI - names
        if missing:
            raise X402Error(
                "compiled token artifact misses required ABI entries",
                code="TOKEN_ARTIFACT_INVALID",
            )


def _hex_code(value: object, *, unlinked: bool = False) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[2:] if value.startswith("0x") else value
    allowed = "0123456789abcdefABCDEF_$" if unlinked else "0123456789abcdefABCDEF"
    if len(text) < 4 or any(c not in allowed for c in text):
        return None
    return "0x" + text.lower()


def _decode_artifact(document: object) -> TokenArtifact | None:
    """Decode the pinned runtime artifact (``bytecodeHex`` + library linkage)."""
    if not isinstance(document, dict):
        return None
    contract_name = document.get("contractName")
    if contract_name not in (None, "FiatTokenV2_2"):
        return None
    abi = document.get("abi")
    if not isinstance(abi, list):
        return None
    bytecode = _hex_code(document.get("bytecodeHex"), unlinked=True) or _hex_code(
        document.get("bytecode"), unlinked=True
    )
    if bytecode is None:
        bytecode = _hex_code(document.get("bin")) or _hex_code(document.get("data"))
    if bytecode is None:
        return None
    runtime = _hex_code(document.get("deployedBytecodeHex"), unlinked=True) or _hex_code(
        document.get("deployedBytecode"), unlinked=True
    )
    link_references = document.get("linkReferences")
    if not isinstance(link_references, dict):
        link_references = {}
    libraries = []
    raw_libraries = document.get("libraries")
    if isinstance(raw_libraries, dict):
        for fqn, entry in raw_libraries.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("abi"), list):
                return None
            library_code = _hex_code(entry.get("bytecode")) or _hex_code(entry.get("bytecodeHex"))
            if library_code is None:
                return None
            libraries.append(LibraryArtifact(fqn=fqn, abi=entry["abi"], bytecode=library_code))
    return TokenArtifact(
        abi=abi,
        bytecode=bytecode,
        runtime_bytecode=runtime,
        link_references=link_references,
        libraries=tuple(libraries),
    )


def link_bytecode(bytecode: str, references: dict | None, addresses: dict[str, str]) -> str:
    """Place deployed library addresses into the compiled creation/runtime code."""
    prefix = "0x" if bytecode.startswith("0x") else ""
    linked = bytecode[2:] if prefix else bytecode
    for source, refs in (references or {}).items():
        for library_name, positions in refs.items():
            address = addresses.get(f"{source}:{library_name}")
            if address is None:
                raise X402Error(
                    "compiled token library was not deployed", code="TOKEN_ARTIFACT_INVALID"
                )
            hex_address = address.lower().removeprefix("0x")
            if len(hex_address) != 40:
                raise X402Error("invalid library address", code="TOKEN_ARTIFACT_INVALID")
            for position in positions:
                start = int(position["start"]) * 2
                linked = linked[:start] + hex_address + linked[start + 40 :]
    if "__$" in linked or "$__" in linked:
        raise X402Error("unlinked library placeholder remains", code="TOKEN_ARTIFACT_INVALID")
    return prefix + linked


def load_token_artifact(path: Path | str | None = None) -> TokenArtifact:
    """Load the compiled Circle FiatTokenV2_2 ABI/bytecode from the pinned artifact."""
    candidates = [Path(path)] if path is not None else [p for p in DEFAULT_ARTIFACT_PATHS]
    for candidate in candidates:
        try:
            document = json.loads(Path(candidate).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        decoded = _decode_artifact(document)
        if decoded is not None:
            return decoded
    raise X402Error("compiled token artifact unavailable", code="TOKEN_ARTIFACT_MISSING")


def find_anvil() -> str:
    for candidate in ANVIL_BINARIES:
        if not candidate:
            continue
        if os.sep in candidate:
            if os.access(candidate, os.X_OK):
                return candidate
            continue
        found = shutil.which(candidate)
        if found:
            return found
    raise X402Error("anvil binary not found", code="ANVIL_UNAVAILABLE")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AnvilService:
    """One owned Anvil child process; survives worker process restarts."""

    def __init__(self, *, chain_id: int = DEFAULT_CHAIN_ID, binary: str | None = None):
        self._chain_id = chain_id
        self._binary = binary
        self._process: subprocess.Popen | None = None
        self._port: int | None = None

    @property
    def rpc_url(self) -> str:
        if self._port is None:
            raise X402Error("anvil service is not running", code="ANVIL_UNAVAILABLE")
        return f"http://127.0.0.1:{self._port}"

    @property
    def chain_id(self) -> int:
        return self._chain_id

    def start(self) -> str:
        if self._process is not None:
            return self.rpc_url
        binary = self._binary or find_anvil()
        self._port = _free_port()
        command = [
            binary,
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port),
            "--chain-id",
            str(self._chain_id),
            "--silent",
            "--no-request-size-limit",
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise X402Error("anvil could not be started", code="ANVIL_UNAVAILABLE") from exc
        if not self._wait_ready():
            self.stop()
            raise X402Error("anvil did not become ready", code="ANVIL_UNAVAILABLE")
        return self.rpc_url

    def _wait_ready(self, timeout: float = START_TIMEOUT) -> bool:
        deadline = time.monotonic() + timeout
        web3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 2}))
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                return False
            try:
                if int(web3.eth.chain_id) == self._chain_id:
                    return True
            except Exception:  # noqa: BLE001 - not ready yet
                time.sleep(0.1)
        return False

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        process.terminate()
        try:
            process.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class ChainAdmin:
    """Synthetic-only chain administration: fund, deploy, configure, mint."""

    def __init__(self, rpc_url: str, *, chain_id: int = DEFAULT_CHAIN_ID, timeout: float = 15.0):
        self._w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        self._chain_id = chain_id

    def wait_ready(self, timeout: float = START_TIMEOUT) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if int(self._w3.eth.chain_id) == self._chain_id:
                    return True
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        return False

    def set_balance(self, address: str, wei: int) -> None:
        self._w3.provider.make_request(
            "anvil_setBalance", [Web3.to_checksum_address(address), hex(wei)]
        )

    def _send(self, account, transaction: dict) -> dict:
        transaction.pop("from", None)
        if transaction.get("to") in ("", b"", None):
            transaction.pop("to", None)
        transaction.setdefault("chainId", self._chain_id)
        if "maxFeePerGas" not in transaction and "gasPrice" not in transaction:
            transaction["gasPrice"] = int(self._w3.eth.gas_price)
        transaction["nonce"] = self._w3.eth.get_transaction_count(account.address, "pending")
        try:
            signed = account.sign_transaction(transaction)
        except (ValueError, TypeError) as exc:
            raise X402Error(
                "synthetic transaction could not be signed", code="CHAIN_TX_FAILED"
            ) from exc
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        if receipt.get("status") != 1:
            raise X402Error("synthetic transaction reverted", code="CHAIN_TX_FAILED")
        return receipt

    def deploy_contract(self, *, account, abi: list, bytecode: str, gas: int) -> str:
        contract = self._w3.eth.contract(abi=abi, bytecode=bytecode)
        transaction = contract.constructor().build_transaction(
            {"from": account.address, "gas": gas}
        )
        receipt = self._send(account, transaction)
        address = receipt["contractAddress"]
        if not address:
            raise X402Error("deployment produced no address", code="CHAIN_TX_FAILED")
        return address

    def call(self, *, account, address: str, abi: list, function: str, args: tuple, gas: int):
        contract = self._w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
        transaction = getattr(contract.functions, function)(*args).build_transaction(
            {"from": account.address, "gas": gas}
        )
        return self._send(account, transaction)

    def token_balance(self, *, address: str, token: str, abi: list) -> int:
        contract = self._w3.eth.contract(address=Web3.to_checksum_address(token), abi=abi)
        return int(contract.functions.balanceOf(Web3.to_checksum_address(address)).call())

    def code_at(self, address: str) -> str:
        return self._w3.eth.get_code(Web3.to_checksum_address(address)).hex()


def bootstrap_token(
    *,
    rpc_url: str,
    admin_key: str,
    payer_address: str,
    token_name: str,
    token_symbol: str,
    decimals: int,
    mint_amount: int,
    chain_id: int = DEFAULT_CHAIN_ID,
    artifact: TokenArtifact | None = None,
) -> str:
    """Deploy the Circle token, initialize it and mint synthetic test funds.

    Returns the deployed token address. Every step is a real chain transaction
    signed by the synthetic administrator; nothing is simulated in memory.
    """
    token = artifact if artifact is not None else load_token_artifact()
    admin = ChainAdmin(rpc_url, chain_id=chain_id)
    if not admin.wait_ready():
        raise X402Error("chain is not reachable", code="CHAIN_UNAVAILABLE")
    account = Account.from_key(admin_key)
    admin.set_balance(account.address, 100 * E18)
    admin.set_balance(payer_address, 10 * E18)

    library_addresses: dict[str, str] = {}
    for library in token.libraries:
        library_addresses[library.fqn] = admin.deploy_contract(
            account=account, abi=library.abi, bytecode=library.bytecode, gas=3_000_000
        )
    creation_code = link_bytecode(
        token.bytecode, (token.link_references or {}).get("bytecode"), library_addresses
    )
    address = admin.deploy_contract(
        account=account, abi=token.abi, bytecode=creation_code, gas=10_000_000
    )
    if token.runtime_bytecode is not None:
        expected_runtime = link_bytecode(
            token.runtime_bytecode,
            (token.link_references or {}).get("deployedBytecode"),
            library_addresses,
        ).removeprefix("0x")
        if admin.code_at(address).lower() != expected_runtime.lower():
            raise X402Error(
                "deployed runtime code differs from the artifact", code="CHAIN_DEPLOY_FAILED"
            )

    # Circle FiatTokenV2_2 initialization order (verified against the pinned
    # runtime image): V1 -> V2 -> V2.1 -> V2.2, then master minter + minter.
    steps = (
        (
            "initialize",
            (
                token_name,
                token_symbol,
                "USD",
                decimals,
                account.address,
                account.address,
                account.address,
                account.address,
            ),
            1_000_000,
        ),
        ("initializeV2", (token_name,), 1_000_000),
        ("initializeV2_1", (account.address,), 1_000_000),
        ("initializeV2_2", ([], token_symbol), 1_000_000),
        ("updateMasterMinter", (account.address,), 200_000),
        ("configureMinter", (account.address, 2**256 - 1), 200_000),
        ("mint", (Web3.to_checksum_address(payer_address), mint_amount), 300_000),
    )
    for function, args, gas in steps:
        admin.call(
            account=account,
            address=address,
            abi=token.abi,
            function=function,
            args=args,
            gas=gas,
        )
    balance = admin.token_balance(address=payer_address, token=address, abi=token.abi)
    if balance != mint_amount:
        raise X402Error("synthetic mint did not land on chain", code="CHAIN_MINT_FAILED")
    return address
