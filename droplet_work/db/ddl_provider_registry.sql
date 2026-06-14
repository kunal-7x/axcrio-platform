-- ============================================================================
-- db/ddl_provider_registry.sql — Universal Provider / Connector Registry (W1).
-- Spec: design/PROVIDER-FRAMEWORK-PLAN.md §5 + §14 (W1). RED-TEAM fixes folded.
--
-- THREE tables, all FORCE ROW LEVEL SECURITY, tenant_id TEXT NOT NULL:
--   1) provider_definitions  — the reusable provider spec. '_global' = platform-shared
--                              (super-admin owned, write-LOCKED from non-admin tenants).
--   2) provider_credentials  — per-tenant AAD-bound AES-256-GCM ciphertext + a `scope`
--                              column (platform-masked vs vendor-revealable).
--   3) provider_health_log    — APPEND-ONLY circuit-breaker input (UPDATE/DELETE revoked).
--
-- IDEMPOTENT: every statement is CREATE ... IF NOT EXISTS / DROP-then-CREATE-POLICY, so
-- this whole file is safe to re-run. Applied standalone via psql as famit_app, NOT an
-- Alembic revision — same posture as kb/schema.sql and db/ddl_wallet.sql (kept off the
-- live P1 0001/0002 migration chain).
--
-- MONEY = INTEGER MICRO-USD (cost_per_unit_micros BIGINT). NO floats anywhere (founder law).
--
-- RLS shape = the P1 ADMIN-GUC policy (db/rls.sql / db/ddl_wallet.sql), with the kb_*
-- `_global` read-share extension on provider_definitions:
--   READ  (USING): admin GUC  OR  own tenant  OR  the shared '_global' row.
--   WRITE (WITH CHECK): admin GUC  OR  (own tenant AND tenant_id <> '_global').
-- WHY '_global' is in WITH CHECK only as the explicit-EXCLUDE: a tenant request path
-- (is_admin=FALSE) can READ a '_global' platform-shared provider def but can NEVER
-- insert/update/delete a '_global' row — the '_global' write-lock (only the super-admin
-- GUC path writes platform-shared rows). This is the anti-privilege-escalation guard for
-- the platform-shared provider catalog, identical in spirit to the kb_chunks write-lock.
-- famit_app is NOSUPERUSER/NOBYPASSRLS (verified on box) so FORCE RLS binds even the owner.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) provider_definitions — the reusable, config-driven provider spec.
--    '_global' tenant_id = platform-shared (super-admin owned, write-locked).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provider_definitions (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            text NOT NULL,                         -- '_global' for platform-shared, else the tenant id
    slug                 text NOT NULL,                         -- 'fal-wan26', 'my-ollama', 'acme-llm'
    display_name         text NOT NULL,
    provider_type        text NOT NULL,                         -- 'hosted_api'|'self_hosted'|'tool_connector'|'platform_builtin'
    capabilities         jsonb NOT NULL DEFAULT '[]'::jsonb,    -- ['video_gen','image_gen','text_gen','tts','stt','embed','rerank','tool_call','webhook','storage']
    base_url             text NOT NULL,                         -- SSRF-validated on write (self_hosted) ; https-only for hosted
    auth_scheme          text NOT NULL DEFAULT 'bearer',        -- 'bearer'|'api_key_header'|'api_key_query'|'basic'|'oauth2_cc'|'none'
    auth_header_name     text,                                  -- e.g. 'Authorization' | 'x-api-key'
    auth_value_tmpl      text DEFAULT 'Bearer {key}',           -- {key} is the ONLY interpolation token
    transform_type       text NOT NULL DEFAULT 'openai_compat', -- 'openai_compat'|'named_provider'|'custom_field_map'
    named_provider       text,                                  -- 'fal'|'replicate'|'luma'|'anthropic'|'gemini'... (named_provider tier)
    request_field_map    jsonb,                                 -- JSONPath map (custom_field_map tier ONLY) ; validated depth<=5, no eval
    response_field_map   jsonb,
    model_default        text,                                  -- the model= value / route default
    cost_per_unit_micros bigint,                                -- INTEGER micro-USD, never float ; e.g. 50000 = $0.05
    cost_unit            text,                                  -- 'per_second'|'per_generation'|'per_1k_tokens'|'per_char'|'per_minute'
    health_check_path    text,                                  -- '/v1/models' | '/health' | '/queue' ; per-type default if NULL
    health_interval_s    int DEFAULT 60,
    priority             int DEFAULT 100,                        -- lower = higher in the fallback chain
    rate_limit_rpm       int,
    is_enabled           boolean NOT NULL DEFAULT true,
    is_platform_default  boolean NOT NULL DEFAULT false,
    created_by           text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, slug)
);
CREATE INDEX IF NOT EXISTS provdef_tenant_idx ON provider_definitions (tenant_id, is_enabled);
CREATE INDEX IF NOT EXISTS provdef_caps_idx   ON provider_definitions USING gin (capabilities);

ALTER TABLE provider_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_definitions FORCE  ROW LEVEL SECURITY;
-- READ: own rows OR the platform-shared '_global' rows OR super-admin GUC.
DROP POLICY IF EXISTS provdef_read ON provider_definitions;
CREATE POLICY provdef_read ON provider_definitions FOR SELECT
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true)
            OR tenant_id = '_global' );
-- WRITE: own rows only ('_global' write-locked to the super-admin GUC) — anti-privilege-escalation.
DROP POLICY IF EXISTS provdef_write ON provider_definitions;
CREATE POLICY provdef_write ON provider_definitions FOR ALL
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR (tenant_id = current_setting('app.tenant_id', true) AND tenant_id <> '_global') );

-- ---------------------------------------------------------------------------
-- 2) provider_credentials — per-tenant encrypted credential binding.
--    Accessed ONLY via credentials.py / the get_secret() seam. Never '_global'
--    read-shared: a credential is always tenant-private (platform creds live under
--    the platform owner via the admin GUC, never readable cross-tenant).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provider_credentials (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        text NOT NULL,
    provider_def_id  uuid NOT NULL REFERENCES provider_definitions(id) ON DELETE CASCADE,
    ciphertext       bytea NOT NULL,                 -- AES-256-GCM(plaintext, DEK), 12-byte nonce prepended
    wrapped_dek      bytea,                          -- DEK wrapped under KEK-1 (Vault) ; NULL on interim Fernet path
    key_aad          text NOT NULL,                  -- 'tenant_id||provider_def_id||version' (GCM binding — MANDATORY)
    key_version      int NOT NULL DEFAULT 1,
    kek_version      text,                            -- enables rolling rotation
    scope            text NOT NULL DEFAULT 'integration',  -- 'integration'(vendor BYO, revealable) | 'ai_provider'(platform, masked-only)
    last_rotated_at  timestamptz,
    expires_at       timestamptz,
    is_active        boolean NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, provider_def_id, key_version)
);
CREATE INDEX IF NOT EXISTS provcred_tenant_idx ON provider_credentials (tenant_id, provider_def_id, is_active);

ALTER TABLE provider_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_credentials FORCE  ROW LEVEL SECURITY;
-- STRICTLY per-tenant (admin GUC OR own tenant) — credentials are never '_global' read-shared.
DROP POLICY IF EXISTS provcred_iso ON provider_credentials;
CREATE POLICY provcred_iso ON provider_credentials
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) );

-- ---------------------------------------------------------------------------
-- 3) provider_health_log — circuit-breaker input ; APPEND-ONLY ; FORCE-RLS.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provider_health_log (
    id               bigserial PRIMARY KEY,
    tenant_id        text NOT NULL,
    provider_def_id  uuid NOT NULL REFERENCES provider_definitions(id) ON DELETE CASCADE,
    checked_at       timestamptz NOT NULL DEFAULT now(),
    is_healthy       boolean,
    latency_ms       int,
    error_code       text
);
CREATE INDEX IF NOT EXISTS provhealth_def_idx ON provider_health_log (provider_def_id, checked_at DESC);

ALTER TABLE provider_health_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_health_log FORCE  ROW LEVEL SECURITY;
-- STRICTLY per-tenant (admin GUC OR own tenant) — health rows are private, not corpus.
DROP POLICY IF EXISTS provhealth_iso ON provider_health_log;
CREATE POLICY provhealth_iso ON provider_health_log
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) );

-- ============ append-only guard for provider_health_log (TRIGGER, not REVOKE) ============
-- WHY a trigger, not `REVOKE UPDATE, DELETE`: provider_health_log has an FK to
-- provider_definitions with ON DELETE CASCADE. A legitimate super-admin delete of a
-- provider_definition must cascade-delete its health rows — and famit_app (the cascade
-- executor, NOSUPERUSER/NOBYPASSRLS) needs the DELETE privilege for the cascade to run.
-- A blanket REVOKE blocks that cascade (proven on box: "permission denied" aborts the def
-- delete). The trigger gives true append-only for DIRECT app writes (any UPDATE, or a
-- DELETE that is NOT part of an FK cascade) while letting the FK cascade through — the
-- same end state the spec wants ("health-log UPDATE/DELETE blocked") without breaking
-- def deletion. A direct `DELETE FROM provider_health_log` from the app still raises.
CREATE OR REPLACE FUNCTION provider_health_log_append_only()
RETURNS trigger LANGUAGE plpgsql AS $aolog$
BEGIN
    IF (TG_OP = 'UPDATE') THEN
        RAISE EXCEPTION 'provider_health_log is append-only: UPDATE is not permitted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- DELETE: allow ONLY when it is the side effect of an FK cascade (def removal).
    -- A direct app DELETE has no cascading parent context -> block it.
    IF (TG_OP = 'DELETE') THEN
        IF pg_trigger_depth() <= 1 THEN
            RAISE EXCEPTION 'provider_health_log is append-only: direct DELETE is not permitted'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        RETURN OLD;  -- depth>1 => FK cascade from provider_definitions delete -> allowed
    END IF;
    RETURN NULL;
END;
$aolog$;

DROP TRIGGER IF EXISTS provider_health_log_append_only_trg ON provider_health_log;
CREATE TRIGGER provider_health_log_append_only_trg
    BEFORE UPDATE OR DELETE ON provider_health_log
    FOR EACH ROW EXECUTE FUNCTION provider_health_log_append_only();

-- ============ grants (famit_app owns these tables ; explicit + future-proofed) ============
GRANT SELECT, INSERT, UPDATE, DELETE ON provider_definitions  TO famit_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON provider_credentials  TO famit_app;
-- provider_health_log keeps DELETE so the provider_definitions FK CASCADE works; the
-- append-only TRIGGER above blocks any DIRECT UPDATE/DELETE from the app path.
GRANT SELECT, INSERT, UPDATE, DELETE ON provider_health_log TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO famit_app;

-- END db/ddl_provider_registry.sql
