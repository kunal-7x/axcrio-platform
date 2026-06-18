# W7 RESEARCH + DECISIONS — Multi-tenant LeadMemory (MemoryService) isolation + right-to-erasure

> Scope: the `MemoryService` Protocol impl + DDL under `voice_kernel/memory/`.
> Binds the FROZEN contracts: `MemoryService` (contracts.py:211-218, async PG/RLS),
> `LeadMemory` layer (packet.py:212-219), `KernelSession` tenant_id REQUIRED scoping
> (contracts.py:38-84), `FencedText(SourceTrust.LEAD_MEMORY)` for stored memory
> (packet.py:79-133, 409-430), `build_kernel(cfg, memory=impl)` registration
> (kernel.py:239-247). This is the binding decision log; it edits NO live file
> (EARNER LAW: agent.py md5=98655dbf frozen; caller.py/aim_voice_agent.py untouched).
> The live splice (`_finalize_call` post-call write + next-call recap seam) is a
> LATER flag-gated wave — recorded in §6 SEAM NOTE, not built here.

## 0. The core tension
Lead memory is the ONE place we persist per-lead PII across calls (name, lifecycle,
last-call summary, open commitments). It is read ONE row at dial (WARM/L4) and
written ONCE post-call (COLD). It is multi-tenant (every tenant's leads in shared
tables) AND it is UNTRUSTED at read time (a prior call may have been prompt-injected
→ the stored summary can be poisoned). Two hard requirements collide: strict
tenant isolation (no Tenant-A row ever served to Tenant-B) AND right-to-erasure
(a lead/tenant deletion must purge memory + summary + any derived cache/vector,
with no residue). The contract already fences the read (`SourceTrust.LEAD_MEMORY`);
this note settles the STORE + ISOLATION + ERASURE.

## 1. RESEARCH — what production systems do (primary sources, 2025/2026)
- **PostgreSQL RLS is the infrastructure-level isolation primitive** (PG docs §5.9;
  AWS "Multi-tenant data isolation with PostgreSQL RLS"). `ENABLE` + `FORCE ROW
  LEVEL SECURITY` subjects even the table OWNER to the policy — mandatory when the
  app role owns the tables (our `famit_app` does). A per-row `tenant_id` policy
  filters EVERY SELECT/INSERT/UPDATE/DELETE automatically, so a forgotten WHERE in
  app code cannot bleed across tenants. This is exactly the proven on-box pattern
  (`db/rls.sql`, `db/ddl_wallet.sql`) — REUSE it, do not invent a new shape.
- **OWASP LLM Top-10 v2025 added LLM08:2025** as a distinct category for multi-tenant
  vector/embedding weaknesses — cross-tenant leakage via shared embedding space is
  now a named, first-class risk, not a corner case.
- **Cross-tenant RAG leakage is STRUCTURAL, not adversarial** (Truto 2026; the arXiv
  "95% of benign queries triggered cross-tenant leakage" finding). In a shared
  vector store, organic entity overlap (shared vendors, names, products) makes a
  benign Tenant-A query surface Tenant-B chunks WITHOUT any attack. Metadata
  `tenant_id` filtering must be a HARD pre-filter enforced infra-side, never a
  post-filter and never "the LLM will behave."
- **Silo vs Pool** (IJETCSIT "Silo, Pool, and Bridge"; AWS Bedrock/OpenSearch JWT
  guide): Silo = DB-per-tenant (max isolation, costly); Pool = shared store +
  metadata/namespace filter (cost-efficient, the SaaS default). Famit is Pool —
  shared PG, FORCE-RLS by `tenant_id`. The deterministic blast-radius control is
  the RLS policy + (for any future vector layer) a tenant-namespaced collection.
- **The cascade-delete problem is the hard part of erasure** (Steve Kinney "Agent
  Memory Systems"; mem0 "AI Memory Security"). Deleting the row is step one. The
  full-text indexes, the embedding caches, AND the consolidated/rolled-up summaries
  that REFERENCE the deleted memory must all be purged too. Named fix: **incorporate
  the tenant namespace into cache keys; provide per-namespace cache eviction; batch
  embeddings per-tenant, never across tenants.**
- **GDPR Art.17 erasure on LLM stores** (MDPI "GDPR and LLMs"; arXiv 2307.03941
  "Right to be Forgotten in the Era of LLMs"): erasure of the *stored conversation
  data* is achievable and required (distinct from unlearning model WEIGHTS, which is
  only partial/procedural). Our LeadMemory is stored data, not weights → a real,
  guaranteeable hard-delete is in scope and expected.

## 2. DECISIONS — DDL (concrete; disjoint new file `voice_kernel/memory/ddl_lead_memory.sql`)
Reuses the EXACT proven `db/ddl_wallet.sql` posture: `IF NOT EXISTS`, applied
standalone via psql as `famit_app` (NOT an Alembic revision — off the live
0001/0002 chain), `tenant_id TEXT` == org_id == tenants.json id, FORCE-RLS with the
admin-GUC escape hatch, idempotent (re-runnable).

```sql
-- ONE authoritative row per (tenant, lead). Maps 1:1 to the frozen LeadMemory
-- dataclass (packet.py:212-219). last_call_summary CLAMPED to 300 chars (mirrors
-- packet _LAST_CALL_SUMMARY_CHARS) so the stored value can never exceed the
-- in-prompt budget. lead_phone is the per-tenant lead key (E.164).
CREATE TABLE IF NOT EXISTS lead_memory (
    tenant_id              TEXT        NOT NULL,
    lead_phone             TEXT        NOT NULL,            -- E.164; per-tenant lead key
    name                   TEXT        NOT NULL DEFAULT '',
    lifecycle              TEXT        NOT NULL DEFAULT 'new',  -- new|hot|warm|cold|dead (Lifecycle enum)
    last_call_summary      TEXT        NOT NULL DEFAULT '',  -- <= 300 chars (app-clamped to match prompt)
    open_commitments       JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- tuple[str,...]
    preferred_callback_ts  TEXT        NOT NULL DEFAULT '',
    do_not_mention         JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- tuple[str,...] (suppression)
    call_count             INTEGER     NOT NULL DEFAULT 0,   -- audit/lifecycle
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, lead_phone),
    CONSTRAINT lead_summary_len CHECK (char_length(last_call_summary) <= 300)
);

-- Append-only summary history (the "consolidated summaries" the cascade research
-- warns about). Erasure MUST purge this leg too, not just the head row.
CREATE TABLE IF NOT EXISTS lead_memory_summary (
    id                BIGSERIAL    PRIMARY KEY,
    tenant_id         TEXT         NOT NULL,
    lead_phone        TEXT         NOT NULL,
    call_id           TEXT         NOT NULL DEFAULT '',  -- provenance: which call wrote this
    summary           TEXT         NOT NULL DEFAULT '',
    lifecycle_at_write TEXT        NOT NULL DEFAULT 'new',
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_lms_tenant_lead ON lead_memory_summary (tenant_id, lead_phone, created_at DESC);

-- ============ RLS (FORCE; admin-GUC escape hatch — identical to db/rls.sql) ============
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

GRANT SELECT, INSERT, UPDATE, DELETE ON lead_memory, lead_memory_summary TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO famit_app;
```

Concrete rules (bind these in `voice_kernel/memory/`):
- **M1 — FORCE RLS + admin-GUC, identical to the box.** Do NOT use a bespoke
  tenant-only policy. Use the WITH-CHECK on BOTH USING and WITH CHECK so an INSERT
  with a forged `tenant_id` is rejected (not just hidden on read). `famit_app` is
  NOSUPERUSER/NOBYPASSRLS so FORCE binds the owner. Fail-closed: GUC unset →
  `current_setting('app.tenant_id', true)` is NULL → `tenant_id = NULL` is NULL (not
  TRUE) → zero rows. A missing tenant scope returns EMPTY, never all rows.
- **M2 — `last_call_summary` clamped at the STORE, not only the prompt.** DB CHECK
  ≤300 chars + app-side `clamp_chars(..., 300)` before persist. The stored value can
  never silently exceed the L4 budget, so a poisoned over-long summary can't bloat a
  future prompt past the cache boundary.
- **M3 — JSONB for the tuple fields** (`open_commitments`, `do_not_mention`) so they
  round-trip the frozen `LeadMemory` tuples losslessly; load coerces JSONB → tuple.

## 3. DECISIONS — the async `MemoryService` impl (`voice_kernel/memory/service.py`)
Reuses `db.engine.asession(tenant_id, is_admin=False)` (engine.py:179-196) VERBATIM —
the proven async context manager that `SET LOCAL app.tenant_id` INSIDE the txn
(auto-resets at COMMIT/ROLLBACK; NullPool + statement_cache_size=0 → PgBouncer
transaction-pooling safe, no scope leak to the next checkout).

- **S1 — `load(tenant_id, lead_phone)` scopes with the GUC, never a body value.**
  Open `asession(tenant_id=tenant_id)`; the query is `SELECT ... WHERE lead_phone=:p`
  (NO `tenant_id` in the WHERE) — RLS supplies the tenant predicate. Belt-and-braces:
  ALSO pass `tenant_id` in the WHERE as a redundant guard (defense-in-depth; RLS is
  the authority, the explicit predicate is the seatbelt). On no row → return the
  empty `LeadMemory()` default (NEW lifecycle), never raise — a first-time lead is
  normal, and `kernel.enrich_prefix` degrades to the core packet on any failure.
- **S2 — `persist(tenant_id, lead_phone, summary)` UPSERT under the same GUC.**
  `INSERT ... ON CONFLICT (tenant_id, lead_phone) DO UPDATE`. ALSO append one row to
  `lead_memory_summary` (the history leg). `is_admin=False` always — a post-call
  write is the tenant's own write, never an admin op. WITH CHECK rejects a forged
  cross-tenant write at the DB.
- **S3 — the kernel `tenant_id` MUST come from `KernelSession` (C2), server-stamped.**
  The contract already routes `ctx.meta.tenant_id` into `memory.load` (kernel.py:148)
  and `_require_session` asserts `session.tenant_id == campaign.tenant_id` BEFORE any
  assembly. So the `tenant_id` handed to MemoryService is provably the resolved
  campaign owner, never a caller-supplied dispatch-body guess. Re-state this as an
  assertion in the impl: refuse a blank `tenant_id` (raise, fail-closed) — a memory
  read/write with no tenant is a bug, not a wildcard.
- **S4 — stored memory is UNTRUSTED on read (already fenced).** The kernel renders L4
  via `FencedText(SourceTrust.LEAD_MEMORY)` (packet.py:409-430) positioned ABOVE the
  vendor CAMPAIGN_BRIEF block but BELOW PLATFORM L0. MemoryService does NOT need to
  re-fence; it returns the typed `LeadMemory` and the packet renderer fences it. But
  DO sanitize on WRITE (NFKC normalize, strip zero-width/bidi/control) so a poisoned
  summary can't carry an invisible fence-breakout into the store (reuse the W3
  `context/sanitizer.py` close-tag-escape helper if present; else a local minimal
  normalize). Write-side sanitize + read-side fence = both legs of D2/D7 from W3.
- **S5 — never block the dial loop.** `load` is on the WARM path (post-opener,
  background `enrich_prefix` create_task — kernel.py:143-152), not the HOT reply
  path. `persist` is COLD (post-call). Both get a bounded timeout via the engine
  pool's connect_timeout; on error → log + degrade, never raise into the call.

## 4. DECISIONS — right-to-erasure (the cascade; `voice_kernel/memory/erasure.py`)
The research is unanimous: deleting the head row is NOT enough — every derived leg
and every cache/vector keyed off the lead must be purged, or the data resurfaces.

- **E1 — Two erasure scopes, both HARD-delete (Art.17 = real removal, not soft).**
  - `erase_lead(tenant_id, lead_phone)` — one lead's right-to-erasure.
  - `erase_tenant(tenant_id)` — full tenant offboarding (suspend already revokes
    tokens; erasure purges data when the tenant leaves / on legal request).
  HARD `DELETE` (not a `deleted_at` flag): GDPR erasure means the bytes are gone.
  (We keep an APPEND-ONLY audit EVENT that "lead X erased at T by actor Y" — that
  audit row contains NO PII content, only the fact + a hashed lead ref — so erasure
  is itself auditable without re-storing what was erased.)
- **E2 — Cascade in ONE transaction, parent→child, under the tenant GUC.** Within a
  single `asession(tenant_id)`:
  `DELETE FROM lead_memory_summary WHERE lead_phone=:p;`
  `DELETE FROM lead_memory WHERE lead_phone=:p;`
  RLS scopes both to the tenant (a cross-tenant erase is structurally impossible —
  the GUC bounds the DELETE). For `erase_tenant`, drop the `lead_phone` predicate;
  RLS still bounds it to that tenant. One txn = atomic: either the whole lead is
  gone or nothing changed (no half-erased residue).
- **E3 — Cache eviction is PART of erase, tenant-namespaced (the named fix).** Any
  per-call WARM cache (the room/lead prefetch the kernel warms at dial) MUST key on
  `(tenant_id, lead_phone)` and expose `evict(tenant_id, lead_phone)` /
  `evict_tenant(tenant_id)`. `erase_*` calls it AFTER the DB delete commits. Cache
  keys carry the tenant namespace so eviction is exact and a sibling tenant's cache
  is never touched. (No cross-tenant batch key — embeddings/caches are batched
  per-tenant, never across, per the research.)
- **E4 — Future vector/RAG leg is erasure-aware from day one.** When W4 adds a vector
  store for `full_product_summary`/lead context, it MUST: (a) be a Pool with a HARD
  `tenant_id` metadata PRE-filter on every query (OWASP LLM08:2025; structural-leak
  finding), and (b) expose `delete_by_lead(tenant_id, lead_phone)` /
  `delete_by_tenant(tenant_id)` that `erase_*` ALSO calls. Erasure is a cross-cutting
  contract: every store that derives from a lead registers a `Purgeable` hook. Bind
  this as a small `Purgeable` Protocol in `memory/` so W4 can't add an un-erasable
  vector leg. Until W4 lands, the hook list is just `[lead_memory tables, WARM cache]`.
- **E5 — Idempotent + safe to retry.** Erasing an already-erased lead is a no-op
  success (0 rows deleted = fine). Erasure NEVER raises on "not found" — Art.17
  compliance means the end state (no data) is what matters, not whether a row existed.

## 5. What to BUILD under `voice_kernel/memory/` (disjoint new files, this wave)
- `ddl_lead_memory.sql` — the two tables + FORCE-RLS admin-GUC policy (above).
- `service.py` — `LeadMemoryService` impl of the FROZEN `MemoryService` Protocol:
  async `load()` (RLS-scoped, empty-on-miss), async `persist()` (UPSERT + history
  append + write-side sanitize). Reuses `db.engine.asession`. JSONB↔tuple coercion.
- `erasure.py` — `erase_lead()` / `erase_tenant()` (cascade in one txn) + the
  `Purgeable` Protocol + cache-eviction call. Audit-event emission (no-PII).
- `cache.py` (or reuse the kernel's WARM cache) — tenant-namespaced
  `(tenant_id, lead_phone)` keys + `evict`/`evict_tenant`.
- `tests/` — bound to FROZEN contracts (no live box, no calls):
  - `isinstance(LeadMemoryService(), MemoryService)` conforms (runtime_checkable).
  - RLS: a load under tenant A NEVER returns tenant B's row (GUC-scoped; with a
    fake/sqlite-or-mocked session asserting the predicate + the empty-on-cross-tenant
    contract). A forged-tenant persist is rejected by WITH CHECK.
  - empty-on-miss: first-time lead → `LeadMemory()` default, no raise.
  - clamp: a >300-char summary is clamped before persist (M2).
  - erasure cascade: `erase_lead` purges head + summary legs + calls cache evict +
    every registered `Purgeable`; idempotent on a second call; cross-tenant erase
    impossible (GUC-bounded).
  - blank tenant_id → raise (S3 fail-closed).
  - write-side sanitize: a summary with a zero-width fence-breakout is normalized
    before store (S4).
- **Registration:** `build_kernel(cfg, memory=LeadMemoryService())` — the frozen
  call. `KernelServices.memory` field already exists (kernel.py:79); `build_kernel`
  does `replace(svc, **impls)` (kernel.py:245-246), so `memory=` binds cleanly
  (NO kwarg-alias mismatch here — unlike W3's `context=`/`context_engine`; verified:
  the field IS named `memory`). No `build_kernel` patch needed for W7.

## 6. SEAM NOTE — the LATER flag-gated live splice (DO NOT build/edit this wave)
EARNER LAW: live `agent.py` md5=98655dbf frozen; `caller.py`/`aim_voice_agent.py`
NOT edited here. The cutover (a future founder-signed, flag-gated wave) wires:
- **post-call WRITE seam** — `_finalize_call` (the post-call hook) calls
  `kernel.persist_summary(tenant_id, lead_phone, summary)` to write LeadMemory after
  the call ends. Default OFF (`KERNEL_MEMORY_ENABLED=0`); OFF = no write, legacy path
  byte-identical. The `tenant_id` is the server-stamped `KernelSession.tenant_id`,
  never a body value.
- **next-call RECAP seam** — at dial, `kernel.enrich_prefix(ctx, packet)` loads the
  ONE lead row and injects it as the fenced `LEAD_MEMORY` L4 block, positioned ABOVE
  the vendor CAMPAIGN_BRIEF (so a poisoned script can't reference caller history) and
  BELOW PLATFORM L0. This REPLACES the legacy lossy recap string. Inbound-first
  (`aim_voice_agent.py:1436` `_build_sales_instructions`), earner-gated, default OFF.
- **erasure seam** — the super-admin "delete lead / offboard tenant" control calls
  `erase_lead`/`erase_tenant`. Mounted behind the existing control-plane auth
  (`require_super_admin`), NOT in this wave.
- Acceptance for the cutover (when it happens): a real outbound call rings before+
  after (earner regression gate); agent.py md5 unchanged; flag-OFF golden-render
  byte-identical; a load under tenant A never returns tenant B's row on the live box;
  erase_lead leaves zero residue (head + summary + cache); /health 200. None runs
  in THIS wave.

## Sources
- PostgreSQL docs §5.9 Row Security Policies — postgresql.org/docs/current/ddl-rowsecurity.html
- AWS, "Multi-tenant data isolation with PostgreSQL Row Level Security" — aws.amazon.com/blogs/database
- Truto, "Multi-Tenant RAG Data Isolation: The 2026 Enterprise Architecture Guide" (2026)
- Medium (Swaraj Patil), "Why 95% of RAG Apps Leak Data Across Users" (Jan 2026)
- IJETCSIT, "Silo, Pool, and Bridge for Multi-Tenant RAG"
- AWS, "Multi-tenant RAG with Amazon Bedrock + OpenSearch using JWT"
- OWASP LLM Top-10 v2025 — LLM08:2025 (vector/embedding multi-tenant weaknesses)
- Steve Kinney, "Memory Systems for AI Agents" (cascade-delete + tenant-namespaced cache keys)
- mem0, "AI Memory Security: Best Practices and Implementation"
- MDPI Future Internet 17(4):151, "GDPR and Large Language Models: Technical and Legal Obstacles"
- arXiv 2307.03941, "Right to be Forgotten in the Era of Large Language Models"
- On-box proven patterns: `droplet_work/db/rls.sql`, `droplet_work/db/ddl_wallet.sql`, `droplet_work/db/engine.py`
