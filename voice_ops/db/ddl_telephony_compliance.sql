-- ============================================================================
-- voice_ops/db/ddl_telephony_compliance.sql
-- W12 Telephony Sales-OS + W26 India Compliance Engine — FORCE-RLS tables.
--
-- Spec: design/W12-TELEPHONY-COMPLIANCE-SEAM.md + design/W26-COMPLIANCE-CONSENT-ENGINE.md.
-- These are the PG tables the later Pg*Store seam swaps bind to. Until applied, the
-- voice_ops InMemory stores run (single dial worker = authoritative). Applying this file
-- changes NOTHING in the live dial path on its own — the seam flags (TELEPHONY_OPS_ENABLED /
-- COMPLIANCE_ENABLED) gate every use, default OFF.
--
-- RLS: the P1 ADMIN-GUC policy shape verbatim (db/rls.sql / ddl_wallet.sql):
--   USING/WITH CHECK ( current_setting('app.is_admin',true)='1'
--                      OR tenant_id = current_setting('app.tenant_id',true) ).
-- famit_app = NOSUPERUSER/NOBYPASSRLS so FORCE ROW LEVEL SECURITY binds even the owner.
-- Applied standalone via psql as famit_app (NOT an Alembic revision; idempotent re-runnable).
--
-- PII-MINIMISATION: NO raw phone numbers at rest in the compliance tables — only salted
-- SHA-256 hashes (number_hash / data_principal_ref). Money/counters are INTEGER (no floats).
-- ============================================================================

-- ====================================================================== --
-- W12 #2 — phone_number_pool : the tenant's outbound fleet (multi-number mgmt).
-- The InMemory twin is voice_ops.telephony.number_pool.PoolNumber.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS phone_number_pool (
    tenant_id        TEXT        NOT NULL,
    number           TEXT        NOT NULL,                 -- E.164 outbound CLI / DID
    trunk_id         TEXT        NOT NULL DEFAULT '',      -- SIP trunk carrying this DID (ST_<id>)
    status           TEXT        NOT NULL DEFAULT 'active',-- active | paused | disabled
    series           TEXT        NOT NULL DEFAULT '',      -- '140' | '160' | '1600' | '' (compliance CLI tag)
    daily_cap        INTEGER     NOT NULL DEFAULT 0,       -- 0 -> config per_number_daily_cap
    concurrency      INTEGER     NOT NULL DEFAULT 0,       -- 0 -> config per_number_concurrency
    cooldown_s       INTEGER     NOT NULL DEFAULT 0,       -- 0 -> config cooldown_seconds
    used_today       INTEGER     NOT NULL DEFAULT 0,
    used_day         DATE        NULL,                     -- UTC date of used_today (day-roll reset)
    in_flight        INTEGER     NOT NULL DEFAULT 0,
    last_dial_at     TIMESTAMPTZ NULL,                     -- cooldown gate (wall clock for PG)
    -- rolling spam-reputation counters (the SpamReputation scorer can persist here)
    answered_window  INTEGER     NOT NULL DEFAULT 0,
    rejected_window  INTEGER     NOT NULL DEFAULT 0,
    blocked_window   INTEGER     NOT NULL DEFAULT 0,
    spam_flag_window INTEGER     NOT NULL DEFAULT 0,
    health_score     NUMERIC(4,3) NOT NULL DEFAULT 0.500,  -- 0.000..1.000
    health_state     TEXT        NOT NULL DEFAULT 'healthy',-- healthy | degraded | quarantined
    rest_until       TIMESTAMPTZ NULL,                     -- set while quarantined
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, number),
    CONSTRAINT pnp_status_chk CHECK (status IN ('active','paused','disabled')),
    CONSTRAINT pnp_inflight_nonneg CHECK (in_flight >= 0),
    CONSTRAINT pnp_used_nonneg     CHECK (used_today >= 0)
);
CREATE INDEX IF NOT EXISTS idx_pnp_tenant_status ON phone_number_pool (tenant_id, status);

-- ====================================================================== --
-- W26 (1) consent_ledger : APPEND-ONLY consent record (the legal evidence).
-- The InMemory twin is voice_ops.compliance.consent.ConsentRow. A revocation/refresh
-- is a NEW row (never UPDATE/DELETE); the gate reads the newest non-revoked, non-expired.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS consent_ledger (
    id                 BIGSERIAL    PRIMARY KEY,
    tenant_id          TEXT         NOT NULL,
    data_principal_ref TEXT         NOT NULL,              -- salted hash of phone / lead_id (NO raw PII)
    consent_type       TEXT         NOT NULL,              -- tcccpr_place_call | dpdp_process_data | recording
    basis              TEXT         NOT NULL,              -- explicit | inferred | legitimate_use
    channel            TEXT         NOT NULL DEFAULT 'import', -- web_form|ivr_dtmf|verbal_oncall|whatsapp|import
    scope              TEXT         NOT NULL DEFAULT '',   -- campaign_id / purpose
    granted_at         TIMESTAMPTZ  NOT NULL,
    expires_at         TIMESTAMPTZ  NULL,                  -- explicit-txn = +7d; inferred = contract end; null = until-revoked
    revoked_at         TIMESTAMPTZ  NULL,                  -- revocation = a NEW row stamped here
    evidence_ref       TEXT         NOT NULL DEFAULT '',   -- pointer to recording/form proving informed consent
    source_meta        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT cl_type_chk  CHECK (consent_type IN ('tcccpr_place_call','dpdp_process_data','recording')),
    CONSTRAINT cl_basis_chk CHECK (basis IN ('explicit','inferred','legitimate_use'))
);
CREATE INDEX IF NOT EXISTS idx_cl_lookup
    ON consent_ledger (tenant_id, data_principal_ref, consent_type, scope, created_at DESC);

-- ====================================================================== --
-- W26 (2) dlt_registry : per-tenant DLT registration state (drives A1/A2/A5).
-- The InMemory twin is voice_ops.compliance.engine.RegistrationState.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS dlt_registry (
    tenant_id          TEXT         NOT NULL,
    pe_id              TEXT         NOT NULL DEFAULT '',
    pe_status          TEXT         NOT NULL DEFAULT 'none',   -- none|pending|active|suspended
    sender_of_record   TEXT         NOT NULL DEFAULT 'tenant', -- tenant | famit (liability decision)
    headers            JSONB        NOT NULL DEFAULT '[]'::jsonb, -- [{header,kind:promo|service,status}]
    templates          JSONB        NOT NULL DEFAULT '[]'::jsonb, -- [{template_id,variable_slots:[...],status}]
    cli_numbers        JSONB        NOT NULL DEFAULT '[]'::jsonb, -- [{number,series:140|1600,status}]
    autodialer_notified BOOLEAN     NOT NULL DEFAULT false,    -- access-provider pre-notification done
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id),
    CONSTRAINT dlt_pe_status_chk CHECK (pe_status IN ('none','pending','active','suspended'))
);

-- ====================================================================== --
-- W26 (3) dnd_cache : NCPR/DND scrub cache (national register, <=30d freshness).
-- NOTE: the NCPR register is national (NOT tenant-scoped) — no tenant_id column. RLS is
-- therefore NOT applied to dnd_cache (a shared cache of public DND status, keyed by a
-- salted hash that contains no PII). The PER-TENANT opt-out (local suppression) lives in
-- the tenant-scoped table below. A stale row (refreshed_at < now()-30d) = MISS -> re-scrub.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS dnd_cache (
    number_hash   TEXT         NOT NULL,                   -- salted SHA-256 of E.164 (no raw PII)
    category      TEXT         NOT NULL DEFAULT 'all',     -- promo categories opted out of
    listed        BOOLEAN      NOT NULL,
    refreshed_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (number_hash, category)
);

-- W26 (3b) local per-tenant suppression (on-call opt-out: "say stop / press 9").
CREATE TABLE IF NOT EXISTS dnd_suppression (
    tenant_id    TEXT         NOT NULL,
    number_hash  TEXT         NOT NULL,                    -- salted hash (no raw PII)
    reason       TEXT         NOT NULL DEFAULT 'on_call_optout',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, number_hash)
);

-- ====================================================================== --
-- W26 (4) compliance_audit : append-only decision log (>=6mo UCC retention).
-- Never UPDATE/DELETE; erasure cascades scrub principal refs, not the decision row.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS compliance_audit (
    id              BIGSERIAL    PRIMARY KEY,
    tenant_id       TEXT         NOT NULL,
    call_id         TEXT         NOT NULL DEFAULT '',
    campaign_id     TEXT         NOT NULL DEFAULT '',
    decision        TEXT         NOT NULL,                 -- allow | block | soft
    gate            TEXT         NOT NULL,                 -- registration|number_series|window|consent|dnd|disclosure
    reason          TEXT         NOT NULL DEFAULT '',
    disclosure_tier SMALLINT     NULL,                     -- 0|1|2 emitted on this call
    at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ca_decision_chk CHECK (decision IN ('allow','block','soft'))
);
CREATE INDEX IF NOT EXISTS idx_ca_tenant_at ON compliance_audit (tenant_id, at DESC);

-- ============================================================================
-- FORCE ROW LEVEL SECURITY (admin-GUC policy) on every TENANT-SCOPED table.
-- dnd_cache is intentionally excluded (national, no tenant_id — see note above).
-- App connects as famit_app (NOSUPERUSER, NOBYPASSRLS); per-op SET LOCAL app.tenant_id /
-- app.is_admin (db.engine.session handles this in-txn). Drop-then-create = idempotent.
-- ============================================================================
DO $rls$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['phone_number_pool','consent_ledger','dlt_registry',
                           'dnd_suppression','compliance_audit']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS %1$s_isolation ON %1$I;', t);
    EXECUTE format($f$
      CREATE POLICY %1$s_isolation ON %1$I
      USING (
        current_setting('app.is_admin', true) = '1'
        OR tenant_id = current_setting('app.tenant_id', true)
      )
      WITH CHECK (
        current_setting('app.is_admin', true) = '1'
        OR tenant_id = current_setting('app.tenant_id', true)
      );
    $f$, t);
  END LOOP;
END $rls$;

-- ============ grants (famit_app owns these tables; explicit + future-proofed) ============
GRANT SELECT, INSERT, UPDATE ON
    phone_number_pool, consent_ledger, dlt_registry, dnd_cache, dnd_suppression, compliance_audit
    TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO famit_app;

-- consent_ledger + compliance_audit are APPEND-ONLY by policy: famit_app is granted
-- INSERT/SELECT but the app NEVER issues UPDATE/DELETE against them (the legal evidence
-- + UCC audit must be immutable). A revocation is a new consent row; an erasure scrubs
-- the data_principal_ref via a controlled admin op, never deletes the decision row.
