-- 008: trusted user accounts, server-side login sessions and CSRF, task
-- policies, server-side browser authorization requests, and login/consent
-- audit events. Additive only; no existing authorization or ledger row is
-- rewritten and no HTTP body can self-enroll a user or an administrator.

CREATE TABLE ag_users (
    tenant_id     TEXT NOT NULL,
    subject       TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, subject)
);

COMMENT ON TABLE ag_users IS
    'Trusted provisioning only; password_hash is a mature KDF encoding, never a bare SM3/SHA digest.';

CREATE TABLE ag_task_policies (
    tenant_id        TEXT NOT NULL,
    task_id          TEXT NOT NULL,
    owner_subject    TEXT NOT NULL,
    scope            TEXT NOT NULL,
    constraints_json BYTEA NOT NULL,
    amount_limit_fen BIGINT NOT NULL CHECK (amount_limit_fen BETWEEN 0 AND 9007199254740991),
    call_limit       BIGINT NOT NULL CHECK (call_limit BETWEEN 0 AND 9007199254740991),
    task_expires_at  TIMESTAMPTZ NOT NULL,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, task_id)
);

COMMENT ON TABLE ag_task_policies IS
    'Server-side task boundary shown to the consent UI; the client cannot submit or widen it.';

CREATE TABLE ag_login_csrf (
    token_sha256 BYTEA PRIMARY KEY CHECK (octet_length(token_sha256) = 32),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);

COMMENT ON TABLE ag_login_csrf IS
    'One-use pre-authentication CSRF tokens; only the SHA-256 digest is stored.';

CREATE TABLE ag_login_sessions (
    session_sha256 BYTEA PRIMARY KEY CHECK (octet_length(session_sha256) = 32),
    tenant_id      TEXT NOT NULL,
    subject        TEXT NOT NULL,
    auth_time      BIGINT NOT NULL CHECK (auth_time BETWEEN 0 AND 9007199254740991),
    csrf_sha256    BYTEA NOT NULL CHECK (octet_length(csrf_sha256) = 32),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at     TIMESTAMPTZ NOT NULL,
    revoked_at     TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, subject) REFERENCES ag_users (tenant_id, subject),
    CHECK (expires_at > created_at)
);

COMMENT ON TABLE ag_login_sessions IS
    'Server-side session; only token digests are stored, never raw session or CSRF tokens.';

CREATE TABLE ag_authorization_requests (
    request_id     TEXT PRIMARY KEY,
    session_sha256 BYTEA NOT NULL REFERENCES ag_login_sessions (session_sha256),
    tenant_id      TEXT NOT NULL,
    task_id        TEXT NOT NULL,
    subject        TEXT NOT NULL,
    client_id      TEXT NOT NULL,
    redirect_uri   TEXT NOT NULL,
    scope          TEXT NOT NULL,
    pkce_challenge TEXT NOT NULL,
    nonce          TEXT NOT NULL,
    state          TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    consent_ref    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at     TIMESTAMPTZ NOT NULL,
    decided_at     TIMESTAMPTZ,
    CHECK (expires_at > created_at),
    CHECK ((status = 'pending') = (decided_at IS NULL))
);

COMMENT ON TABLE ag_authorization_requests IS
    'Validated browser authorization request bound to one login session; consent reads only this row.';

CREATE TABLE ag_auth_events (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL CHECK (event_type IN ('login', 'authorize_request', 'consent')),
    tenant_id   TEXT NOT NULL,
    subject     TEXT NOT NULL,
    request_id  TEXT,
    detail_json BYTEA NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE ag_auth_events IS
    'Append-only login, authorization-request and consent records; stores no password, secret or raw token.';
