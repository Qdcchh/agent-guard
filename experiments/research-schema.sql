-- Research-only schema on the same owned authority instance. No production budget writes.
CREATE SCHEMA IF NOT EXISTS r34;
CREATE TABLE r34.counters (
 grant_id text PRIMARY KEY REFERENCES public.ag_grants(grant_id),
 amount_reserved bigint NOT NULL DEFAULT 0 CHECK(amount_reserved BETWEEN 0 AND 9007199254740991),
 amount_settled bigint NOT NULL DEFAULT 0 CHECK(amount_settled BETWEEN 0 AND 9007199254740991),
 calls_reserved bigint NOT NULL DEFAULT 0 CHECK(calls_reserved BETWEEN 0 AND 9007199254740991),
 calls_settled bigint NOT NULL DEFAULT 0 CHECK(calls_settled BETWEEN 0 AND 9007199254740991),
 amount_high_water bigint NOT NULL DEFAULT 0,
 calls_high_water bigint NOT NULL DEFAULT 0
);
-- Deliberately no total<=limit constraint: noAtomic is an explicit unsafe research baseline.
CREATE TABLE r34.originals (
 reference text PRIMARY KEY,
 token bytea, proof bytea, body bytea NOT NULL
);
CREATE TABLE r34.operations (
 operation_id text PRIMARY KEY, mode text NOT NULL CHECK(mode IN ('noAtomic','Bearer','staticACL')),
 tenant_id text NOT NULL, task_id text NOT NULL, subject text NOT NULL,
 grant_id text NOT NULL, root_id text NOT NULL, client_id text NOT NULL, kid text NOT NULL,
 tool_id text NOT NULL, tool_version text NOT NULL CHECK(tool_version='1'), business_key text NOT NULL,
 canonical_params bytea NOT NULL, canonical_body bytea NOT NULL, intent_digest text NOT NULL,
 amount_fen bigint NOT NULL CHECK(amount_fen BETWEEN 0 AND 9007199254740991),
 calls bigint NOT NULL CHECK(calls=1), quote_snapshot bytea,
 path_ids text[] NOT NULL CHECK(cardinality(path_ids) BETWEEN 1 AND 3),
 first_ref text NOT NULL REFERENCES r34.originals(reference), source_material bytea NOT NULL,
 status text NOT NULL CHECK(status IN ('RESERVED','EXECUTING','UNKNOWN','SUCCEEDED','FAILED')) DEFAULT 'RESERVED',
 accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(mode,tenant_id,task_id,tool_id,business_key)
);
CREATE TABLE r34.proofs (
 kid text NOT NULL, purpose text NOT NULL, endpoint text NOT NULL, jti text NOT NULL,
 digest text NOT NULL, evidence_ref text NOT NULL, operation_id text REFERENCES r34.operations,
 PRIMARY KEY(kid,purpose,endpoint,jti)
);
CREATE TABLE r34.events (
 event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 operation_id text NOT NULL REFERENCES r34.operations, phase text NOT NULL,
 seq integer NOT NULL, at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((phase='RESERVE' AND seq=0) OR (phase IN ('SETTLE','RELEASE') AND seq=1)),
 UNIQUE(operation_id,seq)
);
CREATE TABLE r34.nodes (
 event_id bigint NOT NULL REFERENCES r34.events, position integer NOT NULL CHECK(position BETWEEN 0 AND 2),
 grant_id text NOT NULL REFERENCES r34.counters,
 amount_reserved_delta bigint NOT NULL, amount_settled_delta bigint NOT NULL,
 calls_reserved_delta bigint NOT NULL, calls_settled_delta bigint NOT NULL,
 PRIMARY KEY(event_id,position), UNIQUE(event_id,grant_id),
 CHECK(abs(amount_reserved_delta)<=9007199254740991 AND abs(amount_settled_delta)<=9007199254740991
 AND abs(calls_reserved_delta)<=9007199254740991 AND abs(calls_settled_delta)<=9007199254740991)
);
CREATE TABLE r34.leases (
 operation_id text PRIMARY KEY REFERENCES r34.operations,
 owner text NOT NULL, version bigint NOT NULL CHECK(version BETWEEN 1 AND 9007199254740991),
 expires_at timestamptz NOT NULL
);
CREATE TABLE r34.outbox (
 operation_id text PRIMARY KEY REFERENCES r34.operations,
 status text NOT NULL CHECK(status IN ('SUCCEEDED','FAILED')),
 result_bytes bytea NOT NULL, quote_snapshot bytea,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 signature_capability text NOT NULL DEFAULT 'NOT_APPLICABLE' CHECK(signature_capability='NOT_APPLICABLE')
);
CREATE FUNCTION r34.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable research material' USING ERRCODE='23514'; END $$;
CREATE TRIGGER immutable_originals BEFORE UPDATE OR DELETE ON r34.originals FOR EACH ROW EXECUTE FUNCTION r34.immutable();
CREATE TRIGGER immutable_events BEFORE UPDATE OR DELETE ON r34.events FOR EACH ROW EXECUTE FUNCTION r34.immutable();
CREATE TRIGGER immutable_nodes BEFORE UPDATE OR DELETE ON r34.nodes FOR EACH ROW EXECUTE FUNCTION r34.immutable();
CREATE TRIGGER immutable_outbox BEFORE UPDATE OR DELETE ON r34.outbox FOR EACH ROW EXECUTE FUNCTION r34.immutable();
CREATE FUNCTION r34.operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN
  RAISE EXCEPTION 'immutable research operation' USING ERRCODE='23514';
 END IF;
 IF OLD.status IN ('SUCCEEDED','FAILED') OR NOT ((OLD.status='RESERVED' AND NEW.status='EXECUTING')
  OR (OLD.status IN ('EXECUTING','UNKNOWN') AND NEW.status IN ('UNKNOWN','SUCCEEDED','FAILED'))) THEN
  RAISE EXCEPTION 'illegal research status' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_operations BEFORE UPDATE OR DELETE ON r34.operations FOR EACH ROW EXECUTE FUNCTION r34.operation_guard();
CREATE FUNCTION r34.proof_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-'operation_id') IS DISTINCT FROM (to_jsonb(OLD)-'operation_id')
 OR OLD.operation_id IS NOT NULL OR NEW.operation_id IS NULL THEN
  RAISE EXCEPTION 'immutable research proof' USING ERRCODE='23514';
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER immutable_proofs BEFORE UPDATE OR DELETE ON r34.proofs FOR EACH ROW EXECUTE FUNCTION r34.proof_guard();
CREATE FUNCTION r34.assert_counter(gid text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE c r34.counters; ar numeric; aset numeric; cr numeric; cs numeric;
BEGIN
 SELECT * INTO c FROM r34.counters WHERE grant_id=gid;
 SELECT coalesce(sum(amount_reserved_delta),0),coalesce(sum(amount_settled_delta),0),
  coalesce(sum(calls_reserved_delta),0),coalesce(sum(calls_settled_delta),0)
 INTO ar,aset,cr,cs FROM r34.nodes WHERE grant_id=gid;
 IF c.grant_id IS NULL OR (c.amount_reserved,c.amount_settled,c.calls_reserved,c.calls_settled)
  IS DISTINCT FROM (ar,aset,cr,cs) OR c.amount_high_water<ar+aset OR c.calls_high_water<cr+cs THEN
  RAISE EXCEPTION 'research counter/event mismatch' USING ERRCODE='23514';
 END IF;
END $$;
CREATE FUNCTION r34.counter_complete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM r34.assert_counter(NEW.grant_id); RETURN NULL; END $$;
CREATE CONSTRAINT TRIGGER complete_counter AFTER INSERT OR UPDATE ON r34.counters
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION r34.counter_complete();
CREATE TRIGGER immutable_counter_delete BEFORE DELETE ON r34.counters
 FOR EACH ROW EXECUTE FUNCTION r34.immutable();
CREATE FUNCTION r34.event_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ids text[]; actual text[]; amount bigint; calls bigint; gid text;
BEGIN
 SELECT path_ids,amount_fen,operations.calls INTO ids,amount,calls FROM r34.operations WHERE operation_id=NEW.operation_id;
 SELECT array_agg(grant_id ORDER BY position) INTO actual FROM r34.nodes WHERE event_id=NEW.event_id;
 IF actual IS DISTINCT FROM ids OR EXISTS (
  SELECT 1 FROM r34.nodes WHERE event_id=NEW.event_id AND
  (amount_reserved_delta <> CASE WHEN NEW.phase='RESERVE' THEN amount ELSE -amount END
   OR calls_reserved_delta <> CASE WHEN NEW.phase='RESERVE' THEN calls ELSE -calls END
   OR amount_settled_delta <> CASE WHEN NEW.phase='SETTLE' THEN amount ELSE 0 END
   OR calls_settled_delta <> CASE WHEN NEW.phase='SETTLE' THEN calls ELSE 0 END)) THEN
  RAISE EXCEPTION 'incomplete research event' USING ERRCODE='23514';
 END IF;
 FOREACH gid IN ARRAY ids LOOP PERFORM r34.assert_counter(gid); END LOOP;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER complete_event AFTER INSERT ON r34.events DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION r34.event_complete();
CREATE FUNCTION r34.operation_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE op r34.operations; phases text[]; box r34.outbox;
BEGIN
 SELECT * INTO op FROM r34.operations WHERE operation_id=NEW.operation_id;
 SELECT array_agg(phase ORDER BY seq) INTO phases FROM r34.events WHERE operation_id=op.operation_id;
 SELECT * INTO box FROM r34.outbox WHERE operation_id=op.operation_id;
 IF op.path_ids[1] IS DISTINCT FROM op.root_id
 OR op.path_ids[cardinality(op.path_ids)] IS DISTINCT FROM op.grant_id
 OR (SELECT count(DISTINCT x) FROM unnest(op.path_ids) x) <> cardinality(op.path_ids)
 OR phases IS DISTINCT FROM (CASE WHEN op.status='SUCCEEDED' THEN ARRAY['RESERVE','SETTLE']
  WHEN op.status='FAILED' THEN ARRAY['RESERVE','RELEASE'] ELSE ARRAY['RESERVE'] END)
 OR (op.status IN ('SUCCEEDED','FAILED') AND
  (box.operation_id IS NULL OR box.status<>op.status OR box.quote_snapshot IS DISTINCT FROM op.quote_snapshot))
 OR (op.status NOT IN ('SUCCEEDED','FAILED') AND box.operation_id IS NOT NULL) THEN
  RAISE EXCEPTION 'incomplete research operation' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER complete_operation AFTER INSERT OR UPDATE ON r34.operations
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION r34.operation_complete();
