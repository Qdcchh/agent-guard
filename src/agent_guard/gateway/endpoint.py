"""Pure schema boundary followed by existing real verifier and acceptance."""

import time

from agent_guard.authorization.verifier import InvocationVerifier
from agent_guard.contracts.encoding import (
    EncodingError,
    canonical_json_bytes,
    load_strict_json,
)
from agent_guard.contracts.ledger import INVOKE_ENDPOINT, QUERY_ENDPOINT
from agent_guard.execution.query import AuthorizedQuery
from agent_guard.execution.verified import VerifiedExecution
from agent_guard.gateway.errors import GatewayError
from agent_guard.tools.params import (
    parse_tool_id,
    parse_tool_params,
    parse_tool_version,
)


class GatewayEndpoint:
    def __init__(
        self,
        *,
        verifier: InvocationVerifier,
        execution: VerifiedExecution,
        queries: AuthorizedQuery,
        receipt_verifier=None,
    ):
        if (
            type(verifier) is not InvocationVerifier
            or type(execution) is not VerifiedExecution
            or type(queries) is not AuthorizedQuery
        ):
            raise ValueError("real gateway services required")
        self._receipt_verifier = receipt_verifier
        self._verifier = verifier
        self._execution = execution
        self._queries = queries

    @staticmethod
    def schema(body: bytes, *, query: bool):
        try:
            value = load_strict_json(body)
            fields = (
                {"profile", "task_id", "operation_id"}
                if query
                else {
                    "profile",
                    "task_id",
                    "tool_id",
                    "tool_version",
                    "idempotency_key",
                    "params",
                }
            )
            if type(value) is not dict or set(value) != fields or value["profile"] != "GM-MVP-1":
                raise GatewayError("INVALID_SCHEMA")
            for key in ("task_id", "operation_id") if query else ("task_id", "idempotency_key"):
                if (
                    type(value[key]) is not str
                    or not value[key].isascii()
                    or not 1 <= len(value[key]) <= 128
                    or any(ord(c) < 33 or ord(c) > 126 for c in value[key])
                ):
                    raise GatewayError("INVALID_SCHEMA")
            if not query:
                tool = parse_tool_id(value["tool_id"])
                parse_tool_version(value["tool_version"])
                parse_tool_params(tool, canonical_json_bytes(value["params"]))
        except (EncodingError, UnicodeError, TypeError, RecursionError) as exc:
            raise GatewayError("INVALID_SCHEMA") from exc

    def handle(self, path: str, token: str, proof: str, body: bytes):
        query = path == "/v1/operations/query"
        self.schema(body, query=query)
        if query:
            bundle = self._verifier.verify_query_bundle(
                token, proof, endpoint=QUERY_ENDPOINT, body=body, now=int(time.time())
            )
            return 200, self._queries.query(bundle)
        bundle = self._verifier.verify_bundle(
            token, proof, endpoint=INVOKE_ENDPOINT, body=body, now=int(time.time())
        )
        return 202, self._execution.accept_response(bundle, receipt_verifier=self._receipt_verifier)
