# W7 — LEAD MEMORY (MemoryService L4) — wave run

Lead-centric (not call-centric) memory: hot/warm/cold split + structured salient
extraction + lifecycle/conversion + AI summary card + next-best-action +
conversation continuity + FORCE-RLS schema + right-to-erasure. Binds the FROZEN
contracts; registers via `build_kernel(cfg, memory=LeadMemoryService())`. EARNER
LAW respected: `agent.py` md5 `98655dbf` frozen; no live `.py` edited.

## Phase: BUILD

Built (all under `voice_kernel/memory/`, fully isolated — pulls ZERO
droplet_work/context modules at import; lazy box `asession`):

- `ddl_lead_memory.sql` — FORCE-RLS schema. `lead_memory` (PK `(tenant_id,
  lead_phone)`, 1:1 with the frozen LeadMemory; `last_call_summary` DB CHECK
  ≤300) + `lead_memory_summary` (append-only history). Admin-GUC RLS policy
  (USING + WITH CHECK), identical shape to `db/rls.sql`/`db/ddl_wallet.sql`.
- `hygiene.py` — self-contained NFKC + zero-width strip + fence-defang (write-side
  S4). Disjoint copy (the W3 `context` package has a load-order circular import
  under py3.14 → I do NOT depend on its `__init__`).
- `extraction.py` — `extract_rules` (deterministic, await-free, salient-only:
  commitments / objections / callback / booking / handoff / do-not-mention, lead
  utterances only, reconciled with prior — Mem0 ADD/UPDATE pattern) +
  `extract_with_llm` (async LLM-assist hook, degrades to the rules draft). Internal
  conversion_prob threaded via an id-keyed side table (`prob_for`) so the FROZEN
  LeadMemory stays un-widened.
- `lifecycle.py` — `classify_lifecycle` (deterministic FSM: NEW/HOT/WARM/COLD/DEAD;
  DEAD sticky; booked/handoff→HOT; commitment→WARM; objection-only→COLD; HOT cools
  one notch) + `conversion_probability` (0..100 internal score, DEAD=0) +
  `classify_with_llm` (advisory; may only DOWNGRADE, never resurrect DEAD).
- `cards.py` — `build_summary_card` (AI summary card + business badge per
  lifecycle) + `next_best_action_rules` / `next_best_action_llm` (NBA).
- `continuity.py` — `has_history`, `continuity_opener_hint` ("kal aapne bola
  tha…"), `apply_lead_memory` (applies L4 onto the packet; the renderer fences it).
- `cache.py` — `LeadMemoryCache`, tenant-namespaced `(tenant_id, lead_phone)`
  keys, TTL, `evict`/`evict_tenant`, Purgeable. (`__bool__`→True so an empty cache
  isn't falsy.)
- `erasure.py` — `LeadMemoryEraser.erase_lead`/`erase_tenant` (HARD cascade head +
  history + every Purgeable, one txn, RLS-bounded, idempotent, no-PII audit) +
  `Purgeable` Protocol (W4 vector leg must register).
- `service.py` — `LeadMemoryService` (FROZEN MemoryService impl). `load` (cache-
  first PK read, RLS GUC + redundant WHERE seatbelt, empty-on-miss NEW, fail-closed
  blank tenant) / `persist` (UPSERT head + append history, write-side sanitize,
  clamp ≤300, JSONB↔tuple) / `extract_and_persist` (one-call COLD entry) +
  `summary_card`. Lazy box `asession` (resolved on first use only).
- `__init__.py` — public surface.

Tests: `voice_kernel/memory/tests/` — `fakes.py` (FakeRLSSession mirrors FORCE-RLS:
GUC-scoped reads, WITH-CHECK rejects forged-tenant writes) + `test_memory_service.py`
(27 tests).

### Verification (run, green)
- `pytest voice_kernel/memory/tests/` → **27 passed**.
- Full `pytest voice_kernel/` (after clearing stale `.pyc`) → **212 passed / 0
  failed** (no regression; the W3/redteam/isolation tests pass alongside W7).
- Covered: Protocol conformance (`isinstance(svc, MemoryService)`); registers via
  `build_kernel(memory=…)`; fail-closed blank tenant raises (load+persist+erase);
  empty-on-miss; persist↔load round-trip; **cross-tenant read DENIED** (tenant B
  never sees tenant A's row); forged-tenant write rejected by WITH CHECK; summary
  clamped ≤300 at store; **extraction keeps ONLY salient facts** (raw filler/agent
  lines dropped) + reconciles prior; lifecycle FSM transitions correct; conversion
  score bounded/ordered; **continuity surfaces the prior summary**; L4 rendered
  **inside the `<lead_memory>` fence**; write-side sanitize strips a fence-breakout
  + zero-width; erasure cascade purges head+history+cache, idempotent, tenant-exact;
  cache tenant-namespaced; extract_and_persist e2e (no-LLM + LLM-degrade +
  LLM-refine); **flag-OFF byte-identity 10/10**; **0 droplet_work/agent imports**.

### EARNER LAW
- `droplet_work/agent.py` md5 = `98655dbf` (unchanged).
- `agent.py` / `caller.py` / `aim_voice_agent.py` — NOT edited (git clean).
- Branch: `fix/realtime-voice-kernel-v2`. All new files DISJOINT under
  `voice_kernel/memory/`.

### Seam
- `design/W7-MEMORY-SEAM.md` — the LATER flag-gated cutover: DDL apply step;
  post-call WRITE seam (`aim_voice_agent.py:222` shim / `:955` + `:2036` hangup
  hooks → `extract_and_persist`, flag `KERNEL_MEMORY_ENABLED` default OFF); next-
  call RECAP seam (`aim_voice_agent.py:1436` `_build_sales_instructions` → kernel
  `enrich_prefix` + `continuity_opener_hint`, replaces the lossy legacy recap);
  erasure seam (super-admin, `require_super_admin`). All default OFF; cutover is
  earner-gated + reversible.

### Notes / gotchas for the next agent
- The W3 `context` package `__init__` has a circular-import (`_FORGED_TAG_RE`
  NameError) under Python 3.14 — that's why W7 ships its own `hygiene.py` instead of
  importing `context.text_hygiene`. Pre-existing; not W7's to fix.
- Stale `.pyc` from another session's WIP `context_engine.py` (uncommitted, 97-line
  diff, references a non-existent `Stage.PITCH`) caused 7 phantom full-suite
  failures; `find … -name '*.pyc' -delete` clears them → 212/0.
- An empty `LeadMemoryCache` is falsy by `len`; `service.__init__` uses an explicit
  `is not None` check (not `cache or …`) so an injected empty cache is honoured.
