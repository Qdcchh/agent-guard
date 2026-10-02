-- 004: A2.1 execution lifecycle, terminal ledger events, lease and receipt outbox.
--
-- Never edit 001/002/003. This migration only ADDS tables, constraints and
-- triggers. It never adds a column to the seven existing business tables and
-- never rewrites an existing row: `SELECT *` snapshots of ag_tasks,
-- ag_principals, ag_grants, ag_operations, ag_proofs, ag_ledger_events and
-- ag_ledger_event_nodes are byte-identical before and after a legal upgrade.
--
-- Everything runs in the single migration transaction (see migrate.py), so an
-- aborted upgrade rolls back every DDL change and leaves ag_schema_migrations
-- exactly as it was. The explicit pre-checks below make the *reason* for an
-- illegal upgrade readable instead of relying on a late CHECK failure.
--
-- Scope of enforcement added here:
--   * pre-upgrade integrity checks for the phase/seq binding and terminal
--     events (illegal legacy data refuses the upgrade, never "fixed" in place)
--   * ag_ledger_events: phase <-> seq binding (RESERVE/0, SETTLE|RELEASE/1)
--     combined with the existing UNIQUE (operation_id, seq) gives exactly one
--     RESERVE and at most one mutually exclusive terminal event
--   * ag_ledger_events / ag_ledger_event_nodes: no UPDATE and no DELETE
--   * ag_operations: legal status transitions only; terminal states freeze;
--     explicit DELETE protection for every accepted operation
--   * ag_grants: a node referenced by an accepted operation or by a ledger
--     event node cannot be deleted (blocks delete + same-id rebuild of an
--     accepted path); legitimate counter/revocation UPDATEs stay open
--   * new sidecar/lease/outbox tables, kept outside the seven legacy tables

-- ------------------------------------------------------ pre-upgrade checks
DO $$
BEGIN
    -- phase <-> seq binding that 004 is about to enforce must already hold.
    IF EXISTS (
        SELECT 1 FROM ag_ledger_events
        WHERE NOT (
            (phase = 'RESERVE' AND seq = 0)
            OR (phase IN ('SETTLE', 'RELEASE') AND seq = 1)
        )
    ) THEN
        RAISE EXCEPTION
            '004 pre-check failed: ledger events violate the RESERVE/0, terminal/1 binding; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    -- at most one terminal event per operation (SETTLE and RELEASE are exclusive)
    IF EXISTS (
        SELECT operation_id FROM ag_ledger_events
        WHERE phase IN ('SETTLE', 'RELEASE')
        GROUP BY operation_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            '004 pre-check failed: an operation has more than one terminal event; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    -- a terminal status must already be backed by exactly one terminal event
    IF EXISTS (
        SELECT 1 FROM ag_operations o
        WHERE o.status IN ('SUCCEEDED', 'FAILED')
          AND (SELECT count(*) FROM ag_ledger_events e
               WHERE e.operation_id = o.operation_id
                 AND e.phase IN ('SETTLE', 'RELEASE')) <> 1
    ) THEN
        RAISE EXCEPTION
            '004 pre-check failed: terminal operations without exactly one terminal event; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    -- a non-terminal status must not carry a terminal event
    IF EXISTS (
        SELECT 1 FROM ag_operations o
        WHERE o.status NOT IN ('SUCCEEDED', 'FAILED')
          AND EXISTS (SELECT 1 FROM ag_ledger_events e
                      WHERE e.operation_id = o.operation_id
                        AND e.phase IN ('SETTLE', 'RELEASE'))
    ) THEN
        RAISE EXCEPTION
            '004 pre-check failed: non-terminal operations carry terminal events; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    -- every accepted operation must still have its RESERVE event
    IF EXISTS (
        SELECT 1 FROM ag_operations o
        WHERE (SELECT count(*) FROM ag_ledger_events e
               WHERE e.operation_id = o.operation_id
                 AND e.phase = 'RESERVE') <> 1
    ) THEN
        RAISE EXCEPTION
            '004 pre-check failed: operations without exactly one RESERVE event; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;
END $$;

-- ------------------------------------------ phase <-> seq binding + freeze
ALTER TABLE ag_ledger_events
    ADD CONSTRAINT ag_ledger_events_phase_seq
    CHECK ((phase = 'RESERVE' AND seq = 0) OR (phase IN ('SETTLE', 'RELEASE') AND seq = 1));

COMMENT ON CONSTRAINT ag_ledger_events_phase_seq ON ag_ledger_events IS
    'RESERVE is event 0 and the single terminal event is 1; combined with UNIQUE (operation_id, seq) this gives one reservation and at most one terminal change.';

CREATE FUNCTION ag_ledger_events_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ag_ledger_events rows cannot be updated or deleted'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_ledger_events_guard_trg
    BEFORE UPDATE OR DELETE ON ag_ledger_events
    FOR EACH ROW EXECUTE FUNCTION ag_ledger_events_guard();

CREATE FUNCTION ag_ledger_event_nodes_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ag_ledger_event_nodes rows cannot be updated or deleted'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_ledger_event_nodes_guard_trg
    BEFORE UPDATE OR DELETE ON ag_ledger_event_nodes
    FOR EACH ROW EXECUTE FUNCTION ag_ledger_event_nodes_guard();

-- --------------------------------------------- operation status transition
CREATE FUNCTION ag_operations_status_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        -- UNKNOWN -> UNKNOWN ("still uncertain") is a documented no-op; any
        -- other same-value write is also a no-op and changes nothing.
        IF OLD.status IN ('SUCCEEDED', 'FAILED') THEN
            RAISE EXCEPTION 'terminal operation status cannot be written again'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status = 'RESERVED' AND NEW.status = 'EXECUTING' THEN
        RETURN NEW;
    END IF;
    IF OLD.status = 'EXECUTING'
        AND NEW.status IN ('SUCCEEDED', 'FAILED', 'UNKNOWN') THEN
        RETURN NEW;
    END IF;
    IF OLD.status = 'UNKNOWN'
        AND NEW.status IN ('SUCCEEDED', 'FAILED', 'UNKNOWN') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'illegal operation status transition: % -> %', OLD.status, NEW.status
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_operations_status_guard_trg
    BEFORE UPDATE ON ag_operations
    FOR EACH ROW EXECUTE FUNCTION ag_operations_status_guard();

-- accepted operations are permanent facts: never deleted
CREATE FUNCTION ag_operations_delete_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ag_operations rows cannot be deleted (accepted facts are permanent)'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_operations_delete_guard_trg
    BEFORE DELETE ON ag_operations
    FOR EACH ROW EXECUTE FUNCTION ag_operations_delete_guard();

-- ------------------------------------------------- accepted path delete guard
-- A grant node that backs an accepted operation (its grant_id or any of its
-- root-to-leaf ledger event nodes) can never be deleted, so an accepted path
-- cannot be removed and rebuilt under the same id. Unreferenced non-root nodes
-- keep their old semantics and root deletion stays blocked by 003.
CREATE FUNCTION ag_grants_accepted_path_delete_guard() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM ag_operations o WHERE o.grant_id = OLD.grant_id) THEN
        RAISE EXCEPTION 'grant node referenced by an accepted operation cannot be deleted'
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM ag_ledger_event_nodes n WHERE n.grant_id = OLD.grant_id) THEN
        RAISE EXCEPTION 'grant node referenced by ledger events cannot be deleted'
            USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_grants_accepted_path_delete_guard_trg
    BEFORE DELETE ON ag_grants
    FOR EACH ROW EXECUTE FUNCTION ag_grants_accepted_path_delete_guard();

-- ------------------------------------------------------------- sidecar flags
-- Legacy material that is missing, malformed or incomplete is quarantined
-- here. The original seven tables are untouched and the reserved budget is
-- never cleared, never re-priced from a current quote and never executed.
CREATE TABLE ag_operation_review_flags (
    operation_id TEXT PRIMARY KEY REFERENCES ag_operations (operation_id),
    reason       TEXT NOT NULL,
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    flagged_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE ag_operation_review_flags IS
    'Quarantine sidecar for operations whose persisted material is insufficient; budget stays reserved and the operation is never executed from a replacement quote.';

-- ------------------------------------------------------------------- leases
CREATE TABLE ag_execution_leases (
    operation_id    TEXT PRIMARY KEY REFERENCES ag_operations (operation_id),
    owner_token     TEXT NOT NULL,
    fencing_version BIGINT NOT NULL CHECK (fencing_version BETWEEN 1 AND 9007199254740991),
    lease_expires_at TIMESTAMPTZ NOT NULL,
    acquired_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE ag_execution_leases IS
    'One current lease per operation; terminal writes require owner_token + fencing_version + legal state + an unexpired lease at the database clock after locks.';

CREATE FUNCTION ag_execution_leases_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.operation_id IS DISTINCT FROM OLD.operation_id THEN
        RAISE EXCEPTION 'ag_execution_leases.operation_id is immutable'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.fencing_version < OLD.fencing_version THEN
        RAISE EXCEPTION 'ag_execution_leases.fencing_version cannot go backwards'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_execution_leases_guard_trg
    BEFORE UPDATE ON ag_execution_leases
    FOR EACH ROW EXECUTE FUNCTION ag_execution_leases_guard();

CREATE FUNCTION ag_execution_leases_delete_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ag_execution_leases rows cannot be deleted'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_execution_leases_delete_guard_trg
    BEFORE DELETE ON ag_execution_leases
    FOR EACH ROW EXECUTE FUNCTION ag_execution_leases_delete_guard();

-- --------------------------------------------------------- receipt outbox
-- Stable pending-signature material written in the same gateway transaction as
-- the terminal ledger change. receipt_jws stays NULL until A2.3 produces a
-- real SM2 signature; nothing here claims an RFC 8785 encoding or an SM3.
CREATE TABLE ag_receipt_outbox (
    operation_id        TEXT PRIMARY KEY REFERENCES ag_operations (operation_id),
    receipt_id          TEXT NOT NULL UNIQUE,
    profile             TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    root_grant_id       TEXT NOT NULL,
    grant_id            TEXT NOT NULL,
    tool_id             TEXT NOT NULL,
    tool_version        TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED')),
    amount_fen          BIGINT NOT NULL CHECK (amount_fen BETWEEN 0 AND 9007199254740991),
    ledger_changes_json BYTEA NOT NULL,
    result_bytes        BYTEA NOT NULL,
    token_digest        TEXT NOT NULL,
    proof_digest        TEXT NOT NULL,
    intent_digest       TEXT NOT NULL,
    evidence_ref        TEXT NOT NULL,
    receipt_status      TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (receipt_status IN ('PENDING', 'READY')),
    receipt_jws         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    signed_at           TIMESTAMPTZ,
    CHECK ((receipt_status = 'PENDING' AND receipt_jws IS NULL)
        OR (receipt_status = 'READY' AND receipt_jws IS NOT NULL))
);

COMMENT ON TABLE ag_receipt_outbox IS
    'Immutable pending-signature receipt material; created_at derives the receipt iat, and B is missing so receipt_status stays PENDING.';

CREATE FUNCTION ag_receipt_outbox_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.operation_id IS DISTINCT FROM OLD.operation_id
        OR NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
        OR NEW.profile IS DISTINCT FROM OLD.profile
        OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.task_id IS DISTINCT FROM OLD.task_id
        OR NEW.root_grant_id IS DISTINCT FROM OLD.root_grant_id
        OR NEW.grant_id IS DISTINCT FROM OLD.grant_id
        OR NEW.tool_id IS DISTINCT FROM OLD.tool_id
        OR NEW.tool_version IS DISTINCT FROM OLD.tool_version
        OR NEW.status IS DISTINCT FROM OLD.status
        OR NEW.amount_fen IS DISTINCT FROM OLD.amount_fen
        OR NEW.ledger_changes_json IS DISTINCT FROM OLD.ledger_changes_json
        OR NEW.result_bytes IS DISTINCT FROM OLD.result_bytes
        OR NEW.token_digest IS DISTINCT FROM OLD.token_digest
        OR NEW.proof_digest IS DISTINCT FROM OLD.proof_digest
        OR NEW.intent_digest IS DISTINCT FROM OLD.intent_digest
        OR NEW.evidence_ref IS DISTINCT FROM OLD.evidence_ref
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'ag_receipt_outbox signing material is immutable'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.receipt_status = 'READY' THEN
        IF NEW.receipt_status IS DISTINCT FROM OLD.receipt_status
            OR NEW.receipt_jws IS DISTINCT FROM OLD.receipt_jws
            OR NEW.signed_at IS DISTINCT FROM OLD.signed_at THEN
            RAISE EXCEPTION 'a signed receipt cannot be changed'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_receipt_outbox_guard_trg
    BEFORE UPDATE ON ag_receipt_outbox
    FOR EACH ROW EXECUTE FUNCTION ag_receipt_outbox_guard();

CREATE FUNCTION ag_receipt_outbox_delete_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ag_receipt_outbox rows cannot be deleted'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_receipt_outbox_delete_guard_trg
    BEFORE DELETE ON ag_receipt_outbox
    FOR EACH ROW EXECUTE FUNCTION ag_receipt_outbox_delete_guard();
