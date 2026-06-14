# rag-w2-seed-telecaller — Wave Log

## DO CORPUS

**Date:** 2026-06-14
**Branch:** backend/handoff-name-clean-line
**File:** `droplet_work/kb/seed_global_corpus.json`
**Chunk count:** 37 chunks

**Coverage:**
- (a) Objection handlers (10 chunks): too_expensive, not_interested, call_later, need_to_think, already_have, send_details_whatsapp, no_time, not_right_now, quality_doubt, already_tried_failed, trust_new_company, decision_maker_gatekeeper, payment_UPI_digital, DND_compliance — each with empathy-first Hinglish response + named technique.
- (b) Pricing + value-framing FAQs (2 chunks): pricing_value_framing_faq, handling_price_negotiation — ROI framing, anchor, conditional discount, value-add over bare discount.
- (c) Product explainer scaffolds (5 chunks): generic B2C, SaaS/software, financial services, edtech/courses, real estate, health/wellness — each with hook→problem→solution→benefits→social proof→close structure.
- (d) Rapport + behavior patterns (11 chunks): opening/rapport, mirroring/pacing, backchannel haan/achha, urgency without pushiness, close techniques, follow-up sequence, WhatsApp templates, appointment setting, voice tone, active listening, Indian B2C psychology, mindset, buying signals, upsell/cross-sell, competitor handling, sales openers, demo presentation, language switching.
- All chunks: FTS-quality (strong keyword coverage in Hinglish), tenant-agnostic (_global), tags field for secondary filtering.
- Commit: see git log for sha on backend/handoff-name-clean-line.

## DO SEED MECHANISM

**Date:** 2026-06-14 · **Branch:** fe/unify-run-wavec

**Files (build):**
- `droplet_work/kb/seed_global.py` (NEW, ~190 lines) — idempotent `_global` corpus loader. Public: `seed(*, path="", actor="system")` (kb/seed_global.py:113-186). Helpers `_chunk_text_for` (kb/seed_global.py:78-97 — deterministic chunk text), `load_corpus` (kb/seed_global.py:100-110), `_doc_type_for` (kb/seed_global.py:61-66). CLI entry `python -m kb.seed_global` (kb/seed_global.py:189-194).
- `droplet_work/kb/__init__.py` — exports `seed_global_corpus` (= seed_global.seed) at kb/__init__.py:31.
- `droplet_work/caller.py:3326-3349` — NEW `POST /kb/seed-telecaller`, `require_super_admin`-gated, `asyncio.to_thread(_kb_mod.seed_global_corpus, actor=...)`.

**Idempotency mechanism:** each of the 41 corpus entries is ingested as its OWN kb_source. `kb.ingest` dedups by `(tenant_id, checksum)` where `checksum = sha256(content.strip())` (kb/core.py:235,261-266 → `duplicate_checksum` no-op). `_chunk_text_for` builds the ingested text from a STABLE template `# <topic>\n\n<content>\n\nKeywords: <sorted-unique-lowercased tags>` → identical bytes every run → identical checksum → re-run (or double POST) inserts NOTHING (returns `duplicate` count). Editing one entry changes only THAT entry's checksum → only it re-ingests. Offline self-test PASS: 41 entries, 41 unique checksums (no collision), tag-reorder hash-stable (deterministic), doc_type bucketing correct.

**How only is_admin writes `_global`:** the seeder calls `kb.ingest(GLOBAL_TENANT, text, ..., is_admin=True)` (kb/seed_global.py:160-164). The kb_chunks/sources/documents RLS `WITH CHECK` (kb/schema.sql:45-46,74-75,116-117) is `admin-GUC OR own-tenant` and deliberately OMITS `_global` → the only path that can INSERT a `_global` row is one running under `app.is_admin='1'` (set by `eng.session(is_admin=True)`, kb/core.py:259). A tenant request can never reach it: the HTTP endpoint is `require_super_admin`-gated (caller.py:3340) AND the ingest write sets the admin GUC itself. The `_global` USING policy permits reads → read-shared / write-locked.

**Earner gate:** agent.py md5 `9150fabe…` UNCHANGED · famit-agent PID 1477083 NOT restarted. py_compile OK (seed_global.py + __init__.py + caller.py). gitleaks 0.
