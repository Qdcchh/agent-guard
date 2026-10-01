-- 005: AS-owned immutable child issuance and scoped delegation idempotency.
-- Existing grants/operations are unchanged; apply after 004.

CREATE TABLE ag_delegations (
    parent_grant_id      TEXT NOT NULL REFERENCES ag_grants (grant_id),
    requesting_client_id TEXT NOT NULL,
    delegation_key       TEXT NOT NULL,
    intent_sm3           TEXT NOT NULL,
    intent_json          BYTEA NOT NULL,
    child_grant_id       TEXT NOT NULL UNIQUE REFERENCES ag_grants (grant_id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (parent_grant_id, requesting_client_id, delegation_key)
);

COMMENT ON TABLE ag_delegations IS
    'One immutable child per parent/requester/business key; intent stores a token digest, not a second raw token. Original signed token is in ag_grant_tokens.';

CREATE FUNCTION ag_delegations_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'delegation intent and child relation are immutable'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ag_delegations_immutable_trg
    BEFORE UPDATE OR DELETE ON ag_delegations
    FOR EACH ROW EXECUTE FUNCTION ag_delegations_immutable();

CREATE TABLE ag_exchange_evidence (
    evidence_id      TEXT PRIMARY KEY,
    parent_grant_id  TEXT NOT NULL REFERENCES ag_grants (grant_id),
    child_grant_id   TEXT REFERENCES ag_grants (grant_id),
    request_sm3      TEXT NOT NULL,
    proof_jws        TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE ag_exchange_evidence IS
    'Restricted proof record for original and retried exchanges; no client secret or private key.';

CREATE TRIGGER ag_exchange_evidence_immutable_trg
    BEFORE UPDATE OR DELETE ON ag_exchange_evidence
    FOR EACH ROW EXECUTE FUNCTION ag_delegations_immutable();
