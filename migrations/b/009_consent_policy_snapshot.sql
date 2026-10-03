-- Persist exactly the task policy presented on each authorization page.
-- Existing pending requests have no snapshot and must fail closed at approval.
ALTER TABLE ag_authorization_requests
    ADD COLUMN policy_snapshot_json BYTEA;

ALTER TABLE ag_task_policies
    ADD COLUMN policy_version BIGINT NOT NULL DEFAULT 1 CHECK (policy_version >= 1);

CREATE FUNCTION ag_bump_task_policy_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.policy_version := OLD.policy_version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER ag_task_policy_version_bump
BEFORE UPDATE ON ag_task_policies
FOR EACH ROW EXECUTE FUNCTION ag_bump_task_policy_version();

COMMENT ON COLUMN ag_authorization_requests.policy_snapshot_json IS
    'Canonical policy shown to the user; NULL legacy pending requests cannot be approved.';

COMMENT ON COLUMN ag_task_policies.policy_version IS
    'Monotonic policy revision; changing and restoring the same values still invalidates old consent.';
