-- 006: durable, idempotent task-owner revocation records.
-- Apply after 005; existing grants and ledger operations are not rewritten.

CREATE TABLE ag_task_revocations (
    tenant_id      TEXT NOT NULL,
    task_id        TEXT NOT NULL,
    root_grant_id  TEXT NOT NULL REFERENCES ag_grants (grant_id),
    revocation_id  TEXT NOT NULL UNIQUE,
    subject        TEXT NOT NULL,
    reason_code    TEXT NOT NULL CHECK (reason_code = 'USER_CANCELLED'),
    effective_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, task_id),
    FOREIGN KEY (tenant_id, task_id) REFERENCES ag_tasks (tenant_id, task_id)
);

COMMENT ON TABLE ag_task_revocations IS
    'One immutable user cancellation per task; only trusted authenticated session code may request it.';

CREATE FUNCTION ag_task_revocations_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'task revocation record is immutable'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_task_revocations_immutable_trg
    BEFORE UPDATE OR DELETE ON ag_task_revocations
    FOR EACH ROW EXECUTE FUNCTION ag_task_revocations_immutable();
