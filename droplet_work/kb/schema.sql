-- kb/schema.sql — Platform Knowledge Base + RAG corpus (design/platform-knowledge-rag.md §2).
-- The single tenant-scoped truth store every AI worker answers from. Additive; idempotent.
--
-- LAYERING (F1-aligned):
--   * `CREATE EXTENSION vector` is SUPERUSER-ONLY (famit_app is NOSUPERUSER). It is run ONCE at
--     provision time as the `postgres` superuser (done 2026-06-10 for F2). This file ASSUMES the
--     extension exists; it does NOT attempt CREATE EXTENSION (would die as famit_app).
--   * Tables / RLS / indexes below are all famit_app-ownable -> this file is applied as famit_app.
--   * RLS policy shape is IDENTICAL to db/rls.sql (P1): admin GUC OR tenant match, with WITH CHECK.
--   * Hybrid retrieval: `fts` (Postgres FTS, CORE — needs no key/pgvector) is the sparse leg;
--     `embedding vector(1024)` (dense) is the DORMANT-until-embedder leg. Either degrades cleanly.
--
-- NOT an Alembic revision on purpose: kept OUT of the P1 0001/0002 migration chain so the KB
-- substrate's blast radius never touches the live keystone migration. Applied standalone via
-- kb.ensure_schema() or psql -f. Re-runnable (IF NOT EXISTS everywhere).

-- ============================================================================
-- 2a. kb_sources — provenance root (where knowledge came from)
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_sources (
    id            text PRIMARY KEY,                 -- uuid4().hex[:12]
    tenant_id     text NOT NULL,
    kind          text NOT NULL DEFAULT 'paste',    -- paste|file|url|module
    title         text NOT NULL DEFAULT '',
    uri           text NOT NULL DEFAULT '',
    mime          text NOT NULL DEFAULT '',
    scope         text NOT NULL DEFAULT 'business', -- business | product:<id> | campaign:<id>
    channel_scope text NOT NULL DEFAULT 'all',      -- all|voice|whatsapp|support|creative
    status        text NOT NULL DEFAULT 'pending',  -- pending|indexing|ready|failed
    kb_version    int  NOT NULL DEFAULT 1,          -- bumped on every successful (re)index -> cache-bust
    checksum      text NOT NULL DEFAULT '',         -- sha256 of raw content; skip reindex when unchanged
    error         text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    data          jsonb NOT NULL DEFAULT '{}'
);
ALTER TABLE kb_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_sources FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS kb_sources_isolation ON kb_sources;
-- read-shared (own tenant OR `_global`) / write-locked (own tenant OR admin) — see kb_chunks note.
CREATE POLICY kb_sources_isolation ON kb_sources
    USING      (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true)
                OR tenant_id = '_global')
    WITH CHECK (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true));
CREATE INDEX IF NOT EXISTS kb_sources_tenant_idx ON kb_sources (tenant_id, status);

-- ============================================================================
-- 2b. kb_documents — a logical document derived from a source
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_documents (
    id            text PRIMARY KEY,                 -- uuid4().hex[:12]
    tenant_id     text NOT NULL,
    source_id     text NOT NULL,                    -- -> kb_sources.id (provenance)
    doc_type      text NOT NULL DEFAULT 'generic',  -- faq|product|pricing|policy|objection|script|brochure|generic
    title         text NOT NULL DEFAULT '',
    lang          text NOT NULL DEFAULT '',
    scope         text NOT NULL DEFAULT 'business',
    scope_campaign_id text NOT NULL DEFAULT '',
    scope_product_id  text NOT NULL DEFAULT '',
    kb_version    int  NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    data          jsonb NOT NULL DEFAULT '{}'
);
ALTER TABLE kb_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_documents FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS kb_documents_isolation ON kb_documents;
-- read-shared (own tenant OR `_global`) / write-locked (own tenant OR admin) — see kb_chunks note.
CREATE POLICY kb_documents_isolation ON kb_documents
    USING      (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true)
                OR tenant_id = '_global')
    WITH CHECK (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true));
CREATE INDEX IF NOT EXISTS kb_documents_scope_idx
    ON kb_documents (tenant_id, scope_campaign_id, scope_product_id);

-- ============================================================================
-- 2c. kb_chunks — THE canonical retrieval unit (FTS core + pgvector dense + provenance)
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_chunks (
    id            bigserial PRIMARY KEY,
    tenant_id     text NOT NULL,
    document_id   text NOT NULL,                    -- -> kb_documents.id (citation)
    source_id     text NOT NULL,                    -- denormalized for cache-bust / provenance
    chunk_idx     int  NOT NULL,
    content       text NOT NULL,                    -- the raw chunk (what gets injected / cited)
    section       text NOT NULL DEFAULT '',         -- heading: pricing|amenities|legal|faq|objection|...
    doc_type      text NOT NULL DEFAULT 'generic',
    scope         text NOT NULL DEFAULT 'business',
    channel_scope text NOT NULL DEFAULT 'all',
    scope_campaign_id text NOT NULL DEFAULT '',
    scope_product_id  text NOT NULL DEFAULT '',
    tokens        int  NOT NULL DEFAULT 0,
    embedding     vector(1024),                     -- DENSE leg; NULL when embedder degraded (dormant-until-key)
    fts           tsvector,                         -- SPARSE leg (Postgres FTS) — core, no key needed
    kb_version    int  NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, document_id, chunk_idx)
);
ALTER TABLE kb_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_chunks FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS kb_chunks_isolation ON kb_chunks;
-- READ (USING): admin GUC, OR own tenant, OR the shared `_global` telecaller corpus (read-only).
--   A voice read runs is_admin=FALSE, so `_global` is reachable ONLY via this explicit predicate
--   (NEVER via is_admin=TRUE, NEVER via a `%` wildcard). The matching `OR tenant_id='_global'` in
--   kb/core.py:retrieve UNIONs those shared rows into a tenant's recall.
-- WRITE (WITH CHECK): own tenant OR admin GUC ONLY — `_global` is deliberately ABSENT here, so a
--   tenant request path can NEVER insert/update a `_global` row (the `_global` write-lock; seed runs
--   under is_admin=TRUE). This asymmetry (read-shared / write-locked) is the whole point.
CREATE POLICY kb_chunks_isolation ON kb_chunks
    USING      (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true)
                OR tenant_id = '_global')
    WITH CHECK (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true));
-- dense ANN (cosine), HNSW (pgvector >= 0.5). Safe to create empty; fills as rows embed.
CREATE INDEX IF NOT EXISTS kb_chunks_embed_hnsw ON kb_chunks USING hnsw (embedding vector_cosine_ops);
-- sparse keyword (GIN over tsvector) — the CORE retrieval index (works keyless)
CREATE INDEX IF NOT EXISTS kb_chunks_fts_gin   ON kb_chunks USING gin (fts);
-- tenant + scope filters precede every ANN/FTS scan
CREATE INDEX IF NOT EXISTS kb_chunks_scope_idx ON kb_chunks (tenant_id, channel_scope, scope_campaign_id, doc_type);

-- ============================================================================
-- 2d. kb_query_log — observed retrieval queries (the leakiest artifact: raw caller text)
--   Powers the knowledge-gap loop ("questions your AI couldn't answer") + outcome attribution.
--   This stores RAW caller queries -> it is FORCE-RLS, strictly per-tenant (NO `_global` read-share:
--   query logs are private, never shared corpus). Retention TTL (default 90d) + DPDP tenant-scoped
--   erase keep it from becoming a permanent PII liability. Write is best-effort/fire-and-forget off
--   the voice hot path (NEVER on the per-turn reply loop) — see kb/core.py:log_query.
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_query_log (
    id            bigserial PRIMARY KEY,
    tenant_id     text NOT NULL,
    query         text NOT NULL DEFAULT '',          -- raw caller query (PII-bearing) — RLS + TTL guarded
    channel       text NOT NULL DEFAULT 'all',        -- voice|whatsapp|support|all
    scope_campaign_id text NOT NULL DEFAULT '',
    grounded      boolean NOT NULL DEFAULT false,     -- did retrieval return >=1 chunk? (gap-loop signal)
    leg           text NOT NULL DEFAULT '',           -- sparse|dense|sparse+dense|'' (which leg fired)
    top_ids       jsonb NOT NULL DEFAULT '[]',        -- chunk ids returned (outcome-attribution join key)
    created_at    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE kb_query_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_query_log FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS kb_query_log_isolation ON kb_query_log;
-- STRICTLY per-tenant (admin GUC OR own tenant) — NO `_global` read-share: logs are private, not corpus.
CREATE POLICY kb_query_log_isolation ON kb_query_log
    USING      (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (current_setting('app.is_admin', true) = '1'
                OR tenant_id = current_setting('app.tenant_id', true));
-- gap-loop lookups: per tenant, newest first, filterable by grounded
CREATE INDEX IF NOT EXISTS kb_query_log_tenant_idx ON kb_query_log (tenant_id, grounded, created_at DESC);
-- retention TTL sweep predicate (created_at < now()-interval) is index-supported
CREATE INDEX IF NOT EXISTS kb_query_log_ttl_idx ON kb_query_log (created_at);
