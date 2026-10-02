-- 006: seal committed ledger event node sets (A21-R1-EVENT residual).
--
-- Never edit 001-005 (all already applied and checksummed). This migration
-- only ADDS one sidecar table and triggers; it never adds a column to the seven
-- legacy business tables, never rewrites an existing row and never "repairs" a
-- short legacy node set.
--
-- Why 005 was not enough: 005's completeness check is a DEFERRABLE constraint
-- trigger on `ag_ledger_events` INSERT, so it only seals *new* events. An event
-- that was already committed by a pre-005 database could still have node rows
-- INSERTed afterwards, silently changing history while the receipt outbox kept
-- the original shorter material.
--
-- Design: a *database fact* that identifies "this transaction created the
-- event", not a client-controlled boolean and not a timestamp guess.
--   * `ag_event_seals(event_id, created_xid)` is written by an AFTER INSERT
--     trigger on `ag_ledger_events`, recording `pg_current_xact_id()`;
--   * seal rows are immutable and undeletable, and `created_xid` must always
--     equal the inserting transaction's own id;
--   * a seal row can only be created while its event still has zero nodes, so
--     an already-populated legacy event can never acquire one;
--   * `ag_ledger_event_nodes` INSERT is refused unless a seal row for that
--     event was created **in the current transaction**.
--
-- Consequences:
--   * a legitimate first write (A1's RESERVE, A2's terminal) creates the event
--     and its whole root-to-leaf node set in one transaction and succeeds;
--   * a later transaction can never add, fix or extend a committed event, no
--     matter how "legitimate" its node shape looks;
--   * short legacy node sets stay exactly as they were and are quarantined at
--     runtime (sidecar) with their budget preserved, never patched up here.
--
-- Run-owned TRUNCATE cleanup is unaffected because row triggers do not fire on
-- TRUNCATE.

-- ------------------------------------------------------ pre-upgrade checks
-- Refuse a structurally broken database loudly instead of freezing it in.
-- Short-but-valid legacy sets are NOT refused: they must survive the upgrade
-- so the runtime can isolate them (A2-P19/OBL03).
DO $$
BEGIN
    IF EXISTS (
        WITH RECURSIVE up AS (
            SELECT o.operation_id AS op, g.grant_id AS gid, g.parent_grant_id AS parent
            FROM ag_operations o
            JOIN ag_grants g ON g.grant_id = o.grant_id
            UNION ALL
            SELECT up.op, p.grant_id, p.parent_grant_id
            FROM ag_grants p
            JOIN up ON p.grant_id = up.parent
        )
        SELECT 1
        FROM ag_ledger_event_nodes n
        JOIN ag_ledger_events e ON e.event_id = n.event_id
        WHERE NOT EXISTS (
            SELECT 1 FROM up WHERE up.op = e.operation_id AND up.gid = n.grant_id
        )
    ) THEN
        RAISE EXCEPTION
            '006 pre-check failed: ledger event nodes reference grants outside the operation path; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;
END $$;

-- ----------------------------------------------------------- the seal table
CREATE TABLE ag_event_seals (
    event_id    BIGINT PRIMARY KEY REFERENCES ag_ledger_events (event_id),
    created_xid TEXT NOT NULL
);

COMMENT ON TABLE ag_event_seals IS
    'Transaction identity that created each ledger event; the only fact that may write a node set.';

CREATE FUNCTION ag_event_seals_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ag_event_seals rows are immutable and cannot be deleted'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_event_seals_immutable_trg
    BEFORE UPDATE OR DELETE ON ag_event_seals
    FOR EACH ROW EXECUTE FUNCTION ag_event_seals_immutable();

CREATE FUNCTION ag_event_seals_insert_guard() RETURNS trigger AS $$
DECLARE
    v_nodes INT;
BEGIN
    IF NEW.created_xid IS DISTINCT FROM pg_current_xact_id()::text THEN
        RAISE EXCEPTION 'ag_event_seals.created_xid must be the current transaction'
            USING ERRCODE = '23514';
    END IF;
    -- a seal may only be born together with a still empty node set, so a
    -- populated legacy event can never acquire one after the fact
    SELECT count(*) INTO v_nodes FROM ag_ledger_event_nodes WHERE event_id = NEW.event_id;
    IF v_nodes <> 0 THEN
        RAISE EXCEPTION 'a seal cannot be created for an event that already has nodes'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_event_seals_insert_guard_trg
    BEFORE INSERT ON ag_event_seals
    FOR EACH ROW EXECUTE FUNCTION ag_event_seals_insert_guard();

-- every event born from now on is sealed by its creating transaction
CREATE FUNCTION ag_ledger_events_seal_local() RETURNS trigger AS $$
BEGIN
    INSERT INTO ag_event_seals (event_id, created_xid) VALUES (NEW.event_id, pg_current_xact_id()::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_ledger_events_seal_local_trg
    AFTER INSERT ON ag_ledger_events
    FOR EACH ROW EXECUTE FUNCTION ag_ledger_events_seal_local();

-- ------------------------------------------------- node writes need the seal
CREATE FUNCTION ag_ledger_event_nodes_seal_guard() RETURNS trigger AS $$
DECLARE
    v_xid TEXT;
BEGIN
    SELECT created_xid INTO v_xid FROM ag_event_seals WHERE event_id = NEW.event_id;
    IF v_xid IS NULL THEN
        RAISE EXCEPTION 'ledger event is already sealed: no node may be added'
            USING ERRCODE = '23514';
    END IF;
    IF v_xid IS DISTINCT FROM pg_current_xact_id()::text THEN
        RAISE EXCEPTION 'ledger event node set is sealed by another transaction'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_ledger_event_nodes_seal_guard_trg
    BEFORE INSERT ON ag_ledger_event_nodes
    FOR EACH ROW EXECUTE FUNCTION ag_ledger_event_nodes_seal_guard();

COMMENT ON FUNCTION ag_ledger_event_nodes_seal_guard() IS
    'Refuses any node write to a committed event; only the transaction that created the event may fill its node set.';
