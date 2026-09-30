-- 004: persisted one-use OAuth authorization codes and signed root snapshots.
--
-- Additive only. Existing A1 grant/task rows are untouched. These tables are
-- for the AS process; this migration does not expose an HTTP login bypass.

CREATE TABLE ag_authorization_codes (
    code_sha256       BYTEA PRIMARY KEY CHECK (octet_length(code_sha256) = 32),
    tenant_id         TEXT NOT NULL,
    task_id           TEXT NOT NULL,
    subject           TEXT NOT NULL,
    client_id         TEXT NOT NULL,
    holder_kid        TEXT NOT NULL,
    holder_spki_sm3   TEXT NOT NULL,
    redirect_uri      TEXT NOT NULL,
    pkce_challenge    TEXT NOT NULL,
    nonce             TEXT NOT NULL,
    auth_time         BIGINT NOT NULL CHECK (auth_time BETWEEN 0 AND 9007199254740991),
    scope             TEXT NOT NULL,
    constraints_json  BYTEA NOT NULL,
    amount_limit_fen  BIGINT NOT NULL CHECK (amount_limit_fen BETWEEN 0 AND 9007199254740991),
    call_limit        BIGINT NOT NULL CHECK (call_limit BETWEEN 0 AND 9007199254740991),
    task_expires_at   TIMESTAMPTZ NOT NULL,
    consent_ref       TEXT NOT NULL,
    consented_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at        TIMESTAMPTZ NOT NULL,
    consumed_at       TIMESTAMPTZ,
    root_grant_id     TEXT REFERENCES ag_grants (grant_id),
    CHECK ((consumed_at IS NULL) = (root_grant_id IS NULL)),
    CHECK (expires_at > consented_at AND expires_at <= consented_at + INTERVAL '60 seconds'),
    CHECK (task_expires_at > consented_at)
);

COMMENT ON TABLE ag_authorization_codes IS
    'One-use hashed codes from separately authenticated and recorded user consent; no raw code stored.';

CREATE INDEX ag_authorization_codes_task_idx
    ON ag_authorization_codes (tenant_id, task_id);

CREATE TABLE ag_grant_tokens (
    grant_id          TEXT PRIMARY KEY REFERENCES ag_grants (grant_id),
    token_jws         TEXT NOT NULL,
    token_sm3         TEXT NOT NULL,
    scope             TEXT NOT NULL,
    constraints_json  BYTEA NOT NULL,
    actor_json        BYTEA NOT NULL,
    holder_spki_sm3   TEXT NOT NULL,
    issued_at         TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at        TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE ag_grant_tokens IS
    'Immutable AS token and permission snapshot for each grant; access restricted to trusted AS state role.';

CREATE FUNCTION ag_grant_tokens_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'grant token snapshots are immutable'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_grant_tokens_immutable_trg
    BEFORE UPDATE OR DELETE ON ag_grant_tokens
    FOR EACH ROW EXECUTE FUNCTION ag_grant_tokens_immutable();

CREATE TABLE ag_auth_evidence (
    evidence_id      TEXT PRIMARY KEY,
    code_sha256      BYTEA NOT NULL REFERENCES ag_authorization_codes (code_sha256),
    request_sm3      TEXT NOT NULL,
    proof_jws        TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE ag_auth_evidence IS
    'Restricted proof evidence for code exchange; stores no raw authorization code or client secret.';
