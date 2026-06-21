# EXPLORE-3 — VENDOR CONFIG + MODULE MAP (where settings live, the handoff-list design, the modular seams)

> READ-ONLY exploration of the LIVE box `famit@168.144.153.145`. Evidence-grounded, file:line cited. No
> box changes, no deploy, no git. Builds ON `INBOUND-PIPELINE-MASTER-PLAN.md` + the five plan-*.md docs.
> **#1 rule unchanged:** every inbound capability is ADDITIVE + ISOLATED and NEVER touches the outbound
> earner (`agent.py` / `famit-agent` / outbound trunks). Vendor-config + handoff are pure config/read-path.

---

## 0. THE HEADLINE ANSWERS (for the founder, plain)

- **Per-vendor config lives in THREE places today, each tenant-scoped:** (1) **`var/tenants.json`** =
  the account/plan/caps row (`tenant_id`, email, `role`, `max_concurrency`, `daily_call_cap`,
  `monthly_minutes_cap`); (2) the **Foundation Control Layer** = what *modules* a vendor can see/use —
  `entitlements.py` resolving `var/control/{registry.json,plans.json}` + PG per-tenant overrides
  (HIDE=404 / LOCK=402 / ON); (3) the **Business Brain** = the vendor's *business knowledge & rules* —
  `brain/core.py` JSON at `var/brain/<tenant_id>.json`, exposed by `caller.py:2206 GET /brain` +
  `:2218 PUT /brain`, already carrying an `escalation_rules` field. Voice identity numbers live in a
  fourth store: `ai_manager/registry.py` + `var/aim_numbers.jsonl` (per-DID `tenant/role/grants/status`).
- **RAG IS REAL and already built** — `kb/` module (`kb/core.py` + `kb/schema.sql`) is a tenant-scoped
  hybrid retriever (Postgres-FTS *core* leg LIVE + **pgvector dense leg** — `CREATE EXTENSION vector` is
  **installed in PG**, HNSW cosine index defined); `brain/core.py` wraps it (`retrieve`, `add_knowledge`,
  scopes `business|product:<id>|campaign:<id>`, `channel_scope all|voice|whatsapp|support|creative`). The
  gap: the **dense leg is dormant** (no embedder configured) and **nothing in the voice path uses it** —
  `agent.py`/`aim_voice_agent.py`/`prompt.py` never import `brain`/`kb` (only `caller.py:86` does).
- **Handoff-list design:** store it on the **Business Brain** (additive `handoff` block in
  `var/brain/<tenant_id>.json`, edited via the existing `PUT /brain` + a new panel **Settings → Human
  Handoff** card), NOT a new table — reuses the live versioned/audited per-org write surface and the
  `app/settings/page.tsx` that already exists. WhatsApp send reuses `whatsapp.py:send_whatsapp` verbatim.

---

## 1. WHERE PER-VENDOR / PER-TENANT CONFIG LIVES (the four stores, mapped)

| Store | File / route | Owns | Isolation | Edited via |
|---|---|---|---|---|
| **Account + plan + caps** | `var/tenants.json` (list of rows) | `tenant_id`, email, `role` (admin/manager), `max_concurrency`, `daily_call_cap`, `monthly_minutes_cap`, pass-hash | per-row `tenant_id` | super-admin / signup |
| **Control-Layer entitlements** (what MODULES a vendor gets) | `entitlements.py` → seed `var/control/registry.json` (29 KB feature catalog: `key, kind page/module/api, parent_key, nav_href, api_prefixes, default_mode, is_core`) + `var/control/plans.json` (trial/plan_a Growth=default/plan_b Scale/enterprise → `limits{max_concurrency,daily_call_cap,monthly_minutes_cap,monthly_credits,seats}`) + **PG per-tenant overrides** | resolve order = **status gate ▸ per-vendor override ▸ plan entitlement ▸ global default ▸ parent rolldown**; modes HIDE=404 / LOCK=402 / ON | PG (or all-default when PG absent) | `app/super-admin/{plans,flags,vendors}` → `/admin/*` (`require_super_admin`, `caller.py:632`) |
| **Business Brain** (vendor's KNOWLEDGE + RULES) | `brain/core.py` JSON `var/brain/<tenant_id>.json`; routes `caller.py:2206 GET /brain`, `:2218 PUT /brain` (write-role gated, versioned, audited) | `company_name, agent_name, product_*, persona, escalation_rules, ai_disclosure, call_window_*`, usps, qualifying_questions, etc.; `resolve_campaign_defaults` + `resolve_worker_context(role,channel)` feed workers | `org_id` ALWAYS = `t["tenant_id"]` from `resolve_tenant`, NEVER a body field (RT-5) | panel `app/settings/page.tsx` (exists) |
| **Voice numbers / AI-Manager identity** | `ai_manager/registry.py` + `var/aim_numbers.jsonl` | per-phone `number_id, tenant_id, phone, label, role, verify_mode, grants[], verified, status` | `lookup(phone, tenant_id?)` tenant-scoped; `list_numbers(tenant_id)` | panel `app/ai-manager/{users,setup}` |
| **Knowledge corpus (RAG)** | `kb/schema.sql` PG tables `kb_sources / kb_documents / kb_chunks` | scoped chunks (FTS + `embedding vector` HNSW), `scope`, `channel_scope`, `kb_version` cache-bust | **FORCE-RLS** `app.tenant_id` GUC-in-txn (identical to `db/rls.sql`) | `brain.add_knowledge` → `kb.ingest` |

**Seam for the new work:** the **Business Brain** is the *vendor-settings* surface (knowledge + rules,
already write-audited per-org); the **Control Layer** is the *platform-admin* surface (what a vendor may
use). The handoff list is a vendor *rule* → it belongs on the Brain, not the Control Layer.

---

## 2. THE VENDOR HUMAN-HANDOFF LIST — design (additive, reuse-first)

**Decision: a `handoff` block on the Business Brain** (`var/brain/<tenant_id>.json`), edited via the
existing `PUT /brain` route + a new **Settings → Human Handoff** panel card. No new table, no new auth —
it inherits per-org isolation (RT-5), versioning, and audit for free. Shape:

```jsonc
"handoff": {
  "enabled": true,
  "numbers": [                                  // a vendor may add MULTIPLE
    {"id":"hn_01","name":"Sales lead Rohan","phone":"+9198...","whatsapp":"+9198...",
     "roles":["warm_transfer","hot_lead_wa"],   // can receive live transfers AND/OR WA alerts
     "hours":{"tz":"Asia/Kolkata","start":"10:00","end":"19:00","days":[1,2,3,4,5,6]},
     "priority":1, "active":true}
  ],
  "rules": {
    "transfer_on": {"hot_score_gte":80, "explicit_ask":true},   // HOT or "talk to a human"
    "ring_strategy":"priority_then_roundrobin",                 // who to try first / fallback
    "ring_timeout_s":25, "max_attempts":2,
    "after_hours":"wa_only",                                     // out-of-hours -> WA alert + callback task
    "fallback":"capture_callback"                                // nobody answers -> logged callback, never dead-air
  },
  "wa_template":"hot_lead_alert"                                  // WA template id for the post-call alert
}
```

- **Warm transfer (live call):** a NEW `sales-in`/`manager` worker tool `transfer_to_human` performs a
  LiveKit **SIP REFER / `transfer_sip_participant`** to the next eligible `roles∋warm_transfer` +
  `hours`-open number by `ring_strategy`; speaks a bridge line ("Connecting you to Rohan, one moment"),
  preserves context, falls back down the priority list, then to `capture_callback`. **Outbound earner
  untouched** — transfer is an inbound-worker-only capability via a separate trunk/REFER.
- **Hot-lead → WhatsApp (post-call):** on hangup, if `lead_score ≥ rules.hot_score_gte`, create the
  hot-lead entry and **`whatsapp.py:send_whatsapp(to, "hot_lead_alert", [lead_phone, summary,…])`** to
  every `roles∋hot_lead_wa` number (reuses the LIVE Meta/BSP send path verbatim — `whatsapp.py:248`).
- **Lead scoring source:** reuse `workforce`/`ai_manager` deterministic scoring + the call summary already
  produced for memory/recap; `var/leads.json` + CRM `leads/hot` (`command.dashboard` api_prefix
  `/leads/hot`) is the hot surface.

---

## 3. CURRENT MODULARITY — clean modules vs tangled (the seam audit)

**Already-clean, plug-in-shaped modules (each: own dir, `__init__`, `config.py` flag-gated, `schema.sql`,
import-safe degrade, tenant-scoped):** `ai_manager/` (config/registry/identity/intent/state_machine/
store/recorder/endpoints), `workforce/` (config/roles/runner/tools/guardrails/policy/handover/store),
`kb/` (RAG core+schema), `brain/` (per-org facade), `whatsapp.py` (provider-agnostic single entry),
`firewall.py`, plus feature dirs `funnels/ workflow/ booking/ crm/ payments/ media_gen/ ads_engine/`.
This is **already a modular monolith** — every subsystem is flag-gated, import-safe, and reachable over
the authed loopback (`workforce.config.loopback_base 127.0.0.1:8209`, asset service `:8310`).

**Tangled / monolithic seams:** `caller.py` is **258 KB** — the god-router that mounts everything and
holds resolvers (`norm`, `_resolve_contact_by_phone`, `_link_inbound`, `_load_campaign`); `agent.py`
(43 KB) is the outbound earner with the sales brain **inlined** (not a shared library) → the inbound
worker must **re-implement read-only**, not import it. `aim_voice_agent.py` mixes transport + STT-build +
state-drive in one file. Persistence is **JSONL/PG-mixed** (`aim_numbers.jsonl`, `tenants.json`,
`var/brain/*.json` vs PG `ai_manager_*`/`kb_*`) — not yet consolidated.

---

## 4. TARGET MODULE SEAMS (where a plugin/per-mode structure slots in for scale)

1. **Per-mode voice workers as separate units** (already the plan): `manager` (Mode B) + `sales-in`
   (Mode A) as isolated `agent_name`/systemd/port workers — never one mega-worker.
2. **Extract a `voice_brain` shared lib** from `agent.py`'s `_load_campaign`+`build_system_prompt` so
   inbound reuses it as a *library* (today it's inlined → re-implemented). Pure refactor, outbound-safe.
3. **A `handoff/` module** (transfer strategy + WA-alert dispatch + callback fallback) consuming the Brain
   `handoff` block — one home for both live-transfer and post-call-WA logic, reused by all modes.
4. **Wire `brain`+`kb` (RAG) into the voice prompt assembler** — the biggest missing seam: inject
   `brain.retrieve(tenant, query, scope=campaign:<id>)` for objection/product/history context into both
   inbound modes (and later outbound), behind a flag. Embedder is the one missing credential.
5. **Consolidate config onto PG + FORCE-RLS** (registry/tenants/brain → PG) for true multi-vendor
   isolation at scale; keep JSON as the dev/degrade fallback the modules already support.
6. **A vendor-settings router** (`/settings/handoff`, thin over `PUT /brain`) + panel cards under
   `app/settings/` and `app/ai-manager/setup` — the editable surface for the handoff list and rules.

---

## 12-LINE MAP (vendor config · handoff-list · modularity · target seams)

1. **Account/plan/caps** = `var/tenants.json` (per `tenant_id`: role, max_concurrency, daily_call_cap, monthly_minutes_cap).
2. **What-modules-a-vendor-gets** = `entitlements.py` over `var/control/{registry.json,plans.json}` + PG overrides; HIDE 404 / LOCK 402 / ON; resolve = status▸override▸plan▸default▸rolldown.
3. **Vendor KNOWLEDGE + RULES** = `brain/core.py` JSON `var/brain/<tenant_id>.json` via `caller.py:2206 GET /brain` + `:2218 PUT /brain` (versioned, audited, RT-5 org from token); already has `escalation_rules`.
4. **Voice identity numbers** = `ai_manager/registry.py` + `var/aim_numbers.jsonl` (per-phone tenant/role/grants/verify/status; `lookup` tenant-scoped).
5. **RAG IS REAL** = `kb/core.py`+`kb/schema.sql` hybrid (FTS core LIVE + **pgvector dense** — extension INSTALLED in PG, HNSW cosine), FORCE-RLS by `app.tenant_id`; `brain.retrieve/add_knowledge` wraps it; scopes business/product/campaign, channel_scope voice/whatsapp/…
6. **RAG GAP** = dense leg DORMANT (no embedder) + **not wired into voice** (`agent.py`/`aim_voice_agent.py`/`prompt.py` never import brain/kb; only `caller.py:86`). This is the #1 context win to wire.
7. **HANDOFF-LIST design** = additive `handoff{numbers[],rules,wa_template}` block on the Business Brain (NOT a new table) — multiple numbers, each with phone+whatsapp+roles+hours+priority; edited via `PUT /brain` + new **Settings → Human Handoff** card (`app/settings/page.tsx` exists).
8. **Warm transfer** = new inbound-worker tool `transfer_to_human` → LiveKit SIP REFER/`transfer_sip_participant` to next open `warm_transfer` number by ring_strategy; bridge line + priority fallback → callback; **outbound earner untouched**.
9. **Hot-lead → WA** = on hangup if `score≥hot_score_gte`: create hot-lead + `whatsapp.send_whatsapp(to,"hot_lead_alert",[phone,summary])` to every `hot_lead_wa` number — reuses LIVE `whatsapp.py:248` verbatim.
10. **Already-clean modules** = `ai_manager/ workforce/ kb/ brain/ funnels/ workflow/ booking/ crm/ payments/ media_gen/ whatsapp.py firewall.py` — flag-gated, import-safe, tenant-scoped, loopback-reachable (modular monolith).
11. **Tangled seams** = `caller.py` 258 KB god-router (resolvers inlined), `agent.py` sales brain inlined (re-implement read-only, don't import), `aim_voice_agent.py` mixes transport+STT+drive, JSONL/PG-mixed persistence.
12. **TARGET seams** = per-mode workers (manager/sales-in) ▸ extract `voice_brain` lib ▸ new `handoff/` module ▸ **wire brain+kb RAG into the voice prompt (flag-gated, embedder = one missing cred)** ▸ consolidate config→PG+RLS ▸ thin `/settings/handoff` router + panel cards.
