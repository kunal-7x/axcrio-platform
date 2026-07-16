-- ============================================================================
-- db/ddl_ads_engine.sql — ElevateX ads store · Postgres FORCE-RLS data floor (V2 W2).
-- Spec: plans/elevatex/v2/V2_MASTER_PLAN.md §8 ("THE P0 ISOLATION BUILD") +
--       plans/elevatex/v2/research/buy-vs-build-fit.md Layer 8 (Postgres-RLS, NOT ClickHouse).
--
-- WHY THIS FILE EXISTS: ads_engine/store.py's own header admits the file-JSON store has
-- "ZERO infrastructural tenant enforcement … isolation CANNOT rest on every handler
-- remembering `.get(tenant_id)`." This DDL makes tenant isolation INFRASTRUCTURAL — a
-- Postgres FORCE-RLS floor, the EXACT pattern db/ddl_provider_registry.sql already runs for
-- the secrets vault (lines 67-115 there). A forged body tenant_id, a missing `.get()`, a
-- cross-tenant SELECT — ALL are blocked by the database, not by code convention.
--
-- STRANGLER SHAPE (the key design call): store.py's PUBLIC accessor API is GENERIC
-- (collection name + row_id + a JSON row; or a per-tenant append list). The PG backend
-- implements that SAME generic API behind UNCHANGED signatures, so NOTHING else in
-- ads_engine changes (the whole point of a strangler). Hence the schema is three generic,
-- jsonb-bodied, tenant-scoped tables — NOT one column-typed table per collection. The
-- bank-grade isolation lives in the RLS policy on tenant_id, identical for every collection.
--
--   1) ads_rows         — the tenant-keyed dict collections (campaigns, ad_variants,
--                          bandit_state, budget_account, budget_intents, autorun_*, …).
--                          PK (tenant_id, collection, row_id); a `version` column carries
--                          the optimistic-concurrency CAS counter (store.cas_row).
--   2) ads_tenant_rows  — the high-churn per-tenant LIST files (leads_ads, conversions,
--                          ads_audit, decision_log, consent_log, budget_ledger, …).
--                          Ordered by the bigserial `id` = append order.
--   3) ads_page_tenant_map — the GLOBAL page_id->tenant trust root (the unauth Meta leadgen
--                          webhook resolves the owning tenant from here BEFORE any tenant is
--                          known). page_id PRIMARY KEY = the one-page-one-tenant anti-hijack
--                          uniqueness. Accessed under the admin GUC (pre-auth read).
--
-- IDEMPOTENT: CREATE … IF NOT EXISTS / DROP-then-CREATE-POLICY — safe to re-run. Applied
-- standalone via psql as famit_app (NOT an Alembic revision) — same posture as
-- db/ddl_provider_registry.sql / kb/schema.sql.
--
-- MONEY = INTEGER minor units (paise) and lives INSIDE the jsonb `data` (store.py owns the
-- shape); NO floats. famit_app is NOSUPERUSER/NOBYPASSRLS so FORCE RLS binds even the owner.
--
-- RLS shape = the provider_credentials STRICT-per-tenant policy (db/ddl_provider_registry.sql
-- :107-115): READ/WRITE = admin GUC OR own tenant. NO `_global` read-share — ad rows are
-- ALWAYS tenant-private (unlike provider_definitions, which share a `_global` catalog).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) ads_rows — the tenant-keyed dict collections (store.COLLECTION_FILES).
--    One DB row per (tenant_id, collection, row_id). `data` is the full row dict
--    store.py persists (tenant_id is stamped inside it too). `version` mirrors
--    data->>'version' for the CAS check + cheap indexing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ads_rows (
    tenant_id   text        NOT NULL,
    collection  text        NOT NULL,                 -- e.g. 'campaigns','ad_variants','budget_account'
    row_id      text        NOT NULL,
    data        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    version     integer     NOT NULL DEFAULT 0,        -- optimistic-concurrency CAS counter
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, collection, row_id)
);
-- collection-first index for list_tenant_ids (the privileged tick sweep) + per-collection scans.
CREATE INDEX IF NOT EXISTS ads_rows_coll_idx ON ads_rows (collection, tenant_id);

ALTER TABLE ads_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE ads_rows FORCE  ROW LEVEL SECURITY;
-- STRICTLY per-tenant: admin GUC OR own tenant — both READ (USING) and WRITE (WITH CHECK).
-- A forged data.tenant_id is irrelevant: WITH CHECK binds the *column* tenant_id to the GUC,
-- so tenant A (app.tenant_id='A') can NEVER insert/update a row with tenant_id='B'.
DROP POLICY IF EXISTS ads_rows_iso ON ads_rows;
CREATE POLICY ads_rows_iso ON ads_rows
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) );

-- ---------------------------------------------------------------------------
-- 2) ads_tenant_rows — the high-churn per-tenant LIST files (store.PER_TENANT_FILES).
--    Append order = the bigserial `id`. The append-only collections (decision_log,
--    consent_log, budget_ledger) stay append-only by the SAME app discipline as the
--    JSON store today (store.py only ever appends to them) — NO blanket append-only
--    trigger here, because the replaceable per-tenant files (leads_ads, conversions,
--    ads_audit, ads_jobs) legitimately use put_tenant_file = DELETE-then-INSERT.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ads_tenant_rows (
    id          bigserial   PRIMARY KEY,
    tenant_id   text        NOT NULL,
    collection  text        NOT NULL,                 -- e.g. 'leads_ads','decision_log','budget_ledger'
    data        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ads_tenant_rows_idx ON ads_tenant_rows (tenant_id, collection, id);

ALTER TABLE ads_tenant_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE ads_tenant_rows FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ads_tenant_rows_iso ON ads_tenant_rows;
CREATE POLICY ads_tenant_rows_iso ON ads_tenant_rows
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) );

-- ---------------------------------------------------------------------------
-- 3) ads_page_tenant_map — the GLOBAL inbound-webhook trust root (store W6).
--    The Meta leadgen webhook is the ONLY unauthenticated PII surface; it resolves the
--    owning tenant from THIS table BEFORE any tenant GUC exists, so the backend reads it
--    under the admin GUC. page_id PRIMARY KEY = the one-page->one-tenant anti-hijack
--    uniqueness (a second tenant claiming the same page is rejected in app logic =
--    PageOwnershipConflict). RLS still on (defence in depth): a tenant GUC sees only its
--    OWN page rows; the admin GUC (the webhook/connect path) sees all.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ads_page_tenant_map (
    page_id     text        PRIMARY KEY,              -- external Meta page_id (uniqueness = anti-hijack)
    tenant_id   text        NOT NULL,
    actor       text        DEFAULT '',
    evidence    jsonb,
    linked_at   timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ads_page_map_tenant_idx ON ads_page_tenant_map (tenant_id);

ALTER TABLE ads_page_tenant_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE ads_page_tenant_map FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ads_page_map_iso ON ads_page_tenant_map;
CREATE POLICY ads_page_map_iso ON ads_page_tenant_map
    USING ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) )
    WITH CHECK ( current_setting('app.is_admin', true) = '1'
            OR tenant_id = current_setting('app.tenant_id', true) );

-- ============ grants (famit_app owns these tables ; explicit + future-proofed) ============
GRANT SELECT, INSERT, UPDATE, DELETE ON ads_rows            TO famit_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ads_tenant_rows     TO famit_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ads_page_tenant_map TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO famit_app;

-- END db/ddl_ads_engine.sql
