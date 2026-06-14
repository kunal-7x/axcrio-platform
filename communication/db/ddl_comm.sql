-- ============================================================================
-- communication/db/ddl_comm.sql — the Communication (Telegram/Email/SMS) store.
-- Spec: communication/COMMUNICATION-MASTER-PLAN.md §3 (DATA MODEL) — Wave 1 MVP.
--
-- WAVE 1 = exactly FOUR tables (the over-engineering cut, plan §3.1):
--   1) comm_sessions     — LLM brain rolling 20-turn window (seeded post-call)
--   2) comm_send_log     — every outbound, every channel; APPEND-ONLY
--   3) comm_consent_log  — (channel x purpose) consent artifact; APPEND-ONLY (hard)
--   4) comm_asset_cache  — Telegram file_id reuse (re-send media at zero cost)
--
-- CONVENTIONS (plan README "Conventions any build agent MUST honor"):
--   * tenant_id TEXT everywhere (== org_id). NO uuid/UUID PK/FK (a UUID breaks the
--     RLS GUC string-compare current_setting('app.tenant_id',true) which is TEXT
--     -> fails-open-shaped). All PKs TEXT "<prefix>_<uuid4hex>" (matches ai_wa_*).
--   * All money BIGINT paise. Idempotent CREATE ... IF NOT EXISTS (safe to re-run).
--   * RLS = the ddl_ai_wa.sql admin-GUC DO $rls$ block VERBATIM:
--       USING/WITH CHECK ( current_setting('app.is_admin',true)='1'
--                          OR tenant_id = current_setting('app.tenant_id',true) )
--     famit_app is NOSUPERUSER/NOBYPASSRLS so FORCE RLS binds even the owner.
--   * NO new credential table (Telegram/Email/SMS token = a provider_credentials
--     row via the LIVE registry vault). NO new money table (every send writes ONE
--     wallet_transactions row via wallet.reserve->settle/release).
--
-- Applied STANDALONE via the live db.engine (NOT an Alembic revision — off the
-- live migration chain), exactly like ddl_ai_wa.sql / ddl_wallet.sql. Additive:
-- it alters NOTHING that exists; dropping the 4 tables is a clean rollback.
-- ============================================================================

-- ---------- 1) comm_sessions: the LLM brain rolling window (seeded post-call) ----------
-- One conversational session per (tenant, channel, external_chat_id). Holds the
-- last-20-turn JSONB window + the post-call seed (summary/next_action/outcome).
-- This is the W2 brain's memory; in W1 it is seeded by the post-call hook only.
CREATE TABLE IF NOT EXISTS comm_sessions (
    session_id        TEXT        PRIMARY KEY,                      -- "cse_<uuid4hex>"
    tenant_id         TEXT        NOT NULL,                          -- == org_id (RLS key)
    channel           TEXT        NOT NULL DEFAULT 'telegram',       -- telegram|email|sms|whatsapp
    external_chat_id  TEXT        NOT NULL DEFAULT '',               -- TG chat_id / email addr / phone
    provider_def_id   TEXT        NOT NULL DEFAULT '',               -- the channel registry row (no shared bot across tenants, S4)
    contact_phone     TEXT        NOT NULL DEFAULT '',               -- phone anchor (cross-call recap, W2)
    lead_id           TEXT        NOT NULL DEFAULT '',               -- CRM lead linkage when known
    call_id           TEXT        NOT NULL DEFAULT '',               -- the originating call (provenance)
    agent_persona     TEXT        NOT NULL DEFAULT 'Riya',           -- inherited from the voice earner (§1.2)
    turns             JSONB       NOT NULL DEFAULT '[]'::jsonb,      -- rolling last-20 [{role,text,at}]
    call_summary      TEXT        NOT NULL DEFAULT '',               -- post-call seed
    next_action       TEXT        NOT NULL DEFAULT '',               -- post-call seed
    outcome           TEXT        NOT NULL DEFAULT '',               -- interested|booked|not_interested|callback|... (CAPI input)
    interest          TEXT        NOT NULL DEFAULT '',               -- hot|warm|cold
    status            TEXT        NOT NULL DEFAULT 'open',           -- open|handed_off|closed
    last_message_at   TIMESTAMPTZ NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, channel, external_chat_id, provider_def_id)
);
CREATE INDEX IF NOT EXISTS ix_comm_sessions_tenant   ON comm_sessions (tenant_id, last_message_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_comm_sessions_phone    ON comm_sessions (tenant_id, contact_phone);
CREATE INDEX IF NOT EXISTS ix_comm_sessions_call     ON comm_sessions (tenant_id, call_id);

-- ---------- 2) comm_send_log: every outbound, every channel (APPEND-ONLY) ----------
-- One row per outbound message attempt. cost_minor in INTEGER paise. idempotency_key
-- UNIQUE makes a retried create_task safe (idem_key = comms:{message_id}). outcome is
-- the day-1 CAPI revenue-signal column (§1.2 #1). delivered/read/clicked are W3+.
CREATE TABLE IF NOT EXISTS comm_send_log (
    message_id        TEXT        PRIMARY KEY,                      -- "cms_<uuid4hex>"
    tenant_id         TEXT        NOT NULL,                          -- RLS key
    session_id        TEXT        NOT NULL DEFAULT '',               -- comm_sessions linkage (may be '')
    channel           TEXT        NOT NULL DEFAULT 'telegram',
    provider_def_id   TEXT        NOT NULL DEFAULT '',
    direction         TEXT        NOT NULL DEFAULT 'outbound',       -- outbound|inbound
    kind              TEXT        NOT NULL DEFAULT 'text',           -- text|photo|document|video|alert|summary
    purpose           TEXT        NOT NULL DEFAULT 'service',        -- marketing|service|transactional
    to_ref            TEXT        NOT NULL DEFAULT '',               -- chat_id / email / phone (the destination)
    body_preview      TEXT        NOT NULL DEFAULT '',               -- first ~280 chars (audit; never the full PII blob)
    media_ref         TEXT        NOT NULL DEFAULT '',               -- spaces_key / file_id used
    cost_minor        BIGINT      NOT NULL DEFAULT 0,                -- INR paise (Telegram = 0)
    wallet_txn_id     TEXT        NOT NULL DEFAULT '',               -- the reserve->settle ledger row
    idempotency_key   TEXT        NOT NULL,                          -- comms:{message_id} (UNIQUE)
    status            TEXT        NOT NULL DEFAULT 'queued',         -- queued|sent|delivered|read|failed|blocked_*
    external_id       TEXT        NOT NULL DEFAULT '',               -- provider message id (TG message_id)
    error_code        TEXT        NOT NULL DEFAULT '',
    outcome           TEXT        NOT NULL DEFAULT '',               -- CAPI revenue-signal (booked|sale|...) — day-1 col
    delivered_at      TIMESTAMPTZ NULL,
    read_at           TIMESTAMPTZ NULL,
    clicked_at        TIMESTAMPTZ NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_comm_send_tenant   ON comm_send_log (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_comm_send_session  ON comm_send_log (tenant_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_comm_send_status   ON comm_send_log (tenant_id, status);

-- ---------- 3) comm_consent_log: (channel x purpose) consent artifact (APPEND-ONLY HARD) ----------
-- The canonical (channel x purpose) consent model (plan §5). consent_basis is DERIVED
-- from lead_source (purchased lists != service-implicit). Every contact-facing send
-- records one row BEFORE the first send. Append-only is enforced TWICE: REVOKE +
-- a BEFORE UPDATE/DELETE RAISE trigger (an immutable compliance artifact).
CREATE TABLE IF NOT EXISTS comm_consent_log (
    consent_id        TEXT        PRIMARY KEY,                      -- "cco_<uuid4hex>"
    tenant_id         TEXT        NOT NULL,                          -- RLS key
    contact_ref       TEXT        NOT NULL DEFAULT '',               -- phone / chat_id / email the consent is about
    channel           TEXT        NOT NULL DEFAULT 'telegram',       -- telegram|email|sms|whatsapp|* (any)
    purpose           TEXT        NOT NULL DEFAULT 'service',        -- marketing|service|transactional
    action            TEXT        NOT NULL DEFAULT 'grant',          -- grant|revoke (STOP)
    consent_basis     TEXT        NOT NULL DEFAULT '',               -- derived: inbound_form|prior_transaction|telegram_start|purchased_optin|...
    lead_source       TEXT        NOT NULL DEFAULT '',               -- the source the basis was derived from (provenance)
    wording           TEXT        NOT NULL DEFAULT '',               -- the exact consent prompt shown ("I'll text you a summary, okay?")
    captured_by       TEXT        NOT NULL DEFAULT '',               -- system|agent|tenant
    call_id           TEXT        NOT NULL DEFAULT '',               -- the call where consent was captured (provenance)
    captured_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_comm_consent_contact ON comm_consent_log (tenant_id, contact_ref, channel, purpose, captured_at DESC);

-- ---------- 4) comm_asset_cache: Telegram file_id reuse (re-send media at zero cost) ----------
-- §1.2 #6: a Telegram upload returns a file_id; caching it lets every later send of the
-- SAME asset on the SAME channel reuse the id (brochure/banner re-sends at zero cost).
CREATE TABLE IF NOT EXISTS comm_asset_cache (
    cache_id          TEXT        PRIMARY KEY,                      -- "cac_<uuid4hex>"
    tenant_id         TEXT        NOT NULL,                          -- RLS key
    spaces_key        TEXT        NOT NULL DEFAULT '',               -- the source object (DO Spaces key) or asset_id
    channel           TEXT        NOT NULL DEFAULT 'telegram',
    media_kind        TEXT        NOT NULL DEFAULT 'photo',          -- photo|document|video
    external_file_id  TEXT        NOT NULL DEFAULT '',               -- the provider file_id to reuse (§1.2 #6)
    bytes_size        BIGINT      NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at      TIMESTAMPTZ NULL,
    UNIQUE (tenant_id, spaces_key, channel)
);
CREATE INDEX IF NOT EXISTS ix_comm_asset_cache_key ON comm_asset_cache (tenant_id, spaces_key, channel);

-- ============ RLS (FORCE; admin-GUC escape hatch — ddl_ai_wa.sql shape VERBATIM) ============
-- App connects as famit_app (NOSUPERUSER, NOBYPASSRLS). Per-op the engine sets
-- SET LOCAL app.tenant_id / app.is_admin in-txn. FORCE binds even the table owner.
DO $rls$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['comm_sessions','comm_send_log','comm_consent_log','comm_asset_cache']
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
END
$rls$;

-- ============ APPEND-ONLY hardening (the two compliance/audit ledgers) ============
-- comm_send_log + comm_consent_log are append-only: a written row is immutable truth.
-- Defense 1 = REVOKE the privileges from famit_app. Defense 2 = a BEFORE UPDATE/DELETE
-- trigger that RAISEs (so even a future GRANT cannot silently mutate the ledger).
REVOKE UPDATE, DELETE ON comm_consent_log FROM famit_app;

-- NOTE: comm_send_log needs UPDATE for delivery-state transitions in W3 (delivered/read/
-- clicked + status). In W1 it is written-once. We therefore harden comm_consent_log HARD
-- (no lifecycle ever) and leave comm_send_log REVOKE off so W3 can flip status; its
-- immutability of the create row is covered by the UNIQUE idempotency_key (no re-insert)
-- and the audit trail. (Plan §3.1 lists send-log as append-only at create; W3 adds
-- whitelisted lifecycle columns only.)

CREATE OR REPLACE FUNCTION comm_consent_immutable() RETURNS trigger AS $immut$
BEGIN
  RAISE EXCEPTION 'comm_consent_log is append-only (immutable compliance artifact)';
  RETURN NULL;
END;
$immut$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS comm_consent_no_update ON comm_consent_log;
CREATE TRIGGER comm_consent_no_update
  BEFORE UPDATE OR DELETE ON comm_consent_log
  FOR EACH ROW EXECUTE FUNCTION comm_consent_immutable();

-- ============================================================================
-- END ddl_comm.sql — 4 FORCE-RLS tables, additive, idempotent, append-only consent.
-- Apply: load via the live db.engine as famit_app (the platform pattern), behind
-- COMM_ENABLED (the code flag; the DDL itself is inert data until the code reads it).
-- Rollback: DROP TABLE comm_sessions, comm_send_log, comm_consent_log, comm_asset_cache.
-- ============================================================================
