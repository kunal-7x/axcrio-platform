-- ============================================================================
-- db/ddl_ad_events.sql — ElevateX CONVERSION-SIGNAL SPINE · additive RLS migration (V2 W3/W6).
-- Spec: plans/elevatex/v2/V2_MASTER_PLAN.md §8 ("The event spine (the closed loop, P0)").
-- Apply AFTER db/ddl_ads_engine.sql, as the famit_app NOSUPERUSER/NOBYPASSRLS role.
--
-- WHY THIS FILE EXISTS (and why it is NOT a new typed table):
--   The ad_events spine (lead_submitted -> call_connected -> lead_qualified/hot ->
--   site_visit_booked -> booking) is written by the STRANGLER store API
--   `store.append_ad_event` / `get_ad_events` / `find_ad_event` / `update_ad_event`,
--   which persist into the GENERIC high-churn list table `ads_tenant_rows` with
--   collection = 'ad_events' (one append-only jsonb row per event). That table is ALREADY
--   created with `FORCE ROW LEVEL SECURITY` + the per-tenant GUC policy by db/ddl_ads_engine.sql
--   (lines 82-98) — identical isolation to the vault. So ad_events INHERIT bank-grade
--   tenant isolation for free; a dedicated typed table would be DEAD DDL (nothing writes it)
--   and would FORK the strangler. We deliberately keep ONE storage model.
--
-- WHAT THIS MIGRATION ADDS (purely additive, idempotent, safe to re-run):
--   Performance indexes for the THREE hot ad_events access paths that the W3/W6 closed loop
--   drives every tick on a high-churn collection — so the spine stays fast at volume:
--     (a) per-tenant ad_events scan (feed_optimizer + get_ad_events since_ts window),
--     (b) event_id idempotency lookup (ingest_event dedupe via find_ad_event),
--     (c) the same-day CAPI drain finding NOT-yet-sent QUALITY rows.
--   No new table, no new policy, no schema change — RLS is unchanged and still enforced by
--   the ads_tenant_rows policy. Indexes do not widen visibility (RLS gates the rows first).
-- ============================================================================

-- Guard: ads_tenant_rows must exist (it is created by db/ddl_ads_engine.sql). If this file is
-- applied first, fail loudly rather than silently creating nothing.
DO $$
BEGIN
    IF to_regclass('public.ads_tenant_rows') IS NULL THEN
        RAISE EXCEPTION 'ddl_ad_events.sql: ads_tenant_rows missing — apply db/ddl_ads_engine.sql first';
    END IF;
END $$;

-- (a) Per-tenant ad_events append-order scan. Partial index keyed to the ad_events collection only
--     (the spine is the highest-churn collection; a dedicated partial index keeps it lean vs the
--     shared ads_tenant_rows_idx that spans every collection).
CREATE INDEX IF NOT EXISTS ad_events_tenant_id_idx
    ON ads_tenant_rows (tenant_id, id)
    WHERE collection = 'ad_events';

-- (b) Idempotency lookup: ingest_event dedupes on the deterministic data->>'event_id'.
CREATE INDEX IF NOT EXISTS ad_events_event_id_idx
    ON ads_tenant_rows (tenant_id, (data->>'event_id'))
    WHERE collection = 'ad_events';

-- (c) Same-day CAPI drain: find QUALITY rows not yet sent (is_quality=true AND capi_sent_at IS NULL).
--     A partial expression index on the unsent-quality predicate keeps the drain O(unsent), not O(all).
CREATE INDEX IF NOT EXISTS ad_events_capi_pending_idx
    ON ads_tenant_rows (tenant_id, id)
    WHERE collection = 'ad_events'
      AND (data->>'is_quality') = 'true'
      AND (data->>'capi_sent_at') IS NULL;

-- No GRANT needed: famit_app already holds SELECT/INSERT/UPDATE/DELETE on ads_tenant_rows
-- (db/ddl_ads_engine.sql line 130). Indexes inherit the table's privileges + RLS policy.

-- END db/ddl_ad_events.sql
