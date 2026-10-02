-- 005: seal ledger event node sets (A21-R1-EVENT).
--
-- Never edit 001-004. This migration only ADDS a helper function and triggers.
-- It never adds a column to the legacy tables and never rewrites an existing
-- row: `SELECT *` snapshots of the seven legacy business tables are unchanged
-- before and after a legal upgrade.
--
-- Why this exists: 004 blocks UPDATE and DELETE on `ag_ledger_events` and
-- `ag_ledger_event_nodes`, but a committed event could still have extra rows
-- INSERTed into `ag_ledger_event_nodes`. The outbox's ledger_changes would then
-- disagree with the database. 005 makes the node set of an event a closed,
-- exactly-shaped object:
--
--   * nodes are written contiguously from position 0 and must land on the
--     root-to-leaf grant path of the operation at that position;
--   * each node's deltas must be exactly the ones its phase implies for the
--     accepted cost (RESERVE reserves, SETTLE moves reserved -> settled,
--     RELEASE only drops the reservation);
--   * the set cannot grow past the path length, so a committed event can never
--     be appended to;
--   * at COMMIT a deferred constraint trigger requires the set to be complete,
--     so a partial write is rolled back as a whole.
--
-- Legitimate first writes are unaffected: A1's RESERVE insert and A2's
-- terminal insert both write the whole path inside one transaction. Run-owned
-- TRUNCATE cleanup is unaffected because row triggers do not fire on TRUNCATE.

-- ------------------------------------------------------ pre-upgrade checks
-- These refuse a structurally broken legacy database loudly instead of
-- "fixing" it. An event whose node set is merely *short* is not refused here:
-- such an operation is quarantined at runtime (sidecar) with its budget
-- preserved and no downstream effect, which is the A2-P19/OBL03 requirement.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM ag_ledger_event_nodes n
        WHERE NOT EXISTS (SELECT 1 FROM ag_grants g WHERE g.grant_id = n.grant_id)
    ) THEN
        RAISE EXCEPTION
            '005 pre-check failed: ledger event nodes reference unknown grants; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM ag_ledger_events e
        WHERE NOT EXISTS (SELECT 1 FROM ag_ledger_event_nodes n WHERE n.event_id = e.event_id)
    ) THEN
        RAISE EXCEPTION
            '005 pre-check failed: ledger events without any node exist; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        WITH path_len AS (
            SELECT o.operation_id, g.depth + 1 AS expected
            FROM ag_operations o
            JOIN ag_grants g ON g.grant_id = o.grant_id
        )
        SELECT 1
        FROM ag_ledger_events e
        JOIN path_len p ON p.operation_id = e.operation_id
        WHERE (SELECT count(*) FROM ag_ledger_event_nodes n WHERE n.event_id = e.event_id) > p.expected
    ) THEN
        RAISE EXCEPTION
            '005 pre-check failed: a ledger event has more nodes than its grant path; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;
END $$;

-- ------------------------------------------ root-to-leaf path of an operation
CREATE FUNCTION ag_operation_path_ids(op TEXT) RETURNS TEXT[] AS $$
DECLARE
    result TEXT[];
BEGIN
    SELECT array_agg(x.gid ORDER BY x.pos) INTO result
    FROM (
        WITH RECURSIVE up AS (
            SELECT g.grant_id AS gid, g.parent_grant_id AS parent, g.depth AS pos
            FROM ag_grants g
            JOIN ag_operations o ON o.grant_id = g.grant_id
            WHERE o.operation_id = op
            UNION ALL
            SELECT p.grant_id, p.parent_grant_id, p.depth
            FROM ag_grants p
            JOIN up ON p.grant_id = up.parent
        )
        SELECT gid, pos FROM up
    ) AS x;
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION ag_operation_path_ids(TEXT) IS
    'Immutable root-to-leaf grant path of one accepted operation; used to seal ledger event node sets.';

-- ------------------------------------------------- node insert is shape-safe
CREATE FUNCTION ag_ledger_event_nodes_guard_insert() RETURNS trigger AS $$
DECLARE
    v_operation_id TEXT;
    v_phase        TEXT;
    v_amount       BIGINT;
    v_calls        BIGINT;
    v_path         TEXT[];
    v_expected     INT;
    v_current      INT;
BEGIN
    SELECT e.operation_id, e.phase
      INTO v_operation_id, v_phase
      FROM ag_ledger_events e
     WHERE e.event_id = NEW.event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ag_ledger_event_nodes references an unknown event'
            USING ERRCODE = '23514';
    END IF;

    SELECT o.amount_fen, o.calls INTO v_amount, v_calls
      FROM ag_operations o
     WHERE o.operation_id = v_operation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ag_ledger_event_nodes references an unknown operation'
            USING ERRCODE = '23514';
    END IF;

    v_path := ag_operation_path_ids(v_operation_id);
    IF v_path IS NULL THEN
        RAISE EXCEPTION 'operation grant path cannot be resolved'
            USING ERRCODE = '23514';
    END IF;
    v_expected := coalesce(array_length(v_path, 1), 0);

    SELECT count(*) INTO v_current
      FROM ag_ledger_event_nodes
     WHERE event_id = NEW.event_id;

    IF NEW.position IS DISTINCT FROM v_current THEN
        RAISE EXCEPTION 'ledger event nodes must be written contiguously from position 0'
            USING ERRCODE = '23514';
    END IF;
    IF v_current + 1 > v_expected THEN
        RAISE EXCEPTION 'ledger event node set is already complete (append refused)'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.grant_id IS DISTINCT FROM v_path[NEW.position + 1] THEN
        RAISE EXCEPTION 'ledger event node does not match the grant path at its position'
            USING ERRCODE = '23514';
    END IF;

    IF v_phase = 'RESERVE' THEN
        IF NEW.amount_reserved_delta IS DISTINCT FROM v_amount
            OR NEW.amount_settled_delta IS DISTINCT FROM 0
            OR NEW.calls_reserved_delta IS DISTINCT FROM v_calls
            OR NEW.calls_settled_delta IS DISTINCT FROM 0 THEN
            RAISE EXCEPTION 'RESERVE event node deltas do not match the accepted cost'
                USING ERRCODE = '23514';
        END IF;
    ELSIF v_phase = 'SETTLE' THEN
        IF NEW.amount_reserved_delta IS DISTINCT FROM -v_amount
            OR NEW.amount_settled_delta IS DISTINCT FROM v_amount
            OR NEW.calls_reserved_delta IS DISTINCT FROM -v_calls
            OR NEW.calls_settled_delta IS DISTINCT FROM v_calls THEN
            RAISE EXCEPTION 'SETTLE event node deltas do not match the accepted cost'
                USING ERRCODE = '23514';
        END IF;
    ELSIF v_phase = 'RELEASE' THEN
        IF NEW.amount_reserved_delta IS DISTINCT FROM -v_amount
            OR NEW.amount_settled_delta IS DISTINCT FROM 0
            OR NEW.calls_reserved_delta IS DISTINCT FROM -v_calls
            OR NEW.calls_settled_delta IS DISTINCT FROM 0 THEN
            RAISE EXCEPTION 'RELEASE event node deltas do not match the accepted cost'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        RAISE EXCEPTION 'unknown ledger event phase' USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_ledger_event_nodes_guard_insert_trg
    BEFORE INSERT ON ag_ledger_event_nodes
    FOR EACH ROW EXECUTE FUNCTION ag_ledger_event_nodes_guard_insert();

-- ------------------------------------------- completeness sealed at COMMIT
-- A deferred constraint trigger runs at COMMIT, so a transaction that writes
-- only part of the node set is rolled back as a whole and never becomes a
-- committed, incomplete event.
CREATE FUNCTION ag_ledger_events_complete_set() RETURNS trigger AS $$
DECLARE
    v_expected INT;
    v_actual   INT;
BEGIN
    v_expected := coalesce(array_length(ag_operation_path_ids(NEW.operation_id), 1), 0);
    IF v_expected = 0 THEN
        RAISE EXCEPTION 'ledger event references an operation without a grant path'
            USING ERRCODE = '23514';
    END IF;
    SELECT count(*) INTO v_actual
      FROM ag_ledger_event_nodes
     WHERE event_id = NEW.event_id;
    IF v_actual IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION 'ledger event node set is incomplete at commit'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ag_ledger_events_complete_set_trg
    AFTER INSERT ON ag_ledger_events
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ag_ledger_events_complete_set();

COMMENT ON FUNCTION ag_ledger_events_complete_set() IS
    'Seals each ledger event node set at COMMIT: exactly the full root-to-leaf path, no more, no less.';
