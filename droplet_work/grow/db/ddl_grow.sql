-- ============================================================================
-- grow/db/ddl_grow.sql
-- Haptica Grow — Revenue-Truth Signal Loop (L5 scoring + L7 CAPI) FORCE-RLS tables.
--
-- Spec: plans/GROWTH-OS-BUILD-SPEC.md §11 (signal loop) + §9.5 (lead scoring) + §6.3
-- (journey/correlation spine). The InMemory twins (grow/store.py) run until this is
-- applied; the seam flag GROW_USE_PG=1 + db.engine availability bind the Pg backends.
-- Applying this file changes NOTHING in the live path on its own (FEATURE_GROW gates the
-- mount; the loop runs InMemory by default). Idempotent; re-runnable as famit_app.
--
-- RLS = the admin-GUC policy shape verbatim (ddl_wallet.sql / ddl_telephony_compliance.sql):
--   USING/WITH CHECK ( current_setting('app.is_admin',true)='1'
--                      OR org_id = current_setting('app.tenant_id',true) ).
-- famit_app = NOSUPERUSER/NOBYPASSRLS so FORCE ROW LEVEL SECURITY binds even the owner.
--
-- PII-MIN: NO raw phone/email at rest — only a salted principal_ref + a masked tail; the
-- signal ledger stores match-key TYPES (jsonb array of "ph"/"em"/"fbc"/"ctwa_clid"/…),
-- never the hashed PII values themselves. score/value are INTEGER (no floats for money).
-- ============================================================================

-- ====================================================================== --
-- grow_journeys : one person's journey (the correlation spine, §6.3).
-- journey_id minted at first touch, propagated through every event.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS grow_journeys (
    org_id          TEXT        NOT NULL,
    journey_id      TEXT        NOT NULL,
    principal_ref   TEXT        NOT NULL DEFAULT '',   -- salted hash (PII-min identity)
    phone_masked    TEXT        NOT NULL DEFAULT '',
    source_platform TEXT        NOT NULL DEFAULT '',   -- meta | google | whatsapp | manual
    source_ad_id    TEXT        NOT NULL DEFAULT '',
    ctwa_clid       TEXT        NOT NULL DEFAULT '',   -- click-to-WhatsApp click id (keys CAPI)
    fbclid          TEXT        NOT NULL DEFAULT '',
    gclid           TEXT        NOT NULL DEFAULT '',
    status          TEXT        NOT NULL DEFAULT 'open', -- open|qualified|booked|won|lost
    first_touch_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, journey_id),
    CONSTRAINT grow_journey_status_chk
        CHECK (status IN ('open','qualified','booked','won','lost'))
);
CREATE INDEX IF NOT EXISTS grow_journeys_src_idx ON grow_journeys (org_id, source_platform, status);

-- ====================================================================== --
-- grow_lead_scores : LATEST score per lead (re-scored on each journey event, §9.5).
-- features stored WITH the score = the training set for a future gradient-boosted v2.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS grow_lead_scores (
    org_id          TEXT        NOT NULL,
    lead_id         TEXT        NOT NULL,
    journey_id      TEXT        NOT NULL DEFAULT '',
    principal_ref   TEXT        NOT NULL DEFAULT '',
    phone_masked    TEXT        NOT NULL DEFAULT '',
    score           INTEGER     NOT NULL DEFAULT 0,    -- 0..100
    tier            TEXT        NOT NULL DEFAULT 'junk', -- hot|warm|investor|end_user|junk
    confidence      NUMERIC(4,3) NOT NULL DEFAULT 0.000,
    reasons         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    features        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    model           TEXT        NOT NULL DEFAULT 'heuristic_v1',
    source_platform TEXT        NOT NULL DEFAULT '',
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, lead_id),
    CONSTRAINT grow_score_range_chk CHECK (score >= 0 AND score <= 100),
    CONSTRAINT grow_tier_chk
        CHECK (tier IN ('hot','warm','investor','end_user','junk'))
);
CREATE INDEX IF NOT EXISTS grow_scores_tier_idx ON grow_lead_scores (org_id, tier, score DESC);

-- ====================================================================== --
-- grow_signals_log : the CAPI / Enhanced-Conversions dispatch ledger (§11).
-- event_id = sha256(journey_id|ladder_step) => idempotent re-sends (browser/server dedup).
-- APPEND-ONLY BY POLICY (app upserts status shadow->live on the same event_id; never DELETE).
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS grow_signals_log (
    org_id          TEXT        NOT NULL,
    event_id        TEXT        NOT NULL,              -- dedup key
    journey_id      TEXT        NOT NULL DEFAULT '',
    lead_id         TEXT        NOT NULL DEFAULT '',
    platform        TEXT        NOT NULL DEFAULT 'meta', -- meta | google
    endpoint        TEXT        NOT NULL DEFAULT 'capi', -- capi | enhanced_conversions
    event_name      TEXT        NOT NULL DEFAULT 'Lead', -- Lead|QualifiedLead|Schedule|Attended|Purchase
    value           INTEGER     NOT NULL DEFAULT 0,    -- value=lead_score (Lead) | order_value (Purchase)
    currency        TEXT        NOT NULL DEFAULT 'INR',
    match_keys      JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- key TYPES present, never hashed PII
    status          TEXT        NOT NULL DEFAULT 'shadow', -- shadow|queued|sent|acked|failed|deduped
    emq_estimate    NUMERIC(4,2) NOT NULL DEFAULT 0.00, -- match-quality proxy 0..10
    reason          TEXT        NOT NULL DEFAULT '',
    dispatched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, event_id),
    CONSTRAINT grow_signal_status_chk
        CHECK (status IN ('shadow','queued','sent','acked','failed','deduped'))
);
CREATE INDEX IF NOT EXISTS grow_signals_journey_idx ON grow_signals_log (org_id, journey_id);
CREATE INDEX IF NOT EXISTS grow_signals_status_idx  ON grow_signals_log (org_id, status, dispatched_at DESC);

-- ====================================================================== --
-- grow_orchestrations : one speed-to-lead run per journey (L3, W2) — the <60s
-- capture→fire record (compliance decision + which channels fired + SLA).
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS grow_orchestrations (
    org_id              TEXT        NOT NULL,
    journey_id          TEXT        NOT NULL,
    lead_id             TEXT        NOT NULL DEFAULT '',
    status              TEXT        NOT NULL DEFAULT 'done', -- done|blocked|no_channels|error
    compliance_decision TEXT        NOT NULL DEFAULT 'allow',-- allow|block|soft|unenforced
    compliance_reasons  JSONB       NOT NULL DEFAULT '[]'::jsonb,
    channels            JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- [{channel,status,ref,reason}]
    latency_ms          INTEGER     NOT NULL DEFAULT 0,      -- capture -> fire
    sla_met             BOOLEAN     NOT NULL DEFAULT true,
    completed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, journey_id),
    CONSTRAINT grow_orch_status_chk
        CHECK (status IN ('done','blocked','no_channels','error'))
);
CREATE INDEX IF NOT EXISTS grow_orch_status_idx ON grow_orchestrations (org_id, status, completed_at DESC);

-- ============================================================================
-- FORCE ROW LEVEL SECURITY (admin-GUC policy) on every grow table.
-- App connects as famit_app (NOSUPERUSER, NOBYPASSRLS); per-op SET LOCAL app.tenant_id /
-- app.is_admin (db.engine.session handles this in-txn). Drop-then-create = idempotent.
-- ============================================================================
DO $rls$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['grow_journeys','grow_lead_scores','grow_signals_log','grow_orchestrations']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS %1$s_isolation ON %1$I;', t);
    EXECUTE format($f$
      CREATE POLICY %1$s_isolation ON %1$I
      USING (
        current_setting('app.is_admin', true) = '1'
        OR org_id = current_setting('app.tenant_id', true)
      )
      WITH CHECK (
        current_setting('app.is_admin', true) = '1'
        OR org_id = current_setting('app.tenant_id', true)
      );
    $f$, t);
  END LOOP;
END $rls$;

-- ============ grants (famit_app owns these tables) ============
GRANT SELECT, INSERT, UPDATE ON grow_journeys, grow_lead_scores, grow_signals_log, grow_orchestrations TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;

-- grow_signals_log is APPEND-ONLY BY POLICY: the app issues INSERT + idempotent status
-- UPDATE (shadow->live on the same event_id) but NEVER DELETE — the dispatch ledger is the
-- audit + the learning dataset. An erasure scrubs the principal_ref, never deletes the row.
