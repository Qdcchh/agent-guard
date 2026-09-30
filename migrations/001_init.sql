-- A1 execution-ledger schema, version 001.
--
-- Applied by src/agent_guard/ledger/migrate.py; never edit this file after it
-- has been applied anywhere (the runner enforces a checksum). Future changes
-- ship as new numbered migrations; incompatible changes must be documented in
-- README/docs with an upgrade path.
--
-- Numeric policy (docs/oauth-oidc-sm2-mvp.md 8.1): CNY integer fen and call
-- counts are bounded to [0, 2^53-1]; booleans/floats never reach these columns
-- (the service layer rejects them first). Ledger delta columns are the only
-- columns allowed to go negative, within +/- (2^53-1).
--
-- Budget invariants use the safe form `settled <= limit AND
-- reserved <= limit - settled` so that no checked expression relies on an
-- addition that could overflow.

CREATE TABLE ag_tasks (
    tenant_id     TEXT NOT NULL,
    task_id       TEXT NOT NULL,
    root_grant_id TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, task_id)
);

COMMENT ON TABLE ag_tasks IS
    'Permanent (tenant_id, task_id) -> single root grant relation; never reset by expiry/revocation/re-init.';

CREATE TABLE ag_principals (
    tenant_id      TEXT NOT NULL,
    client_id      TEXT NOT NULL,
    kid            TEXT NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    deactivated_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, client_id, kid),
    CHECK (NOT (active AND deactivated_at IS NOT NULL))
);

COMMENT ON TABLE ag_principals IS
    'Holder key registry, created only by trusted in-process initialization fixtures.';

CREATE TABLE ag_grants (
    grant_id         TEXT PRIMARY KEY,
    parent_grant_id  TEXT REFERENCES ag_grants (grant_id),
    root_grant_id    TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    task_id          TEXT NOT NULL,
    subject          TEXT NOT NULL,
    holder_client_id TEXT NOT NULL,
    holder_kid       TEXT NOT NULL,
    depth            INTEGER NOT NULL CHECK (depth BETWEEN 0 AND 2),
    not_before       TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ NOT NULL,
    revoked          BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at       TIMESTAMPTZ,
    amount_limit     BIGINT NOT NULL CHECK (amount_limit BETWEEN 0 AND 9007199254740991),
    call_limit       BIGINT NOT NULL CHECK (call_limit BETWEEN 0 AND 9007199254740991),
    amount_reserved  BIGINT NOT NULL DEFAULT 0 CHECK (amount_reserved BETWEEN 0 AND 9007199254740991),
    amount_settled   BIGINT NOT NULL DEFAULT 0 CHECK (amount_settled BETWEEN 0 AND 9007199254740991),
    calls_reserved   BIGINT NOT NULL DEFAULT 0 CHECK (calls_reserved BETWEEN 0 AND 9007199254740991),
    calls_settled    BIGINT NOT NULL DEFAULT 0 CHECK (calls_settled BETWEEN 0 AND 9007199254740991),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (not_before < expires_at),
    CHECK ((parent_grant_id IS NULL) = (depth = 0)),
    CHECK (amount_settled <= amount_limit AND amount_reserved <= amount_limit - amount_settled),
    CHECK (calls_settled <= call_limit AND calls_reserved <= call_limit - calls_settled)
);

COMMENT ON TABLE ag_grants IS
    'Immutable authorization tree nodes (root + up to two child levels); only counters and revocation state may change.';

CREATE INDEX ag_grants_task_idx ON ag_grants (tenant_id, task_id);

-- Parent links and limit/validity fields are immutable: re-pointing a parent
-- must never reset accumulated budget. Only counters and revocation change.
CREATE FUNCTION ag_grants_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.grant_id IS DISTINCT FROM OLD.grant_id
        OR NEW.parent_grant_id IS DISTINCT FROM OLD.parent_grant_id
        OR NEW.root_grant_id IS DISTINCT FROM OLD.root_grant_id
        OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.task_id IS DISTINCT FROM OLD.task_id
        OR NEW.subject IS DISTINCT FROM OLD.subject
        OR NEW.holder_client_id IS DISTINCT FROM OLD.holder_client_id
        OR NEW.holder_kid IS DISTINCT FROM OLD.holder_kid
        OR NEW.depth IS DISTINCT FROM OLD.depth
        OR NEW.not_before IS DISTINCT FROM OLD.not_before
        OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
        OR NEW.amount_limit IS DISTINCT FROM OLD.amount_limit
        OR NEW.call_limit IS DISTINCT FROM OLD.call_limit
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'ag_grants immutable columns cannot change'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_grants_guard_trg
    BEFORE UPDATE ON ag_grants
    FOR EACH ROW EXECUTE FUNCTION ag_grants_guard();

CREATE TABLE ag_operations (
    operation_id     TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    task_id          TEXT NOT NULL,
    tool_id          TEXT NOT NULL,
    idempotency_key  TEXT NOT NULL,
    grant_id         TEXT NOT NULL,
    holder_client_id TEXT NOT NULL,
    holder_kid       TEXT NOT NULL,
    tool_version     TEXT NOT NULL,
    canonical_params BYTEA NOT NULL,
    currency         TEXT NOT NULL,
    amount_fen       BIGINT NOT NULL CHECK (amount_fen BETWEEN 0 AND 9007199254740991),
    calls            BIGINT NOT NULL CHECK (calls BETWEEN 1 AND 9007199254740991),
    quote_id         TEXT,
    quote_version    TEXT,
    quote_snapshot   BYTEA,
    token_digest     TEXT NOT NULL,
    proof_digest     TEXT NOT NULL,
    intent_digest    TEXT NOT NULL,
    evidence_ref     TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'RESERVED'
        CHECK (status IN ('RESERVED', 'EXECUTING', 'SUCCEEDED', 'FAILED', 'UNKNOWN')),
    accepted_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ag_operations_business_key
        UNIQUE (tenant_id, task_id, tool_id, idempotency_key)
);

COMMENT ON TABLE ag_operations IS
    'One row per accepted business intent; the business key is (tenant_id, task_id, tool_id, idempotency_key).';

-- Intent, cost snapshot and first-accept evidence are immutable for the
-- lifetime of the operation; only status may transition later (A2).
CREATE FUNCTION ag_operations_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.operation_id IS DISTINCT FROM OLD.operation_id
        OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.task_id IS DISTINCT FROM OLD.task_id
        OR NEW.tool_id IS DISTINCT FROM OLD.tool_id
        OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
        OR NEW.grant_id IS DISTINCT FROM OLD.grant_id
        OR NEW.holder_client_id IS DISTINCT FROM OLD.holder_client_id
        OR NEW.holder_kid IS DISTINCT FROM OLD.holder_kid
        OR NEW.tool_version IS DISTINCT FROM OLD.tool_version
        OR NEW.canonical_params IS DISTINCT FROM OLD.canonical_params
        OR NEW.currency IS DISTINCT FROM OLD.currency
        OR NEW.amount_fen IS DISTINCT FROM OLD.amount_fen
        OR NEW.calls IS DISTINCT FROM OLD.calls
        OR NEW.quote_id IS DISTINCT FROM OLD.quote_id
        OR NEW.quote_version IS DISTINCT FROM OLD.quote_version
        OR NEW.quote_snapshot IS DISTINCT FROM OLD.quote_snapshot
        OR NEW.token_digest IS DISTINCT FROM OLD.token_digest
        OR NEW.proof_digest IS DISTINCT FROM OLD.proof_digest
        OR NEW.intent_digest IS DISTINCT FROM OLD.intent_digest
        OR NEW.evidence_ref IS DISTINCT FROM OLD.evidence_ref
        OR NEW.accepted_at IS DISTINCT FROM OLD.accepted_at
    THEN
        RAISE EXCEPTION 'ag_operations intent/cost/evidence columns cannot change'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_operations_guard_trg
    BEFORE UPDATE ON ag_operations
    FOR EACH ROW EXECUTE FUNCTION ag_operations_guard();

CREATE TABLE ag_proofs (
    holder_kid   TEXT NOT NULL,
    purpose      TEXT NOT NULL,
    endpoint     TEXT NOT NULL,
    proof_jti    TEXT NOT NULL,
    operation_id TEXT REFERENCES ag_operations (operation_id),
    proof_digest TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (holder_kid, purpose, endpoint, proof_jti)
);

COMMENT ON TABLE ag_proofs IS
    'Anti-replay registry; the primary key is the unique proof scope (kid, purpose, endpoint, jti).';

CREATE INDEX ag_proofs_operation_idx ON ag_proofs (operation_id);

CREATE TABLE ag_ledger_events (
    event_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES ag_operations (operation_id),
    phase        TEXT NOT NULL CHECK (phase IN ('RESERVE', 'SETTLE', 'RELEASE')),
    seq          INTEGER NOT NULL CHECK (seq >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ag_ledger_events_op_seq UNIQUE (operation_id, seq)
);

COMMENT ON TABLE ag_ledger_events IS
    'One row per ledger event (A1 writes a single RESERVE event per first accept; retries never add a second one).';

CREATE TABLE ag_ledger_event_nodes (
    event_id              BIGINT NOT NULL REFERENCES ag_ledger_events (event_id) ON DELETE CASCADE,
    position              INTEGER NOT NULL CHECK (position >= 0),
    grant_id              TEXT NOT NULL,
    amount_reserved_delta BIGINT NOT NULL
        CHECK (amount_reserved_delta BETWEEN -9007199254740991 AND 9007199254740991),
    amount_settled_delta  BIGINT NOT NULL
        CHECK (amount_settled_delta BETWEEN -9007199254740991 AND 9007199254740991),
    calls_reserved_delta  BIGINT NOT NULL
        CHECK (calls_reserved_delta BETWEEN -9007199254740991 AND 9007199254740991),
    calls_settled_delta   BIGINT NOT NULL
        CHECK (calls_settled_delta BETWEEN -9007199254740991 AND 9007199254740991),
    PRIMARY KEY (event_id, position),
    UNIQUE (event_id, grant_id)
);

COMMENT ON TABLE ag_ledger_event_nodes IS
    'Per-event root-to-leaf node deltas; A1 stores canonical data only (no SM3, no signed receipts).';
