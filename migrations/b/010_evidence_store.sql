-- Restricted exact verified material. Orphan staging is retained indefinitely;
-- automatic expiry/deletion is deliberately not implemented.
CREATE TABLE ag_verified_evidence (
    evidence_ref TEXT PRIMARY KEY CHECK (evidence_ref ~ '^ev-[0-9a-f]{64}$'),
    token_bytes BYTEA NOT NULL CHECK (octet_length(token_bytes) BETWEEN 1 AND 16384),
    proof_bytes BYTEA NOT NULL CHECK (octet_length(proof_bytes) BETWEEN 1 AND 16384),
    body_bytes BYTEA NOT NULL CHECK (octet_length(body_bytes) BETWEEN 1 AND 65536),
    token_sm3 TEXT NOT NULL,
    proof_sm3 TEXT NOT NULL,
    body_sm3 TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    root_id TEXT NOT NULL,
    holder_client_id TEXT NOT NULL,
    holder_kid TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('invoke', 'result-read')),
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method = 'POST'),
    proof_jti TEXT NOT NULL,
    chain_json BYTEA NOT NULL,
    context_json BYTEA NOT NULL,
    state TEXT NOT NULL DEFAULT 'STAGED' CHECK (state = 'STAGED'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ag_operation_evidence (
    evidence_ref TEXT PRIMARY KEY REFERENCES ag_verified_evidence(evidence_ref),
    operation_id TEXT NOT NULL REFERENCES ag_operations(operation_id),
    kind TEXT NOT NULL CHECK (kind IN ('first', 'retry')),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX ag_operation_first_evidence ON ag_operation_evidence(operation_id)
WHERE kind = 'first';
CREATE FUNCTION ag_verified_evidence_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'verified evidence and accepted links are immutable' USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER ag_verified_evidence_guard BEFORE UPDATE OR DELETE ON ag_verified_evidence
FOR EACH ROW EXECUTE FUNCTION ag_verified_evidence_immutable();
CREATE TRIGGER ag_operation_evidence_guard BEFORE UPDATE OR DELETE ON ag_operation_evidence
FOR EACH ROW EXECUTE FUNCTION ag_verified_evidence_immutable();
REVOKE ALL ON ag_verified_evidence, ag_operation_evidence FROM PUBLIC;
