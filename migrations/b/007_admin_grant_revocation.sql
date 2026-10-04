-- 007: tenant-admin registry and immutable grant-level revocation events.
-- No existing authorization or ledger row is rewritten.

CREATE TABLE ag_tenant_admins (
    tenant_id       TEXT NOT NULL,
    subject         TEXT NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, subject)
);

COMMENT ON TABLE ag_tenant_admins IS
    'Trusted provisioning only; an HTTP request cannot enroll itself as an administrator.';

CREATE TABLE ag_grant_revocations (
    grant_id        TEXT PRIMARY KEY REFERENCES ag_grants (grant_id),
    tenant_id       TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    revocation_id   TEXT NOT NULL UNIQUE,
    admin_subject   TEXT NOT NULL,
    reason_code     TEXT NOT NULL CHECK (reason_code = 'USER_CANCELLED'),
    effective_at    TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, task_id) REFERENCES ag_tasks (tenant_id, task_id)
);

COMMENT ON TABLE ag_grant_revocations IS
    'One immutable administrator revocation record per target grant; subtree flags are updated atomically.';

CREATE FUNCTION ag_grant_revocations_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'grant revocation record is immutable'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_grant_revocations_immutable_trg
    BEFORE UPDATE OR DELETE ON ag_grant_revocations
    FOR EACH ROW EXECUTE FUNCTION ag_grant_revocations_immutable();
