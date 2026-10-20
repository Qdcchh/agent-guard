-- 008: durable 2-of-3 threshold approval -> operation binding (T4).
--
-- One row per (tenant_id, task_id, action_id). The row is inserted in the same
-- gateway transaction as the operation, its budget reservation and its evidence
-- links, so a failed transaction never consumes an approval. Rows are immutable
-- and an operation is bound to at most one approval: retries must match the
-- original operation, message digest and exact approval material. This
-- migration only adds one sidecar table, one unique index and guards; earlier
-- migrations and the seven legacy business tables are untouched.
CREATE TABLE ag_threshold_approvals (
    tenant_id       TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    action_id       TEXT NOT NULL CHECK (length(action_id) BETWEEN 1 AND 128),
    operation_id    TEXT NOT NULL REFERENCES ag_operations (operation_id),
    grant_id        TEXT NOT NULL,
    root_grant_id   TEXT NOT NULL,
    path_ids        TEXT[] NOT NULL CHECK (cardinality(path_ids) BETWEEN 1 AND 3),
    holder_client_id TEXT NOT NULL,
    holder_kid      TEXT NOT NULL,
    tool_id         TEXT NOT NULL,
    tool_version    TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    amount_fen      BIGINT NOT NULL CHECK (amount_fen BETWEEN 0 AND 9007199254740991),
    currency        TEXT NOT NULL CHECK (currency = 'CNY'),
    quote_id        TEXT,
    quote_version   TEXT,
    policy_version  BIGINT NOT NULL CHECK (policy_version BETWEEN 1 AND 9007199254740991),
    key_epoch       BIGINT NOT NULL CHECK (key_epoch BETWEEN 1 AND 9007199254740991),
    expires_at      TIMESTAMPTZ NOT NULL,
    message_sha256  TEXT NOT NULL CHECK (message_sha256 ~ '^[0-9a-f]{64}$'),
    envelope_sm3    TEXT NOT NULL,
    envelope_bytes  BYTEA NOT NULL CHECK (octet_length(envelope_bytes) BETWEEN 1 AND 24576),
    linked_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, task_id, action_id),
    CHECK (path_ids[1] = root_grant_id),
    CHECK (path_ids[cardinality(path_ids)] = grant_id)
);

COMMENT ON TABLE ag_threshold_approvals IS
    'Durable threshold approval binding written only inside the accept transaction; never updated or deleted, and one operation carries at most one approval.';

CREATE UNIQUE INDEX ag_threshold_approvals_operation_unique
    ON ag_threshold_approvals (operation_id);

CREATE FUNCTION ag_threshold_approvals_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'threshold approval bindings are immutable'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_threshold_approvals_guard_trg
    BEFORE UPDATE OR DELETE ON ag_threshold_approvals
    FOR EACH ROW EXECUTE FUNCTION ag_threshold_approvals_guard();

REVOKE ALL ON ag_threshold_approvals FROM PUBLIC;
