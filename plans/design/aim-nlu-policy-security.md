# AI Manager — NLU + Policy + Risk + Security — Execution-Ready Design Spec

> **Scope of THIS doc (one wave, one owner):** the *intelligence + safety brain* of the dedicated AI
> Manager service — (1) the NLU contract (system prompt + strict JSON schema §22 + few-shot + provider
> call), (2) the intent→action_type→risk_level table + always-block list, (3) the `PolicyEngine` decision
> function, (4) PIN security (Argon2id, set/verify/reset, lockout), (5) the compliance gate
> (hours/DND/STOP/consent), (6) the audit-event taxonomy + immutability, (7) the tenant-isolation test
> plan. This is the deterministic machinery between "speech→text" and "adapter→/api". It does **not**
> design the voice transport, the dashboard UI, the adapters, or the wallet math — those are sibling waves
> (`design/platform-ai-manager.md` voice front; `design/credit-ledger-firewall.md` wallet/firewall;
> `AI_MANAGER_MASTER_PROMPT.md` §§14/9 UI+adapters). Everything here conforms to the 28-section master spec.
>
> **Status:** READY-TO-BUILD design. READ-ONLY wave — no app code, no deploy, no git.
> **Architecture (decided):** AI Manager is a **dedicated coarse service** — own process, own Postgres
> schema `ai_manager_*` (FORCED RLS), own port + systemd unit — co-located on the backend box
> `famit@168.144.153.145` now, extractable later. It calls the monolith `/api` (`:8209`,
> `X-Auth: FamitCall2026` / tenant JWT) over the network to *execute*; it owns *understanding + authority*.
> **Reuse, never rebuild:** monolith `firewall.py` (step-up token mint/verify), `wallet.py`
> (holds/settle), `audit.py` (immutable `events` leg), `auth.py` (issue_pair/resolve), RLS admin-GUC shape,
> Groq LLM abstraction, the existing thin `/ai-manager` router (numbers/sessions — **absorbed**, see §0.2).

---

## 0. GROUND TRUTH — what already exists (cited; do not re-derive)

Verified 2026-06-10 against memory brain + build logs + the firewall/wallet design.

### 0.1 Monolith primitives this service calls (exact symbols, not the spec's prose names)
| Primitive | Real symbol (verified) | This service's use |
|---|---|---|
| **Step-up token mint** | `firewall.mint_step_up(tenant, scope)` → `jwt.encode({sub:tenant_id, amr:"pin", scope, type:"step_up", exp:now+300}, SECRET, HS256)` | After AIM verifies the caller's PIN locally (Argon2id), it mints a step-up via the monolith's `/firewall/step-up` (or in-proc if co-located) and attaches it as `X-Step-Up` on the execute call. |
| **Step-up verify** | `firewall.verify_step_up_token(...)` asserts signature+exp+type+scope **AND `sub == authenticated caller`** (G3/F3: a leaked tenant-A token is NOT replayable by tenant-B → 403 "step-up identity mismatch") | The monolith adapter endpoints re-verify on execute — defense in depth; AIM never the only gate. |
| **Action→scope map** | `firewall.classify(action)` → `spend` \| `destructive` \| `""` | AIM's risk table (§2) is the *authoritative pre-filter*; it must **converge to the same scope vocabulary** so the downstream `require_step_up(scope)` recognizes it. |
| **Spend hold/settle** | `wallet.reserve(tenant, amount_minor, resource_type, resource_id, idem_key)` → hold_id\|None (atomic conditional UPDATE, no oversell); `wallet.settle(hold_id, actual, idem_key)`; `wallet.release(hold_id)`; `wallet.balance(tenant)` | AIM's CostGuard estimates → reserves before a billable execute → settles actual after → releases on fail. Money in **integer paise**, never float. |
| **Immutable audit** | `audit.record(actor, action, object_type, object_id, channel, meta)` → append-only `var/audit_log.jsonl` **+ mirrored to the P1 Postgres `events` table** (the immutable leg; JSONL rotates) | Every AIM command/decision writes here. Money-mutating rows ride **inside the wallet txn** as `wallet_transactions.meta` (F2: a JSONL append can't be atomic with a PG COMMIT). |
| **Identity/JWT** | `auth.issue_pair(tenant)`, `auth.resolve_token(cred)`, role model (`role`, `is_admin`) | AIM mints a short-lived tenant access token for the verified caller and acts as that tenant for every adapter call — never an anonymous "system" identity. |
| **RLS** | P1 admin-GUC policy: `USING/WITH CHECK (current_setting('app.is_admin',true)='1' OR tenant_id=current_setting('app.tenant_id',true))`; per-txn `SET LOCAL app.tenant_id`/`app.is_admin` | The `ai_manager_*` tables use the **identical** shape (§0.3, §7). |
| **LLM** | Groq round-robin (`GROQ_API_KEY_1..N`), OpenAI-compatible chat, JSON-mode capable | The NLU provider (§1). Claude optional. `none` → deterministic stub. |

### 0.2 The existing thin `/ai-manager` router is ABSORBED, not duplicated
A thin `/ai-manager` module is already mounted in `caller.py` (flag `FEATURE_AI_MANAGER` default OFF):
7 routes (`/numbers`, `/numbers/lookup`, `/numbers/{id}/verify|grants|revoke`, `/sessions`, `/status`),
tenant **token-derived** (never body), sessions persisted as JSONL on the control plane, no PG/DDL. The
dedicated service **supersedes** it:
- The router's `numbers` registry becomes the dedicated service's **`ai_manager_authorized_users`** table
  (PG, RLS) — phone/role/grants migrate 1:1; `pin_hash` is **upgraded from the firewall's tenant-level
  salted-sha256 to per-user Argon2id** (§4).
- The router's `sessions` JSONL becomes **`ai_manager_sessions`** (PG, RLS).
- The two SERVICE-TOKEN routes (`/numbers/lookup`, `POST /sessions`) the voice worker calls are
  re-pointed at the dedicated service's API; the monolith router can stay mounted (dormant) as a thin
  shim or be retired once the service owns the data. **Migration:** a one-shot `aim_migrate_numbers.py`
  reads the JSONL, re-hashes nothing (PINs were tenant-level in firewall, not per-number — so each
  migrated user starts `pin_hash=NULL` → must (re)set a PIN on first risky action). No silent re-use of a
  weaker hash.

### 0.3 Schema this service owns (`ai_manager_*`, FORCED RLS) — master spec §8, recited for the security design
The six tables from master spec §8 are created by this service's own migration with the **P1 admin-GUC RLS
shape** on all six (the columns load-bearing for THIS doc are bolded):
- `ai_manager_profiles` — per-vendor policy: `require_pin_for_level`, **`daily_spend_limit`**,
  **`monthly_spend_limit`**, **`max_bulk_leads_without_pin`**, **`allowed_call_start_time`**,
  **`allowed_call_end_time`**, **`timezone`**, enabled, ai_manager_phone_number, language_preference.
- `ai_manager_authorized_users` — **`normalized_phone_number`**, **`role`**, **`permissions`(jsonb)**,
  **`pin_hash`** (Argon2id, nullable), **`pin_set_at`**, **`failed_pin_attempts`**, **`locked_until`**,
  is_active.
- `ai_manager_sessions` — channel, caller_phone, status, transcript_text, providers, metadata.
- `ai_manager_commands` — **`detected_intent`**, **`action_type`**, **`action_payload`(jsonb)**,
  **`risk_level`**, **`status`**, **`confirmation_required/_status`**, **`pin_required/_verified`**,
  **`permission_result`(jsonb)**, **`cost_estimate`(jsonb)**, `execution_result`(jsonb), `error_message`,
  **`idempotency_key`**.
- `ai_manager_audit_logs` (immutable) — event_type, severity, message, metadata.
- `ai_manager_action_runs` (async) — action_type, target_module, status, job_id, input/output/error.

---

## 1. NLU — system prompt + strict JSON schema + provider call

### 1.1 The contract (non-negotiable invariants)
The NLU's ONLY job is **classify + extract + summarize**. It **never executes, never authorizes, never
decides risk-final, never invents data.** It emits ONE JSON object conforming to §1.2. The deterministic
`PolicyEngine` (§3) + `classify_risk` (§2) are the sole authorities; the model's `risk_level`,
`requires_pin`, `safe_to_execute` are **advisory only** — recomputed and overridden by code (master spec
§22, §27 "never trust LLM output without validation").

### 1.2 Strict output JSON schema (master spec §22, expanded for validation)
```jsonc
{
  "intent": "string",              // dotted intent from the CLOSED enum §2 (e.g. "campaign.update_budget")
  "action_type": "string",         // the engine action_type the intent maps to (e.g. "ads.set_budget")
  "confidence": 0.0,               // 0..1; < CONF_MIN (0.55) -> force clarify, never execute
  "risk_level": "L0|L1|L2|L3|L4",  // ADVISORY — recomputed by classify_risk(); model cannot lower it
  "requires_confirmation": false,  // ADVISORY
  "requires_pin": false,           // ADVISORY
  "entities": {                    // extracted slots; ONLY from utterance/ctx, never invented
    "campaign_ref": null,          // name/id as SPOKEN; resolver matches to ctx.active_campaigns (may be ambiguous)
    "platform": null,              // "meta"|"google"|null
    "amount_minor": null,          // INTEGER paise; "500 rupees" -> 50000; never a float, never guessed
    "currency": "INR",
    "lead_segment": null,          // "hot"|"warm"|"cold"|"not_interested"|null
    "lead_ref": null,              // a single named lead, if any
    "count": null,                 // explicit count if the user gave one
    "channel_target": null,        // "whatsapp"|"sms"|null (for send_report)
    "destination": null,           // phone/email for export/send — flagged high-risk if external
    "schedule_time": null,         // ISO-ish or "after 5 PM" normalized to tenant tz
    "date_ref": null,              // "today"|"tomorrow"|"kal"|ISO date
    "workflow_spec": null,         // for workflow.create_draft: {trigger, steps:[...]}
    "creative_spec": null,         // for creative.*: {type, count, subject, variant}
    "note_text": null              // for lead.add_note
  },
  "missing_fields": [],            // REQUIRED slots absent for this action_type (drives the clarify question)
  "assumptions": [],               // anything the model inferred (e.g. "assumed platform=meta") — surfaced to user
  "user_facing_summary": "string", // short Hinglish-ok readback the agent will speak BEFORE acting
  "safe_to_execute": false,        // ALWAYS false from the model; only PolicyEngine flips the real gate
  "block_reason": null             // non-null ONLY for always-block items §2.3 (the model's first-line refusal hint)
}
```
**Validation (code, after every model call):** parse JSON (JSON-mode); assert `intent ∈ CLOSED_ENUM` and
`action_type ∈ ACTION_ENUM` else `intent="clarify"`; coerce `amount_minor` to int paise or null (reject
floats); drop any `entities` key not in the schema; recompute `risk_level` via `classify_risk(action_type,
entities)` (§2) and **ignore the model's value**; if `confidence < 0.55` or `missing_fields` non-empty →
route to `clarify` (never execute). A malformed/garbage response → `{"intent":"clarify"}`, never an action.

### 1.3 System prompt (verbatim, shipped as `nlu/system_prompt.txt`)
```
You are the NLU unit of an AI Manager that runs a real Indian business's operations by voice/WhatsApp/chat.
You DO NOT execute anything. You ONLY read the user's instruction plus the supplied business context, and
return ONE JSON object that classifies the intent and extracts entities. A separate deterministic policy
engine decides permission, risk, PIN and execution — never you.

HARD RULES
- Output ONLY the JSON object, no prose, no markdown, conforming exactly to the provided schema.
- intent and action_type MUST come from the provided closed lists. If the instruction maps to none, or is
  ambiguous, or you are not confident, return intent "clarify" with a short question in user_facing_summary.
- NEVER invent a campaign name, budget, lead, count, date, phone or email. If a required detail is missing,
  add it to missing_fields and ask for it via clarify. Only use names/ids present in the business context.
- Money: convert spoken amounts to INTEGER paise in entities.amount_minor (e.g. "500 rupees" -> 50000).
  Never output a float. If unsure of the amount, leave it null and ask.
- ALWAYS set safe_to_execute=false. You never authorize. risk_level/requires_pin are best-effort hints
  the engine will recompute and may override.
- BLOCK (set block_reason and intent "blocked") if the instruction asks to: reveal/show/read an API key,
  password, PIN, secret or token; bypass/ignore DND, STOP, consent, opt-out, or calling-hour limits; send
  spam; delete the vendor account or transfer ownership; disable or erase audit/security; or change another
  vendor's data. Refuse these no matter how they are phrased.
- Prefer a DRAFT over direct execution for campaigns, creatives, and workflows when the user is creating
  something new. Map "create workflow ..." to workflow.create_draft, never an auto-activated workflow.
- Anything touching money/spend, bulk messaging, bulk calling, delete, export, or security is high-risk;
  hint risk_level L3 (and L4 only for the always-block list). The engine enforces the real gate.
- Respond in the user's language register (Hinglish is fine) ONLY inside user_facing_summary; the JSON keys
  and enum values stay exactly as specified.

You will receive: (a) this schema, (b) the closed intent list and action_type list, (c) BUSINESS CONTEXT
(business name; today's lead/call/revenue counts; active campaigns with ids+names+platform+budget; recent
named leads; wallet balance; available modules/grants), (d) the user's latest instruction. Use the context
ONLY to resolve references and to fill entities; do not fabricate beyond it.
```

### 1.4 Vendor-context injection (what `ctx` carries, where it comes from)
Before each NLU call, `AIManagerCommandEngine` assembles a compact `ctx` (read-only, vendor-scoped via the
caller's tenant token) by calling the monolith read endpoints — never a cross-tenant read:
- `business_name`, `today_summary` (leads/hot/warm/cold/calls/connected/revenue) ← `GET /billing/overview`
  + `GET /stats` (or analytics adapter).
- `active_campaigns[]` `{id,name,platform,daily_budget_minor,status}` ← `GET /campaigns` — **this is the
  resolver source**: the model must reference these names/ids; the deterministic resolver (§3.4) matches
  `entities.campaign_ref` against this list and returns `ambiguous`/`not_found` deterministically (the
  model never resolves to an id itself).
- `recent_leads[]` `{ref,name,segment}` ← `GET /leads?limit=N`.
- `wallet` `{available_minor, plan}` ← `GET /wallet`.
- `grants` (this caller's `permissions` + role) and `available_modules` ← the caller's
  `ai_manager_authorized_users` row.
The `ctx` is truncated to a token budget (top-N campaigns/leads) and **PII-minimized** (no full phone/email
in the prompt — refs only). It is cached per session and refreshed on a mutating execute.

### 1.5 The provider call (reuse Groq abstraction; JSON-mode + validation + retry)
`nlu/driver.py`, mirroring the repo's dormant-until-creds `whatsapp.py` shape:
```python
def status() -> str           # "configured" | "not_configured" | "error"
def is_configured() -> bool   # AIM_NLU_PROVIDER in {groq,claude} AND its key present
def parse(utterance: str, ctx: dict) -> dict   # returns a VALIDATED schema-§1.2 object; NEVER raises
```
- **provider=groq** (default when keyed): OpenAI-compatible chat completion with
  `response_format={"type":"json_object"}` (JSON-mode), `temperature=0` (deterministic classification),
  system=§1.3, user = schema + closed lists + `ctx` + utterance + the few-shot block (§1.6). Round-robin
  the `GROQ_API_KEY_1..N` pool already supported in the repo.
- **provider=claude** (optional, harder reasoning): `claude-opus-4-8`, structured output via
  `output_config.format` bound to the §1.2 schema, manual tool-use NOT used (pure extraction); per the
  in-repo claude-api note **no `temperature`/`top_p`/`budget_tokens` on Opus 4.8**.
- **provider=none** (offline / dormant): deterministic keyword+regex matcher over the CLOSED enum (extracts
  rupee→paise, segment, channel, date) — the offline-test path; off-enum/low-confidence → clarify.
- **Validation + retry loop:** call → parse JSON. On (a) JSON parse failure, (b) schema-key violation, or
  (c) `intent ∉ enum` → **retry once** with an appended corrector message ("Your previous reply was not
  valid JSON / used an unknown intent. Return ONLY the schema object."). Second failure →
  `{"intent":"clarify","user_facing_summary":"Sorry, I didn't catch that — could you say it again?"}`.
  **Never** surface a raw model error or execute on an unvalidated object. After validation, **always**
  recompute risk (§2) and run PolicyEngine (§3) — the model output is input, not authority.

### 1.6 Few-shot examples (cover the master-spec §23 sample commands)
Shipped as `nlu/fewshots.jsonl` (utterance → expected validated object). One example per intent family;
the full set covers every §23 command. Representative rows (paise-correct, draft-preferred, block-aware):

| Utterance (§23) | intent | action_type | key entities | model risk hint | gate (recomputed) |
|---|---|---|---|---|---|
| "Aaj ka report WhatsApp kar do" | `analytics.send_report` | `analytics.send_report` | channel_target=whatsapp, date_ref=today | L1 | confirm-only (no PIN; PIN only if external dest) |
| "How many hot leads today?" | `analytics.lead_summary` | `analytics.read` | lead_segment=hot, date_ref=today | L0 | execute (read, no gate) |
| "Meta budget 500 kar do" | `campaign.update_budget` | `ads.set_budget` | platform=meta, amount_minor=50000, campaign_ref=<from ctx or missing> | L3 | **PIN (spend)** + confirm |
| "Stop campaigns spending but no leads" | `campaign.kill_losers` | `ads.pause_campaign` (bulk) | (selector: high-spend/no-conv) | L3 | confirm + PIN (bulk pause) |
| "Create 5 video ads for Satellite 2BHK" | `creative.generate_video` | `creative.generate_video` | creative_spec={type:video,count:5,subject:"Satellite 2BHK"} | L1 | draft/job create (no PIN; **launch** later is the gated step) |
| "Launch low budget test campaign tomorrow" | `campaign.create_draft` then `campaign.launch` | `campaigns.create` (draft) / `campaigns.launch` | date_ref=tomorrow | L3 on launch | draft = L1; **launch = PIN (spend)** |
| "Call all hot leads after 5 PM" | `lead.call_hot` | `leads.enqueue_calls` (bulk) | lead_segment=hot, schedule_time=17:00 | L3 | compliance(hours/DND) + cost estimate + **PIN (bulk)** |
| "Send brochure to all warm leads" | `whatsapp.send_brochure` | `whatsapp.send` (bulk) | lead_segment=warm | L3 | DND/consent + **PIN (bulk)** |
| "Workflow: hot lead → brochure → 2h → call" | `workflow.create_draft` | `workflow.create_draft` | workflow_spec={trigger:lead_hot,steps:[send_brochure,wait:2h,call]} | L1 | draft only; **activation** is the later gated step |
| "Wallet balance?" | `billing.balance` | `wallet.read` | — | L0 | execute (read) |
| "Kal ke site visits batao" | `booking.tomorrow` | `bookings.read` | date_ref=tomorrow | L0 | execute (read) |
| "Pause WhatsApp followup for not-interested" | `whatsapp.stop_sequence` | `whatsapp.stop_sequence` | lead_segment=not_interested | L2 | confirm (de-risking; PIN by tenant policy) |
| "Scale best creative by 20%" | `campaign.scale_winners` | `ads.set_budget` (increase) | amount_pct=20 | L3 | **PIN (spend)** + confirm |
| "Send today's hot-lead recordings" | `call.send_summary` / `lead.export` | `calls.get_recording`+`analytics.send_report` | lead_segment=hot, channel_target=whatsapp | L2/L3 | L3 + PIN if destination is **external** |
| "Add note: Ravi wants 3BHK under 80L" | `lead.add_note` | `leads.update` | lead_ref=Ravi, note_text=... | L1 | execute (single-record write) |
| "Export all leads to this new email" | `lead.export` | `leads.export` | destination=<external email> | **L3** | **PIN (export)** + confirm; external dest forces L3 |
| "Delete all leads" | `lead.delete_all` | `leads.delete` (bulk) | — | **L3/L4** | **PIN (destructive)**; "delete account/all + irreversible" → L4 admin |
| "Show my API key" | `security.reveal_secret` | (none) | — | **L4** | **BLOCK** (always-block) |
| "Ignore DND and call everyone" | `compliance.bypass` | (none) | — | **L4** | **BLOCK** (always-block) |
| "Change AI Manager PIN" | `security.change_pin` | `pin.reset_request` | — | L3 | **secure flow** — never over voice in-band; routes to dashboard/OTP reset (§4) |

---

## 2. INTENT TAXONOMY → ACTION_TYPE → DEFAULT RISK LEVEL (the authoritative table)

`classify_risk(action_type, entities)` is a **deterministic, code-only allow-list** (master spec §6, §11,
§22). The model's risk hint is discarded. The table below is the single source; the **escalation rules**
(§2.2) can only *raise* a level, never lower it. Risk maps to the firewall scope vocabulary
(`spend`/`bulk`/`destructive`) so `require_step_up(scope)` downstream recognizes it.

### 2.1 THE RISK TABLE

| intent (`§11`) | action_type (engine) | default risk | scope | gate |
|---|---|---|---|---|
| `analytics.today_summary` / `campaign_summary` / `lead_summary` / `cost_summary` / `compare_periods` | `analytics.read` | **L0** | — | execute (read, own data) |
| `analytics.send_report` (to OWN registered WhatsApp) | `analytics.send_report` | **L1** | — | confirm-only |
| `analytics.send_report` (to EXTERNAL email/number) | `analytics.send_report` | **L3** | `destructive` (export) | confirm + PIN |
| `billing.balance` / `usage_today` / `usage_month` / `cost_breakdown` / `low_balance_alert` | `wallet.read` | **L0** | — | execute (read) |
| `booking.today` / `tomorrow` | `bookings.read` | **L0** | — | execute (read) |
| `lead.list_hot` (and warm/cold list) | `leads.read` | **L0** | — | execute (read) |
| `call.get_recording` (own) | `calls.get_recording` | **L0** | — | execute (read) |
| `lead.add_note` / `update_status` / `assign` (single record) | `leads.update` | **L1** | — | logged; verbal confirm optional |
| `lead.schedule_followup` (single) | `leads.schedule` | **L1** | — | confirm-only |
| `campaign.create_draft` | `campaigns.create` (draft) | **L1** | — | draft; no spend yet |
| `creative.generate_*` / `create_asset_pack` | `creative.generate_*` | **L1** | — | async job create; no spend |
| `workflow.create_draft` / `update` (draft) | `workflow.create_draft` | **L1** | — | DRAFT only — never auto-activate |
| `campaign.update_copy` | `campaigns.update_copy` | **L1** | — | confirm-only |
| `whatsapp.send_brochure`/`send_followup` to a SELECTED small set (≤ `max_bulk_leads_without_pin`) | `whatsapp.send` (limited) | **L2** | — | confirm; PIN by tenant policy |
| `call.call_single_lead` | `leads.enqueue_calls` (n=1) | **L2** | — | compliance check + confirm |
| `call.stop_queue` / `retry_failed` | `calls.control` | **L2** | — | confirm |
| `workflow.activate` (low-impact) / `pause` / `run_now` | `workflow.activate` | **L2** | — | confirm; PIN by tenant policy |
| `booking.create` / `reschedule` / `cancel` / `send_reminder` | `bookings.write` | **L2** | — | confirm |
| `campaign.resume` | `campaigns.resume` | **L2** | — | confirm (re-enables spend → policy may force PIN) |
| `whatsapp.stop_sequence` | `whatsapp.stop_sequence` | **L2** | — | confirm (de-risking) |
| **`campaign.update_budget` (increase)** | `ads.set_budget` | **L3** | `spend` | **PIN** + confirm + wallet/cap check |
| **`campaign.launch`** | `campaigns.launch` | **L3** | `spend` | **PIN** + confirm + wallet/cap check |
| **`campaign.scale_winners`** (budget up) | `ads.set_budget` | **L3** | `spend` | **PIN** + confirm |
| **`campaign.pause` (ALL) / `kill_losers` (bulk)** | `ads.pause_campaign` (bulk) | **L3** | `destructive` | **PIN** + confirm |
| **`lead.call_hot` / `call.start_bulk`** (mass) | `leads.enqueue_calls` (bulk) | **L3** | `bulk` | compliance + cost est + **PIN** + confirm |
| **`whatsapp.send_bulk`** (broadcast) | `whatsapp.send` (bulk) | **L3** | `bulk` | DND/consent + **PIN** + confirm |
| **`lead.export`** | `leads.export` | **L3** | `destructive` | **PIN** + confirm (external dest mandatory PIN) |
| **`lead.delete_*` (bulk) / data delete** | `leads.delete` | **L3** | `destructive` | **PIN** + confirm |
| **billing settings / plan change** | `billing.write` | **L3** | `destructive` | **PIN** + confirm |
| **team perms / role change** | `users.write` | **L3** | `destructive` | **PIN** + confirm |
| **wallet top-up / any external spend** | `wallet.topup` / ads spend | **L3** | `spend` | **PIN** + confirm + balance check |
| `workflow.activate` (HIGH-impact: spend/bulk steps) | `workflow.activate` | **L3** | `spend`/`bulk` | **PIN** + confirm |
| **delete vendor account / transfer ownership** | — | **L4** | — | **BLOCK → human admin** |
| **reveal secrets/keys/PIN** | — | **L4** | — | **BLOCK** |
| **bypass DND/STOP/consent/calling-hours; spam** | — | **L4** | — | **BLOCK** |
| **disable/erase audit; remove security; spend over hard limit** | — | **L4** | — | **BLOCK** |

### 2.2 Escalation rules (code, applied AFTER the table — can only RAISE)
1. **Money present** (`action_type ∈ {ads.set_budget, campaigns.launch, wallet.topup}` OR any external
   spend) → **min L3, scope `spend`**.
2. **Bulk threshold** — `leads.enqueue_calls`/`whatsapp.send` where target count >
   `profiles.max_bulk_leads_without_pin` → **min L3, scope `bulk`** (a "send to 3 selected" stays L2; a
   broadcast crosses to L3 deterministically by count, not by the model's word "bulk").
3. **Delete / mass-pause / suppression mass-add** → **min L3, scope `destructive`**.
4. **Export OR any external destination** (email/phone not the caller's own registered number) → **min L3,
   scope `destructive`**; if the destination is a brand-new external address → mandatory PIN, never
   "confirm-only".
5. **Security-sensitive** (reveal secret/key/PIN, bypass compliance, delete account, transfer ownership,
   disable audit, spend over the tenant hard limit) → **L4 BLOCK** (§2.3) — no PIN can unlock it over the
   AIM channel.
6. **`require_pin_for_level` policy** — a tenant may set their profile to require PIN from L2 (stricter);
   the engine takes `max(table_level, policy_floor)`. It can tighten, never loosen below the table.

### 2.3 THE ALWAYS-BLOCK LIST (L4 — refuse on every channel, no PIN unlocks them)
These are refused by both the NLU (first-line `block_reason`) **and** the PolicyEngine (final authority);
neither a correct PIN nor an admin role over the AIM voice/chat channel can execute them. They require a
human admin acting in the dashboard with its own controls.
1. **Reveal / read / "show me" any secret** — API key, provider key, password, PIN, JWT/token, `var/secret`,
   webhook signing secret, another user's credentials.
2. **Bypass / ignore / disable compliance** — call past DND, contact a STOP/opt-out/suppressed lead,
   ignore consent, override calling-hours, "call everyone anyway".
3. **Spam** — unsolicited bulk to non-consented numbers; "message every number you can find".
4. **Delete the vendor account / transfer ownership / change the owner**.
5. **Disable, clear, or tamper with the audit log or security controls** (firewall, RLS, lockout, PIN
   policy) — including "turn off the PIN", "stop logging this".
6. **Act on another vendor's data** — any cross-tenant read/write (also structurally impossible under RLS;
   blocked here as a first line + tested in §7).
7. **Spend above the tenant hard ceiling** — a single action exceeding `daily_spend_limit` /
   `monthly_spend_limit` outright (not merely needing PIN — refused; raising the ceiling is a dashboard
   admin action).
8. **Self-modify safety** — change `require_pin_for_level` downward, lengthen lockout bypass, or alter the
   risk table from the voice/chat channel.

Every always-block hit writes `audit.record(action="aimanager.blocked", severity="warn",
meta={reason, intent, redacted_utterance})` and speaks a CAN-DO redirect ("I can't do that — but I can
send you today's report or queue your hot-lead calls").

---

## 3. THE PolicyEngine DECISION FUNCTION

`AIManagerPolicyEngine.decide(ctx) -> Decision` is **pure, deterministic, side-effect-free** (it reads;
it does not execute). It is the single chokepoint every command passes through after NLU validation. The
adapter layer also re-checks downstream (defense in depth) — the engine is never the *only* gate.

### 3.1 Inputs
```python
@dataclass
class PolicyInput:
    vendor_id: str            # tenant, token-derived (NEVER from NLU/body)
    user_id: str | None       # the authorized_users row id resolved from caller phone
    role: str                 # admin | manager | operator (the user's role)
    permissions: dict         # the user's per-user grants jsonb (module allow-list)
    action_type: str          # validated, from ACTION_ENUM
    risk_level: str           # recomputed by classify_risk (§2) — NOT the model's
    scope: str                # "spend"|"bulk"|"destructive"|"" (firewall vocabulary)
    cost_estimate_minor: int  # 0 for non-billable; else CostGuard estimate (paise)
    wallet_available_minor: int
    daily_spend_used_minor: int; daily_spend_limit_minor: int
    monthly_spend_used_minor: int; monthly_spend_limit_minor: int
    target_count: int         # for bulk: number of leads/messages
    max_bulk_without_pin: int
    compliance: ComplianceResult   # from §5 (hours_ok, dnd_ok, stop_ok, consent_ok, blocked_refs)
    require_pin_for_level: str     # tenant policy floor ("L2"/"L3")
    is_always_block: bool          # §2.3 hit
```

### 3.2 Output
```python
@dataclass
class Decision:
    outcome: str        # "allow" | "confirm" | "pin" | "block"
    scope: str          # step-up scope to demand if outcome=="pin"
    reason: str         # machine reason code (for audit + spoken redirect)
    user_message: str   # short Hinglish-ok line the agent speaks
    needs_confirmation: bool
    cost_estimate_minor: int
```

### 3.3 The decision logic (exact order — first match wins; fail-CLOSED)
```
1. ALWAYS-BLOCK:   if is_always_block OR risk_level == "L4":
                       return block(reason="always_block:<rule>")               # §2.3
2. PERMISSION:     if not permits(role, permissions, action_type):              # role-family AND per-user grant
                       return block(reason="not_permitted")                      # default-DENY on unknown action
3. COMPLIANCE:     if action touches outreach (call/whatsapp) and not compliance.all_ok():
                       return block(reason="compliance:<hours|dnd|stop|consent>") # NEVER PIN-overridable (§5)
4. SPEND CEILING:  if cost_estimate_minor > 0:
                       if daily_spend_used+cost > daily_spend_limit
                          OR monthly_spend_used+cost > monthly_spend_limit:
                              return block(reason="over_spend_limit")            # hard ceiling = block, not PIN
                       if cost_estimate_minor > wallet_available_minor:
                              return block(reason="insufficient_credit")         # tell vendor, offer top-up
5. BULK FLOOR:     if scope=="bulk" and target_count > max_bulk_without_pin:
                       risk_level = max(risk_level, "L3")                        # escalate (mirrors §2.2.2)
6. RISK FLOOR:     effective = max(risk_level, require_pin_for_level)            # tenant policy can tighten
7. GATE BY LEVEL:
       L0          -> allow(needs_confirmation=False)                            # read-only
       L1          -> allow(needs_confirmation=verbal_confirm_for_writes)        # logged write, light confirm
       L2          -> confirm(needs_confirmation=True)                           # explicit yes/no; PIN iff policy floor==L2
       L3          -> pin(scope=scope or default_scope(action_type),
                          needs_confirmation=True)                               # PIN AFTER confirm read-back
8. DEFAULT:        return block(reason="unclassified")                          # fail-closed: anything unmatched is blocked
```
**Invariants:** (a) money/bulk/destructive/export/security can never resolve to `allow`; (b) a hard spend
ceiling or a compliance violation returns `block`, **never** `pin` (you can't PIN your way past DND or a
hard cap); (c) unknown action/role/grant → `block` (default-deny); (d) the engine **recomputes** risk and
cost — it never trusts a model-supplied `safe_to_execute`/`requires_pin`; (e) PIN is demanded **after** the
spoken confirmation read-back (master spec §7), and the resulting step-up is fresh, scoped, 300 s, one per
risky action.

### 3.4 Deterministic reference resolution (so the model never resolves authority-bearing ids)
`resolve_campaign(entities.campaign_ref, ctx.active_campaigns)` → `{matched_id}` | `ambiguous(candidates)`
| `not_found`. On `ambiguous`/`not_found` the engine returns a **clarify** (not block, not execute) — "Aapke
do 2BHK campaigns hain — Urban Nest ya Satellite? Konsa?". Budgets, counts, destinations are taken from
`entities` only after the same null/format checks (no float money, no invented count). This keeps the LLM
out of the "which exact campaign gets the ₹1500" decision.

---

## 4. PIN SECURITY (Argon2id; set/verify/reset; rate-limit + lockout)

> **Conformance delta (deliberate, stated):** master spec §3.9 mandates **Argon2/bcrypt** for the PIN. The
> monolith `firewall.py` today hashes the *tenant-level* PIN as salted-sha256. This dedicated service owns a
> **per-authorized-user** PIN in `ai_manager_authorized_users.pin_hash` and uses **Argon2id** — the
> stronger, spec-mandated scheme — for *its* PINs. It still reuses `firewall.mint_step_up` to mint the
> cross-service authorization token AFTER its own Argon2id verify succeeds (the token is a signed assertion
> "this caller proved a PIN", not the PIN itself). Two PIN stores by design: firewall's tenant PIN (legacy,
> monolith spend gate) and AIM's per-user PIN (Argon2id, the voice/chat caller identity). They never mix;
> the migration (§0.2) starts every AIM user at `pin_hash=NULL`.

### 4.1 Hashing — Argon2id parameters (library: `argon2-cffi`, `PasswordHasher`)
PINs are short (4 or 6 digits → ≤ 10^6 keyspace), so **lockout is the primary defense and the KDF cost is
the backstop** against an offline `pin_hash` dump. Parameters (OWASP-aligned, server-side ~50–100 ms):
```
type        = Argon2id
time_cost   = 3            # iterations
memory_cost = 65536        # 64 MiB
parallelism = 2
hash_len    = 32
salt        = 16 bytes, CSPRNG, unique per user (argon2-cffi embeds it in the encoded hash)
pepper      = HMAC-SHA256(server_secret, pin) BEFORE Argon2id   # server_secret = reuse var/secret (auth.py)
encoded     = "$argon2id$v=19$m=65536,t=3,p=2$<salt>$<hash>"     # stored whole in pin_hash
```
- **Pepper:** pre-hash the PIN with `HMAC-SHA256(SECRET, pin)` (SECRET = the existing `var/secret`) before
  Argon2id, so a stolen DB dump without the file-system secret is unusable. Pepper is NOT in the DB.
- **Verify** uses `PasswordHasher.verify` (constant-time inside argon2-cffi) + `ph.check_needs_rehash` to
  transparently upgrade parameters on a correct login.
- The raw PIN exists only transiently in memory for the verify call; it is `del`'d immediately, **never
  logged, never returned, never put in a transcript/session/audit row** (audio hygiene in §6/master §7.5
  belongs to the voice wave — this doc owns the text/store hygiene).

### 4.2 Flows
**set / change (`POST /pin/set`)** — caller authenticated (tenant token), self only. Body `pin` (validated
4–6 digits, reject sequential/repeated like `0000`,`1234`,`123456` as a UX warning, not a hard block).
`pin_hash = argon2(pepper(pin))`, `pin_set_at = now()`, `failed_pin_attempts = 0`, `locked_until = NULL`.
Audited `aimanager.pin.set` (NO value). A change requires the *current* PIN OR a dashboard/OTP reset (§4.4).

**verify (`POST /pin/verify`, and internally at S6 step-up)** — never exposes raw:
```
if locked_until and now() < locked_until:           -> {ok:false, locked:true}      # short-circuit, no hash work
ok = argon2.verify(pin_hash, pepper(pin))           # constant-time; exception on mismatch caught -> ok=false
if ok:
    failed_pin_attempts = 0; locked_until = NULL
    if check_needs_rehash: pin_hash = re-encode      # transparent param upgrade
    step_up = POST monolith /firewall/step-up (as this tenant, scope) -> X-Step-Up token (sub==caller)
    audit("aimanager.pin.ok"); return {ok:true, step_up_token}
else:
    failed_pin_attempts += 1
    if failed_pin_attempts >= MAX_PIN_ATTEMPTS(5):   # config; voice default 3 (master §7), dashboard 5
        locked_until = now() + LOCKOUT_TTL            # exponential: 60s,5m,30m by lock-count
    audit("aimanager.pin.fail", meta={attempts, locked: bool})
    return {ok:false, attempts_left: MAX-failed}
```
- **Rate-limit** additionally via the monolith's redis token bucket (`ratelimit.py`, redis:6380) keyed by
  `aim:pin:{vendor}:{user}` AND by `caller_phone`, so a spoofed caller-id can't grind PINs across users.
- **Lockout** is authoritative in `ai_manager_authorized_users.{failed_pin_attempts, locked_until}` (the
  DB row, RLS-scoped) — not an in-memory counter that resets on restart. A locked user is told "too many
  attempts, locked for N minutes; reset from the dashboard" and **no business data is revealed**.
- **Never** reveal whether the *user* exists vs the *PIN* is wrong (uniform "PIN didn't match") to avoid
  user-enumeration.

**reset (`POST /pin/reset/request` → `POST /pin/reset/confirm`)** — master spec: *reset only via secure
dashboard or OTP*. No PIN reset is ever done in-band over a voice call (a caller who forgot the PIN cannot
talk their way to a new one). `reset/request` (dashboard, authenticated, or admin-for-user) issues an OTP
to the *registered* contact via the monolith OTP path (Twilio/MSG91/WA, dormant→ admin-mediated);
`reset/confirm` verifies the OTP then sets a new PIN (§4.2 set). An admin may force-reset another user's PIN
from the dashboard (audited, both-ends), which clears `pin_hash` → the user must set a fresh PIN. All reset
events audited (`aimanager.pin.reset.request/confirm`), value never logged.

### 4.3 Config
`AIM_PIN_MAX_ATTEMPTS` (default 5; voice channel passes 3), `AIM_PIN_LOCKOUT_BASE_S` (60),
`AIM_PIN_LOCKOUT_MAX_S` (1800), `AIM_ARGON_TIME_COST` (3), `AIM_ARGON_MEMORY_KIB` (65536),
`AIM_ARGON_PARALLELISM` (2). All have safe defaults; nothing required to pass the offline test.

### 4.4 What the PIN does and does NOT prove
A passing PIN mints a **step-up** (fresh, scoped, 300 s) authorizing **one** risky action. It is NOT a
login (the login = the tenant access token from caller-identity + the S2 voice/session auth). One PIN never
silently authorizes ten budget bumps (master spec §6.2 / §7). The step-up `sub` is bound to the caller
(F3); the monolith re-verifies on execute.

---

## 5. COMPLIANCE GATE (calling hours, DND, STOP, consent)

`compliance.check(action_type, target_refs, ctx) -> ComplianceResult` runs **before** any outreach execute
and its failures are **never PIN-overridable** (master spec §6 L4 "bypass compliance" is always-block).
Reuses the monolith's existing leads/run-path compliance (DND/suppression + calling-window + consent) — AIM
does not re-implement the lists, it calls the gate and refuses on a violation.
```python
@dataclass
class ComplianceResult:
    hours_ok: bool        # now (tenant tz) within [allowed_call_start_time, allowed_call_end_time]
    dnd_ok: bool          # none of target_refs on the DND registry
    stop_ok: bool         # none have sent STOP / opt-out keyword
    consent_ok: bool      # all have a consent-ledger entry where required
    blocked_refs: list    # the specific leads filtered out
    def all_ok(self): return hours_ok and dnd_ok and stop_ok and consent_ok and not blocked_refs
```
- **Calling hours:** `allowed_call_start_time`/`end_time` + `timezone` from `ai_manager_profiles`. A command
  "call all hot leads" at 9 PM with a 6 PM cutoff → the engine either **schedules** for the next allowed
  window (if the user said "after 5 PM" and 5 PM is inside the window) or refuses with a spoken reason. A
  scheduled-for-allowed-window job is a normal L3 bulk action (PIN at command time, executes in-window).
- **DND / STOP / suppression:** target leads are intersected with the suppression + DND + STOP-keyword sets;
  **blocked refs are dropped, never contacted**, and the count is spoken ("42 hot leads — 3 are on DND, so
  39 will be called"). A command that is *only* blocked leads → refuse.
- **Consent ledger:** where consent is required (jurisdiction/channel), a lead without a consent entry is
  dropped from the batch. "Ignore consent / DND" as an instruction is an **always-block** (§2.3), logged.
- **Decision recorded:** every compliance decision (allowed N, blocked M, reason) is written to the command
  row + an `aimanager.compliance` audit event, so the compliance trail is auditable (master spec §7, §21).

---

## 6. AUDIT-LOG EVENT TAXONOMY + IMMUTABILITY

Reuse `audit.record(actor, action, object_type, object_id, channel, meta)` (append-only `var/audit_log.jsonl`
**+ the immutable Postgres `events` leg**). AIM channel = `"ai_manager"`. The verified tenant is **always**
the `actor` — never "system". Master-spec §7 fields ride in `meta` (redacted).

### 6.1 Event types (one per meaningful transition)
| event_type (`action`) | when | severity | key meta (redacted) |
|---|---|---|---|
| `aimanager.session.start` | inbound call/chat opens | info | channel, caller_phone(redacted), provider_call_id |
| `aimanager.auth.ok` / `.fail` | caller PIN/OTP at session login | info / warn | method, attempts |
| `aimanager.lockout` | failed_pin_attempts ≥ max | warn | user_id, locked_until |
| `aimanager.command.parsed` | NLU validated | info | intent, action_type, risk_level, confidence, missing_fields |
| `aimanager.permission.denied` | PolicyEngine block (not_permitted) | warn | role, action_type |
| `aimanager.compliance` | outreach gate ran | info/warn | allowed_n, blocked_n, reason |
| `aimanager.confirm.shown` / `.yes` / `.cancelled` | S7 read-back | info | summary_redacted |
| `aimanager.pin.ok` / `.fail` | per-action step-up | info / warn | scope, attempts (NEVER the value) |
| `aimanager.pin.set` / `.reset.request` / `.reset.confirm` | PIN lifecycle | info | user_id (NEVER value) |
| `aimanager.cost.reserved` / `.settled` / `.released` | CostGuard wallet ops | info | hold_id, estimate_minor, actual_minor |
| `aimanager.execute.start` / `.ok` / `.fail` | adapter call | info / error | action_type, idempotency_key, provider_summary, resource_ids |
| `aimanager.blocked` | always-block (§2.3) | warn | reason, intent, redacted_utterance |
| `aimanager.session.end` | hangup/close | info | outcome, n_actions, duration |

### 6.2 Immutability rules (which are tamper-evident, and how)
- **All AIM events are append-only.** No update/delete path exists in the service; the `ai_manager_audit_logs`
  table grants `famit_app` only `SELECT, INSERT` (no UPDATE/DELETE), FORCE-RLS, matching the wallet pattern.
- **The immutable leg is Postgres `events`** (the JSONL can rotate / is mutable on disk; the PG `events`
  mirror is the source of truth — verified in F4: firewall/wallet rows landed in PG `events`, append-only,
  RLS-scoped).
- **Money-mutating AIM decisions** (autonomous/voice-initiated spend) write their audit row **inside the
  wallet txn** as `wallet_transactions.meta` (carry actor+action+decision) — a file append cannot be atomic
  with a PG COMMIT (F2). So a charge and its audit can never diverge.
- **Secrets never enter audit:** PIN/OTP values, tokens, keys are categorically excluded; utterances that
  contain a spoken PIN are masked (`"****"`) before the row is written. Reviewed by the §7 test that greps
  the written rows for the test PIN → 0 hits.

---

## 7. TENANT-ISOLATION TEST PLAN (forge tenant B while authed as A → reject)

Master spec §20/§25: every query vendor-scoped; cross-tenant must be impossible. Two enforcement layers are
tested independently so a bug in either is caught: **(L1) token-derived tenant** (the service NEVER reads
`vendor_id` from a body/query — only from the authenticated token, like the existing router) and **(L2)
FORCE-RLS** (`SET LOCAL app.tenant_id` per txn; the DB refuses cross-tenant rows even if app code slips).

### 7.1 Per-endpoint isolation matrix (each row is one test; authed as tenant **A**, attacking **B**)
| Endpoint | Forge attempt | Expected |
|---|---|---|
| `GET /ai-manager/profile` | pass `?vendor_id=B` / body `vendor_id:B` | ignored — returns **A's** profile (tenant from token) |
| `PUT /ai-manager/profile` | body sets `vendor_id:B`, `daily_spend_limit` | writes **A's** row only; B unchanged |
| `GET/POST /ai-manager/authorized-users` | create a user with `vendor_id:B` | created under **A**; never visible to B |
| `PATCH/DELETE /authorized-users/:id` | use an **id that belongs to B** | **404** (RLS hides B's row → not found, no info leak) |
| `POST /pin/set` / `verify` | target a B user id | **404**/forbidden; A cannot set/verify B's PIN |
| `POST /pin/reset/*` | request reset for a B user | **404**; reset only for own/admin-scoped users |
| `GET /sessions` / `/sessions/:id` | id belonging to B | list shows only A; detail **404** for B's id |
| `GET /commands` / `/commands/:id` | B's command id | **404** |
| `POST /commands/:id/confirm` / `/cancel` / `/execute` | B's command id | **404** — cannot drive B's command |
| `POST /commands/test` | body `vendor_id:B` | runs the engine as **A**; ctx loaded for A only |
| `GET /dashboard/summary` / `/audit-logs` / `/action-runs` | `?vendor_id=B` | A's data only; B rows absent |
| `POST /voice/inbound` (webhook) | spoofed caller maps to B's number while session token is A | identity resolves the NUMBER's tenant; a forged token mismatch → reject; signature-verified webhook |
| step-up replay | present **A's** step-up token (sub=A) on a **B** execute | **403 "step-up identity mismatch"** (firewall F3: sub==caller) |

### 7.2 RLS-level probes (run as `famit_app`, the restricted role — DB is the backstop)
For each of the six `ai_manager_*` tables:
1. `SET LOCAL app.tenant_id='A'` → INSERT a row → COMMIT.
2. `SET LOCAL app.tenant_id='B'` → `SELECT * FROM <table>` → **0 rows of A** (and B sees only its own).
3. As B, attempt `UPDATE/DELETE` of A's row by primary key → **0 rows affected** (WITH CHECK + USING block).
4. Without any `app.tenant_id` set → **0 rows** (FORCE-RLS, no default visibility).
5. Admin path: `SET LOCAL app.is_admin='1'` + `app.tenant_id='B'` → an admin op on B succeeds **only**
   when explicitly scoped to B (no superuser connection; mirrors F4 admin-GUC top-up).

### 7.3 Negative control (proves the tests have teeth)
Temporarily disable the token-derivation (read `vendor_id` from body) on a throwaway copy → the §7.1 forge
attempts now **succeed** (cross-tenant) → confirms the test would FAIL a broken build. Restore. (Mirrors the
wallet "negative control" that drove the balance to −16000 to prove the no-oversell test means something.)

### 7.4 Offline-runnable
The full §7.1 token-layer matrix runs against the service with **stub adapters + a throwaway PG schema** (or
the live PG with `vendor_id ∈ {aimtestA, aimtestB}`, rows DELETED after). Zero external creds. The §7.2 RLS
probes need the PG schema applied (`ai_manager_*` DDL) but no LLM/voice/telephony. Wired into CI as the
`test_tenant_isolation.py` gate; a single cross-tenant leak = red build.

---

## 8. BUILD ORDER (each a verifiable unit; this doc is the security+intelligence half)
1. `ai_manager_*` DDL (6 tables, FORCE-RLS admin-GUC) + the §7.2 RLS probe → green before any logic.
2. `classify_risk` table (§2) + escalation rules + always-block list → unit test every §23 command's
   recomputed level (asserts the model's risk is ignored).
3. `PolicyEngine.decide` (§3) pure function → table-driven unit test of every outcome branch (allow/confirm/
   pin/block) incl. fail-closed default + spend-ceiling-blocks-not-PINs.
4. PIN store (Argon2id, §4) — set/verify/lockout/reset → unit test (correct/ wrong/ lockout/ rehash/ no raw
   in store), grep store+audit for the PIN → 0 hits.
5. NLU `driver.py` (§1) — `none` stub first (offline), then groq JSON-mode + validation+retry → schema-
   validation test + the §23 few-shot golden set.
6. Compliance gate (§5) wrapper over the monolith path + audit taxonomy (§6) wired into every transition.
7. `test_tenant_isolation.py` (§7) as the CI gate. Ship 1–4 first: that is the entire deterministic safety
   spine, offline-testable, before any LLM/voice/spend is live.

## 9. CONFORMANCE TO THE MASTER SPEC (traceability)
§6 risk levels → §2 table; §7 security (identity/PIN/authz/confirm/spend/compliance/audit) → §3,§4,§5,§6;
§8 DB models → §0.3; §9 services (NLU/PolicyEngine/AuthService/CostGuard/AuditService) → §1,§3,§4,§5,§6;
§11 intent taxonomy → §2; §22 NLU strict-JSON → §1.2,§1.3; §23 sample commands → §1.6 few-shots + §2 table;
§25 tests → §7 + the per-unit tests in §8. Deltas from existing code, stated and justified: (a) Argon2id
per-user PIN supersedes firewall's tenant-level sha256 (§4 — spec §3.9 mandates Argon2/bcrypt); (b) the thin
`/ai-manager` router's JSONL number/session stores are absorbed into RLS PG tables (§0.2); (c) AIM's risk
table converges to the firewall scope vocabulary so `require_step_up` recognizes it (§0.1, §2).

## 10. OPEN FORKS (recorded for the founder to steer; safe defaults chosen, build proceeds)
1. **PIN length** — default accept BOTH 4 and 6 digits; recommend 6 for spend-capable users. (Default: allow
   4–6, warn on weak patterns.) 2. **Lockout cross-channel** — voice MAX_ATTEMPTS=3 vs dashboard=5 (chosen);
   founder may want a single value. 3. **Argon2 memory_cost** on the shared box — 64 MiB × parallel verifies
   could spike RAM under a burst; if the co-located box is tight, drop to 32 MiB (still > OWASP floor) — flag
   for the deploy wave. 4. **External-destination allow-list** — export/send to an external email is L3+PIN
   now; founder may want a pre-approved-recipients list to downgrade repeat sends. (Default: always L3+PIN.)
```
