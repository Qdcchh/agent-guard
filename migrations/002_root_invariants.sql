-- 002: task-root invariants and single-call billing (review F2/F4).
--
-- Never edit 001; this migration only adds constraints. It first checks
-- existing data and aborts loudly when inconsistencies are found — it never
-- deletes, resets or "fixes" rows on its own.
--
-- Enforcement added:
--   * at most one root grant per (tenant_id, task_id)   — partial unique index
--   * ag_tasks identity/root mapping immutable, no DELETE (no root rebuild)
--   * ag_tasks.root_grant_id references an existing root grant of the same
--     task (deferred FK + deferred constraint trigger for root-ness)
--   * every root grant maps back to its ag_tasks row (deferred trigger)
--   * operations always cost exactly one call (ag_operations.calls = 1)
--
-- Deferred mechanisms keep the existing creation order valid: the task row is
-- inserted before its root grant inside one transaction.

-- ------------------------------------------------------ pre-upgrade checks
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM ag_tasks t
        WHERE NOT EXISTS (
            SELECT 1 FROM ag_grants g
            WHERE g.grant_id = t.root_grant_id
              AND g.tenant_id = t.tenant_id
              AND g.task_id = t.task_id
              AND g.parent_grant_id IS NULL
        )
    ) THEN
        RAISE EXCEPTION
            '002 pre-check failed: ag_tasks rows with invalid root mapping exist; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT tenant_id, task_id FROM ag_grants
        WHERE parent_grant_id IS NULL
        GROUP BY tenant_id, task_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            '002 pre-check failed: multiple root grants for one task exist; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM ag_grants g
        WHERE g.parent_grant_id IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM ag_tasks t
            WHERE t.tenant_id = g.tenant_id
              AND t.task_id = g.task_id
              AND t.root_grant_id = g.grant_id
        )
    ) THEN
        RAISE EXCEPTION
            '002 pre-check failed: root grants without matching task mapping exist; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (SELECT 1 FROM ag_operations WHERE calls <> 1) THEN
        RAISE EXCEPTION
            '002 pre-check failed: operations with calls <> 1 exist; refusing to upgrade'
            USING ERRCODE = '23514';
    END IF;
END $$;

-- --------------------------------------------- one root node per task
CREATE UNIQUE INDEX ag_grants_one_root_per_task
    ON ag_grants (tenant_id, task_id)
    WHERE parent_grant_id IS NULL;

-- support for the composite root-mapping foreign key below
ALTER TABLE ag_grants
    ADD CONSTRAINT ag_grants_task_identity UNIQUE (tenant_id, task_id, grant_id);

-- ------------------------------- task identity/root mapping are immutable
CREATE FUNCTION ag_tasks_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'ag_tasks rows cannot be deleted (task roots must not be rebuilt)'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.task_id IS DISTINCT FROM OLD.task_id
        OR NEW.root_grant_id IS DISTINCT FROM OLD.root_grant_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'ag_tasks identity and root mapping are immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_tasks_guard_trg
    BEFORE UPDATE OR DELETE ON ag_tasks
    FOR EACH ROW EXECUTE FUNCTION ag_tasks_guard();

-- root mapping must reference an existing grant of the same tenant/task;
-- deferred so the documented create order (task row, then root grant) works
ALTER TABLE ag_tasks
    ADD CONSTRAINT ag_tasks_root_fk
    FOREIGN KEY (tenant_id, task_id, root_grant_id)
    REFERENCES ag_grants (tenant_id, task_id, grant_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION ag_tasks_root_is_root() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM ag_grants g
        WHERE g.grant_id = NEW.root_grant_id
          AND g.tenant_id = NEW.tenant_id
          AND g.task_id = NEW.task_id
          AND g.parent_grant_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'ag_tasks.root_grant_id must reference a root grant of the same task'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ag_tasks_root_mapping_trg
    AFTER INSERT OR UPDATE ON ag_tasks
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ag_tasks_root_is_root();

-- every root grant must map back to exactly one task row (cross-task/non-root
-- associations cannot be created behind the provisioning API)
CREATE FUNCTION ag_grants_root_mapping() RETURNS trigger AS $$
BEGIN
    IF NEW.parent_grant_id IS NULL AND NOT EXISTS (
        SELECT 1 FROM ag_tasks t
        WHERE t.tenant_id = NEW.tenant_id
          AND t.task_id = NEW.task_id
          AND t.root_grant_id = NEW.grant_id
    ) THEN
        RAISE EXCEPTION 'root grant must match the ag_tasks root mapping'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ag_grants_root_mapping_trg
    AFTER INSERT OR UPDATE ON ag_grants
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ag_grants_root_mapping();

-- ------------------------------------------- one call per operation (F4)
ALTER TABLE ag_operations
    ADD CONSTRAINT ag_operations_single_call CHECK (calls = 1);
