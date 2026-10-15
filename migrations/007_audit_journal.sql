-- execution007 depends on execution006 AND authorization010. PostgreSQL16.
-- The immutable transaction witnesses are server written. They prevent both
-- an enabled old binary omitting records and later transactions filling gaps.
ALTER TABLE ag_operations ADD COLUMN audit_created_xid text,
    ADD COLUMN audit_terminal_xid text;
ALTER TABLE ag_proofs ADD COLUMN audit_linked_xid text;
ALTER TABLE ag_operation_evidence ADD COLUMN audit_linked_xid text;
ALTER TABLE ag_receipt_outbox ADD COLUMN audit_ready_xid text;
CREATE TABLE ag_audit_streams (
 stream_id text PRIMARY KEY, gateway_id text NOT NULL, tenant_id text NOT NULL,
 task_id text NOT NULL, epoch bigint NOT NULL CHECK(epoch=1), genesis_digest text NOT NULL,
 bootstrap_digest text NOT NULL, enabled_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 created_xid text NOT NULL, head_seq bigint NOT NULL DEFAULT 0 CHECK(head_seq BETWEEN 0 AND 9007199254740991),
 head_digest text NOT NULL, UNIQUE(gateway_id,tenant_id,task_id),
 FOREIGN KEY(tenant_id,task_id) REFERENCES ag_tasks(tenant_id,task_id)
);
CREATE TABLE ag_audit_records (
 stream_id text NOT NULL REFERENCES ag_audit_streams(stream_id),
 seq bigint NOT NULL CHECK(seq BETWEEN 1 AND 9007199254740991), record_id text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('BOOTSTRAP','FIRST','RETRY','QUERY','TERMINAL','PUBLISH')),
 operation_id text REFERENCES ag_operations(operation_id),
 evidence_ref text REFERENCES ag_verified_evidence(evidence_ref), previous_digest text NOT NULL,
 digest text NOT NULL, raw bytea NOT NULL CHECK(octet_length(raw) BETWEEN 1 AND 32768),
 material_binding_bytes bytea NOT NULL CHECK(octet_length(material_binding_bytes) BETWEEN 2 AND 262183),
 recorded_at timestamptz NOT NULL, created_xid text NOT NULL,
 PRIMARY KEY(stream_id,seq), UNIQUE(stream_id,record_id)
);
CREATE UNIQUE INDEX ag_audit_first ON ag_audit_records(operation_id) WHERE kind='FIRST';
CREATE UNIQUE INDEX ag_audit_terminal ON ag_audit_records(operation_id) WHERE kind='TERMINAL';
CREATE UNIQUE INDEX ag_audit_retry ON ag_audit_records(evidence_ref) WHERE kind='RETRY';
CREATE UNIQUE INDEX ag_audit_query ON ag_audit_records(evidence_ref) WHERE kind='QUERY';
CREATE TABLE ag_audit_bootstrap (
 stream_id text PRIMARY KEY REFERENCES ag_audit_streams(stream_id),
 boundary text NOT NULL CHECK(boundary IN ('NEW_EMPTY','LEGACY_WITH_GAPS')),
 snapshot_as_of timestamptz NOT NULL, root_grant_id text NOT NULL REFERENCES ag_grants(grant_id),
 index_root text NOT NULL, manifest_digest text NOT NULL,
 manifest_bytes bytea NOT NULL CHECK(octet_length(manifest_bytes) BETWEEN 1 AND 32768),
 schema_lineage_bytes bytea NOT NULL CHECK(octet_length(schema_lineage_bytes) BETWEEN 1 AND 32768),
 object_count bigint NOT NULL CHECK(object_count BETWEEN 1 AND 200000),
 chunk_count bigint NOT NULL CHECK(chunk_count BETWEEN 1 AND 400000),
 wire_bytes bigint NOT NULL CHECK(wire_bytes BETWEEN 1 AND 268435456), created_xid text NOT NULL
);
CREATE TABLE ag_audit_bootstrap_chunks (
 stream_id text NOT NULL REFERENCES ag_audit_bootstrap(stream_id),
 object_kind text NOT NULL, object_id text NOT NULL, chunk_index bigint NOT NULL CHECK(chunk_index>=0),
 chunk_count bigint NOT NULL CHECK(chunk_count BETWEEN 1 AND 400000),
 total_raw_bytes bigint NOT NULL CHECK(total_raw_bytes BETWEEN 1 AND 65536),
 object_digest text NOT NULL, raw bytea NOT NULL CHECK(octet_length(raw) BETWEEN 1 AND 24576),
 created_xid text NOT NULL, PRIMARY KEY(stream_id,object_kind,object_id,chunk_index),
 CHECK(chunk_index<chunk_count),
 CHECK(chunk_count=(total_raw_bytes+24575)/24576),
 CHECK(octet_length(raw)=LEAST(24576,total_raw_bytes-chunk_index*24576)),
 CHECK(object_kind IN ('token','proof','ancestor_token','receipt','checkpoint','journal','request',
 'result','ledger','quote','context','source','raw_authorization_snapshot','typed_snapshot_metadata')),
 CHECK(total_raw_bytes<=CASE WHEN object_kind IN ('token','proof','ancestor_token','receipt','checkpoint')
 THEN 16384 WHEN object_kind='journal' THEN 32768 ELSE 65536 END)
);
CREATE TABLE ag_audit_delivery (
 stream_id text PRIMARY KEY REFERENCES ag_audit_streams(stream_id),
 ack_sequence bigint NOT NULL DEFAULT 0 CHECK(ack_sequence BETWEEN 0 AND 9007199254740991),
 ack_head_digest text NOT NULL, ack_checkpoint_digest text, pending_batch_id text,
 registration_state text NOT NULL DEFAULT 'REGISTRATION_REQUIRED'
 CHECK(registration_state IN ('REGISTRATION_REQUIRED','REGISTERED'))
);
CREATE TABLE ag_audit_delivery_batches (
 stream_id text NOT NULL REFERENCES ag_audit_streams(stream_id), batch_id text NOT NULL,
 exact_body bytea NOT NULL CHECK(octet_length(exact_body) BETWEEN 1 AND 65536),
 start_sequence bigint NOT NULL, end_sequence bigint NOT NULL,
 end_digest text NOT NULL, base_checkpoint_digest text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), checkpoint_jws text, ack_at timestamptz,
 PRIMARY KEY(stream_id,batch_id), CHECK(start_sequence>0 AND end_sequence>=start_sequence),
 CHECK(end_sequence-start_sequence<64),
 FOREIGN KEY(stream_id,start_sequence) REFERENCES ag_audit_records(stream_id,seq),
 FOREIGN KEY(stream_id,end_sequence) REFERENCES ag_audit_records(stream_id,seq),
 CHECK((checkpoint_jws IS NULL)=(ack_at IS NULL))
);
ALTER TABLE ag_audit_delivery ADD FOREIGN KEY(stream_id,pending_batch_id)
 REFERENCES ag_audit_delivery_batches(stream_id,batch_id) DEFERRABLE INITIALLY DEFERRED;
CREATE FUNCTION ag_audit_xid() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.created_xid:=pg_current_xact_id()::text; RETURN NEW; END $$;
CREATE FUNCTION ag_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable audit fact' USING ERRCODE='23514'; END $$;
CREATE FUNCTION ag_audit_witness() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='ag_operations' THEN
  IF TG_OP='INSERT' THEN
   NEW.audit_created_xid:=pg_current_xact_id()::text; NEW.audit_terminal_xid:=NULL;
  ELSE
   NEW.audit_created_xid:=OLD.audit_created_xid;
   NEW.audit_terminal_xid:=OLD.audit_terminal_xid;
   IF OLD.status NOT IN ('SUCCEEDED','FAILED') AND NEW.status IN ('SUCCEEDED','FAILED') THEN
    NEW.audit_terminal_xid:=pg_current_xact_id()::text;
   END IF;
  END IF;
 ELSIF TG_TABLE_NAME='ag_operation_evidence' THEN
  NEW.audit_linked_xid:=pg_current_xact_id()::text;
 ELSIF TG_TABLE_NAME='ag_proofs' THEN
  IF TG_OP='INSERT' THEN NEW.audit_linked_xid:=NULL;
  ELSE
   NEW.audit_linked_xid:=OLD.audit_linked_xid;
   IF OLD.operation_id IS NULL AND NEW.operation_id IS NOT NULL THEN
    NEW.audit_linked_xid:=pg_current_xact_id()::text;
   END IF;
  END IF;
 ELSE
  IF TG_OP='INSERT' THEN NEW.audit_ready_xid:=NULL;
  ELSE
   NEW.audit_ready_xid:=OLD.audit_ready_xid;
   IF OLD.receipt_status='PENDING' AND NEW.receipt_status='READY' THEN
    NEW.audit_ready_xid:=pg_current_xact_id()::text;
   END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ag_audit_op_witness BEFORE INSERT OR UPDATE ON ag_operations
 FOR EACH ROW EXECUTE FUNCTION ag_audit_witness();
CREATE TRIGGER ag_audit_proof_witness BEFORE INSERT OR UPDATE ON ag_proofs
 FOR EACH ROW EXECUTE FUNCTION ag_audit_witness();
CREATE TRIGGER ag_audit_link_witness BEFORE INSERT ON ag_operation_evidence
 FOR EACH ROW EXECUTE FUNCTION ag_audit_witness();
CREATE TRIGGER ag_audit_ready_witness BEFORE INSERT OR UPDATE ON ag_receipt_outbox
 FOR EACH ROW EXECUTE FUNCTION ag_audit_witness();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ag_audit_streams','ag_audit_records','ag_audit_bootstrap','ag_audit_bootstrap_chunks'] LOOP
  EXECUTE format('CREATE TRIGGER ag_audit_created_xid BEFORE INSERT ON %I FOR EACH ROW EXECUTE FUNCTION ag_audit_xid()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['ag_audit_records','ag_audit_bootstrap','ag_audit_bootstrap_chunks'] LOOP
  EXECUTE format('CREATE TRIGGER ag_audit_immutable BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION ag_audit_immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION ag_audit_b64(raw bytea) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT translate(rtrim(replace(encode(raw,'base64'),E'\n',''),'='),'+/','-_') $$;
CREATE FUNCTION ag_audit_require(k text, op text, ref text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM ag_audit_streams s JOIN ag_operations o
 ON (s.tenant_id,s.task_id)=(o.tenant_id,o.task_id) WHERE o.operation_id=op)
 AND NOT EXISTS(SELECT 1 FROM ag_audit_records r WHERE r.kind=k AND r.operation_id=op
 AND (ref IS NULL OR r.evidence_ref=ref) AND r.created_xid=pg_current_xact_id()::text) THEN
  RAISE EXCEPTION 'enabled interaction missing current transaction audit record: %',k USING ERRCODE='23514';
 END IF;
END $$;
CREATE FUNCTION ag_audit_coverage() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='ag_operations' THEN
  IF TG_OP='INSERT' THEN PERFORM ag_audit_require('FIRST',NEW.operation_id,NEW.evidence_ref);
  ELSIF OLD.status NOT IN ('SUCCEEDED','FAILED') AND NEW.status IN ('SUCCEEDED','FAILED') THEN
   PERFORM ag_audit_require('TERMINAL',NEW.operation_id,NULL);
  END IF;
 ELSIF TG_TABLE_NAME='ag_operation_evidence' THEN
  PERFORM ag_audit_require(CASE WHEN NEW.kind='first' THEN 'FIRST' ELSE 'RETRY' END,NEW.operation_id,NEW.evidence_ref);
 ELSIF TG_TABLE_NAME='ag_proofs' THEN
  IF OLD.operation_id IS NULL AND NEW.operation_id IS NOT NULL AND NEW.purpose='result-read' THEN
   PERFORM ag_audit_require('QUERY',NEW.operation_id,NEW.evidence_ref);
  END IF;
 ELSIF TG_TABLE_NAME='ag_receipt_outbox' THEN
  IF TG_OP='INSERT' THEN PERFORM ag_audit_require('TERMINAL',NEW.operation_id,NULL);
  ELSIF OLD.receipt_status='PENDING' AND NEW.receipt_status='READY' THEN
   PERFORM ag_audit_require('PUBLISH',NEW.operation_id,NULL);
  END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ag_audit_op_coverage AFTER INSERT OR UPDATE ON ag_operations
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ag_audit_coverage();
CREATE CONSTRAINT TRIGGER ag_audit_link_coverage AFTER INSERT ON ag_operation_evidence
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ag_audit_coverage();
CREATE CONSTRAINT TRIGGER ag_audit_query_coverage AFTER UPDATE ON ag_proofs
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ag_audit_coverage();
CREATE CONSTRAINT TRIGGER ag_audit_outbox_coverage AFTER INSERT OR UPDATE ON ag_receipt_outbox
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ag_audit_coverage();
CREATE FUNCTION ag_audit_head_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'immutable stream' USING ERRCODE='23514'; END IF;
 IF (to_jsonb(NEW)-'head_seq'-'head_digest') IS DISTINCT FROM (to_jsonb(OLD)-'head_seq'-'head_digest')
 OR NEW.head_seq<>OLD.head_seq+1 OR NOT EXISTS(SELECT 1 FROM ag_audit_records
 WHERE stream_id=NEW.stream_id AND seq=NEW.head_seq AND digest=NEW.head_digest
 AND previous_digest=OLD.head_digest AND created_xid=pg_current_xact_id()::text) THEN
  RAISE EXCEPTION 'invalid contiguous head update' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ag_audit_head BEFORE UPDATE OR DELETE ON ag_audit_streams
 FOR EACH ROW EXECUTE FUNCTION ag_audit_head_guard();

CREATE FUNCTION ag_audit_wire_schema(raw bytea, expected_kind text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE j jsonb; f jsonb; expected text[]; key text; val jsonb; typ text;
BEGIN
 j:=convert_from(raw,'UTF8')::jsonb;
 IF jsonb_typeof(j) IS DISTINCT FROM 'object' OR
 (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(j) k) IS DISTINCT FROM
 ARRAY['epoch','evidence_ref','facts','gateway_id','journal_profile','kind','operation_id','previous_digest','record_id','recorded_at','seq','stream_id','task_id','tenant_id']
 OR (SELECT count(*) FROM json_each(convert_from(raw,'UTF8')::json))<>14 THEN
  RAISE EXCEPTION 'strict record keys' USING ERRCODE='23514';
 END IF;
 f:=j->'facts';
 expected:=CASE expected_kind
 WHEN 'BOOTSTRAP' THEN ARRAY['boundary','chunk_count','index_root','manifest_digest','object_count','root_grant_id','schema_lineage_digest','snapshot_as_of','wire_bytes']
 WHEN 'FIRST' THEN ARRAY['amount_fen','body_digest','calls','context_digest','currency','grant_id','intent_digest','introduced_grants','path_ids','proof_digest','quote_digest','reserve_digest','root_grant_id','source_digest','source_material_digest','token_digest']
 WHEN 'RETRY' THEN ARRAY['body_digest','context_digest','first_evidence_ref','intent_digest','proof_digest','receipt_jws_digest','receipt_status','response_digest','response_kind','source_digest','source_material_digest','status','token_digest']
 WHEN 'QUERY' THEN ARRAY['body_digest','context_digest','first_evidence_ref','proof_digest','receipt_jws_digest','receipt_status','response_digest','result_digest','source_digest','source_material_digest','status','token_digest']
 WHEN 'TERMINAL' THEN ARRAY['action','fencing_version','first_evidence_ref','lease_expires_at','ledger_digest','owner_token','path_ids','pending_receipt_digest','receipt_id','result_digest','status']
 WHEN 'PUBLISH' THEN ARRAY['receipt_id','receipt_jws_digest','signed_at']
 ELSE NULL END;
 IF expected IS NULL OR jsonb_typeof(f) IS DISTINCT FROM 'object' OR
 (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(f) k) IS DISTINCT FROM expected
 OR (SELECT count(*) FROM json_each((convert_from(raw,'UTF8')::json)->'facts'))<>cardinality(expected) THEN
  RAISE EXCEPTION 'strict facts keys' USING ERRCODE='23514';
 END IF;
 FOR key,val IN SELECT * FROM jsonb_each(j) LOOP
  typ:=jsonb_typeof(val);
  IF key IN ('epoch','seq') THEN
   IF typ IS DISTINCT FROM 'number' OR val::text !~ '^[1-9][0-9]*$'
    OR val::text::numeric>9007199254740991 THEN
    RAISE EXCEPTION 'strict integer' USING ERRCODE='23514';
   END IF;
  ELSIF key IN ('operation_id','evidence_ref') THEN
   IF typ NOT IN ('string','null') THEN RAISE EXCEPTION 'strict nullable ID' USING ERRCODE='23514'; END IF;
  ELSIF key<>'facts' AND typ IS DISTINCT FROM 'string' THEN
   RAISE EXCEPTION 'strict scalar' USING ERRCODE='23514';
  END IF;
 END LOOP;
 FOR key,val IN SELECT * FROM jsonb_each(f) LOOP
  typ:=jsonb_typeof(val);
  IF key IN ('amount_fen','calls','fencing_version','object_count','chunk_count','wire_bytes') THEN
   IF typ IS DISTINCT FROM 'number' OR val::text !~ '^(0|[1-9][0-9]*)$'
    OR val::text::numeric>9007199254740991 THEN
    RAISE EXCEPTION 'strict facts integer' USING ERRCODE='23514';
   END IF;
  ELSIF key IN ('path_ids','introduced_grants') THEN
   IF typ IS DISTINCT FROM 'array' OR jsonb_array_length(val)>3 THEN
    RAISE EXCEPTION 'strict path/list' USING ERRCODE='23514';
   END IF;
  ELSIF typ='null' AND key IN ('quote_digest','receipt_jws_digest','result_digest','first_evidence_ref') THEN NULL;
  ELSIF typ IS DISTINCT FROM 'string' THEN
   RAISE EXCEPTION 'strict fact scalar' USING ERRCODE='23514';
  END IF;
 END LOOP;
 IF j->>'recorded_at' !~ '^....-..-..T..:..:..\.[0-9]{6}Z$' THEN
  RAISE EXCEPTION 'precise UTC record timestamp' USING ERRCODE='23514';
 END IF;
 EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
  RAISE EXCEPTION 'malformed audit wire' USING ERRCODE='23514';
END $$;

CREATE FUNCTION ag_audit_record_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s ag_audit_streams; o ag_operations; e ag_verified_evidence; r ag_receipt_outbox;
 j jsonb; f jsonb; m jsonb; witness text; b ag_audit_bootstrap; material_key text; material_value jsonb;
BEGIN
 SELECT * INTO STRICT s FROM ag_audit_streams WHERE stream_id=NEW.stream_id;
 PERFORM ag_audit_wire_schema(NEW.raw,NEW.kind);
 j:=convert_from(NEW.raw,'UTF8')::jsonb; f:=j->'facts';
 m:=convert_from(NEW.material_binding_bytes,'UTF8')::jsonb;
 IF octet_length(NEW.material_binding_bytes)>(CASE NEW.kind WHEN 'FIRST' THEN 262183
 WHEN 'RETRY' THEN 174790 WHEN 'QUERY' THEN 174790 WHEN 'TERMINAL' THEN 174789
 WHEN 'PUBLISH' THEN 16394 ELSE 2 END) THEN
  RAISE EXCEPTION 'bounded material projection' USING ERRCODE='23514';
 END IF;
 IF jsonb_typeof(m) IS DISTINCT FROM 'object' OR
 (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(m) k) IS DISTINCT FROM
 (CASE NEW.kind WHEN 'FIRST' THEN ARRAY['context','quote','source']
 WHEN 'RETRY' THEN ARRAY['context','source'] WHEN 'QUERY' THEN ARRAY['context','source']
 WHEN 'TERMINAL' THEN ARRAY['ledger','result'] WHEN 'PUBLISH' THEN ARRAY['jws'] ELSE NULL::text[] END) THEN
  RAISE EXCEPTION 'strict material projection keys' USING ERRCODE='23514';
 END IF;
 IF (SELECT count(*) FROM json_each(convert_from(NEW.material_binding_bytes,'UTF8')::json))
 IS DISTINCT FROM (SELECT count(*) FROM jsonb_each(m)) THEN
  RAISE EXCEPTION 'duplicate material projection key' USING ERRCODE='23514';
 END IF;
 FOR material_key,material_value IN SELECT * FROM jsonb_each(m) LOOP
  IF material_key='quote' AND material_value='null'::jsonb THEN CONTINUE; END IF;
  IF jsonb_typeof(material_value) IS DISTINCT FROM 'string'
  OR length(m->>material_key)>(CASE WHEN material_key='jws' THEN 16384 ELSE 87382 END) THEN
   RAISE EXCEPTION 'material logical type/capacity' USING ERRCODE='23514';
  END IF;
 END LOOP;
 IF (j->>'stream_id',j->>'gateway_id',j->>'tenant_id',j->>'task_id') IS DISTINCT FROM
 (s.stream_id,s.gateway_id,s.tenant_id,s.task_id) OR (j->>'epoch')::bigint<>1
 OR j->>'journal_profile'<>'AG-AUDIT-JOURNAL-1'
 OR (j->>'seq')::bigint<>NEW.seq OR j->>'kind'<>NEW.kind OR j->>'record_id'<>NEW.record_id
 OR (j->>'operation_id') IS DISTINCT FROM NEW.operation_id
 OR (j->>'evidence_ref') IS DISTINCT FROM NEW.evidence_ref
 OR j->>'previous_digest'<>NEW.previous_digest OR (j->>'recorded_at')::timestamptz<>NEW.recorded_at
 OR NEW.seq<>s.head_seq+1 OR NEW.previous_digest<>s.head_digest THEN
  RAISE EXCEPTION 'audit record relation mismatch' USING ERRCODE='23514';
 END IF;
 IF NEW.kind='BOOTSTRAP' THEN
  SELECT * INTO STRICT b FROM ag_audit_bootstrap WHERE stream_id=s.stream_id;
  IF NEW.seq<>1 OR s.created_xid<>pg_current_xact_id()::text OR b.created_xid<>s.created_xid
  OR NEW.operation_id IS NOT NULL OR NEW.evidence_ref IS NOT NULL
  OR f->>'boundary' IS DISTINCT FROM b.boundary OR f->>'root_grant_id' IS DISTINCT FROM b.root_grant_id
  OR f->>'index_root' IS DISTINCT FROM b.index_root OR f->>'manifest_digest' IS DISTINCT FROM b.manifest_digest
  OR (f->>'snapshot_as_of')::timestamptz<>b.snapshot_as_of
  OR (f->>'object_count')::bigint<>b.object_count OR (f->>'chunk_count')::bigint<>b.chunk_count
  OR (f->>'wire_bytes')::bigint<>b.wire_bytes THEN
   RAISE EXCEPTION 'invalid bootstrap record' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT * INTO STRICT o FROM ag_operations WHERE operation_id=NEW.operation_id;
  IF (s.tenant_id,s.task_id) IS DISTINCT FROM (o.tenant_id,o.task_id) THEN
   RAISE EXCEPTION 'operation scope mismatch' USING ERRCODE='23514';
  END IF;
  IF NEW.kind IN ('FIRST','RETRY','QUERY') THEN
   SELECT * INTO STRICT e FROM ag_verified_evidence WHERE evidence_ref=NEW.evidence_ref;
   IF (e.tenant_id,e.task_id,e.grant_id) IS DISTINCT FROM (o.tenant_id,o.task_id,o.grant_id)
   OR f->>'token_digest' IS DISTINCT FROM e.token_sm3 OR f->>'proof_digest' IS DISTINCT FROM e.proof_sm3 OR f->>'body_digest' IS DISTINCT FROM e.body_sm3
   OR f->>'source_digest' IS DISTINCT FROM (convert_from(e.chain_json,'UTF8')::jsonb->>'digest')
   OR m->>'context' IS DISTINCT FROM ag_audit_b64(e.context_json)
   OR m->>'source' IS DISTINCT FROM ag_audit_b64(e.chain_json)
   OR NOT EXISTS(SELECT 1 FROM ag_proofs p WHERE p.operation_id=o.operation_id
      AND p.evidence_ref=e.evidence_ref AND p.audit_linked_xid=pg_current_xact_id()::text) THEN
    RAISE EXCEPTION 'signed request relationship mismatch' USING ERRCODE='23514';
   END IF;
   IF NEW.kind='QUERY' THEN
    SELECT audit_linked_xid INTO witness FROM ag_proofs WHERE evidence_ref=e.evidence_ref
     AND operation_id=o.operation_id AND purpose='result-read';
   ELSE
    SELECT audit_linked_xid INTO witness FROM ag_operation_evidence WHERE evidence_ref=e.evidence_ref
      AND operation_id=o.operation_id AND kind=CASE WHEN NEW.kind='FIRST' THEN 'first' ELSE 'retry' END;
   END IF;
   IF NEW.kind='FIRST' THEN
    IF o.audit_created_xid<>pg_current_xact_id()::text OR f->>'intent_digest' IS DISTINCT FROM o.intent_digest
    OR f->>'grant_id' IS DISTINCT FROM o.grant_id OR (f->>'amount_fen')::bigint<>o.amount_fen
    OR (f->>'calls')::bigint<>o.calls OR f->>'currency' IS DISTINCT FROM o.currency
    OR m->>'quote' IS DISTINCT FROM ag_audit_b64(o.quote_snapshot)
    OR NOT EXISTS(SELECT 1 FROM ag_ledger_events WHERE operation_id=o.operation_id AND phase='RESERVE') THEN
     RAISE EXCEPTION 'first accept mismatch' USING ERRCODE='23514';
    END IF;
   ELSE
    IF f->>'first_evidence_ref' IS DISTINCT FROM o.evidence_ref OR f->>'status' IS DISTINCT FROM o.status THEN
     RAISE EXCEPTION 'response state mismatch' USING ERRCODE='23514';
    END IF;
   END IF;
  ELSE
   SELECT * INTO STRICT r FROM ag_receipt_outbox WHERE operation_id=o.operation_id;
   IF NEW.evidence_ref IS DISTINCT FROM (SELECT evidence_ref FROM ag_operation_evidence
      WHERE operation_id=o.operation_id AND kind='first') OR f->>'receipt_id' IS DISTINCT FROM r.receipt_id THEN
    RAISE EXCEPTION 'receipt relation mismatch' USING ERRCODE='23514';
   END IF;
   IF NEW.kind='TERMINAL' THEN
    witness:=o.audit_terminal_xid;
    IF f->>'status' IS DISTINCT FROM o.status OR f->>'action' IS DISTINCT FROM (CASE WHEN o.status='SUCCEEDED' THEN 'SETTLE' ELSE 'RELEASE' END)
    OR m->>'result' IS DISTINCT FROM ag_audit_b64(r.result_bytes)
    OR m->>'ledger' IS DISTINCT FROM ag_audit_b64(r.ledger_changes_json)
    OR NOT EXISTS(SELECT 1 FROM ag_execution_leases l WHERE l.operation_id=o.operation_id
      AND l.owner_token=f->>'owner_token' AND l.fencing_version=(f->>'fencing_version')::bigint
      AND l.lease_expires_at=(f->>'lease_expires_at')::timestamptz) THEN
     RAISE EXCEPTION 'terminal material mismatch' USING ERRCODE='23514';
    END IF;
   ELSE
    witness:=r.audit_ready_xid;
    IF r.receipt_status<>'READY' OR m->>'jws' IS DISTINCT FROM r.receipt_jws
    OR (f->>'signed_at')::timestamptz<>r.signed_at THEN
     RAISE EXCEPTION 'publication material mismatch' USING ERRCODE='23514';
    END IF;
   END IF;
  END IF;
  IF witness IS DISTINCT FROM pg_current_xact_id()::text THEN
   RAISE EXCEPTION 'no current transaction business witness; late audit fill prohibited' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ag_audit_record BEFORE INSERT ON ag_audit_records
 FOR EACH ROW EXECUTE FUNCTION ag_audit_record_guard();
CREATE FUNCTION ag_audit_bootstrap_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b ag_audit_bootstrap; n bigint; objects bigint;
BEGIN
 SELECT * INTO STRICT b FROM ag_audit_bootstrap WHERE stream_id=NEW.stream_id;
 SELECT count(*),count(DISTINCT (object_kind,object_id)) INTO n,objects
 FROM ag_audit_bootstrap_chunks WHERE stream_id=NEW.stream_id;
 IF n<>b.chunk_count OR objects<>b.object_count OR EXISTS(
 SELECT 1 FROM ag_audit_bootstrap_chunks WHERE stream_id=NEW.stream_id
 GROUP BY object_kind,object_id HAVING count(*)<>max(chunk_count) OR min(chunk_count)<>max(chunk_count)
 OR min(total_raw_bytes)<>max(total_raw_bytes) OR min(object_digest)<>max(object_digest)
 OR min(chunk_index)<>0 OR max(chunk_index)<>max(chunk_count)-1) OR NOT EXISTS(SELECT 1 FROM ag_audit_records
 WHERE stream_id=NEW.stream_id AND seq=1 AND kind='BOOTSTRAP' AND created_xid=b.created_xid)
 OR EXISTS(SELECT 1 FROM ag_audit_bootstrap_chunks WHERE stream_id=NEW.stream_id
 AND created_xid<>b.created_xid) THEN
  RAISE EXCEPTION 'incomplete same transaction bootstrap' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ag_audit_bootstrap_complete AFTER INSERT ON ag_audit_bootstrap
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ag_audit_bootstrap_complete();
CREATE FUNCTION ag_audit_initial_stream() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.head_seq<>0 OR NEW.head_digest IS DISTINCT FROM NEW.genesis_digest THEN
  RAISE EXCEPTION 'initial stream head must be genesis' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ag_audit_initial_stream BEFORE INSERT ON ag_audit_streams
 FOR EACH ROW EXECUTE FUNCTION ag_audit_initial_stream();
CREATE FUNCTION ag_audit_stream_complete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM ag_audit_bootstrap b WHERE b.stream_id=NEW.stream_id
 AND b.created_xid=NEW.created_xid AND b.manifest_digest=NEW.bootstrap_digest)
 OR NOT EXISTS(SELECT 1 FROM ag_audit_delivery d WHERE d.stream_id=NEW.stream_id
 AND d.ack_sequence=0 AND d.ack_head_digest=NEW.genesis_digest
 AND d.ack_checkpoint_digest IS NULL AND d.pending_batch_id IS NULL
 AND d.registration_state='REGISTRATION_REQUIRED') THEN
  RAISE EXCEPTION 'stream requires complete same transaction bootstrap and initial delivery' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ag_audit_stream_complete AFTER INSERT ON ag_audit_streams
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ag_audit_stream_complete();
CREATE FUNCTION ag_audit_batch_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-'checkpoint_jws'-'ack_at') IS DISTINCT FROM
 (to_jsonb(OLD)-'checkpoint_jws'-'ack_at') OR OLD.checkpoint_jws IS NOT NULL
 OR NEW.checkpoint_jws IS NULL OR NEW.ack_at IS NULL THEN
  RAISE EXCEPTION 'immutable exact pending batch' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ag_audit_batch_guard BEFORE UPDATE OR DELETE ON ag_audit_delivery_batches
 FOR EACH ROW EXECUTE FUNCTION ag_audit_batch_guard();
CREATE FUNCTION ag_audit_cursor_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR NEW.stream_id<>OLD.stream_id OR NEW.ack_sequence<OLD.ack_sequence
 OR (NEW.ack_sequence=OLD.ack_sequence AND (NEW.ack_head_digest,NEW.ack_checkpoint_digest)
 IS DISTINCT FROM (OLD.ack_head_digest,OLD.ack_checkpoint_digest)) THEN
  RAISE EXCEPTION 'audit cursor cannot roll back' USING ERRCODE='23514';
 END IF;
 IF NEW.ack_sequence>OLD.ack_sequence AND NOT EXISTS(SELECT 1 FROM ag_audit_delivery_batches b
 WHERE b.stream_id=NEW.stream_id AND b.batch_id=OLD.pending_batch_id AND b.end_sequence=NEW.ack_sequence
 AND b.end_digest=NEW.ack_head_digest AND b.checkpoint_jws IS NOT NULL AND NEW.pending_batch_id IS NULL) THEN
  RAISE EXCEPTION 'cursor must acknowledge exact pending batch' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ag_audit_cursor_guard BEFORE UPDATE OR DELETE ON ag_audit_delivery
 FOR EACH ROW EXECUTE FUNCTION ag_audit_cursor_guard();
REVOKE ALL ON ag_audit_streams,ag_audit_records,ag_audit_bootstrap,ag_audit_bootstrap_chunks,
 ag_audit_delivery,ag_audit_delivery_batches FROM PUBLIC;
