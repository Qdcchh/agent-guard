"""Actual research accept/query/lease/terminal API. No production budget helper."""

import json
import uuid
from dataclasses import asdict, dataclass

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.contracts.execution import ExecutionError, ToolId
from agent_guard.execution.service import strict_snapshots_equal
from agent_guard.tools import policy, results
from agent_guard.tools.catalog import snapshot_from_bytes, snapshot_to_bytes
from agent_guard.tools.params import parse_tool_params

from .research_contracts import (
    ACLContext,
    BearerContext,
    ResearchError,
    ResearchPoPContext,
    context_fields,
)
from .research_store import Lease, ResearchStore


@dataclass(frozen=True)
class Accepted:
    operation_id: str
    disposition: str
    status: str
    amount_fen: int


def _bytes(value):
    return bytes(value) if value is not None else None


def validate_material(operation, nodes):
    ids = operation["path_ids"]
    reserve = [n for n in nodes if n["phase"] == "RESERVE"]
    if len(reserve) != len(ids) or [n["grant_id"] for n in reserve] != ids:
        raise ResearchError("INCOMPLETE_MATERIAL")
    for n in reserve:
        if (
            n["amount_reserved_delta"],
            n["amount_settled_delta"],
            n["calls_reserved_delta"],
            n["calls_settled_delta"],
        ) != (operation["amount_fen"], 0, 1, 0):
            raise ResearchError("INCOMPLETE_MATERIAL")
    policy.check_stored_snapshot(
        tool_id=ToolId(operation["tool_id"]),
        params=parse_tool_params(operation["tool_id"], _bytes(operation["canonical_params"])),
        amount_fen=operation["amount_fen"],
        quote_snapshot_bytes=_bytes(operation["quote_snapshot"]),
    )


class ResearchService:
    def __init__(self, *, store, authenticator, catalog):
        if type(store) is not ResearchStore:
            raise ValueError("research store required")
        self.store, self.authenticator, self.catalog = store, authenticator, catalog

    def authenticate(self, **request):
        return self.authenticator.authenticate(mode=self.store.mode, **request)

    def authenticate_query(self, **request):
        return self.authenticator.authenticate(
            mode=self.store.mode, purpose="result-read", **request
        )

    def _context(self, context, purpose):
        expected = {
            "noAtomic": ResearchPoPContext,
            "Bearer": BearerContext,
            "staticACL": ACLContext,
        }[self.store.mode]
        if type(context) is not expected or context.purpose != purpose:
            raise ResearchError("INVALID_CONTEXT")
        return context_fields(context)

    def initialize_path(self, context):
        """Trusted setup after genuine AS chain; never an invoke or budget charge.

        All sibling paths must be initialized before competing accepts. Missing
        counters in accept are rejected, never implicitly inserted under race.
        """
        self._context(context, context.purpose)
        with self.store.transaction() as conn:
            path = self.store.authority_path(conn, context)
            for g in path:
                conn.execute(
                    "INSERT INTO r34.counters(grant_id) VALUES(%s) ON CONFLICT DO NOTHING",
                    (g["grant_id"],),
                )
            self.store.final_clock(conn, context, path)

    def _facts(self, conn, operation_id):
        row = self.store.operation(conn, operation_id)
        if row is None:
            return None
        return (
            row["tenant_id"],
            row["task_id"],
            row["grant_id"],
            row["client_id"],
            row["kid"],
        )

    def _material(self, conn, row):
        nodes = conn.execute(
            "SELECT e.phase,n.* FROM r34.events e JOIN r34.nodes n USING(event_id) WHERE "
            "e.operation_id=%s ORDER BY e.seq,n.position",
            (row["operation_id"],),
        ).fetchall()
        validate_material(row, nodes)
        original = conn.execute(
            "SELECT token,proof,body FROM r34.originals WHERE reference=%s",
            (row["first_ref"],),
        ).fetchone()
        if original is None:
            raise ResearchError("INCOMPLETE_MATERIAL")
        originals = {name: _bytes(original[name]) for name in ("body", "token", "proof")}
        from .research_contracts import parse_intent

        if originals["body"] is None:
            raise ResearchError("INCOMPLETE_MATERIAL")
        intent = parse_intent(originals["body"])
        if (
            intent.body,
            intent.params,
            intent.digest,
            intent.key,
            intent.tool_id.value,
        ) != (
            _bytes(row["canonical_body"]),
            _bytes(row["canonical_params"]),
            row["intent_digest"],
            row["business_key"],
            row["tool_id"],
        ):
            raise ResearchError("INCOMPLETE_MATERIAL")
        if row["mode"] in ("noAtomic", "Bearer"):
            source = load_strict_json(_bytes(row["source_material"]))
            chain = load_strict_json(source["chain"].encode())
            if not chain or originals["token"] != chain[-1]["token"].encode("ascii"):
                raise ResearchError("INCOMPLETE_MATERIAL")
        if row["mode"] == "noAtomic":
            from agent_guard.crypto.sm import sm3_b64url

            proof = conn.execute(
                "SELECT digest FROM r34.proofs WHERE operation_id=%s AND evidence_ref=%s",
                (row["operation_id"], row["first_ref"]),
            ).fetchall()
            if (
                originals["proof"] is None
                or len(proof) != 1
                or proof[0]["digest"] != sm3_b64url(originals["proof"])
            ):
                raise ResearchError("INCOMPLETE_MATERIAL")
        return nodes

    @staticmethod
    def _same_intent(row, context):
        f = context_fields(context)
        i = context.intent
        if (
            row["tenant_id"],
            row["task_id"],
            row["subject"],
            row["grant_id"],
            row["root_id"],
            row["client_id"],
            row["kid"],
            row["tool_id"],
            row["tool_version"],
            row["business_key"],
            _bytes(row["canonical_params"]),
            _bytes(row["canonical_body"]),
            row["intent_digest"],
        ) != (
            f["tenant"],
            f["task"],
            f["subject"],
            f["grant"],
            f["root"],
            f["client"],
            f["kid"],
            i.tool_id.value,
            "1",
            i.key,
            i.params,
            i.body,
            i.digest,
        ):
            raise ResearchError("IDEMPOTENCY_CONFLICT")

    def accept(self, context, *, controlled_before_update=None):
        """Own RC transaction; optional barrier ONLY for labelled safety probes."""
        f = self._context(context, "invoke")
        i = context.intent
        if i is None:
            raise ResearchError("INVALID_CONTEXT")
        with self.store.transaction() as conn:
            path = self.store.authority_path(conn, context)
            policy.check_static_authorization(
                f["source"],
                grant_id=f["grant"],
                root_id=f["root"],
                tenant_id=f["tenant"],
                task_id=f["task"],
                subject=f["subject"],
                tool_id=i.tool_id,
                params=parse_tool_params(i.tool_id, i.params),
                db_path=tuple(g["grant_id"] for g in path),
            )
            self.store.business_mutex(conn, context)
            self.store.record_proof(conn, context)
            existing = self.store.candidate(conn, context)
            if existing:
                self._same_intent(existing, context)
                self._material(conn, existing)
                self.store.link_proof(conn, context, existing["operation_id"])
                answer = Accepted(
                    existing["operation_id"],
                    "EXISTING",
                    existing["status"],
                    existing["amount_fen"],
                )
                self.store.final_clock(conn, context, path)
                return answer
            try:
                quote = policy.resolve_tool_resources(
                    self.catalog,
                    tenant_id=f["tenant"],
                    task_id=f["task"],
                    tool_id=i.tool_id,
                    params=parse_tool_params(i.tool_id, i.params),
                    operation_facts=lambda op: self._facts(conn, op),
                    caller_grant_id=f["grant"],
                    caller_holder_client_id=f["client"],
                    caller_holder_kid=f["kid"],
                )
            except Exception:
                # Hold exact-key mutex: any candidate that committed during
                # prelookup remains recoverable; no repricing an existing row.
                existing = self.store.candidate(conn, context)
                if not existing:
                    raise
                self._same_intent(existing, context)
                self._material(conn, existing)
                self.store.link_proof(conn, context, existing["operation_id"])
                answer = Accepted(
                    existing["operation_id"],
                    "EXISTING",
                    existing["status"],
                    existing["amount_fen"],
                )
                self.store.final_clock(conn, context, path)
                return answer
            amount = quote.total_fen if quote is not None else 0
            counters = []
            for g in path:
                counter = conn.execute(
                    "SELECT * FROM r34.counters WHERE grant_id=%s"
                    + (" FOR UPDATE" if self.store.mode == "Bearer" else ""),
                    (g["grant_id"],),
                ).fetchone()
                if counter is None:
                    raise ResearchError("PATH_NOT_INITIALIZED")
                counters.append(counter)
            if self.store.mode != "staticACL":
                for g, c in zip(path, counters, strict=True):
                    if c["amount_reserved"] + c["amount_settled"] + amount > g["amount_limit"]:
                        raise ResearchError("BUDGET_EXCEEDED")
                    if c["calls_reserved"] + c["calls_settled"] + 1 > g["call_limit"]:
                        raise ResearchError("CALL_LIMIT_EXCEEDED")
            if controlled_before_update is not None:
                if self.store.mode != "noAtomic" or not callable(controlled_before_update):
                    raise ResearchError("INVALID_CONTROLLED_PROBE")
                controlled_before_update()
            operation_id = uuid.uuid4().hex
            source = (
                context.source.material()
                if type(context) in (ResearchPoPContext, BearerContext)
                else canonical_json_bytes(
                    {
                        "role": context.registration.role,
                        "policy": "preapproved ACL",
                        "grant_id": f["grant"],
                        "expires_at": context.registration.expires_at,
                        "snapshot": load_strict_json(
                            json.dumps(asdict(context.registration.snapshot)).encode()
                        ),
                    }
                )
            )
            originals = tuple(
                self.authenticator.evidence.original(f["ref"], name)
                for name in ("token", "proof", "body")
            )
            if originals[2] != context.body:
                raise ResearchError("INCOMPLETE_MATERIAL")
            conn.execute(
                "INSERT INTO r34.originals(reference,token,proof,body) VALUES(%s,%s,%s,%s)",
                (f["ref"], *originals),
            )
            row = conn.execute(
                "INSERT INTO "
                "r34.operations(operation_id,mode,tenant_id,task_id,subject,grant_id,ro"
                "ot_id,client_id,kid,tool_id,tool_version,business_key,canonical_params"
                ",canonical_body,intent_digest,amount_fen,calls,quote_snapshot,path_ids"
                ",first_ref,source_material) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s) "
                "RETURNING *",
                (
                    operation_id,
                    self.store.mode,
                    f["tenant"],
                    f["task"],
                    f["subject"],
                    f["grant"],
                    f["root"],
                    f["client"],
                    f["kid"],
                    i.tool_id.value,
                    "1",
                    i.key,
                    i.params,
                    i.body,
                    i.digest,
                    amount,
                    snapshot_to_bytes(quote) if quote else None,
                    [g["grant_id"] for g in path],
                    f["ref"],
                    source,
                ),
            ).fetchone()
            # Server-side increments: noAtomic cannot lose an update, but its
            # unlocked prior checks deliberately permit concurrent overspend.
            for g in path:
                conn.execute(
                    "UPDATE r34.counters SET "
                    "amount_reserved=amount_reserved+%s,calls_reserved=calls_reserved+1,amo"
                    "unt_high_water=greatest(amount_high_water,amount_reserved+amount_settl"
                    "ed+%s),calls_high_water=greatest(calls_high_water,calls_reserved+calls"
                    "_settled+1) WHERE grant_id=%s",
                    (amount, amount, g["grant_id"]),
                )
            self.store.event(conn, row, "RESERVE")
            self.store.link_proof(conn, context, operation_id)
            answer = Accepted(operation_id, "NEW", "RESERVED", amount)
            self.store.final_clock(conn, context, path)
            return answer

    def query(self, context):
        f = self._context(context, "result-read")
        operation_id = (
            context.verified.operation_id
            if type(context) is ResearchPoPContext
            else context.operation_id
        )
        with self.store.transaction() as conn:
            path = self.store.authority_path(conn, context)
            row = self.store.operation(conn, operation_id)
            if row is None or (
                row["tenant_id"],
                row["task_id"],
                row["subject"],
                row["grant_id"],
                row["client_id"],
                row["kid"],
            ) != (
                f["tenant"],
                f["task"],
                f["subject"],
                f["grant"],
                f["client"],
                f["kid"],
            ):
                raise ResearchError("SCOPE_DENIED")
            policy.check_static_authorization(
                f["source"],
                grant_id=f["grant"],
                root_id=f["root"],
                tenant_id=f["tenant"],
                task_id=f["task"],
                subject=f["subject"],
                tool_id=ToolId(row["tool_id"]),
                params=parse_tool_params(row["tool_id"], _bytes(row["canonical_params"])),
                db_path=tuple(g["grant_id"] for g in path),
            )
            self._material(conn, row)
            self.store.record_proof(conn, context, operation_id)
            outbox = conn.execute(
                "SELECT * FROM r34.outbox WHERE operation_id=%s", (operation_id,)
            ).fetchone()
            answer = {
                "operation_id": operation_id,
                "status": row["status"],
                "result_bytes": _bytes(outbox["result_bytes"]) if outbox else None,
                "receipt": "NOT_APPLICABLE",
            }
            self.store.final_clock(conn, context, path)
            return answer

    def claim(self, operation_id, owner):
        with self.store.transaction(readonly=True) as conn:
            row = self.store.operation(conn, operation_id)
            if row is None:
                raise ResearchError("OPERATION_NOT_FOUND")
            self._material(conn, row)
        return self.store.claim(operation_id, owner)

    def load_operation(self, operation_id):
        with self.store.transaction(readonly=True) as conn:
            row = self.store.operation(conn, operation_id)
            if row is None:
                raise ResearchError("OPERATION_NOT_FOUND")
            self._material(conn, row)
            return row

    @staticmethod
    def terminal_action(operation, outcome):
        if outcome is None:
            return None
        from agent_guard.contracts.execution import DownstreamOutcome

        if (
            type(outcome) is not DownstreamOutcome
            or type(outcome.amount_fen) is not int
            or type(outcome.final_rejection) is not bool
        ):
            return None
        quote = snapshot_from_bytes(_bytes(operation["quote_snapshot"]))
        if (outcome.operation_id, outcome.tool_id.value, outcome.canonical_params) != (
            operation["operation_id"],
            operation["tool_id"],
            _bytes(operation["canonical_params"]),
        ) or not strict_snapshots_equal(quote, outcome.quote):
            return None
        try:
            result = results.parse_result(outcome.result_bytes)
            effect = results.bind_result(
                result,
                operation_id=operation["operation_id"],
                tool_id=operation["tool_id"],
            )
            if outcome.final_rejection:
                return (
                    "RELEASE"
                    if type(result) is results.RefusalResult
                    and outcome.amount_fen == 0
                    and outcome.effect_ref is None
                    else None
                )
            if (
                type(result) is results.RefusalResult
                or outcome.amount_fen != operation["amount_fen"]
                or effect != outcome.effect_ref
            ):
                return None
            if type(result) is results.OrderResult:
                if quote is None or (
                    result.supplier_id,
                    result.quote_id,
                    result.quote_version,
                    result.total_fen,
                    tuple(result.items),
                ) != (
                    quote.supplier_id,
                    quote.quote_id,
                    quote.quote_version,
                    quote.total_fen,
                    tuple((x.sku, x.quantity, x.unit_price_fen) for x in quote.items),
                ):
                    return None
            if type(result) is results.NotificationResult:
                params = parse_tool_params(
                    operation["tool_id"], _bytes(operation["canonical_params"])
                )
                if (result.template_id, result.recipient_id) != (
                    params.template_id,
                    params.recipient_id,
                ):
                    return None
            return "SETTLE"
        except (ValueError, TypeError, AttributeError, ExecutionError):
            return None

    def finalize(self, lease: Lease, outcome):
        if type(lease) is not Lease:
            raise ResearchError("INVALID_LEASE")
        probe = self.load_operation(lease.operation_id)
        action = self.terminal_action(probe, outcome)
        with self.store.transaction() as conn:
            # Consistent terminal lock order: all counter rows root→leaf,
            # operation, lease. No current authority/revoke check for recovery.
            for grant in probe["path_ids"]:
                conn.execute(
                    "SELECT grant_id FROM r34.counters WHERE grant_id=%s FOR UPDATE",
                    (grant,),
                ).fetchone()
            row = self.store.operation(conn, lease.operation_id, lock=True)
            current = conn.execute(
                "SELECT * FROM r34.leases WHERE operation_id=%s FOR UPDATE",
                (lease.operation_id,),
            ).fetchone()
            now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            if (
                row is None
                or row["status"] not in ("EXECUTING", "UNKNOWN")
                or current is None
                or (current["owner"], current["version"], current["expires_at"])
                != (lease.owner, lease.version, lease.expires_at)
                or current["expires_at"] <= now
            ):
                raise ResearchError("STALE_FENCE")
            self._material(conn, row)
            status = "UNKNOWN"
            if action:
                amount = row["amount_fen"]
                settle = action == "SETTLE"
                for grant in row["path_ids"]:
                    conn.execute(
                        "UPDATE r34.counters SET "
                        "amount_reserved=amount_reserved-%s,amount_settled=amount_settled+%s,ca"
                        "lls_reserved=calls_reserved-1,calls_settled=calls_settled+%s "
                        "WHERE grant_id=%s",
                        (amount, amount if settle else 0, 1 if settle else 0, grant),
                    )
                self.store.event(conn, row, action)
                status = "SUCCEEDED" if settle else "FAILED"
                conn.execute(
                    "INSERT INTO "
                    "r34.outbox(operation_id,status,result_bytes,quote_snapshot) "
                    "VALUES(%s,%s,%s,%s)",
                    (
                        lease.operation_id,
                        status,
                        outcome.result_bytes,
                        row["quote_snapshot"],
                    ),
                )
            conn.execute(
                "UPDATE r34.operations SET status=%s WHERE operation_id=%s",
                (status, lease.operation_id),
            )
            conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
            final_now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            if final_now >= lease.expires_at:
                raise ResearchError("STALE_FENCE")
            return status


def create_research_tls_server(service, *, host, port, certificate, private_key):
    """Isolated HTTPS research listener, canonical fixed invocation/query routes.

    Operator chooses exact owned private address and port. No production ENV
    switches. External callers supply raw bytes/credentials, never contexts.
    """
    import ipaddress
    import ssl
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    address = ipaddress.ip_address(host)
    if (
        str(address) != host
        or not address.is_private
        or address.is_unspecified
        or address.is_multicast
        or address.is_link_local
    ):
        raise ValueError("exact owned private listener required")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("fixed port required")
    slots = threading.BoundedSemaphore(32)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass  # Never serialize credentials, proof or body into logs.

        def do_POST(self):
            status = 200
            try:
                if self.path not in ("/v1/invocations", "/v1/operations/query"):
                    raise ResearchError("INVALID_ENDPOINT")
                if (
                    self.headers.get("Transfer-Encoding") is not None
                    or len(self.headers.get_all("Content-Length", [])) != 1
                ):
                    raise ResearchError("INVALID_SCHEMA")
                length = self.headers["Content-Length"]
                if not length.isdecimal() or not 0 < int(length) <= 65536:
                    raise ResearchError("INVALID_SCHEMA")
                for name in ("Authorization", "AG-Proof", "X-ACL-Role"):
                    if len(self.headers.get_all(name, [])) > 1:
                        raise ResearchError("INVALID_SCHEMA")
                self.connection.settimeout(30)
                body = self.rfile.read(int(length))
                if len(body) != int(length):
                    raise ResearchError("INVALID_SCHEMA")
                auth = self.headers.get("Authorization", "")
                request = dict(body=body, now=int(time.time()), proof=self.headers.get("AG-Proof"))
                if service.store.mode == "staticACL":
                    if not auth.startswith("ACL "):
                        raise ResearchError("INVALID_CREDENTIAL")
                    request.update(role=self.headers.get("X-ACL-Role"), password=auth[4:])
                else:
                    scheme = "Bearer " if service.store.mode == "Bearer" else "AGPoP "
                    if not auth.startswith(scheme):
                        raise ResearchError("INVALID_CREDENTIAL")
                    request["token"] = auth[len(scheme) :]
                with slots:
                    if self.path == "/v1/invocations":
                        accepted = service.accept(service.authenticate(**request))
                        value = {
                            "operation_id": accepted.operation_id,
                            "status": accepted.status,
                            "disposition": accepted.disposition,
                        }
                    else:
                        value = service.query(service.authenticate_query(**request))
                        if value["result_bytes"] is not None:
                            from agent_guard.contracts.encoding import b64url_encode

                            value["result_bytes"] = b64url_encode(value["result_bytes"])
            except Exception as exc:
                status = 400
                code = getattr(exc, "code", "RESEARCH_UNAVAILABLE")
                value = {"error": getattr(code, "value", str(code))}
            raw = canonical_json_bytes(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(str(certificate), str(private_key))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    return server
