-- voice_kernel/memory/ddl_lead_memory.sql
-- W7 — Structured LEAD MEMORY store (the MemoryService L4 home).
--
-- Posture REUSES the proven on-box pattern (db/ddl_wallet.sql + db/rls.sql) EXACTLY:
--   * IF NOT EXISTS / idempotent (re-runnable)
--   * applied STANDALONE via psql as the app role (NOT an Alembic revision — off
--     the live 0001/0002 chain)
--   * tenant_id TEXT == org_id == tenants.json id
--   * FORCE ROW LEVEL SECURITY with the admin-GUC escape hatch (USING + WITH CHECK)
--   * fail-closed: GUC unset -> current_setting(...,true) is NULL -> tenant_id=NULL
--     is NULL (not TRUE) -> ZERO rows (a missing tenant scope returns EMPTY, never all).
--
-- Maps 1:1 to the FROZEN LeadMemory dataclass (voice_kernel/packet.py:212-219).
-- last_call_summary is CLAMPED to 300 chars at the store (mirrors the prompt cap
-- _LAST_CALL_SUMMARY_CHARS) so a poisoned over-long summary can never bloat a
-- future prompt past the cache boundary.
--
-- EARNER LAW: this file edits NO live code. It is applied to the box only in the
-- LATER flag-gated cutover wave (see design/W7-MEMORY-SEAM.md).

-- =========================================================================== --
-- 1. lead_memory — ONE authoritative row per (tenant, lead). The WARM L4 head.
-- =========================================================================== --
CREATE TABLE IF NOT EXISTS lead_memory (
    tenant_id              TEXT        NOT NULL,
    lead_phone             TEXT        NOT NULL,                       -- E.164; per-tenant lead key
    name                   TEXT        NOT NULL DEFAULT '',
    lifecycle              TEXT        NOT NULL DEFAULT 'new',          -- new|hot|warm|cold|dead (Lifecycle enum)
    last_call_summary      TEXT        NOT NULL DEFAULT '',            -- <= 300 chars (app-clamped to match prompt)
    open_commitments       JSONB       NOT NULL DEFAULT '[]'::jsonb,   -- tuple[str,...]
    preferred_callback_ts  TEXT        NOT NULL DEFAULT '',
    do_not_mention         JSONB       NOT NULL DEFAULT '[]'::jsonb,   -- tuple[str,...] (suppression)
    conversion_prob        INTEGER     NOT NULL DEFAULT 0,             -- 0..100 internal score (founder's hidden number)
    call_count             INTEGER     NOT NULL DEFAULT 0,             -- audit/lifecycle
    next_best_action       TEXT        NOT NULL DEFAULT '',            -- COLD-generated NBA (advisory)
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, lead_phone),
    CONSTRAINT lead_summary_len  CHECK (char_length(last_call_summary) <= 300),
    CONSTRAINT lead_lifecycle_ck CHECK (lifecycle IN ('new','hot','warm','cold','dead')),
    CONSTRAINT lead_prob_range   CHECK (conversion_prob >= 0 AND conversion_prob <= 100)
);

-- =========================================================================== --
-- 2. lead_memory_summary — append-only summary HISTORY (the "consolidated
--    summaries" the cascade-delete research warns about). Erasure MUST purge
--    this leg too, not just the head row.
-- =========================================================================== --
CREATE TABLE IF NOT EXISTS lead_memory_summary (
    id                  BIGSERIAL    PRIMARY KEY,
    tenant_id           TEXT         NOT NULL,
    lead_phone          TEXT         NOT NULL,
    call_id             TEXT         NOT NULL DEFAULT '',   -- provenance: which call wrote this
    summary             TEXT         NOT NULL DEFAULT '',
    lifecycle_at_write  TEXT         NOT NULL DEFAULT 'new',
    conversion_prob     INTEGER      NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_lms_tenant_lead
    ON lead_memory_summary (tenant_id, lead_phone, created_at DESC);

-- =========================================================================== --
-- 3. RLS (FORCE; admin-GUC escape hatch — IDENTICAL shape to db/rls.sql).
--    WITH CHECK on BOTH USING and WITH CHECK so an INSERT/UPDATE with a forged
--    tenant_id is REJECTED (not merely hidden on read).
-- =========================================================================== --
DO $rls$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['lead_memory','lead_memory_summary']
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

-- =========================================================================== --
-- 4. Grants — app role only (NOSUPERUSER / NOBYPASSRLS so FORCE binds the owner).
-- =========================================================================== --
GRANT SELECT, INSERT, UPDATE, DELETE ON lead_memory, lead_memory_summary TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO famit_app;
