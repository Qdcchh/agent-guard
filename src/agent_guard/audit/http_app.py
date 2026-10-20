"""Small fixed-route HTTP adapter; no public operator or signing endpoint."""

from __future__ import annotations

from agent_guard.audit.contracts import exact_object, identifier, integer
from agent_guard.audit.store import AuditStoreError
from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes


class AuditHTTPApp:
    def __init__(self, store):
        self.store = store

    def dispatch(self, method: str, path: str, headers, raw: bytes):
        try:
            if method != "POST" or path not in (
                "/v1/audit/append",
                "/v1/audit/latest",
                "/v1/audit/history",
                "/v1/audit/records",
            ):
                raise AuditStoreError("NOT_FOUND", 404)
            if headers.get("Content-Type") != "application/json":
                raise AuditStoreError("CONTENT_TYPE", 415)
            auth = headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or ":" not in auth:
                raise AuditStoreError("UNAUTHORIZED", 401)
            credential_id, credential = auth[7:].rsplit(":", 1)
            auth_args = {"credential_id": credential_id, "credential": credential}
            if path.endswith("append"):
                result = self.store.append(raw, **auth_args)
                return 200, canonical_json_bytes({"checkpoint_jws": result})
            keys = (
                {"stream_id"}
                if path.endswith("latest")
                else {"stream_id", "observed_checkpoint_id", "after_sequence"}
            )
            value = exact_object(raw, keys)
            identifier(value["stream_id"])
            if path.endswith("latest"):
                result = self.store.latest(value["stream_id"], **auth_args)
                if result is None:
                    raise AuditStoreError("NO_CHECKPOINT", 404)
                return 200, canonical_json_bytes({"checkpoint_jws": result})
            identifier(value["observed_checkpoint_id"])
            integer(value["after_sequence"])
            return 200, self.store.page(**value, **auth_args, records=path.endswith("records"))
        except AuditStoreError as exc:
            return exc.status, canonical_json_bytes({"error": exc.code})
        except (EncodingError, ValueError, TypeError):
            return 400, canonical_json_bytes({"error": "INVALID_REQUEST"})
        except Exception:
            # No database errors, signer material or credentials cross HTTP.
            return 503, canonical_json_bytes({"error": "AUDIT_UNAVAILABLE"})
