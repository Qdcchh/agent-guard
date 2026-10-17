"""Real local-EVM reconciliation for one persisted x402 authorization.

A transaction hash, a current balance or a consumed nonce alone never proves
*this* exact transfer. Every confirmation here binds the original payer, the
persisted nonce, the recipient, the amount and the token contract through the
token's own ``AuthorizationUsed`` and ERC-20 ``Transfer`` events read from the
real chain, plus a successful transaction receipt. A candidate transaction
hash (for example one returned by a settlement response) is only a lookup
hint: it must itself carry the nonce-bound ``AuthorizationUsed`` event of the
configured token, and a failed or unavailable nonce-bound lookup never settles.
"""

from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3

from agent_guard.x402.contracts import LOWER_ADDRESS_PATTERN, NONCE_PATTERN, X402Error


def _topic_hash(text: str) -> str:
    digest = Web3.keccak(text=text).hex()
    if not digest.startswith("0x"):
        digest = "0x" + digest
    return digest.lower()


def _hex_data(value: object) -> str:
    """Lower-case 0x-hex for bytes, hex strings and web3 HexBytes alike."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "0x" + bytes(value).hex()
    text = str(value)
    if text[:2].lower() == "0x":
        text = text[2:]
    return "0x" + text.lower()


def _address_topic(address: str) -> str:
    return "0x" + _hex_data(address)[2:].rjust(64, "0")


def _topic_address(topic: str) -> str:
    return "0x" + _hex_data(topic)[2:].rjust(64, "0")[-40:]


TRANSFER_TOPIC = _topic_hash("Transfer(address,address,uint256)")
AUTHORIZATION_USED_TOPIC = _topic_hash("AuthorizationUsed(address,bytes32)")


@dataclass(frozen=True)
class ChainConfirmation:
    """What the chain proves about one persisted authorization."""

    settled: bool
    tx_hash: str | None
    receipt_status: int | None
    authorization_used: bool
    transfer_matched: bool
    nonce_consumed: bool
    reason: str = ""


class ChainReader:
    """Bounded read-only JSON-RPC view of the fixed local chain."""

    def __init__(self, rpc_url: str, *, chain_id: int, token_address: str, timeout: float = 10.0):
        if LOWER_ADDRESS_PATTERN.fullmatch(token_address) is None:
            raise X402Error("invalid token address")
        if type(chain_id) is not int or isinstance(chain_id, bool) or chain_id < 1:
            raise X402Error("invalid chain id")
        self._w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        self._chain_id = chain_id
        self._token = Web3.to_checksum_address(token_address)

    @property
    def web3(self) -> Web3:
        return self._w3

    def chain_matches(self) -> bool:
        try:
            return int(self._w3.eth.chain_id) == self._chain_id
        except Exception:  # noqa: BLE001 - an unreachable chain proves nothing
            return False

    def latest_block_timestamp(self) -> int | None:
        """The configured chain's head timestamp; ``None`` proves nothing.

        A head is only meaningful when the endpoint is currently serving the
        configured chain id: an endpoint that answers with another chain must
        never justify a release, so the mismatch is treated exactly like an
        unreachable chain.
        """
        if not self.chain_matches():
            return None
        try:
            return int(self._w3.eth.get_block("latest")["timestamp"])
        except Exception:  # noqa: BLE001 - an unreachable chain proves nothing
            return None

    def _receipt(self, tx_hash: str):
        try:
            return self._w3.eth.get_transaction_receipt(tx_hash)
        except Exception:  # noqa: BLE001 - unknown is not failure
            return None

    def receipt_status(self, tx_hash: str) -> int | None:
        receipt = self._receipt(tx_hash)
        if receipt is None:
            return None
        status = receipt.get("status")
        return int(status) if status is not None else None

    def authorization_used_hashes(self, *, payer: str, nonce: str) -> tuple[bool, tuple[str, ...]]:
        """``(lookup available, distinct tx hashes)`` for this exact nonce use.

        The event must come from the configured token contract. ``False`` for
        the availability flag means the nonce-bound lookup itself failed; a
        caller must then stay uncertain and never settle from a candidate hash.
        """
        if LOWER_ADDRESS_PATTERN.fullmatch(payer) is None or NONCE_PATTERN.fullmatch(nonce) is None:
            return False, ()
        topic_payer = _address_topic(payer)
        try:
            entries = self._w3.eth.get_logs(
                {
                    "address": self._token,
                    "fromBlock": 0,
                    "toBlock": "latest",
                    "topics": [AUTHORIZATION_USED_TOPIC, topic_payer, nonce.lower()],
                }
            )
        except Exception:  # noqa: BLE001 - unreadable logs prove nothing
            return False, ()
        hashes: list[str] = []
        for entry in entries:
            tx_hash = _hex_data(entry["transactionHash"])
            if tx_hash not in hashes:
                hashes.append(tx_hash)
        return True, tuple(hashes)

    def _has_authorization_used(self, receipt, *, payer: str, nonce: str) -> bool:
        """The token's own ``AuthorizationUsed(payer, nonce)`` inside one receipt."""
        token = _hex_data(self._token)
        topic_payer = _address_topic(payer)
        topic_nonce = _hex_data(nonce)
        logs = receipt.get("logs") or ()
        for entry in logs:
            if _hex_data(entry.get("address", "")) != token:
                continue
            topics = [_hex_data(topic) for topic in (entry.get("topics") or ())]
            if len(topics) != 3 or topics[0] != AUTHORIZATION_USED_TOPIC:
                continue
            if topics[1] == topic_payer and topics[2] == topic_nonce:
                return True
        return False

    def _transfer_matched_receipt(self, receipt, *, payer: str, pay_to: str, amount: str) -> bool:
        """Exact ERC-20 ``Transfer`` from the configured token in one receipt."""
        try:
            wanted_amount = int(amount)
        except (TypeError, ValueError):
            return False
        token = _hex_data(self._token)
        wanted_from = _hex_data(payer)
        wanted_to = _hex_data(pay_to)
        logs = receipt.get("logs") or ()
        for entry in logs:
            if _hex_data(entry.get("address", "")) != token:
                continue
            topics = [_hex_data(topic) for topic in (entry.get("topics") or ())]
            if len(topics) != 3 or topics[0] != TRANSFER_TOPIC:
                continue
            if _topic_address(topics[1]) != wanted_from or _topic_address(topics[2]) != wanted_to:
                continue
            raw_value = _hex_data(entry.get("data", ""))[2:]
            value = int(raw_value, 16) if raw_value else 0
            if value == wanted_amount:
                return True
        return False

    def transfer_matched(self, *, tx_hash: str, payer: str, pay_to: str, amount: str) -> bool:
        """Exact Transfer log from the token in that transaction."""
        receipt = self._receipt(tx_hash)
        if receipt is None:
            return False
        return self._transfer_matched_receipt(receipt, payer=payer, pay_to=pay_to, amount=amount)

    def authorization_state(self, *, payer: str, nonce: str) -> bool | None:
        """The token's own nonce-consumption flag, read through ``eth_call``."""
        contract = self._w3.eth.contract(
            address=self._token,
            abi=[
                {
                    "type": "function",
                    "name": "authorizationState",
                    "stateMutability": "view",
                    "inputs": [
                        {"name": "authorizer", "type": "address"},
                        {"name": "nonce", "type": "bytes32"},
                    ],
                    "outputs": [{"name": "", "type": "bool"}],
                }
            ],
        )
        try:
            return bool(
                contract.functions.authorizationState(
                    Web3.to_checksum_address(payer), bytes.fromhex(nonce.removeprefix("0x"))
                ).call()
            )
        except Exception:  # noqa: BLE001 - unreadable is not "unused"
            return None

    def balance_of(self, address: str) -> int | None:
        contract = self._w3.eth.contract(
            address=self._token,
            abi=[
                {
                    "type": "function",
                    "name": "balanceOf",
                    "stateMutability": "view",
                    "inputs": [{"name": "account", "type": "address"}],
                    "outputs": [{"name": "", "type": "uint256"}],
                }
            ],
        )
        try:
            return int(contract.functions.balanceOf(Web3.to_checksum_address(address)).call())
        except Exception:  # noqa: BLE001
            return None

    def confirm(
        self,
        *,
        payer: str,
        pay_to: str,
        amount: str,
        nonce: str,
        candidate_tx: str | None = None,
    ) -> ChainConfirmation:
        """Confirm exactly one successful transfer for this authorization.

        The persisted nonce's ``AuthorizationUsed`` event from the configured
        token on the configured chain is mandatory evidence. ``candidate_tx``
        merely names the transaction expected to carry it: a candidate that
        does not carry the nonce-bound event is rejected, and an unavailable
        nonce-bound lookup keeps the outcome uncertain instead of settling.
        """
        if LOWER_ADDRESS_PATTERN.fullmatch(payer) is None or NONCE_PATTERN.fullmatch(nonce) is None:
            return ChainConfirmation(
                settled=False,
                tx_hash=candidate_tx,
                receipt_status=None,
                authorization_used=False,
                transfer_matched=False,
                nonce_consumed=False,
                reason="invalid payer or nonce",
            )
        if not self.chain_matches():
            return ChainConfirmation(
                settled=False,
                tx_hash=candidate_tx,
                receipt_status=None,
                authorization_used=False,
                transfer_matched=False,
                nonce_consumed=False,
                reason="configured chain is unavailable or does not match",
            )
        available, hashes = self.authorization_used_hashes(payer=payer, nonce=nonce)
        if not available:
            return ChainConfirmation(
                settled=False,
                tx_hash=candidate_tx,
                receipt_status=None,
                authorization_used=False,
                transfer_matched=False,
                nonce_consumed=False,
                reason="authorization event lookup is unavailable",
            )
        if len(hashes) > 1:
            return ChainConfirmation(
                settled=False,
                tx_hash=candidate_tx,
                receipt_status=None,
                authorization_used=True,
                transfer_matched=False,
                nonce_consumed=True,
                reason="multiple authorization events for this nonce",
            )
        used_tx = hashes[0] if hashes else None
        if candidate_tx is not None:
            if used_tx is None or used_tx != _hex_data(candidate_tx):
                return ChainConfirmation(
                    settled=False,
                    tx_hash=candidate_tx,
                    receipt_status=self.receipt_status(candidate_tx),
                    authorization_used=used_tx is not None,
                    transfer_matched=False,
                    nonce_consumed=used_tx is not None,
                    reason="candidate transaction does not carry this authorization",
                )
            tx_hash = candidate_tx
        else:
            if used_tx is None:
                state = self.authorization_state(payer=payer, nonce=nonce)
                return ChainConfirmation(
                    settled=False,
                    tx_hash=None,
                    receipt_status=None,
                    authorization_used=False,
                    transfer_matched=False,
                    nonce_consumed=state is True,
                    reason="no authorization event found",
                )
            tx_hash = used_tx
        receipt = self._receipt(tx_hash)
        status: int | None = None
        if receipt is not None:
            raw_status = receipt.get("status")
            status = int(raw_status) if raw_status is not None else None
        if status != 1:
            return ChainConfirmation(
                settled=False,
                tx_hash=tx_hash,
                receipt_status=status,
                authorization_used=True,
                transfer_matched=False,
                nonce_consumed=True,
                reason="transaction receipt is unavailable or did not succeed",
            )
        if not self._has_authorization_used(receipt, payer=payer, nonce=nonce):
            return ChainConfirmation(
                settled=False,
                tx_hash=tx_hash,
                receipt_status=status,
                authorization_used=False,
                transfer_matched=False,
                nonce_consumed=True,
                reason="receipt does not carry the token authorization event",
            )
        matched = self._transfer_matched_receipt(receipt, payer=payer, pay_to=pay_to, amount=amount)
        return ChainConfirmation(
            settled=matched,
            tx_hash=tx_hash,
            receipt_status=status,
            authorization_used=True,
            transfer_matched=matched,
            nonce_consumed=True,
            reason="" if matched else "transfer event does not match the authorization",
        )
