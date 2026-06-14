-- ============================================================================
-- db/ddl_trunk_registry.sql — Telephony Trunk Registry (T1).
-- Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.2 + §3 (red-team B1/D) + §5 (T1).
--
-- A column-for-column TWIN of db/ddl_provider_registry.sql (the LIVE provider_registry W1):
-- same FORCE ROW LEVEL SECURITY posture, the kb_*/`_global` read-share + write-lock,
-- AAD AES-256-GCM credential ciphertext, and the append-only health-log TRIGGER (not REVOKE).
--
-- THREE tables, all FORCE ROW LEVEL SECURITY, tenant_id TEXT NOT NULL:
--   1) sip_trunks             — the trunk spec (analog of provider_definitions). '_global'
--                               = platform-shared (super-admin owned, write-LOCKED from
--                               non-admin tenants). RED-TEAM B1: an `is_campaign_eligible`
--                               GENERATED column + a CHECK so an unregistered / non-140-series
--                               trunk is NEVER campaign-eligible at the DB layer (unbypassable
--                               even via a direct API write). RED-TEAM D: the live Vobiz
--                               `_global` row is marked un-deletable (is_undeletable) and a
--                               trigger refuses its DELETE.
--   2) sip_trunk_credentials  — per-tenant AAD-bound AES-256-GCM SIP-digest password
--                               ciphertext + a `scope` column (analog of provider_credentials).
--   3) sip_trunk_health_log   — APPEND-ONLY per-DID reputation/health log (analog of
--                               provider_health_log). UPDATE blocked + direct DELETE blocked
--                               via a trigger; FK cascade allowed (so a legit trunk delete
--                               cascades its health rows).
--
-- IDEMPOTENT: every statement is CREATE ... IF NOT EXISTS / DROP-then-CREATE-POLICY/TRIGGER,
-- so this whole file is safe to re-run (the seed at the bottom is ON CONFLICT DO NOTHING).
-- Applied standalone via `psql -f` as famit_app, NOT an Alembic revision — same posture as
-- db/ddl_provider_registry.sql / kb/schema.sql / db/ddl_wallet.sql.
--
-- MONEY = INTEGER PAISE (cost_per_minute_paise INTEGER). NO floats anywhere (founder law).
--
-- RLS shape = the P1 ADMIN-GUC policy (db/rls.sql / db/ddl_provider_registry.sql):
--   READ  (USING): admin GUC  OR  own tenant  OR  the shared '_global' row (trunks only).
--   WRITE (WITH CHECK): admin GUC  OR  (own tenant AND tenant_id <> '_global').
-- A tenant request path (is_admin=FALSE) can READ a '_global' trunk (so flag-on dials the
-- SAME live Vobiz trunk) but can NEVER insert/update/delete a '_global' row. Credentials and
-- health rows are STRICTLY per-tenant (no '_global' read-share — creds/health are private).
-- famit_app is NOSUPERUSER/NOBYPASSRLS (verified on box) so FORCE RLS binds even the owner.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) sip_trunks — the reusable, config-driven trunk spec.
--    '_global' tenant_id = platform-shared (super-admin owned, write-locked).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sip_trunks (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            text NOT NULL,                         -- '_global' for platform-shared, else the tenant id
    slug                 text NOT NULL,                         -- 'vobiz-outbound-tcp', 'plivo-blr', 'goip-personal'
    display_name         text NOT NULL,
    -- trunk_type: how this trunk bridges to PSTN. A consumer SIM is NEVER a trunk directly (§0).
    trunk_type           text NOT NULL DEFAULT 'sip_provider', -- 'sip_provider'|'gsm_gateway'|'direct_sip'
    provider_vendor      text,                                  -- 'vobiz'|'plivo'|'exotel'|'airtel'|'yeastar'...
    direction            text NOT NULL DEFAULT 'outbound',      -- 'outbound'|'inbound'|'both'
    -- SIP transport endpoint (host/port split; ssrf_guard validates host on write).
    sip_host             text NOT NULL,                         -- '2c24f731.sip.vobiz.ai'
    sip_port             int  NOT NULL DEFAULT 5060,
    transport            text NOT NULL DEFAULT 'udp',           -- 'udp'|'tcp'|'tls'
    encryption           text NOT NULL DEFAULT 'disable',       -- 'disable'|'srtp' (mirrors LiveKit trunk Encryption)
    auth_username        text,                                  -- SIP digest username ('capsy-project') ; password in table 2
    allowed_addresses    jsonb NOT NULL DEFAULT '[]'::jsonb,    -- inbound IP allowlist (CIDRs)
    did_pool             jsonb NOT NULL DEFAULT '[]'::jsonb,    -- rotated caller-IDs / from-numbers (E.164 '+91…')
    caller_id            text,                                  -- the default presented CLI (a single DID)
    -- concurrency cap (channel cap). GSM: == #SIMs, HARD 1/SIM. SIP-provider: the elastic ceiling.
    max_concurrency      int  NOT NULL DEFAULT 1,
    cost_per_minute_paise int,                                  -- INTEGER paise, never float (founder law)
    -- ===== COMPLIANCE GATES (red-team B1) — required for campaign use =====
    is_140_series        boolean NOT NULL DEFAULT false,        -- the DID is a 140-series promotional CLI
    dlt_entity_id        text,                                  -- DLT Principal-Entity id
    dlt_status           text NOT NULL DEFAULT 'unregistered',  -- 'unregistered'|'pending'|'registered'
    per_did_daily_cap    int  NOT NULL DEFAULT 0,               -- per-DID calls/day cap (0 = unset)
    -- rotation / failover
    priority             int  NOT NULL DEFAULT 100,             -- lower = higher in the selection/fallback chain
    rotation_strategy    text NOT NULL DEFAULT 'round_robin',   -- 'round_robin'|'least_used'|'sticky'
    -- state
    is_enabled           boolean NOT NULL DEFAULT true,
    is_test_verified     boolean NOT NULL DEFAULT false,        -- a founder test-call connected (gates campaign use)
    quarantined_until    timestamptz,                           -- spam-rest window end (NULL = not rested)
    is_undeletable       boolean NOT NULL DEFAULT false,        -- red-team D: the live Vobiz/env/AIM trunk
    livekit_trunk_id     text,                                  -- the LiveKit-SIP ST_<id> this row resolves to
    created_by           text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, slug),
    -- ===== RED-TEAM B1 — the campaign-eligibility GATE as a GENERATED column =====
    -- A trunk may ONLY be returned for a CAMPAIGN dial when it is a 140-series DID on a
    -- DLT-REGISTERED route. This is computed at the DB layer (STORED), so registry.get_trunk(
    -- purpose='campaign') filters on it and it is UNBYPASSABLE even by a direct /trunks/byo
    -- INSERT that flips is_enabled — the column is derived, not user-set.
    is_campaign_eligible boolean
        GENERATED ALWAYS AS ( is_140_series AND dlt_status = 'registered' ) STORED,
    -- defensive CHECKs (cheap, declarative)
    CONSTRAINT sip_trunks_trunk_type_ck CHECK (trunk_type IN ('sip_provider','gsm_gateway','direct_sip')),
    CONSTRAINT sip_trunks_direction_ck  CHECK (direction  IN ('outbound','inbound','both')),
    CONSTRAINT sip_trunks_transport_ck  CHECK (transport  IN ('udp','tcp','tls')),
    CONSTRAINT sip_trunks_dlt_status_ck CHECK (dlt_status IN ('unregistered','pending','registered')),
    CONSTRAINT sip_trunks_concurrency_ck CHECK (max_concurrency >= 1),
    -- RED-TEAM B1 belt-and-braces: a DB CHECK that the derived eligibility implies the inputs
    -- (a registered+140 row can never silently lose eligibility; a non-140/unregistered row can
    -- never be eligible). The GENERATED column already enforces the value; this CHECK documents
    -- + locks the invariant so a future ALTER can't quietly weaken it.
    CONSTRAINT sip_trunks_campaign_gate_ck CHECK (
        is_campaign_eligible = (is_140_series AND dlt_status = 'registered')
    )
);
CREATE INDEX IF NOT EXISTS sip_trunks_tenant_idx   ON sip_trunks (tenant_id, is_enabled, priority);
CREATE INDEX IF NOT EXISTS sip_trunks_campaign_idx ON sip_trunks (tenant_id, is_campaign_eligible);
CREATE INDEX IF NOT EXISTS sip_trunks_did_idx      ON sip_trunks USING gin (did_pool);

ALTER TABLE sip_trunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE sip_trunks FORCE  ROW LEVEL SECURITY;
-- READ: own rows OR the platform-shared '_global' rows OR super-admin GUC.
DROP POLICY IF EXISTS siptrunk_read ON sip_trunks;
CREATE POLICY siptrunk_read ON sip_trunks FOR SELECT
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true)
            OR tenant_id = '_global' );
-- WRITE: own rows only ('_global' write-locked to the super-admin GUC) — anti-privilege-escalation.
DROP POLICY IF EXISTS siptrunk_write ON sip_trunks;
CREATE POLICY siptrunk_write ON sip_trunks FOR ALL
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR (tenant_id = current_setting('app.tenant_id', true) AND tenant_id <> '_global') );

-- ============ RED-TEAM D — refuse DELETE of an un-deletable (live) trunk ============
-- The live Vobiz/env/AIM-inbound trunk shares the SAME LiveKit the earner dials; a misclick /
-- wrong-id / '_global' DELETE would kill the live trunk with no restart. A row flagged
-- is_undeletable=TRUE (seeded for the Vobiz '_global' row) RAISES on any DELETE — even the
-- super-admin GUC path. The package layer (T2/T3) defaults to soft-disable (is_enabled=false)
-- and gates any genuine hard-delete behind PIN + audit; this trigger is the DB backstop so the
-- live trunk can never be removed by accident regardless of the calling path.
CREATE OR REPLACE FUNCTION sip_trunks_protect_undeletable()
RETURNS trigger LANGUAGE plpgsql AS $undel$
BEGIN
    IF (OLD.is_undeletable) THEN
        RAISE EXCEPTION 'sip_trunks: trunk % (%) is marked un-deletable (live trunk) — soft-disable it, never DELETE',
            OLD.slug, OLD.id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN OLD;
END;
$undel$;

DROP TRIGGER IF EXISTS sip_trunks_protect_undeletable_trg ON sip_trunks;
CREATE TRIGGER sip_trunks_protect_undeletable_trg
    BEFORE DELETE ON sip_trunks
    FOR EACH ROW EXECUTE FUNCTION sip_trunks_protect_undeletable();

-- Keep is_undeletable itself immutable once TRUE (a row can't be un-protected then deleted in
-- two steps). A direct attempt to flip a TRUE->FALSE is refused.
CREATE OR REPLACE FUNCTION sip_trunks_lock_undeletable_flag()
RETURNS trigger LANGUAGE plpgsql AS $lockf$
BEGIN
    IF (OLD.is_undeletable AND NOT NEW.is_undeletable) THEN
        RAISE EXCEPTION 'sip_trunks: is_undeletable cannot be cleared on a protected (live) trunk %', OLD.slug
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$lockf$;

DROP TRIGGER IF EXISTS sip_trunks_lock_undeletable_trg ON sip_trunks;
CREATE TRIGGER sip_trunks_lock_undeletable_trg
    BEFORE UPDATE ON sip_trunks
    FOR EACH ROW EXECUTE FUNCTION sip_trunks_lock_undeletable_flag();

-- ---------------------------------------------------------------------------
-- 2) sip_trunk_credentials — per-tenant encrypted SIP-digest password.
--    Accessed ONLY via trunk_registry/credentials.py (REUSES provider_registry/credentials.py:
--    AAD = tenant_id||trunk_id||key_version, AES-256-GCM). Never '_global' read-shared.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sip_trunk_credentials (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        text NOT NULL,
    trunk_id         uuid NOT NULL REFERENCES sip_trunks(id) ON DELETE CASCADE,
    ciphertext       bytea NOT NULL,                 -- AES-256-GCM(sip_password, DEK), 12-byte nonce prepended
    wrapped_dek      bytea,                          -- DEK wrapped under KEK-1 (Vault) ; NULL on interim Fernet path
    key_aad          text NOT NULL,                  -- 'tenant_id||trunk_id||version' (GCM binding — MANDATORY)
    key_version      int NOT NULL DEFAULT 1,
    kek_version      text,                            -- enables rolling rotation
    scope            text NOT NULL DEFAULT 'integration',  -- 'integration'(vendor BYO, revealable) | 'platform'(masked-only)
    last_rotated_at  timestamptz,
    expires_at       timestamptz,
    is_active        boolean NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, trunk_id, key_version),
    CONSTRAINT sip_trunk_credentials_scope_ck CHECK (scope IN ('integration','platform'))
);
CREATE INDEX IF NOT EXISTS siptrunk_cred_tenant_idx ON sip_trunk_credentials (tenant_id, trunk_id, is_active);

ALTER TABLE sip_trunk_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE sip_trunk_credentials FORCE  ROW LEVEL SECURITY;
-- STRICTLY per-tenant (admin GUC OR own tenant) — SIP passwords are never '_global' read-shared.
DROP POLICY IF EXISTS siptrunk_cred_iso ON sip_trunk_credentials;
CREATE POLICY siptrunk_cred_iso ON sip_trunk_credentials
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) );

-- ---------------------------------------------------------------------------
-- 3) sip_trunk_health_log — per-DID reputation/health ; APPEND-ONLY ; FORCE-RLS.
--    (analog of provider_health_log). The spam-reputation + circuit input.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sip_trunk_health_log (
    id               bigserial PRIMARY KEY,
    tenant_id        text NOT NULL,
    trunk_id         uuid NOT NULL REFERENCES sip_trunks(id) ON DELETE CASCADE,
    did              text,                            -- the specific DID this event is about (reputation tracking)
    checked_at       timestamptz NOT NULL DEFAULT now(),
    event            text,                            -- 'probe'|'ring_out'|'connected'|'quarantine'|'release'...
    is_healthy       boolean,
    sip_code         int,                             -- the SIP response code when captured (NULL when inferred)
    latency_ms       int,
    error_code       text
);
CREATE INDEX IF NOT EXISTS siptrunk_health_trunk_idx ON sip_trunk_health_log (trunk_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS siptrunk_health_did_idx   ON sip_trunk_health_log (did, checked_at DESC);

ALTER TABLE sip_trunk_health_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE sip_trunk_health_log FORCE  ROW LEVEL SECURITY;
-- STRICTLY per-tenant (admin GUC OR own tenant) — health rows are private, not corpus.
DROP POLICY IF EXISTS siptrunk_health_iso ON sip_trunk_health_log;
CREATE POLICY siptrunk_health_iso ON sip_trunk_health_log
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) );

-- ============ append-only guard for sip_trunk_health_log (TRIGGER, not REVOKE) ============
-- Same rationale as provider_health_log: the FK ON DELETE CASCADE to sip_trunks needs
-- famit_app's DELETE priv for a legit trunk-delete to cascade; a blanket REVOKE would abort
-- it. The trigger blocks any UPDATE and any DIRECT app DELETE (pg_trigger_depth() <= 1) while
-- allowing the FK cascade (depth > 1) — the same end state ("health-log UPDATE/DELETE blocked")
-- without breaking trunk deletion.
CREATE OR REPLACE FUNCTION sip_trunk_health_log_append_only()
RETURNS trigger LANGUAGE plpgsql AS $aolog$
BEGIN
    IF (TG_OP = 'UPDATE') THEN
        RAISE EXCEPTION 'sip_trunk_health_log is append-only: UPDATE is not permitted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (TG_OP = 'DELETE') THEN
        IF pg_trigger_depth() <= 1 THEN
            RAISE EXCEPTION 'sip_trunk_health_log is append-only: direct DELETE is not permitted'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        RETURN OLD;  -- depth>1 => FK cascade from sip_trunks delete -> allowed
    END IF;
    RETURN NULL;
END;
$aolog$;

DROP TRIGGER IF EXISTS sip_trunk_health_log_append_only_trg ON sip_trunk_health_log;
CREATE TRIGGER sip_trunk_health_log_append_only_trg
    BEFORE UPDATE OR DELETE ON sip_trunk_health_log
    FOR EACH ROW EXECUTE FUNCTION sip_trunk_health_log_append_only();

-- ============ grants (famit_app owns these tables ; explicit + future-proofed) ============
GRANT SELECT, INSERT, UPDATE, DELETE ON sip_trunks            TO famit_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON sip_trunk_credentials TO famit_app;
-- sip_trunk_health_log keeps DELETE so the sip_trunks FK CASCADE works; the append-only
-- TRIGGER above blocks any DIRECT UPDATE/DELETE from the app path.
GRANT SELECT, INSERT, UPDATE, DELETE ON sip_trunk_health_log  TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO famit_app;

-- ============================================================================
-- SEED — the live Vobiz trunk (ST_fmtVmNJmpzKa) as ONE '_global' row, UN-DELETABLE
-- (red-team D). Marked NOT campaign-eligible by construction (is_140_series=false,
-- dlt_status='unregistered') so flag-on dials the EXACT same trunk for a founder TEST/
-- manual dial but is BLOCKED from the campaign pool until a 140/DLT route is bought (§7).
-- Values mirror the live LiveKit outbound trunk (read-only `lk sip outbound list`):
--   ST_fmtVmNJmpzKa = vobiz-outbound-tcp · host 2c24f731.sip.vobiz.ai · TCP · +918071583488
--   · auth user 'capsy-project' · encryption DISABLE.
-- Idempotent: ON CONFLICT (tenant_id, slug) DO NOTHING. Inserted under the super-admin GUC
-- (set in the apply step) because '_global' writes are admin-only.
-- ============================================================================
INSERT INTO sip_trunks (
    tenant_id, slug, display_name, trunk_type, provider_vendor, direction,
    sip_host, sip_port, transport, encryption, auth_username,
    did_pool, caller_id, max_concurrency, cost_per_minute_paise,
    is_140_series, dlt_status, per_did_daily_cap,
    priority, rotation_strategy, is_enabled, is_test_verified,
    is_undeletable, livekit_trunk_id, created_by
)
VALUES (
    '_global', 'vobiz-outbound-tcp', 'Vobiz Outbound (live, TCP)', 'sip_provider', 'vobiz', 'outbound',
    '2c24f731.sip.vobiz.ai', 5060, 'tcp', 'disable', 'capsy-project',
    '["+918071583488"]'::jsonb, '+918071583488', 1, NULL,
    false, 'unregistered', 0,
    10, 'round_robin', true, true,
    true, 'ST_fmtVmNJmpzKa', 'seed:ddl_trunk_registry.sql'
)
ON CONFLICT (tenant_id, slug) DO NOTHING;

-- END db/ddl_trunk_registry.sql
