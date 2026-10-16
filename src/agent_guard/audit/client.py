"""Fixed-origin, bounded TLS transport; authentication belongs to delivery."""

from __future__ import annotations

import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from agent_guard.audit.contracts import (
    AppendBatch,
    decode_append_batch,
    decode_history_page,
    decode_record_page,
    exact_object,
    identifier,
)
from agent_guard.contracts.encoding import EncodingError, canonical_json_bytes


class AuditUnavailable(Exception):
    """A bounded transport failure, with no credentials or response body."""


class ReconcileRequired(AuditUnavailable):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AuditClient:
    def __init__(
        self,
        origin: str,
        *,
        ca_file: str,
        writer_credential: str,
        reader_credential: str,
        timeout: float = 5,
    ):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or origin != "https://" + parsed.netloc
        ):
            raise ValueError("fixed HTTPS origin required")
        if type(timeout) not in (int, float) or not 0 < timeout <= 15:
            raise ValueError("bounded timeout required")
        self.origin, self.timeout = origin, timeout
        self.writer = self._credential(writer_credential)
        self.reader = self._credential(reader_credential)
        context = ssl.create_default_context(cafile=ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), _NoRedirect())

    @staticmethod
    def _credential(value):
        import re

        identifier(value, maximum=2048)
        credential_id, sep, secret = value.rpartition(":")
        if not sep or not credential_id or not re.fullmatch(r"[A-Za-z0-9_-]{32,512}", secret):
            raise ValueError("credential ID and safe secret required")
        identifier(credential_id)
        return value

    def _post(self, endpoint, body, *, writer=False):
        request = Request(
            self.origin + "/v1/audit/" + endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + (self.writer if writer else self.reader),
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200 or response.geturl() != request.full_url:
                    raise AuditUnavailable("unexpected audit HTTP response")
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise AuditUnavailable("audit response capacity exceeded")
                return raw
        except HTTPError as exc:
            raw = exc.read(65537)
            if (
                exc.code == 409
                and writer
                and raw == canonical_json_bytes({"error": "RECONCILE_REQUIRED"})
            ):
                raise ReconcileRequired("audit reconciliation required") from None
            if (
                exc.code == 404
                and endpoint == "latest"
                and raw == canonical_json_bytes({"error": "NO_CHECKPOINT"})
            ):
                return raw
            raise AuditUnavailable("audit HTTP request failed") from None
        except (URLError, OSError, TimeoutError):
            raise AuditUnavailable("audit transport unavailable") from None

    @staticmethod
    def _checkpoint(raw):
        value = exact_object(raw, {"checkpoint_jws"})["checkpoint_jws"]
        if type(value) is not str or not value.isascii() or not 1 <= len(value) <= 16384:
            raise EncodingError("invalid checkpoint response")
        return value

    def append(self, batch: AppendBatch) -> str:
        if decode_append_batch(batch.exact_body) != batch:
            raise EncodingError("inconsistent append DTO")
        return self._checkpoint(self._post("append", batch.exact_body, writer=True))

    def latest(self, stream_id: str) -> str | None:
        raw = self._post("latest", canonical_json_bytes({"stream_id": identifier(stream_id)}))
        if raw == canonical_json_bytes({"error": "NO_CHECKPOINT"}):
            return None
        return self._checkpoint(raw)

    def _page(self, endpoint, stream_id, observed_checkpoint_id, after_sequence):
        from agent_guard.audit.contracts import integer

        return self._post(
            endpoint,
            canonical_json_bytes(
                {
                    "stream_id": identifier(stream_id),
                    "observed_checkpoint_id": identifier(observed_checkpoint_id),
                    "after_sequence": integer(after_sequence),
                }
            ),
        )

    def history(self, stream_id, *, observed_checkpoint_id, after_sequence):
        return decode_history_page(
            self._page("history", stream_id, observed_checkpoint_id, after_sequence)
        )

    def records(self, stream_id, *, observed_checkpoint_id, after_sequence):
        return decode_record_page(
            self._page("records", stream_id, observed_checkpoint_id, after_sequence)
        )
