-- Append-only provenance for the common, execution and authorization lineages.
CREATE TABLE ag_schema_migration_lineages (
    namespace TEXT NOT NULL CHECK (namespace IN ('common', 'execution', 'authorization', 'infrastructure')),
    version TEXT NOT NULL CHECK (version ~ '^[0-9]{3}$'),
    original_filename TEXT NOT NULL,
    checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    origin TEXT NOT NULL CHECK (origin IN ('legacy-import', 'new')),
    source_lineage TEXT NOT NULL,
    original_applied_at TIMESTAMPTZ,
    PRIMARY KEY (namespace, version),
    CHECK ((origin = 'legacy-import') = (original_applied_at IS NOT NULL))
);
CREATE TABLE ag_schema_legacy_binding (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    source_lineage TEXT NOT NULL CHECK (source_lineage IN ('A', 'B', 'common-only')),
    registry_json TEXT NOT NULL,
    registry_sha256 TEXT NOT NULL CHECK (registry_sha256 ~ '^[0-9a-f]{64}$'),
    infrastructure_sha256 TEXT NOT NULL CHECK (infrastructure_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION ag_schema_lineage_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'migration provenance is append-only' USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER ag_schema_lineages_guard BEFORE UPDATE OR DELETE ON ag_schema_migration_lineages
FOR EACH ROW EXECUTE FUNCTION ag_schema_lineage_immutable();
CREATE TRIGGER ag_schema_binding_guard BEFORE UPDATE OR DELETE ON ag_schema_legacy_binding
FOR EACH ROW EXECUTE FUNCTION ag_schema_lineage_immutable();
REVOKE ALL ON ag_schema_migration_lineages, ag_schema_legacy_binding FROM PUBLIC;
