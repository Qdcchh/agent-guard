-- 009: x402 payment intent, independent asset budget and durable payment state.
--
-- The immutable payment intent is written in the *same* accept transaction as
-- the operation, its CNY reservation and its threshold approval binding. It is
-- covered by the V3 approval payment digest and references that exact approval
-- row through a composite foreign key, so a payment can only exist when the
-- signed quorum approval committed to the same payment facts. State transitions
-- (UNPAID -> AUTHORIZED -> SUBMITTING -> SETTLED/FAILED/UNKNOWN) are persisted
-- separately and never rewrite the intent. Database triggers keep intents and
-- approvals immutable and reject illegal state transitions even if a buggy
-- writer tries them.
--
-- This migration only adds tables, guards and one sidecar column; earlier
-- migrations, historical rows and the seven legacy business tables are
-- untouched.
ALTER TABLE ag_threshold_approvals
    ADD COLUMN payment_digest TEXT
    CHECK (payment_digest IS NULL OR payment_digest ~ '^[0-9a-f]{64}$');

COMMENT ON COLUMN ag_threshold_approvals.payment_digest IS
    'V3 approval-only digest of the complete x402 payment facts; NULL for V2 approvals.';

-- Composite key lets the payment intent reference (tenant, task, action,
-- digest) so the database itself refuses a payment whose digest differs from
-- the approved one.
ALTER TABLE ag_threshold_approvals
    ADD CONSTRAINT ag_threshold_approvals_action_payment_key
    UNIQUE (tenant_id, task_id, action_id, payment_digest);

CREATE TABLE ag_payment_intents (
    operation_id    TEXT PRIMARY KEY REFERENCES ag_operations (operation_id),
    tenant_id       TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    grant_id        TEXT NOT NULL,
    root_grant_id   TEXT NOT NULL,
    action_id       TEXT NOT NULL CHECK (length(action_id) BETWEEN 1 AND 128),
    payment_digest  TEXT NOT NULL CHECK (payment_digest ~ '^[0-9a-f]{64}$'),
    tool_id         TEXT NOT NULL CHECK (tool_id = 'procurement.order.create'),
    idempotency_key TEXT NOT NULL,
    profile         TEXT NOT NULL CHECK (profile = 'AG-X402-PAYMENT-INTENT-1'),
    scheme          TEXT NOT NULL CHECK (scheme = 'exact'),
    transfer_method TEXT NOT NULL CHECK (transfer_method = 'eip3009'),
    network         TEXT NOT NULL CHECK (network ~ '^eip155:[1-9][0-9]{0,17}$'),
    chain_id        BIGINT NOT NULL CHECK (chain_id BETWEEN 1 AND 9007199254740991),
    asset           TEXT NOT NULL CHECK (asset ~ '^0x[0-9a-f]{40}$'),
    asset_name      TEXT NOT NULL CHECK (length(asset_name) BETWEEN 1 AND 128),
    asset_version   TEXT NOT NULL CHECK (length(asset_version) BETWEEN 1 AND 32),
    asset_amount    NUMERIC(78, 0) NOT NULL CHECK (asset_amount > 0),
    pay_to          TEXT NOT NULL CHECK (pay_to ~ '^0x[0-9a-f]{40}$'),
    resource_url    TEXT NOT NULL CHECK (length(resource_url) BETWEEN 1 AND 512),
    amount_fen      BIGINT NOT NULL CHECK (amount_fen BETWEEN 0 AND 9007199254740991),
    quote_id        TEXT NOT NULL,
    quote_version   TEXT NOT NULL,
    valid_before    BIGINT NOT NULL CHECK (valid_before BETWEEN 1 AND 9007199254740991),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (tenant_id, task_id, quote_id, quote_version),
    FOREIGN KEY (tenant_id, task_id, action_id, payment_digest)
        REFERENCES ag_threshold_approvals (tenant_id, task_id, action_id, payment_digest)
);

COMMENT ON TABLE ag_payment_intents IS
    'Immutable x402 payment facts fixed in the accept transaction and covered by the V3 threshold approval digest; one quote version maps to at most one payment.';

CREATE FUNCTION ag_payment_intents_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'x402 payment intents are immutable'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_payment_intents_guard_trg
    BEFORE UPDATE OR DELETE ON ag_payment_intents
    FOR EACH ROW EXECUTE FUNCTION ag_payment_intents_guard();

REVOKE ALL ON ag_payment_intents FROM PUBLIC;

CREATE TABLE ag_payment_budgets (
    tenant_id       TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    asset           TEXT NOT NULL CHECK (asset ~ '^0x[0-9a-f]{40}$'),
    chain_id        BIGINT NOT NULL CHECK (chain_id BETWEEN 1 AND 9007199254740991),
    amount_limit    NUMERIC(78, 0) NOT NULL CHECK (amount_limit > 0),
    amount_reserved NUMERIC(78, 0) NOT NULL DEFAULT 0 CHECK (amount_reserved >= 0),
    amount_settled  NUMERIC(78, 0) NOT NULL DEFAULT 0 CHECK (amount_settled >= 0),
    PRIMARY KEY (tenant_id, task_id, asset, chain_id),
    CHECK (amount_reserved + amount_settled <= amount_limit)
);

COMMENT ON TABLE ag_payment_budgets IS
    'Independent, explicitly seeded test-asset budget per tenant/task/asset; no implicit CNY conversion and no implicit budget creation.';

CREATE FUNCTION ag_payment_budgets_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'payment budgets cannot be deleted' USING ERRCODE = '23514';
    END IF;
    IF NEW.tenant_id <> OLD.tenant_id
        OR NEW.task_id <> OLD.task_id
        OR NEW.asset <> OLD.asset
        OR NEW.chain_id <> OLD.chain_id
        OR NEW.amount_limit <> OLD.amount_limit THEN
        RAISE EXCEPTION 'payment budget identity and limit are immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_payment_budgets_guard_trg
    BEFORE UPDATE OR DELETE ON ag_payment_budgets
    FOR EACH ROW EXECUTE FUNCTION ag_payment_budgets_guard();

REVOKE ALL ON ag_payment_budgets FROM PUBLIC;

CREATE TABLE ag_payment_states (
    operation_id      TEXT PRIMARY KEY REFERENCES ag_payment_intents (operation_id),
    status            TEXT NOT NULL CHECK (status IN (
                          'UNPAID', 'AUTHORIZED', 'SUBMITTING', 'SETTLED', 'FAILED', 'UNKNOWN'
                      )),
    nonce             TEXT CHECK (nonce IS NULL OR nonce ~ '^0x[0-9a-f]{64}$'),
    authorization_json BYTEA CHECK (
                          authorization_json IS NULL
                          OR octet_length(authorization_json) BETWEEN 1 AND 8192
                      ),
    payload_json      BYTEA CHECK (
                          payload_json IS NULL
                          OR octet_length(payload_json) BETWEEN 1 AND 65536
                      ),
    payload_sha256    TEXT CHECK (
                          payload_sha256 IS NULL OR payload_sha256 ~ '^[0-9a-f]{64}$'
                      ),
    tx_hash           TEXT CHECK (tx_hash IS NULL OR tx_hash ~ '^0x[0-9a-f]{64}$'),
    failure_code      TEXT CHECK (
                          failure_code IS NULL OR failure_code ~ '^[A-Z0-9_]{1,64}$'
                      ),
    authorized_at     TIMESTAMPTZ,
    submitted_at      TIMESTAMPTZ,
    settled_at        TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (status IN ('UNPAID', 'FAILED') OR (nonce IS NOT NULL AND payload_sha256 IS NOT NULL)),
    CHECK (status <> 'SETTLED' OR (tx_hash IS NOT NULL AND settled_at IS NOT NULL))
);

COMMENT ON TABLE ag_payment_states IS
    'Durable x402 payment state; authorization material is persisted before any network call and is never rewritten.';

CREATE FUNCTION ag_payment_states_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'payment states cannot be deleted' USING ERRCODE = '23514';
    END IF;
    IF NOT (
        (OLD.status = 'UNPAID' AND NEW.status IN ('AUTHORIZED', 'UNKNOWN', 'FAILED'))
        OR (OLD.status = 'AUTHORIZED' AND NEW.status IN ('SUBMITTING', 'UNKNOWN', 'FAILED'))
        OR (OLD.status = 'SUBMITTING' AND NEW.status IN ('UNKNOWN', 'SETTLED', 'FAILED'))
        OR (OLD.status = 'UNKNOWN' AND NEW.status IN ('AUTHORIZED', 'SUBMITTING', 'SETTLED', 'FAILED'))
    ) THEN
        RAISE EXCEPTION 'illegal x402 payment transition % -> %', OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF OLD.nonce IS NOT NULL AND NEW.nonce IS DISTINCT FROM OLD.nonce THEN
        RAISE EXCEPTION 'payment nonce is immutable' USING ERRCODE = '23514';
    END IF;
    IF OLD.authorization_json IS NOT NULL
        AND NEW.authorization_json IS DISTINCT FROM OLD.authorization_json THEN
        RAISE EXCEPTION 'payment authorization is immutable' USING ERRCODE = '23514';
    END IF;
    IF OLD.payload_json IS NOT NULL AND NEW.payload_json IS DISTINCT FROM OLD.payload_json THEN
        RAISE EXCEPTION 'payment payload is immutable' USING ERRCODE = '23514';
    END IF;
    IF OLD.payload_sha256 IS NOT NULL
        AND NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256 THEN
        RAISE EXCEPTION 'payment payload hash is immutable' USING ERRCODE = '23514';
    END IF;
    IF OLD.tx_hash IS NOT NULL AND NEW.tx_hash IS DISTINCT FROM OLD.tx_hash THEN
        RAISE EXCEPTION 'settlement transaction is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_payment_states_guard_trg
    BEFORE UPDATE OR DELETE ON ag_payment_states
    FOR EACH ROW EXECUTE FUNCTION ag_payment_states_guard();

REVOKE ALL ON ag_payment_states FROM PUBLIC;
