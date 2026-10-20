-- Independent checkpoint database; never installed by the GW bundle.
CREATE TABLE ag_checkpoint_streams (
 stream_id text PRIMARY KEY, gateway_id text NOT NULL, tenant_id text NOT NULL,
 task_id text NOT NULL, epoch bigint NOT NULL CHECK(epoch=1), genesis_digest text NOT NULL,
 bootstrap_digest text NOT NULL, boundary text NOT NULL CHECK(boundary IN ('NEW_EMPTY','LEGACY_WITH_GAPS')),
 public_descriptor bytea NOT NULL CHECK(octet_length(public_descriptor)<=32768),
 latest_sequence bigint NOT NULL DEFAULT 0 CHECK(latest_sequence BETWEEN 0 AND 9007199254740991),
 latest_digest text NOT NULL, latest_checkpoint_id text,
 UNIQUE(gateway_id,tenant_id,task_id)
);
CREATE TABLE ag_checkpoint_records (
 stream_id text NOT NULL REFERENCES ag_checkpoint_streams(stream_id),
 seq bigint NOT NULL CHECK(seq BETWEEN 1 AND 9007199254740991),
 raw bytea NOT NULL CHECK(octet_length(raw) BETWEEN 1 AND 32768), digest text NOT NULL,
 previous_digest text NOT NULL, record_id text NOT NULL,
 PRIMARY KEY(stream_id,seq), UNIQUE(stream_id,record_id)
);
CREATE TABLE ag_audit_checkpoint_keys (
 kid text PRIMARY KEY, role text NOT NULL CHECK(role='AUDIT_SIGNER'), spki_der bytea NOT NULL,
 first_sequence bigint NOT NULL CHECK(first_sequence>0), last_sequence bigint,
 CHECK(last_sequence IS NULL OR last_sequence>=first_sequence)
);
CREATE TABLE ag_checkpoints (
 checkpoint_id text PRIMARY KEY, stream_id text NOT NULL REFERENCES ag_checkpoint_streams(stream_id),
 sequence bigint NOT NULL, head_digest text NOT NULL, previous_checkpoint_digest text,
 issued_at timestamptz NOT NULL, kid text NOT NULL REFERENCES ag_audit_checkpoint_keys(kid),
 jws text NOT NULL CHECK(octet_length(jws) BETWEEN 1 AND 16384), jws_digest text NOT NULL,
 UNIQUE(stream_id,sequence), FOREIGN KEY(stream_id,sequence) REFERENCES ag_checkpoint_records(stream_id,seq)
);
CREATE TABLE ag_checkpoint_batches (
 stream_id text NOT NULL REFERENCES ag_checkpoint_streams(stream_id), batch_id text NOT NULL,
 exact_body bytea NOT NULL CHECK(octet_length(exact_body) BETWEEN 1 AND 65536),
 start_sequence bigint NOT NULL, end_sequence bigint NOT NULL, end_digest text NOT NULL,
 checkpoint_id text NOT NULL REFERENCES ag_checkpoints(checkpoint_id), PRIMARY KEY(stream_id,batch_id),
 CHECK(start_sequence>0 AND end_sequence>=start_sequence AND end_sequence-start_sequence<64),
 FOREIGN KEY(stream_id,start_sequence) REFERENCES ag_checkpoint_records(stream_id,seq),
 FOREIGN KEY(stream_id,end_sequence) REFERENCES ag_checkpoint_records(stream_id,seq)
);
ALTER TABLE ag_checkpoint_streams ADD FOREIGN KEY(latest_checkpoint_id)
 REFERENCES ag_checkpoints(checkpoint_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE ag_audit_principals (
 credential_id text PRIMARY KEY, role text NOT NULL CHECK(role IN ('WRITER','READER')),
 credential_verifier bytea NOT NULL, stream_id text NOT NULL REFERENCES ag_checkpoint_streams(stream_id)
);
CREATE FUNCTION ag_checkpoint_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable checkpoint fact' USING ERRCODE='23514'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ag_checkpoint_records','ag_checkpoint_batches','ag_checkpoints'] LOOP
  EXECUTE format('CREATE TRIGGER ag_checkpoint_immutable BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION ag_checkpoint_immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION ag_checkpoint_head_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-'latest_sequence'-'latest_digest'-'latest_checkpoint_id')
 IS DISTINCT FROM (to_jsonb(OLD)-'latest_sequence'-'latest_digest'-'latest_checkpoint_id')
 OR NEW.latest_sequence<=OLD.latest_sequence OR NOT EXISTS(SELECT 1 FROM ag_checkpoints c
 WHERE c.checkpoint_id=NEW.latest_checkpoint_id AND c.stream_id=NEW.stream_id
 AND c.sequence=NEW.latest_sequence AND c.head_digest=NEW.latest_digest) THEN
  RAISE EXCEPTION 'checkpoint head cannot reset' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ag_checkpoint_head_guard BEFORE UPDATE OR DELETE ON ag_checkpoint_streams
 FOR EACH ROW EXECUTE FUNCTION ag_checkpoint_head_guard();
REVOKE ALL ON ag_checkpoint_streams,ag_checkpoint_records,ag_checkpoint_batches,ag_checkpoints,
 ag_audit_principals,ag_audit_checkpoint_keys FROM PUBLIC;
