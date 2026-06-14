-- ============================================================================
-- communication/db/ddl_comm_cost.sql — the Communication COST-GUARD store (Wave 3).
-- Spec: communication/COMMUNICATION-MASTER-PLAN.md §6 (the 6 cost guards as ACCEPTANCE
-- GATES, not "later"). Additive to ddl_comm.sql (the 4 W1 tables); alters nothing.
--
-- THREE durable cost-guard tables (the 4th/5th/6th guards — metering + token-bucket —
-- need no new table: metering rides wallet_transactions, the token-bucket is in-process):
--   1) comm_daily_spend   — per-(tenant, channel, UTC-day) running spend in paise. The
--                           per-tenant daily BUDGET CEILING checks SUM against the cap, and
--                           the SPEND-ANOMALY guard reads the trailing-7-day series here.
--   2) comm_freq_counter  — per-(tenant, contact_ref, channel, UTC-day) send count. The
--                           per-contact FREQUENCY CAP (stops a journey bug spamming+billing).
--   3) comm_deliverability — per-(tenant, contact_ref, channel) reachability state. A 403
--                           block flips state='dead' so "cheapest" = "cheapest NOT known-dead
--                           for THIS contact", never "column non-null".
--
-- CONVENTIONS (identical to ddl_comm.sql — gate at review):
--   * tenant_id TEXT everywhere (== org_id). NO uuid/UUID PK/FK (breaks the RLS GUC
--     string-compare current_setting('app.tenant_id',true) which is TEXT -> fails-open).
--   * All money BIGINT paise. Idempotent CREATE ... IF NOT EXISTS (safe to re-run).
--   * RLS = the ddl_ai_wa.sql admin-GUC DO $rls$ block VERBATIM (FORCE; famit_app
--     NOSUPERUSER/NOBYPASSRLS so it binds even the owner).
--   * NO new credential table, NO new money table (metering reuses wallet.reserve->settle).
--
-- Applied STANDALONE via the live db.engine (off the Alembic chain), like ddl_comm.sql.
-- Rollback: DROP TABLE comm_daily_spend, comm_freq_counter, comm_deliverability.
-- ============================================================================

-- ---------- 1) comm_daily_spend: per-(tenant,channel,day) spend (budget ceiling + anomaly) ----------
-- One row per (tenant, channel, UTC day). spend_minor accumulates the SETTLED cost of every
-- send that day (Telegram = 0; paid channels add their per-message cost). The budget ceiling
-- reads SUM(spend_minor) for today vs the per-tenant cap; the anomaly guard reads the last 7
-- days' totals to compute the trailing median. INTEGER paise. send_count is a free side-signal.
CREATE TABLE IF NOT EXISTS comm_daily_spend (
    tenant_id     TEXT        NOT NULL,                       -- RLS key
    channel       TEXT        NOT NULL DEFAULT 'telegram',    -- telegram|email|sms|whatsapp
    day           DATE        NOT NULL,                        -- UTC day bucket
    spend_minor   BIGINT      NOT NULL DEFAULT 0,              -- INR paise spent this (tenant,channel,day)
    send_count    BIGINT      NOT NULL DEFAULT 0,              -- # of metered sends this bucket
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, channel, day)
);
CREATE INDEX IF NOT EXISTS ix_comm_daily_spend_tenant ON comm_daily_spend (tenant_id, day DESC);

-- ---------- 2) comm_freq_counter: per-(tenant,contact,channel,day) send count (frequency cap) ----------
-- One row per (tenant, contact_ref, channel, UTC day). sent_count is atomically incremented
-- on each contact-facing send; the cap blocks the (N+1)-th send to the SAME contact that day.
-- This stops a runaway journey/loop from both SPAMMING the contact and BILLING the tenant.
CREATE TABLE IF NOT EXISTS comm_freq_counter (
    tenant_id     TEXT        NOT NULL,                       -- RLS key
    contact_ref   TEXT        NOT NULL DEFAULT '',            -- chat_id / phone / email
    channel       TEXT        NOT NULL DEFAULT 'telegram',
    day           DATE        NOT NULL,                        -- UTC day bucket
    sent_count    BIGINT      NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, contact_ref, channel, day)
);
CREATE INDEX IF NOT EXISTS ix_comm_freq_tenant ON comm_freq_counter (tenant_id, day DESC);

-- ---------- 3) comm_deliverability: per-(tenant,contact,channel) reachability state ----------
-- One row per (tenant, contact_ref, channel). A Telegram 403 (bot blocked / chat not found)
-- flips state='dead' so the cost-router never re-attempts (and never bills) a known-dead
-- destination. An email bounce/complaint flips 'suppressed' (W3 email). 'ok' is reachable.
CREATE TABLE IF NOT EXISTS comm_deliverability (
    tenant_id     TEXT        NOT NULL,                       -- RLS key
    contact_ref   TEXT        NOT NULL DEFAULT '',            -- chat_id / phone / email
    channel       TEXT        NOT NULL DEFAULT 'telegram',
    state         TEXT        NOT NULL DEFAULT 'ok',          -- ok|dead|suppressed
    reason        TEXT        NOT NULL DEFAULT '',            -- a short machine code (http_403 / bounce / complaint)
    fail_count    BIGINT      NOT NULL DEFAULT 0,
    last_event_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, contact_ref, channel)
);
CREATE INDEX IF NOT EXISTS ix_comm_deliverability_tenant ON comm_deliverability (tenant_id, channel, state);

-- ============ RLS (FORCE; admin-GUC escape hatch — ddl_ai_wa.sql shape VERBATIM) ============
DO $rls$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['comm_daily_spend','comm_freq_counter','comm_deliverability']
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

-- ============================================================================
-- END ddl_comm_cost.sql — 3 FORCE-RLS cost-guard tables, additive, idempotent.
-- The 4th guard (per-message metering) reuses wallet_transactions; the 6th
-- (per-bot token-bucket) is an in-process async limiter (no table).
-- ============================================================================
