-- 003: preserve root grant lifecycle state (review F2 remainder).
-- A deferred task FK permits same-ID delete/reinsert within a transaction.
-- Reject root deletion before it can discard counters or revocation state.
-- No stored rows are changed; legitimate counter/revocation UPDATEs and
-- non-root DELETE semantics are unchanged. Never edit applied 001/002.
CREATE FUNCTION ag_grants_root_delete_guard() RETURNS trigger AS $$
BEGIN
    IF OLD.parent_grant_id IS NULL THEN
        RAISE EXCEPTION 'root grants cannot be deleted (task roots must not be rebuilt)'
            USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_grants_root_delete_guard_trg
    BEFORE DELETE ON ag_grants
    FOR EACH ROW EXECUTE FUNCTION ag_grants_root_delete_guard();
