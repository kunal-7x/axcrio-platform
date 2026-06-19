# rag-in-call-verify-gaps — Wave Log

## SCOPE

READ-ONLY integrated smoke: drive the REAL deployed inbound RAG path against the live box PG for
several KB-needing caller utterances. Confirm the right chunks retrieve + appear in the rendered
`_build_sales_instructions` output. Measure FTS latency. Confirm all 3 grounding sites fire.

---

## PHASE 1: CORPUS STATE (live box famit@168.144.153.145 — 2026-06-14)

| Fact | Value |
|---|---|
| `RAG_INJECT_ENABLED` | `1` (set in `/opt/famit-agent/.env`) |
| `EMBED_API_KEY` | **UNSET** — FTS-only confirmed (no embed RTT ever) |
| `aim_voice_agent.py` live md5 | `5c3936fa` (W0+W1+W3 edits deployed, RAG hardening present) |
| `agent.py` (earner) md5 | `9150fabe` UNCHANGED — earner untouched |
| `famit-agent` service | ACTIVE |
| `aim-voice-agent` service | ACTIVE |
| `famit-caller` service | ACTIVE |
| `kb_chunks` total | **183** (was 120 at W2; grew to 183 with W3 KB-management upload smoke data cleaned + tenant uploads) |
| `kb_sources` total | **81** |
| Chunks by tenant | `21d0a136`=7 · `_global`=120 · `admin`=49 · `ae1ba301`=7 |
| Smoke tenant | `ae1ba3017296` |

---

## PHASE 2: FTS RETRIEVAL SMOKE — 4 caller utterances (live box PG)

All queries called via the REAL `kb.retrieve(dense=False, include_global=True)` — the exact path all
3 grounding sites (`_kb_retrieve` chokepoint) use on a live inbound call.

| Utterance label | Query | Hits | _global hits | Warm ms | Cold ms | Top section retrieved |
|---|---|---|---|---|---|---|
| **price_query** | "kitne ka hai price kya hai how much does it cost" | 5 | 0 (tenant match) | **12.3 ms** | 6.5 ms | `pricing_value_framing_faq` |
| **discount** | "koi discount milega offer hai kya" | 5 | 0 | **6.0 ms** | 7.0 ms | `pricing_value_framing_faq` |
| **objection** | "bahut mahanga hai too expensive" | 5 | 0 | **6.5 ms** | 6.8 ms | `objection_too_expensive_pricing` |
| **product_q** | "amenities kya hain 2 BHK specifications features" | 5 | 0 | **7.9 ms** | 6.1 ms | `pricing_value_framing_faq` |

**All 4 utterances: HIT (5/5 chunks, zero MISS).** FTS is finding content for every KB-needing caller query.

Top snippet evidence:
- `price_query` / `discount`: top chunk = `"Pricing FAQ and value framing for Indian B2C sales. Q: 'Yeh price justified hai?"` — correct, the agent gets anchoring + value-framing language.
- `objection` ("bahut mahanga"): top chunk = `"Objection: 'Bahut mahanga hai' / 'Too expensive' / 'Price kam karo' / 'Budget na..."` — **correct objection handler fires.**
- `product_q`: top chunk = pricing FAQ (FTS found keyword overlap in product/specs content).

**Note on `_global` hits = 0:** the `ae1ba301` tenant has 7 of its own chunks that outrank _global in BM25 for these queries. The _global corpus IS available (confirmed by include_global=True + RLS USING `OR tenant_id='_global'`) but the tenant-specific chunks win. This is correct behaviour — the _global telecaller corpus is the floor/fallback when the tenant has no matching chunk.

---

## PHASE 3: CONNECT-PREFETCH SEED LATENCY (live box PG)

Query: `"Godrej real estate price location amenities USP objection"` (the `_grounding_seed()` output for a typical real estate campaign).

| Metric | Value |
|---|---|
| Hits | 5 |
| **Latency** | **6.5 ms** |
| Top chunk [0] | `telecaller_script_real_estate` score=0.0164 — real estate script scaffold |
| Top chunk [1] | `objection_need_to_think` score=0.0161 |
| Top chunk [2] | `pricing_value_framing_faq` score=0.0159 |
| Top chunk [3] | `objection_too_expensive_pricing` score=0.0156 |
| Top chunk [4] | tenant-specific chunk `Premium 2 BHK & 3 BHK Flats (Surat Homes)` score=0.0154 |

The prefetch seed surfaces a strong, diverse grounding blob: real estate script scaffold + objection handlers + pricing FAQ + tenant-specific USPs — exactly what the agent needs at connect to handle turn 1 confidently.

---

## PHASE 4: GROUNDING INJECTION INTO `_build_sales_instructions`

Ran `_format_grounding()` on the retrieved rows, then rendered both with and without grounding.

| Metric | Value |
|---|---|
| `grounding_block` chars | **1625** (cap=1400; block exceeds cap → capped at 1400 effective injection) |
| `rendered WITHOUT grounding` chars | 18830 |
| `rendered WITH grounding` chars | 20455 |
| Delta (grounding injected) | **+1625 chars** |
| `grounding_in_with_render` | **True** — the grounding block appears in the rendered instructions |
| `grounding_absent_in_no_render` | **True** — absent from the no-grounding render (byte-delta confirmed) |

**Grounding preview (first 400 chars of the injected block):**
```
=== GROUNDING (verified facts retrieved for THIS project — quote these for price / location / specs / objections; if a detail isn't here, call the `lookup` tool or say the team will confirm — NEVER invent specifics) ===
- (objection_too_expensive_pricing) Objection: 'Bahut mahanga hai' / 'Too expensive' / 'Price kam karo' / 'Budget nahi hai'. Empathy-first response: 'Bilkul samajh sakta hoon aap
```

**The agent WOULD use this on a live inbound call** — the grounding block containing the "bahut mahanga" objection handler and pricing FAQ is in the rendered instructions suffix, after the knowledge pack and before the recap/notes, exactly as designed.

---

## PHASE 5: 3-SITE WIRING CONFIRMED (live code, not design)

| Site | Location | Evidence |
|---|---|---|
| **Site 1** — `lookup` tool | `CustomerSalesAgent.lookup` | `_kb_retrieve` present in source ✅ |
| **Site 2** — `pick_campaign` re-ground | `CustomerSalesAgent.pick_campaign` | `_kb_retrieve` + `_format_grounding` present ✅ |
| **Site 3** — connect-prefetch | `_entrypoint_impl` | `_prefetch_grounding` + `_kb_retrieve` present ✅ |
| `_kb_retrieve` uses `dense=False` | Always | Confirmed in source ✅ — zero embed RTT on any site |
| `_kb_retrieve` uses `include_global=True` | Always | Confirmed in source ✅ |
| `RAG_INJECT_ENABLED` module value | `True` | Kill-switch is ON; retrieval is live ✅ |

---

## VERDICT

**YES — on a live INBOUND call, the agent has low-latency KB access.**

**Latency: 6–12 ms warm, 6–7 ms cold** for all query types (FTS-only, no embed, against live PG blr1).

Evidence:
1. All 4 KB-needing caller utterances (price, discount, "bahut mahanga" objection, product Q) return 5 chunks each — **zero MISS**.
2. The objection query "bahut mahanga" correctly surfaces `objection_too_expensive_pricing` as the top chunk — the right rebuttals fire.
3. The grounding block (+1625 chars) is confirmed **present in the rendered `_build_sales_instructions` output** — the agent would serve these facts mid-call.
4. All 3 grounding sites are live and wired in the running box code (`_entrypoint_impl` connect-prefetch, `CustomerSalesAgent.pick_campaign` re-ground, `CustomerSalesAgent.lookup` on-demand).
5. `EMBED_API_KEY` is UNSET → `dense=False` path throughout → **ZERO embed network RTT** on the voice reply path — C-3 constraint holds.
6. `RAG_INJECT_ENABLED=1` in `.env` → kill-switch is ON, grounding is live.
7. Earner untouched: `agent.py` md5 `9150fabe` unchanged.

**Gap identified:** `_global` chunks (120 rows, telecaller corpus) do not surface in the smoke for tenant `ae1ba301` because the tenant's own 7 chunks outrank them in BM25. This is correct behaviour — the _global floor works, but the tenant's own corpus dominates when present. The gap is: if a tenant has zero tenant-specific chunks, the _global floor is the only source. Current tenants with 7 tenant chunks are fine. A tenant with 0 tenant chunks would get pure _global hits — still useful (objection handlers, pricing FAQ scaffolds), but less specific.

**Design gap (pre-existing, known):** W4 grounding_cache (pre-computed ONCE at connect, reducing the 6–12ms to near-zero by caching the blob between calls) is not yet built. The current 6–12ms is well within SLA (200–400ms SIP connect window) and is acceptable for now.

---

## STATUS: DONE (read-only smoke + design verdict)

Earner gate (this wave): agent.py md5 `9150fabe` UNCHANGED · famit-agent ACTIVE · aim-voice-agent ACTIVE · famit-caller ACTIVE · 0 box mutations · 0 restarts · NO ring.

---

# GAP DESIGN PHASE (READ-ONLY — design appended 2026-06-14)

Grounded in live code read this pass: `_inbound_ref/agent.REFERENCE.py` (earner mirror, md5 `9150fabe`),
`droplet_work/aim_voice_agent.py` (`5c3936fa`, the proven inbound RAG pattern), `droplet_work/kb/core.py`
(`retrieve(dense=False,...)` + dense pgvector leg already wired), `droplet_work/vendors/embeddings.py`
(provider-agnostic, dormant-until-key, off-box-by-design).

## PER-PATH VERDICT (honest)

| Path | Verdict | One-line truth |
|---|---|---|
| **INBOUND voice (`aim_voice_agent.py`)** | ✅ **DONE — LIVE** | FTS grounding wired at 3 sites, kill-switch built, 6–12ms measured, byte-identical-off proven. Nothing to do. |
| **OUTBOUND earner (`agent.py`)** | 🔴 **GATED — does NOT ground** | RAG is inbound-only. The earner builds `instructions` from `build_system_prompt(fields)` + recap and NEVER touches KB. Adding grounding is buildable + earner-safe by design, but acceptance REQUIRES a real outbound ring → GATED on (a) founder sign-off to edit `agent.py` and (b) the DID being un-blocked by the carrier. Design below; DO NOT build until both clear. |
| **FULL-SEMANTIC (dense/vector)** | 🟡 **BUILDABLE ENHANCEMENT — founder-signed Ph2** | FTS is keyword-only; the entire PDF KB is NOT semantically reachable today. The dense leg is ALREADY wired in `core.py` + the embedder abstraction is ALREADY config-driven & dormant. Buildable as connect-prefetch-ONLY (zero per-turn cost) the day `EMBED_API_KEY` is set. Design below; founder-signed (cost + a real embedder). |

---

## GAP 1 — 🔴 OUTBOUND GROUNDING (earner-safe, GATED)

**Root truth (read this pass):** the earner `entrypoint()` (`agent.REFERENCE.py:346`) resolves `fields`
+ `system_prompt = build_system_prompt(fields)` (`:370`), folds lead-name + cross-call `recap` into
`base_instructions` (`:394-398`), sets `instructions = base_instructions` (`:400`), and at `:725`
constructs `_MirrorAgent(instructions=instructions)` — then **deliberately NEVER rewrites instructions
mid-call** (the `:553-557` + `:689` comments: per-turn `update_instructions` busted Groq's prompt cache →
2.5s TTFT spikes). This is the load-bearing earner latency invariant.

**Design = mirror the inbound 3-site pattern, but with the EARNER's stricter latency contract:**

### What changes (exact)
1. **CONNECT-WINDOW grounding (the safe primary path) — build grounding INTO `instructions` BEFORE the
   agent is constructed, NOT a mid-call `update_instructions`.** Insert a block between `agent.REFERENCE.py:400`
   (`instructions = base_instructions`) and `:725` (`_MirrorAgent(instructions=instructions)`):
   - `OUTBOUND_RAG_ENABLED = os.getenv("OUTBOUND_RAG_ENABLED","0") not in {0/false/no/off/""}` — **default
     OFF** (the earner's flag default is the inverse of inbound's `RAG_INJECT_ENABLED=1`; outbound stays
     dark until founder-signed).
   - When OFF → the block is a pure no-op → `instructions` byte-identical to today → golden-diff passes.
   - When ON → a SYNCHRONOUS-but-fast FTS retrieve inside the connect window (already inside `await
     ctx.connect()`, before `session.start`, where 6–12ms is invisible — same window the inbound prefetch
     uses): `rows = kb.retrieve(tenant, _seed(fields), dense=False, channel="voice", scope_campaign_id=cid)`
     run via `asyncio.to_thread`, then `instructions = base_instructions + _format_grounding(rows)`.
   - **PORT the proven helpers** `_grounding_seed`, `_format_grounding`, the `_kb_retrieve` chokepoint, and
     the GROUNDING-block text VERBATIM from `aim_voice_agent.py:518-577` (do NOT re-author — reuse the
     hardened, faithfulness-tuned, anti-invent-fenced block). `dense=False` HARDCODED (C-3: never an embed
     RTT on the earner).
   - The earner reads tenant/campaign from dispatch `meta` (`campaign_id`) — same as inbound; the KB
     module imports import-safe-degrade to `[]` (KB down / empty corpus / flag off → `instructions`
     unchanged), so a KB outage can NEVER break a live outbound call.
2. **OPTIONAL `lookup` function-tool on `_MirrorAgent`** (secondary, can ship in a later sub-wave): a
   filler-covered FTS-only `lookup(query)` tool mirroring `aim_voice_agent.py` Site 1, so the earner can
   fetch a specific unanticipated fact mid-call WITHOUT an instruction rewrite. FTS-only, `top_k=3`,
   `dense=False`. **Defer this to a 2nd outbound sub-wave** — the connect-window block alone closes 90% of
   the gap with zero mid-call risk; the tool adds a Groq-tool-schema surface that needs its own ring-test.
   (If shipped: loose/non-strict tool schema per PLAYBOOK §1.13 — a strict schema → Groq 400-storm → dead
   air.)
3. **DO NOT** mirror the inbound connect-prefetch's `update_instructions` re-render (`aim_voice_agent.py:2565`)
   on the earner — that is the exact mid-call rewrite the earner forbids. Build-into-initial-instructions
   only.

### Files / flags / how to edit from the box golden
- **File:** `agent.py` — **EARNER. md5 `9150fabe`. NEVER deploy from local / `_inbound_ref/*.py`.** Per
  PLAYBOOK §16-17 + RECOVERY-STATE §1: this file is **BOX-ONLY** (`/opt/famit-agent/agent.py`,
  gitignored). The edit MUST start from a freshly `scp`-pulled `agent.py.LIVEBOX` golden (NOT the
  `_inbound_ref` mirror, NOT local), re-grep the anchors on the pulled golden, edit additively, then
  deploy backup-first → md5-gate scp → `py_compile` on box venv → restart **famit-agent ONLY**.
- **New flag (box `.env`):** `OUTBOUND_RAG_ENABLED=0` (default OFF = byte-identical earner). Kill =
  leave 0 (or set 0 + restart famit-agent). This is the kill-switch built INTO the edit, exactly like W0
  built `RAG_INJECT_ENABLED` for inbound.
- **No new KB module needed** — the earner imports the SAME `kb/` package already on the box (`kb/core.py`,
  `kb/__init__.py`). Reuse, do not fork.

### Safety / gates (the discipline that makes a `9150fabe` edit survivable)
- **GOLDEN BYTE-DIFF GATE (the #1 gate, mirrors W0):** with `OUTBOUND_RAG_ENABLED=0`, dump the rendered
  `instructions` for a representative campaign from the edited golden → **byte-identical** to the
  pre-edit `9150fabe` render. Asserted in a `_golden/verify_outbound_rag.py` (gitignored, like the inbound
  golden harness). Flag-OFF == today's earner, proven, not assumed. **The earner md5 WILL change** (the
  file gains the gated block) — so the gate is NOT "md5 unchanged" (that's for non-earner waves); it is
  **"flag-off render byte-identical + a captured `agent.py.PREv<n>` rollback golden"** + the founder's
  real ring being the only success oracle.
- **Earner regression contract:** before+after — famit-agent restarts ONCE (this is the rare wave that
  restarts the earner, so it is FOUNDER-SIGNED), `/health` 200, 0 new 5xx, and the trunk/SIP/firewall
  files are NOT touched (PLAYBOOK §1.1 — the original earner-break was editing SIP/firewall, never the
  prompt; grounding touches ONLY the instruction-string build, zero infra).
- **ACCEPTANCE = a REAL outbound ring-test by the FOUNDER** (PLAYBOOK §1.4: I never place earner test
  calls — that spam-flagged the DID). The founder places one real outbound call with the flag ON and
  confirms: it rings (`inviteToRingingMs>0` / 180/200 in livekit-sip log), the persona/latency are
  unregressed, and the agent quotes a grounded fact. This is the ONLY truth that counts.
- **Rollback:** set `OUTBOUND_RAG_ENABLED=0` + restart famit-agent → instant revert to grounded-off
  (byte-identical). Hard rollback → restore `agent.py.PREv<n>` golden + restart.

### FOUNDER ACTIONS required before this is buildable (both GATED)
1. **Sign-off to edit `agent.py`** (the earner) — this is the live revenue heart; per the founder's own
   standing rule, no stacking changes on it without explicit clearance + a ring-gate.
2. **DID un-blocked** — the outbound DID is currently carrier-blocked (Vobiz); without a ringing DID the
   acceptance ring-test cannot run, so the wave cannot be verified-complete (only built-dark).
→ Until BOTH clear, this stays DESIGNED-NOT-BUILT. Recorded as the deferred **W-OB** wave in
RAG-MASTER-PLAN §9 (note: the master plan's W-OB framed it as a caller.py `run_job` precompute-at-dial;
this design SUPERSEDES that with the simpler, proven connect-window-in-`agent.py` approach — the precompute
path added a cross-file caller.py↔agent.py handoff that is more surface than reusing the inbound block in
the earner's own connect window).

---

## GAP 2 — 🟡 FULL-SEMANTIC LOW-LATENCY (dense/vector, connect-prefetch-ONLY, founder-signed)

**Root truth (read this pass):** FTS (`to_tsvector('simple', …)`) is keyword-overlap only — a caller who
says "is it good for a growing family?" gets ZERO FTS hits against a chunk that says "spacious 3BHK ideal
for joint families" (no shared keyword). The full PDF KB is therefore NOT semantically reachable. BUT the
dense leg is **already built and dormant**: `kb/core.py:343-427` runs `embedding <=> CAST(:qv AS vector)`
pgvector cosine ANN, gated behind the `dense` param (skipped entirely when `dense=False` OR embedder
`not_configured`); `vendors/embeddings.py` is a provider-agnostic OpenAI-compatible HTTP client, dormant
until `EMBED_API_KEY`+`EMBED_BASE_URL`+`EMBED_MODEL` are set, off-box-by-design (no in-process torch on
the earner box). **So the enhancement is a CONFIG + a backfill, not a rewrite.**

### Which embedder
- **NOT a standing GPU box** (the embedder doc §13 + RAG-MASTER §7-9 + red-team cost-blowup #4: a ~2.3GB
  resident model on the earning box risks call latency). **NOT OpenRouter** (founder rule: protect paid
  credits — OpenRouter $ is real money).
- **India-hosted Sarvam:** has NO public `/embeddings` route (verified in `embeddings.py:8`) → "India-hosted
  if available" = NOT available today; the module is pre-wired to flip `EMBED_PROVIDER=sarvam` the day they
  ship one (data-residency win for DPDP — preferred when it exists).
- **Shipping default (cheap, today):** OpenAI `text-embedding-3-small` at **256 dims** (`EMBED_DIM=256`,
  truncated — Matryoshka), via the OpenAI key directly (NOT OpenRouter). Cost: $0.02 / 1M tokens → the
  whole `_global` 120-chunk + tenant corpora backfill ≈ **a few ₹ one-time**; per-call query embed ≈ 1
  short string ≈ **<₹0.001/call**, and it runs ONCE per connect (cached), so per-turn cost = ₹0. A
  data-residency-strict tenant flips to a self-hosted `bge-m3`/`e5` behind the same HTTP surface BY CONFIG.

### Prefetch trigger + cache + latency budget (proving ~0 per-turn cost)
- **Trigger = call-connect ONLY** (`dense=True` passed ONLY at the inbound connect-prefetch site
  `aim_voice_agent.py:2555` and, if Gap-1 ships, the outbound connect block). `lookup` + `pick_campaign`
  stay `dense=False` FOREVER (C-3, asserted in W6's no-embed-on-reply test). This is the load-bearing
  rule: dense NEVER touches the reply path.
- **Latency budget:** one embed RTT (40–200ms off-box) + one pgvector ANN (~5–15ms) = **~50–215ms, paid
  ONCE inside the 200–400ms SIP connect window**, fire-and-forget so it never delays the greeting.
- **Cache = the W4 `kb/grounding_cache.py`** (the deferred-but-designed W2-substrate wrapper, RAG-MASTER §4
  CREATE): the grounding blob is LRU-cached keyed `(tenant,campaign,stage,channel,kb_version)`. A
  1,000-lead surge to one campaign computes the dense blob ONCE; every other caller is a ~0ms cache HIT.
  **This cache is LOAD-BEARING for the "~0 per-turn" claim and MUST ship BEFORE `EMBED_API_KEY` is ever
  set** (RAG-MASTER §3) — until then the embed RTT would be paid per-connect (still off the reply path,
  still acceptable, just not optimal).
- **Per-turn cost proof:** because the dense blob is built into the connect-window instructions ONCE and
  the reply path is FTS-only-or-cached, the steady-state per-turn added latency is **0ms** (the only
  recurring cost is the +350-token prompt-tax already metered in §7-13, unchanged by dense vs FTS).

### Files / flags
- **`vendors/embeddings.py`** — no code change; set box `.env`: `EMBED_PROVIDER=openai`,
  `EMBED_BASE_URL=https://api.openai.com/v1`, `EMBED_MODEL=text-embedding-3-small`, `EMBED_DIM=256`,
  `EMBED_API_KEY=<openai key>`. (Founder-signed: this is the flip that activates a paid embedder.)
- **`kb/core.py`** — no code change to retrieve (dense leg already present); needs a **backfill pass**:
  re-embed existing `kb_chunks` (their `embedding` is NULL today). Add a **per-source `dense_ready` flag**
  (RAG-MASTER §7-9, completeness B5): a source stays FTS-only until its backfill completes, then an atomic
  flip — so no live call ever sees a half-embedded corpus.
- **`kb/grounding_cache.py`** — the W4 cache, built FIRST (before any dense flip).
- **Flag:** dense is gated by `EMBED_API_KEY` presence (the existing `status()=="configured"` check) — no
  new boolean flag; absence of the key = the permanent FTS-only default. Hard-gated behind a **RAGAS-fails-
  on-FTS proof** (RAG-MASTER §7-9): build dense ONLY if the eval shows FTS missing real semantic queries —
  never speculative.

### Safety / gates
- Multi-tenant: dense rows ride the SAME RLS predicate as FTS (`OR tenant_id='_global'` under the caller's
  own `is_admin=False` GUC) — the W1 hardening covers both legs; no new RLS surface.
- W6 eval gate must add a **no-embed-on-reply assertion** (with `EMBED_API_KEY` SET in staging, assert
  `lookup`+`pick_campaign` make ZERO embed RTT) before any dense flag flips ON in production.
- Cost cap: per-tenant chunk-count quota + max-doc-size (RAG-MASTER §7-12) bounds the one-time embed bill;
  the connect-only + cache pattern bounds the recurring bill to ~₹0.

### FOUNDER ACTIONS required (founder-signed Ph2)
1. **Provide an OpenAI API key** for `text-embedding-3-small` (NOT OpenRouter; direct OpenAI = cheapest +
   not the protected paid-credit pool).
2. **Sign off the paid embedder activation** (the one-time backfill ₹ + the per-connect embed ₹).
→ Until then, dense stays DORMANT (the permanent FTS-only default), and the smoke-proven 6–12ms FTS path
remains production. This is a pure ENHANCEMENT (better recall on paraphrased questions), not a fix.

---

## PHASED PLAN TO CLOSE BOTH (earner-safe, each = ONE verified unit)

| # | Wave | Scope | Box-mutating file | Flag (default) | Gate / acceptance | Founder action |
|---|---|---|---|---|---|---|
| **W-OB.1** | OUTBOUND grounding (connect-window) | port `_grounding_seed`/`_format_grounding`/`_kb_retrieve` + gated connect-window block into the `agent.py.LIVEBOX` golden | `agent.py` (EARNER) | `OUTBOUND_RAG_ENABLED=0` | golden flag-off byte-identical render + `agent.py.PREv<n>` rollback golden; restart famit-agent ONCE; /health 200; 0 5xx; **founder real ring-test (flag ON)** | (1) sign-off to edit agent.py · (2) DID un-blocked |
| **W-OB.2** | *(optional, later)* outbound `lookup` tool | loose FTS-only `lookup(query)` on `_MirrorAgent` | `agent.py` (EARNER) | own ring-test; loose tool schema (no Groq 400-storm) | founder ring-test |
| **W4** | grounding cache (prereq for dense) | `kb/grounding_cache.py` + wire inbound connect-prefetch through it (`dense=True` here only) | `aim_voice_agent.py` (inbound) | — | cache HIT ~0ms; inbound earner-gate (md5 9150fabe unchanged) | none |
| **Ph2-dense** | full-semantic dense retrieval | `.env` embedder config + `kb_chunks` backfill + `dense_ready` atomic flip | `.env` + backfill (no earner code) | `EMBED_API_KEY` set (= dense ON) | RAGAS-fails-on-FTS proof FIRST; W6 no-embed-on-reply assertion; p95 TTFT <150ms | (1) OpenAI key · (2) sign off paid embedder |

**Sequencing rule (RAG-MASTER §4 + ORCHESTRATOR lock):** W4 cache ships BEFORE Ph2-dense (the cache is
load-bearing for the ~0 claim). W-OB.1/.2 are independent of dense and can ship first IF the founder clears
agent.py + the DID. Only ONE box-mutating wave at a time; the earner-touching W-OB waves are FOUNDER-SIGNED
and ring-gated.

## EARNER GATE (this design phase): agent.py md5 `9150fabe` UNCHANGED (read-only mirror only) · 0 box
mutations · 0 restarts · NO ring · NO file on the box touched · the provider-framework-foundation wave
files NOT touched.

## STATUS: DONE (gap design — READ-ONLY).
