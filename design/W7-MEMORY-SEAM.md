# W7 LEAD-MEMORY SEAM — the LATER flag-gated live splice

> Status: **SEAM NOTE ONLY — DO NOT BUILD/EDIT in this wave.**
> EARNER LAW: live `droplet_work/agent.py` md5 = `98655dbf` FROZEN; `caller.py` /
> `aim_voice_agent.py` NOT edited. The cutover below is a future, founder-signed,
> flag-gated wave. This document is the exact wiring spec so that wave is a small,
> reversible, earner-gated splice — not a rebuild.

The W7 module is **BUILT + GREEN** (27/27 tests) under `voice_kernel/memory/`,
fully isolated (pulls ZERO `droplet_work` / `context` modules at import; lazy box
`asession`). It implements the FROZEN `MemoryService` Protocol and registers via
`build_kernel(cfg, memory=LeadMemoryService())`. Nothing live calls it yet.

---

## 0. What is already built (this wave) vs spliced LATER

| Piece | Built now (`voice_kernel/memory/`) | Spliced LATER (this doc) |
|---|---|---|
| `MemoryService` impl (load/persist, hot/warm/cold) | ✅ `service.py` | — |
| salient extraction (rules + LLM hook) | ✅ `extraction.py` | — |
| lifecycle FSM + conversion score | ✅ `lifecycle.py` | — |
| AI summary card + next-best-action | ✅ `cards.py` | — |
| conversation-continuity builder | ✅ `continuity.py` | — |
| right-to-erasure cascade + Purgeable | ✅ `erasure.py` | — |
| FORCE-RLS schema | ✅ `ddl_lead_memory.sql` | applied to the box (DDL step) |
| **post-call WRITE call site** | seam only | `_finalize_call` / hangup hook |
| **next-call RECAP injection call site** | seam only | `_build_sales_instructions` |
| **super-admin erase control** | seam only | control-plane route |

---

## 1. DDL apply step (box, one-time, off the Alembic chain)
Apply `voice_kernel/memory/ddl_lead_memory.sql` to the box PG as the app role
(`famit_app`), exactly like `db/ddl_wallet.sql`:

```
psql "$DATABASE_URL" -f voice_kernel/memory/ddl_lead_memory.sql
```

Idempotent (`IF NOT EXISTS`). Creates `lead_memory` (PK `(tenant_id, lead_phone)`)
+ `lead_memory_summary` (append-only history) + FORCE-RLS admin-GUC policy. This
is a DB-only change; it touches NO live `.py`. Verify after: a SELECT under
`SET app.tenant_id='tA'` returns only tenant A's rows; GUC unset returns zero.

---

## 2. POST-CALL WRITE seam — `aim_voice_agent.py`

**Anchor (today's no-op shim, already present):** `aim_voice_agent.py:222`
```python
# W3b: durable post-call memory extraction (flag LEAD_MEMORY_PG, default 0 => no-op).
try:
    import lead_memory as _lead_memory   # enqueue_episode / enabled (W3b)
except Exception:
    _lead_memory = None
```
**Hangup hook anchors:** `aim_voice_agent.py:955` (room-disconnect shutdown hooks
"memory/lead persist") and `aim_voice_agent.py:2036` (`-- hangup: stop recording
+ close the session row --`).

**The splice (LATER, flag-gated):** in the post-call shutdown hook, AFTER the
transcript + outcome are finalized, call the W7 COLD path:

```python
# behind a NEW flag KERNEL_MEMORY_ENABLED (default "0").
if os.getenv("KERNEL_MEMORY_ENABLED", "0") == "1":
    from voice_kernel.memory import LeadMemoryService
    svc = LeadMemoryService()                 # lazy box asession; tenant-RLS
    await svc.extract_and_persist(
        tenant_id=session.tenant_id,          # SERVER-STAMPED KernelSession tenant — NEVER a body value
        lead_phone=lead_phone,
        turns=transcript_turns,               # the session's role-tagged turns
        raw_summary=agent_end_summary,        # optional: the agent's own closing line
        name=lead_name,
        llm=None,                             # or a cheap async LLM callable for refine
    )
```

Rules for the splice:
- **Flag default OFF.** `KERNEL_MEMORY_ENABLED=0` ⇒ the block never runs ⇒ the
  legacy path is byte-identical (the OFF golden-render test stays 10/10).
- **`tenant_id` is the server-stamped `KernelSession.tenant_id`** (resolved campaign
  owner), never a dispatch-body `campaign_id`. The W7 service ALSO fail-closes on a
  blank tenant (raises) so a tenant-less write can't slip through.
- **Never blocks / never raises into the call.** `extract_and_persist` is COLD and
  swallows its own errors (degrades to the deterministic draft, logs, returns). The
  hangup hook must still `try/except` around it as a second belt.
- **Relationship to the W3b `lead_memory` shim:** W7 is the structured, kernel-bound
  successor. The cutover wave either (a) routes the W3b flag to the W7 service, or
  (b) adds the new `KERNEL_MEMORY_ENABLED` flag and retires `LEAD_MEMORY_PG`. Pick
  ONE write path so a call writes the lead row exactly once.

---

## 3. NEXT-CALL RECAP seam — `aim_voice_agent.py:1436` `_build_sales_instructions`

**Anchor:** `_build_sales_instructions(fields, recap, caller_name, ...)` (line 1436)
already takes a legacy `recap` string and folds it into the inbound sales
instructions (it REUSES `prompt.build_system_prompt`). This is the lossy legacy
recap W7 replaces.

**The splice (LATER, flag-gated):** at dial, load the ONE lead row and inject it as
the fenced `LEAD_MEMORY` L4 block via the kernel, instead of the legacy recap
string:

```python
if os.getenv("KERNEL_MEMORY_ENABLED", "0") == "1":
    from voice_kernel.kernel import build_kernel
    from voice_kernel.memory import LeadMemoryService, continuity_opener_hint
    kernel = build_kernel(memory=LeadMemoryService())
    # WARM, post-opener background task (NOT on the reply path) — matches the
    # existing grounding-prefetch shape (create_task), kernel.enrich_prefix:
    packet = await kernel.enrich_prefix(ctx, packet)      # loads L4, fences it
    opener_hint = continuity_opener_hint(packet.lead)     # "kal aapne bola tha..."
    # apply via session.update_instructions(...) AFTER the opener fires.
```

Rules:
- **Positioning is the FROZEN packet's job.** `render_call_suffix` wraps L4 in
  `FencedText(SourceTrust.LEAD_MEMORY)` ABOVE the vendor `CAMPAIGN_BRIEF` and BELOW
  PLATFORM L0 — so a poisoned vendor script can't reference caller history, and a
  poisoned prior summary can't climb above safety. Do NOT inline lead text raw.
- **Continuity, not restart.** `continuity_opener_hint()` returns "" for a fresh
  NEW lead (cold opener) and the resume hint for a known lead — so the call opens
  with "last time you said you'd check the budget…", never from zero.
- **Never on the HOT reply path.** `enrich_prefix` runs as a post-opener background
  task (kernel.py:143); the opener fires from `assemble_prefix_core` (sync, no
  await). The DoD is: no await between prefix-core and the opener.
- **Flag OFF ⇒ legacy recap string path unchanged** (byte-identical).

---

## 4. ERASURE seam — super-admin control plane (NOT this wave)

The super-admin "delete lead / offboard tenant" control calls:
```python
from voice_kernel.memory import LeadMemoryService, LeadMemoryEraser
svc = LeadMemoryService()
eraser = LeadMemoryEraser(purgeables=[svc.cache])   # register the WARM cache (+ any W4 vector leg)
await eraser.erase_lead(tenant_id, lead_phone)      # or erase_tenant(tenant_id)
```
Mounted behind the existing control-plane auth (`require_super_admin`), behind the
same flag. Cascade = head + history + cache, one txn, RLS-bounded, idempotent,
no-PII audit event. A future W4 vector leg MUST register as `Purgeable` so erasure
can never miss it (E4).

---

## 5. ACCEPTANCE for the cutover wave (when it actually happens)
1. A real OUTBOUND call rings BEFORE and AFTER the splice (earner regression gate).
2. `droplet_work/agent.py` md5 still `98655dbf` (the outbound earner brain untouched).
3. Flag OFF ⇒ golden-render byte-identical, 10/10 (the W7 OFF-identity test).
4. On the live box: a `load` under tenant A NEVER returns tenant B's row; a forged
   cross-tenant write is rejected by RLS WITH CHECK.
5. `erase_lead` leaves ZERO residue (head + summary + cache); idempotent on retry.
6. `/health` 200 throughout; one box-mutating change at a time + an immediate revert
   path (the flag back to 0 + the DDL is additive, not destructive).
NONE of these run in the BUILD wave — they gate the future cutover.

---

## 6. Quick file map (what to read for the splice)
- `voice_kernel/memory/service.py` — `LeadMemoryService.load/persist/extract_and_persist`
- `voice_kernel/memory/continuity.py` — `apply_lead_memory`, `continuity_opener_hint`, `has_history`
- `voice_kernel/memory/extraction.py` — `extract_rules`, `extract_with_llm`, `prob_for`
- `voice_kernel/memory/lifecycle.py` — `classify_lifecycle`, `conversion_probability`, `classify_with_llm`
- `voice_kernel/memory/cards.py` — `build_summary_card`, `next_best_action_rules/llm`
- `voice_kernel/memory/erasure.py` — `LeadMemoryEraser`, `Purgeable`
- `voice_kernel/memory/cache.py` — `LeadMemoryCache` (tenant-namespaced; Purgeable)
- `voice_kernel/memory/ddl_lead_memory.sql` — the FORCE-RLS schema
- `voice_kernel/kernel.py:143` `enrich_prefix` / `:204` `persist_summary` — the kernel seams
- `voice_kernel/memory/RESEARCH_DECISIONS.md` — the binding decision log (M1–E5, S1–S5)
