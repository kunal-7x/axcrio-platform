# W3 INTEGRATION SEAM — campaign-context (compiler + understanding + vendor-script + ContextEngine)

Status: **DESIGN NOTE ONLY.** This wave built + tested `voice_kernel/context/`.
It did NOT edit any live file. This document specifies the LATER, flag-gated
wiring into `droplet_work/caller.py` so a future wave (human-gated) can land it
with a one-line revert. EARNER LAW held this wave: `agent.py` md5 unchanged
(`98655dbf`); `caller.py` / `aim_voice_agent.py` untouched.

The whole seam is gated behind ONE new flag, default **OFF**:

```
KERNEL_W3_CONTEXT   # off by default; when on, the dual-layer compile + vendor
                    # script blueprint replace the lossy extract path.
```

When the flag is OFF, every code path below is byte-identical to today. The W3
package is additive and import-safe (pure-stdlib core; zero droplet imports —
proven by `test_w3_context.py::test_context_subsystem_pulls_no_droplet_modules`).

---

## Seam 1 — `/extract` save-time compile (the LOSSY-COMPRESSION fix)

**File:line:** `droplet_work/caller.py:4031` (`@app.post("/extract")` → `extract`)
and the helper it calls, `extract_fields` at `caller.py:1409`
(+ `_sanitize_extracted` at `caller.py:1372`).

**Problem today:** `extract_fields` (caller.py:1409) sends `brief[:12000]` to Groq
and returns a tiny JSON; `_sanitize_extracted` (caller.py:1372) clamps it further.
The **full brief is never persisted** — the agent behaves as if it never read the
brochure. (Note: `raw_script` IS already stored verbatim by `_coerce_vendor_script`
at caller.py:1330 — W3 extends that lossless discipline to the WHOLE compiled card.)

**Wire (flag-gated):** after `extract_fields(brief)` returns `fields`, when
`KERNEL_W3_CONTEXT` is on, ALSO run the dual-layer compile and persist BOTH layers:

```python
# caller.py /extract handler (additive branch, flag-gated)
from voice_kernel.context import compile_campaign
fields = extract_fields(brief or "")          # unchanged lossy projection (T2 seed)
if os.getenv("KERNEL_W3_CONTEXT", "0") in ("1", "true", "True"):
    compiled = compile_campaign(
        tenant_id=resolve_tenant(request),     # caller.py:404 resolve_tenant (token, not body)
        campaign_id=cid,                        # the campaign being saved
        brief=brief or "",                      # T0 RAW preserved verbatim
        fields=fields,                          # vendor-authored fields win
    )
    # persist T0 lossless + T1 full_* + T2 compact card alongside the campaign row.
    _persist_compiled(cid, compiled)            # NEW save-time store (see Seam 4)
return JSONResponse(fields)                      # response shape unchanged (OFF-safe)
```

`compile_campaign` is RETRIEVAL-OVER-TRUNCATION: it preserves the full brief
(`CompiledCampaign.full_brief`), sets the H13 lossless fields
(`full_product_summary`, `full_usps`, `summary_overflow`, `usps_overflow`) and a
`raw_script_ref` POINTER (`campaign:{cid}#source`) for W4 mid-call recall.

**Editable understanding:** `compiled.understanding` (use_case / industry /
objective / needs_booking / needs_handoff / needs_whatsapp) is returned to the
panel so the vendor can edit it; `CampaignUnderstanding.with_overrides(...)` and
`classify(brief, fields)` honour vendor overrides (explicit field wins).

---

## Seam 2 — `run_job` dispatch: build the ContextEngine + VendorScriptEngine

**File:line:** `droplet_work/caller.py:2852` (`run_job`), specifically where it
reads `camp_fields = camp.get("fields", {})` (caller.py:2858) and assembles the
per-call dispatch/grounding for each lead.

**Wire (flag-gated):** when `KERNEL_W3_CONTEXT` is on, construct the kernel with
the registered engines instead of feeding the legacy field dict straight into the
prompt. The vendor script becomes the AUTHORITATIVE blueprint:

```python
# inside run_job, once per job (NOT per tick):
if os.getenv("KERNEL_W3_CONTEXT", "0") in ("1", "true", "True"):
    from voice_kernel import build_kernel, KernelConfig
    from voice_kernel.context import ContextEngineImpl, VendorScriptEngineImpl
    compiled = _load_compiled(cid)               # the Seam-1 artifact (or compile on the fly)
    vs = VendorScriptEngineImpl()
    vs.register(cid, camp_fields.get("raw_script", ""), variables={
        "lead_name": lead.get("name", ""), "agent_name": camp_fields.get("agent_name", "Riya"),
        "company": camp_fields.get("company_name", ""), "product": camp_fields.get("product_name", ""),
        # ...campaign + per-lead variables for {{...}} substitution
    })
    ce = ContextEngineImpl({cid: compiled}, vendor_script=vs,
                           safety_rules=SHARED_RULES)   # from prompt.py, passed in (no kernel import of prompt)
    kernel = build_kernel(KernelConfig.from_env(), context=ce, vendor_script=vs)
    # kernel.assemble_prefix_core(ctx) -> the system prompt; vendor flow overrides the default.
```

`SHARED_RULES` is the PLATFORM L0 safety text (`droplet_work/prompt.py:179`). It
is passed IN at wiring time — the kernel never imports prompt.py (isolation). The
ContextEngine renders L0 (safety) FIRST by position, with the campaign card +
vendor blueprint fenced (`<campaign_brief>`) BELOW it (C3). Proven by
`test_w3_context.py::test_fences_present_and_safety_above_by_position`.

**Vendor-script authority:** when a campaign has a `raw_script`, `ContextEngineImpl`
folds the vendor's GREET/PERMISSION/INTRO blueprint into the card greeting +
leading talking points, so the flow ordering the vendor wrote
(greet→confirm→intro→reason→qualify→pitch→objections→close) overrides the default
framework. When absent, `stage_excerpt` returns "" and the kernel's default FSM /
brain-pack flow runs unchanged (proven:
`test_vendor_script_absent_falls_back_to_default_framework`).

---

## Seam 3 — recap seam (per-call lead memory join)

**File:line:** the recap is built today via `memory.py build_recap`
(`caller.py:50` import; `caller.py:2180` `_wa_memory_recap`; `caller.py:2194`
`build_recap(rec, agent_name)[:500]`) and joined into grounding at
`caller.py:2216–2226`. The OUTBOUND voice recap is passed as `CallContext.recap`
(back-compat) and on the dispatch metadata that `agent.py` reads.

**Wire (flag-gated):** when `KERNEL_W3_CONTEXT` is on, the recap stops being a raw
string spliced into the prompt and instead flows through L4 (`LeadMemory`) via the
kernel's `enrich_prefix` / `MemoryService` seam (W7 owns the structured store).
For W3 alone, the minimal change is to keep passing the legacy `recap` string on
`CallContext.recap` (already supported) — the W3 ContextEngine does not consume it
yet, so behaviour is identical. The FULL L4 cutover is a W7 concern; this note
records the join point so W7 lands cleanly:

```python
ctx = CallContext(meta=meta, fields=camp_fields, recap=mem_recap, session=session)
# W7 later: kernel.enrich_prefix(ctx, packet) loads LeadMemory (L4) from the
# structured store keyed by (tenant_id, lead_phone) — fenced as LEAD_MEMORY.
```

`session` is the server-stamped `KernelSession(tenant_id, call_id)` (C2,
fail-closed) — stamped from the resolved campaign owner, NEVER the dispatch body.

---

## Seam 4 — persistence (new save-time store, additive)

The compiled artifact (T0 raw + T1 full_* + T2 card + understanding) needs a home.
Two additive options, both tenant-RLS-isolated, neither touching existing rows:

1. **Inline (fastest to land):** stash `compiled` as extra keys ON the existing
   campaign `fields` JSON — `fields["_compiled"] = {...}` — so no DDL. The raw is
   already there (`fields["raw_script"]`); add `full_product_summary`, `full_usps`,
   `understanding`. `run_job` reads it back with zero migration.
2. **New table (cleaner for W4 FTS):** `campaign_source(tenant_id, campaign_id,
   raw_text, full_summary, full_usps, understanding_json, ts)` with FORCE-RLS, so
   W4 can build a Postgres FTS index over `raw_text`/`full_summary` for mid-call
   recall via `raw_script_ref`. Recommended for the W4 wave; option 1 is enough to
   ship the vendor-script + dual-layer fix alone.

DDL (if option 2) follows the `db/ddl_wallet.sql` FORCE-RLS pattern; zero `%`
DDL, admin-GUC. This note does not create it (no live mutation this wave).

---

## OFF-safety checklist (verify before any cutover)

- `KERNEL_W3_CONTEXT` default OFF → all four seams no-op; `/extract` response shape
  unchanged; `run_job` dispatch unchanged; recap unchanged.
- `KERNEL_ENABLED` stays the master switch for the kernel REPLACING the live prompt
  (config.py `enabled_for`); W3 only PRODUCES the better packet — the live cutover
  is the existing human-gated G3 step, unchanged.
- agent.py md5 stays `98655dbf` (W3 never imports/edits it).
- Place `KERNEL_W3_CONTEXT` via the systemd drop-in for inbound, NOT the shared
  `.env` (LEARNINGS §2: shared `.env` flags leak to the outbound earner on restart).
- Revert = unset the one flag (instant) or `git revert` the seam commit.

## Public surface this seam binds against (built + green this wave)

- `voice_kernel.context.compile_campaign(tenant_id, campaign_id, brief, fields, distiller=, understanding=) -> CompiledCampaign`
- `voice_kernel.context.CompiledCampaign` (`.full_brief`, `.card`, `.understanding`, `.raw_script_ref`, `.raw_fenced`)
- `voice_kernel.context.classify(brief, fields) -> CampaignUnderstanding` (`.with_overrides(...)`)
- `voice_kernel.context.ContextEngineImpl(campaigns, *, vendor_script=, safety_rules=, budget=)` — `ContextEngine` Protocol
- `voice_kernel.context.VendorScriptEngineImpl(scripts=, variables=)` — `VendorScriptEngine` Protocol; `.register(cid, raw, variables=, greeting_hint=)`
- `voice_kernel.context.{compile_script, parse_script, render_vars, sanitize}`
- registration: `build_kernel(cfg, context=ce, vendor_script=vs)` (alias `context`→`context_engine` added in `kernel.py`)
