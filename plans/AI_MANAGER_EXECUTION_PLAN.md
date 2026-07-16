# AI MANAGER — UNIT-LEVEL EXECUTION PLAN (crash-safe, build-ready)

> **Role of this file:** the single ASSEMBLED build plan that fuses the six AI-Manager design
> docs into one crash-safe, unit-level sequence. It conforms to `AI_MANAGER_MASTER_PROMPT.md`
> (28-section founder spec) and supersedes the per-doc build orders by reconciling them into ONE
> wave/unit map with owners, models, ordering, isolation gates, and rollbacks.
> **Status:** PLANNING (READ-ONLY wave). No app code, no deploy, no git. Builds happen in later waves.
> **Date:** 2026-06-10 · **Box:** `famit@168.144.153.145` (API `:8209`, header `X-Auth: FamitCall2026`).
>
> **Source design docs (all on disk, all verified against live source):**
> - `design/aim-reuse-inventory.md` — what already exists + the execution-adapter map (THE big finding).
> - `design/aim-architecture.md` — the dedicated SERVICE shape + `ai_manager_*` schema + units C-A1…C-A14.
> - `design/aim-nlu-policy-security.md` — NLU contract, risk table, PolicyEngine, Argon2id PIN, compliance, isolation tests.
> - `design/aim-voice-telephony.md` — inbound DID → LiveKit `manager` persona → streaming state machine → PIN-over-voice.
> - `design/aim-ui-spec.md` — 13 dashboard pages, all Core_2-ported, Test-Console-first.
> - `design/aim-web-research.md` — Groq strict structured-outputs, dual-LLM privilege separation, Hatchet (not Temporal), TRAI/DLT compliance.

---

## 0. THE ONE RECONCILIATION THAT GOVERNS THE WHOLE PLAN (read first)

The two backend design docs say **different things** and the plan must hold both:

- **`aim-architecture.md`** designs a *fresh* dedicated service at `/opt/famit-aimanager/` (own venv, own port
  `:8290`, own `ai_manager_*` PG schema) — the clean, extractable target the founder/orchestrator decided on.
- **`aim-reuse-inventory.md`** finds that **~80% already exists ON THE BOX, IN-PROCESS** inside
  `/opt/famit-agent/`: a 1908-LOC `ai_manager/` control plane (state_machine S0..S9, delegate, identity/RBAC,
  registry, firewall/audit bridges, intent driver, 9 mounted routes behind `FEATURE_AI_MANAGER`) **plus** a
  2252-LOC `workforce/` execution engine whose `tools/catalog.py` IS the execution-adapter layer the spec asks for,
  each tool mapping 1:1 to a real `caller.py` route over an authenticated loopback (`transport.py`), RLS-scoped
  per run via `auth.issue_pair`. The Test Console already passes offline 10/10.

**RECONCILED DECISION (governs every unit below):** the dedicated service is the **TARGET shell**, but we build it
by **PORTING the proven in-process logic, not rewriting it**, and we **prove value first by lighting up what already
exists** (Test Console through the live `state_machine`) before paying the cost of standing up a second process.
Concretely:

1. **Don't throw away the 4160 LOC.** `state_machine`, `identity.canonical_phone`, `intent/driver` (keyword stub),
   `workforce/tools/catalog.py` + `transport.py`, `firewall_bridge`/`audit_bridge`, the offline scripted-transport
   test harness — these are PORTED into the new service's modules (`engine/`, `adapters/`, `identity.py`), not
   re-derived. The architecture doc's file skeleton is the destination; the inventory's files are the source.
2. **The new `ai_manager_*` PG schema is genuinely new** (today the in-process module uses JSONL + in-code tenant
   filtering) — schema/RLS/repo (Units in Wave B) are real net-new work, and they ABSORB the JSONL registry/sessions.
3. **The deterministic safety brain in `aim-nlu-policy-security.md` is the authority** wherever it differs from the
   existing code: per-user **Argon2id** PIN (the in-process path uses firewall's tenant-level salted-sha256 — the
   service owns the stronger per-user store and still mints the firewall step-up token after its own verify); the
   `classify_risk` table + always-block list; the `PolicyEngine.decide` pure function; the dual-LLM boundary.
4. **The one concrete bug to fix at wiring:** `catalog._ads_set_budget`/`_ads_pause` call placeholder paths
   `/ads/budget`,`/ads/pause` that don't exist — the real `ads_engine` routes are
   `/ads/campaigns/propose|{id}/approve|{id}/pause|optimize` (only when `FEATURE_ADS=1`). The ads adapter must be
   re-pointed before the ads intent group goes live (Wave C, ads adapter unit).
5. **Co-located now, extractable later.** The service is network-call-only to the monolith from day one EXCEPT the
   `firewall.py`/`wallet.py`/`audit.py` reuse, which is **direct import while co-located** behind a
   `config._mode = "lib"|"http"` switch — extraction flips that one env, not the call sites.

**Net:** the execution plan = **stand up the dedicated-service shell + new RLS schema, PORT the existing brain into
it, layer the authoritative safety spine on top, add the gap adapters + voice + async + UI, then wire live behind
`AIM_ENABLED`.** Nothing touches the live platform until the final wiring unit, which ships as un-applied diffs + a
founder HOWTO and stays dormant.

---

## 1. WAVE BREAKDOWN (B → C → D → E) + the parallelization map

Five waves. **Wave A is the design wave that produced these six docs (DONE).** Waves B–E build. Each wave is a set
of small verifiable units (≤ ~1 file/deliverable each), each committed before the next per the crash-safe protocol.

| Wave | Theme | Units | Touches live platform? | Gate to exit the wave |
|---|---|---|---|---|
| **B** | **Service scaffold + DB/RLS + safety spine** (shell, `ai_manager_*` schema, repo, identity/auth, Argon2id PIN, NLU, PolicyEngine, CostGuard, AuditService) | B1–B12 | **NO** — new dir, new schema, nothing mounted/routed | the deterministic safety machinery passes **offline** (risk/policy/PIN/isolation/idempotency) with zero keys |
| **C** | **Execution adapters + orchestrator + async + voice** (port catalog, monolith client + scoped-token, command engine lifecycle, Hatchet workers, gap adapters, LiveKit `manager` persona, webhooks) | C1–C11 | **NO** — adapters call a MOCK `/api` in tests; voice/Hatchet units ship dormant | full §12 lifecycle runs offline end-to-end; async run row queued→succeeded on Hatchet; voice state machine passes on stubs |
| **D** | **Dashboard UI** (Core_2-ported, Test-Console-first, dormant-safe) | D1–D9 | **NO** — frontend only; every page degrades to `NoFound` with backend OFF | every page renders premium with the backend OFF (dormant-safe acceptance bar) |
| **E** | **Integration + live test + security harden + deploy** (mint-scoped-token route on monolith, nginx routing, systemd install, retire in-process router, founder HOWTO, real-call test) | E1–E7 | **YES — but gated** — ships as un-applied diffs; with `AIM_ENABLED=0` the live platform is byte-identical | tenant-isolation + step-up-replay + no-double-spend pass on the LIVE box; `AIM_ENABLED=0` proven inert; one real authed command executes + audits |

### 1.1 Parallelization map (what runs in parallel vs MUST serialize)

> Rule (global CLAUDE.md): **one agent per file/domain; never two agents editing the same file.** Partition by
> directory. The serialize constraints below are load-bearing.

**MUST SERIALIZE (hard ordering — a later unit reads/needs the earlier one's output):**
- `B1 (shell/config) → B2 (schema+RLS+engine) → B3 (repo)` — repo needs the engine+schema; everything DB-touching
  needs B2.
- `B4 (identity/auth caller-match) → B5 (Argon2id PIN/lockout)` — PIN bookkeeping lives on the user row B4 owns.
- `B6 (NLU) + B7 (PolicyEngine) + B8 (CostGuard) → B12 (CommandEngine orchestrator)` — the engine composes all three;
  **B12 cannot start until B6/B7/B8 land.** (B9 AuditService + B10 adapters ABC + B11 client also feed B12.)
- `C2 (port catalog into adapters) → C3 (CommandEngine wiring) → C4 (Test-Console endpoint)` — the console drives the
  wired engine.
- **THE MONOLITH SERIALIZATION (the single cross-team interlock):** **E1** adds ONE new route to the monolith
  `caller.py` — `POST /api/internal/mint-scoped-token` (service-token-only). **This edit to `caller.py` MUST serialize
  with EVERY OTHER wave that edits `caller.py`** (ads_engine activation, workflow/booking/media feature flips, the
  in-process `/ai-manager` router retirement E5). Only ONE agent may hold `caller.py` at a time. Schedule E1 + E5 as a
  **single serialized `caller.py` unit owned by one agent**, never parallel with another `caller.py`-touching wave.
- `E2 (nginx route) → E3 (systemd install) → E4 (enable + smoke)` — can't smoke before the unit is installed and routed.

**PARALLELIZABLE (independent files/domains — safe to run as separate agents simultaneously):**
- Within Wave B, after B3: **B4/B5 (auth+PIN)**, **B6 (NLU)**, **B7 (PolicyEngine)**, **B8 (CostGuard)**,
  **B9 (AuditService)** are five INDEPENDENT files — run as up to 5 parallel agents (each owns one `engine/*.py` +
  its test). They converge only at B12.
- Within Wave C: the **gap adapters** (`creative.py`, `workflow.py`, `booking.py`, `ads.py`, `billing.py`) are
  independent files — parallelize one agent per adapter (after C1 ABC + C2 client land). The **voice** units (C8–C10)
  are an independent domain (own `voice/` dir, own systemd unit) — a separate agent track, parallel with the adapters.
- **Wave D (UI) is a wholly independent domain** (`famit-panel/app/ai-manager/`) — it can run **fully in parallel with
  Waves B/C** because it's dormant-safe by construction (renders against a backend that's OFF). One UI agent track
  from the start; it only needs the §10 API *contract* (frozen in `aim-ui-spec.md` + `aim-architecture.md §8`), not a
  running backend. **This is the biggest parallelism win.**
- **Waves B and C backend vs D frontend run on different repos** (`/opt/famit-agent` paths vs
  `C:\Users\kunal\Desktop\caps\famit-panel`) → zero file contention → always parallel.

**SUMMARY of the parallel tracks you can run at once:** (1) Backend-safety track (Wave B units, fanning to 5 parallel
agents mid-wave, converging at B12), (2) Frontend track (Wave D, independent, dormant-safe, start immediately), (3)
later, Voice track (C8–C10) parallel with Adapters track (C5–C7). The **only** true global chokepoint is the single
serialized `caller.py` unit in Wave E.

---

## 2. WAVE B — SERVICE SCAFFOLD + DB/RLS + DETERMINISTIC SAFETY SPINE

> Goal: stand up the dormant service shell + the new RLS schema + the entire **offline-provable** safety brain
> (identity, Argon2id PIN, NLU-validation, risk table, PolicyEngine, CostGuard, AuditService) BEFORE any real
> execution. Nothing here is mounted or routed; the live platform is untouched. Maps to `aim-architecture.md`
> C-A1..C-A8/A10 + `aim-nlu-policy-security.md §8` build order.

| Unit | Deliverable (owner file under `/opt/famit-aimanager/`) | Model | Order / depends on | Isolation/regression GATE (the test that must pass) | Rollback |
|---|---|---|---|---|---|
| **B1** | Package skeleton: dir, `app/main.py` factory + `AIM_ENABLED` gate (default 0), `config.py` (dormant-until-key, never raises at import, `_mode=lib\|http`), `.venv`+`requirements.txt`, 3 systemd unit files (api/worker/voice, installed-disabled), `/health`+`/status`. | sonnet | FIRST (none) | service boots; `/health`=200; `/status`→`{enabled:false}`; **import does not touch `/opt/famit-agent` or any live process**; `ps`/`systemctl` show no live service changed. | `rm -rf /opt/famit-aimanager` (new dir only — nothing else references it). |
| **B2** | `db/schema.sql` (7 tables, §2.1 of architecture doc) + `db/rls.sql` (FORCE RLS admin-GUC, audit_logs INSERT/SELECT-only) + `db/engine.py` (own engine, `session(vendor_id,is_admin)` GUC ctx) + `db/bootstrap.ensure_schema()` (lazy, gated on `AIM_PG_DSN`). | sonnet | after B1 | apply on a **scratch PG** → 7 tables present, `FORCE` RLS on all 7, audit_logs has NO update/delete grant; **re-run = no-op (idempotent)**; **with `AIM_PG_DSN` unset, ensure_schema is a no-op** (live PG untouched). | drop the `ai_manager_*` tables on the scratch DB; DDL is additive `IF NOT EXISTS` so it never alters existing tables. |
| **B3** | `db/repo.py` — typed vendor-scoped CRUD over all 7 tables; **every** read/write opens `session(vendor_id=…)`; absorbs the JSONL registry/session shape. | sonnet | after B2 | `test_tenant_isolation.py` (§7.2 RLS probes): auth A insert → as B select = **0 rows**; B update/delete A's PK = **0 rows**; no-GUC = 0 rows; **negative control** (read vendor_id from body) makes the forge SUCCEED → proves the test bites. | revert `repo.py`; schema stays (harmless). |
| **B4** | `identity.py` (PORT `canonical_phone` + `_match_forms` from `ai_manager/identity.py`+crm-core) + `engine/auth_service.py` caller-ID match + lockout bookkeeping (NO PIN yet). | sonnet | after B3 | `test_phone_norm.py` (+91/raw-10/0-prefix collapse to one canonical), `test_caller_match.py` (manager stored `+91…` matches caller arriving `0…`/bare-10 — the silent-join fix), **unknown caller → None reveals nothing**. | revert the two files. |
| **B5** | Argon2id PIN in AuthService: `argon2-cffi` `PasswordHasher`, HMAC pepper from `var/secret`, set/verify/lockout/reset; lockout authoritative on `ai_manager_authorized_users.{failed_pin_attempts,locked_until}`; mints firewall step-up AFTER local verify. | **opus** (PIN/crypto correctness) | after B4 | `test_pin_lockout.py`: correct verify, wrong increments, lock after N (exp backoff), `check_needs_rehash` upgrade, **grep the store + audit rows for the test PIN → 0 hits** (never stored/logged raw), user-enumeration uniform error. | revert; firewall tenant PIN path unaffected (separate store). |
| **B6** | `providers/llm.py` (`LLMProvider` ABC + `GroqLLM` **strict structured-outputs** `response_format:{type:json_schema,strict:true}` + `MockLLM` keyword stub ported from `intent/driver.py`) + `nlu_prompt.py` (§22 verbatim) + `engine/nlu.py` (parse→validate→retry-once→clarify; **Pydantic semantic validators**; recompute risk, ignore model's). | **opus** (dual-LLM boundary + injection) | after B3 (parallel w/ B4/B7/B8/B9) | `test_nlu_json.py`: schema-valid out; **bad JSON → safe_to_execute=false** never executes; off-enum/low-conf → clarify; money coerced to int paise (no float); **MockLLM deterministic with ZERO keys**; injection ("reveal my key") → `block_reason`. | revert; provider was never keyed live. |
| **B7** | `engine/policy.py` — `classify_risk` deterministic table (§2.1) + escalation rules (raise-only) + always-block list (§2.3) + `PolicyEngine.decide` pure fail-closed function (§3.3 order). | **opus** (risk-matrix correctness = the security crux) | after B3 (parallel) | `test_risk_classify.py` + `test_policy_caps.py`: **every §23 sample** recomputes to the table's level (model's risk IGNORED); money/bulk/export→L3+; secrets/DND/spend-over-cap→block; hard-cap returns **block not pin**; unknown action→block (default-deny); negative-control wrong-level asserts the test bites. | revert (pure function, no state). |
| **B8** | `engine/cost_guard.py` — deterministic per-action estimate + `reserve/settle/release` via `wallet.py` (lib mode); **prepaid (billing.balance) vs prepaid_wallet (wallet_accounts) branch — NEVER summed**; reserve-before-execute, settle actual, release on fail, idempotent on idem_key. | sonnet | after B3 (parallel) | reserve→hold, settle min(actual,reserved), release on fail; **idempotent replay = charged once** (reuse the proven wallet concurrency harness); **no-wallet → fails CLOSED (treat 0, block)**, never fail-open on money. | revert; wallet untouched (read-through). |
| **B9** | `engine/audit_service.py` — dual write: `audit.record(channel="ai_manager", actor=verified-tenant)` (immutable PG `events`) + `repo.append_audit` → `ai_manager_audit_logs`; **secret-scrub** (`pin/otp/secret/code/token`→`***`) before every write. | sonnet | after B3 (parallel) | event written to BOTH legs; **grep written rows for a planted secret → 0 hits**; actor is the tenant never "system"; money-mutating audit rides inside the wallet txn (no JSONL-vs-COMMIT divergence). | revert; audit.py untouched. |
| **B10** | `adapters/__init__.py` — `ModuleAdapter` ABC + REGISTRY (`module`,`actions`,`is_async`,`estimate_cost`,`execute`). Pure interface, no live calls. | sonnet | after B1 (parallel) | ABC importable; a `MockAdapter` satisfies it; missing module → `{ok:false,error:{status:"not_configured"}}` clean. | revert. |
| **B11** | `adapters/monolith_client.py` — httpx client to `caller.py /api`; service token + scoped-tenant-token plumbing (the mint hop is stubbed until E1); retries, timeouts, idempotency-key passthrough. | sonnet | after B10 | against a **mock `/api`**: sends `X-Auth: <scoped token>`, carries idem_key, retries on 5xx, **never sends a forged vendor_id in body** (tenant only via token). | revert. |
| **B12** | `engine/command_engine.py` — full §12 lifecycle (receive→identify→parse→policy→cost→confirm→pin→reserve→execute→settle→audit), persisting `ai_manager_commands` at every hop; `run_command/confirm/submit_pin/cancel/execute`. | **opus** (orchestrator) | after B6+B7+B8+B9+B10+B11 (the convergence point) | `test_offline_lifecycle.py` + `test_idempotent_exec.py`: receive→…→audit **deterministic, zero network** (Mock adapters/LLM); **replayed command (same idem_key) executes ONCE**; a blocked/denied path persists `status` and audits, no side effect. | revert; nothing wired live. |

**Wave-B exit gate (must all be green, all OFFLINE, zero external creds):** RLS probes (B3), phone/caller-match
(B4), Argon2id PIN + no-raw-leak (B5), NLU validation + injection-block (B6), risk-table + fail-closed policy (B7),
no-double-spend cost guard (B8), secret-scrubbed audit (B9), full lifecycle + idempotency (B12). **This is the entire
deterministic safety spine, provable on a laptop with no LLM/voice/telephony/wallet creds.**

---

## 3. WAVE C — EXECUTION ADAPTERS + ORCHESTRATOR WIRING + ASYNC + VOICE

> Goal: turn the offline brain into a thing that can actually execute against the monolith `/api`, run long jobs
> durably on Hatchet, and answer a phone — while STILL touching nothing live (adapters tested against a mock `/api`;
> voice + Hatchet units ship dormant). Maps to architecture C-A9/A12/A13 + the inventory's catalog port + the voice doc.

| Unit | Deliverable | Model | Order / depends on | Isolation/regression GATE | Rollback |
|---|---|---|---|---|---|
| **C1** | **Safe/common adapters** — `analytics.py`, `leads.py`, `campaigns.py` (the read + low-risk write set) PORTED from `workforce/tools/catalog.py`, each calling the real `/api` route per the inventory adapter table (analytics→GET /analytics, leads→/leads, contacts→PUT /contacts/{phone}, run→POST /run). | sonnet | after B11 | against mock `/api`: each adapter hits the **correct route+method+payload**; `not_configured` clean on missing module; RLS-scoped via the run token. | revert per file. |
| **C2** | **Wire the orchestrator to real adapters** — `ExecutionRouter` dispatch (`action_type`→adapter; sync inline, async→action_run); replace Mock adapters in `CommandEngine` with the C1 set behind a flag. | sonnet | after C1 + B12 | the §12 lifecycle now routes to C1 adapters against mock `/api`; sync L0 read executes inline; idempotency preserved. | flip flag back to Mock adapters. |
| **C3** | **Test-Console endpoint** `POST /commands/test` + `confirm/cancel/execute` API handlers — dashboard chat drives the SAME engine (the spine proof without telephony). | sonnet | after C2 | offline scripted chat: parse→policy→PIN→execute→audit through the real handlers; vendor-scoped; PIN never raw; matches the proven `run_command_offline` behavior. | revert handlers. |
| **C4** | **`api/*` routers** — profile/users/pin/sessions/commands/execution/dashboard (the §10 surface the service serves under `/ai-manager`). | sonnet | after C3 | each route vendor-scoped from token; `PATCH/DELETE` cross-tenant id → 404 (the §7.1 forge matrix); PIN endpoints never expose raw. | revert routers (service still boots, just fewer routes). |
| **C5** | **Gap adapter: creative** — `creative.py` → `media_gen` `POST /media/video/jobs`/`/media/image/generate` (async job; respond "started, will notify"); + `COMMAND_INTENTS` enum + risk class + role. | sonnet | after C2 (parallel w/ C6/C7) | async job create against mock; returns `{job_id}`; **dormant clean when FEATURE_MEDIA off** → `not_configured`. | revert file. |
| **C6** | **Gap adapter: workflow + booking** — `workflow.py` → `POST /workflows` (DRAFT, never auto-activate; publish/run behind step-up) + `booking.py` → `/booking/availability\|book\|reschedule` (FREE, no step-up). | sonnet | after C2 (parallel) | draft-only path proven; **activation requires step-up**; booking creates no spend; dormant clean when features off. | revert files. |
| **C7** | **Gap adapter: ads (with the bug fix) + billing reads** — `ads.py` re-pointed to the REAL `ads_engine` routes `/ads/campaigns/propose\|{id}/approve\|{id}/pause\|optimize` (NOT the placeholder `/ads/budget`,`/ads/pause`); `billing.py` → `/usage`,`/wallet`,`/billing/ledger`. | **opus** (money path + the known incorrectness) | after C2 (parallel) | ads adapter calls the real routes; **launch/budget = L3 money gate → wallet reserve/settle**; fails CLOSED with no wallet; dormant clean when FEATURE_ADS off. | revert; ads stays unwired (parks safely — default-deny). |
| **C8** | **Hatchet async** — `workers/workflows.py` (one workflow per long-running action: bulk_call/send_report/creative_pack) + `workers/hatchet_worker.py` (registers + `worker.start()`); writes/updates `ai_manager_action_runs`; idempotency keyed by run id. | sonnet | after C2 | Hatchet trigger updates run row queued→running→succeeded; **worker crash resumes** (F3 Postgres-broker durable); **Hatchet env unset → bounded inline for small jobs, large jobs marked `not_configured`, never crashes**. | stop the worker unit; inline fallback covers small jobs. |
| **C9** | **Voice session service + webhooks** — `voice/session_service.py` (`on_inbound/on_event/on_status/on_recording/finalize`) + the 4 `/voice/*` routes (**signature-verified**, HMAC like the WA webhook); caller→user identify via PG `_match_forms`; session row write (PIN-masked transcript, incremental flush). | **opus** (voice safety + PIN audio hygiene) | after C4 (parallel w/ adapters) | offline stub (scripted utterances + DTMF strings, StubFirewall/StubEngine): full S0→S_END; **unknown caller reveals nothing**; **PIN never in transcript** (recorder paused around S2/S6); webhooks reject bad signature 403; **dormant when `AIM_INBOUND_TRUNK_ID` unset** (`sip:not_configured`). | revert; voice dir unmounted, no live worker. |
| **C10** | **LiveKit `manager` persona worker** — `voice/manager_agent.py` 2nd `WorkerOptions(agent_name="manager")`, COPIES `agent.py`'s tuned `AgentSession` kwargs verbatim (latency moat); own systemd unit, **DORMANT** until DID lands. **`agent.py`/`capsy` NEVER imported/touched.** | **opus** (latency-safe 2nd persona) | after C9 | worker registers as a 2nd persona; **the live outbound agent is byte-unchanged** (`agent.py` untouched, separate process/unit); copied kwargs degrade-not-crash via `_session_kwargs_filter`. | disable the voice systemd unit (installed-disabled by default). |
| **C11** | **Compliance gate wrapper** — `compliance.check(action_type, target_refs, ctx)` over the monolith DND/suppression/calling-window/consent path; TRAI 9-21 window clamp, DLT-aware audit; **never PIN-overridable**; wired into PolicyEngine before cost/confirm. | **opus** (compliance correctness, legal exposure) | after B7 + C2 | bulk-call at 9PM with 6PM cutoff → schedule-or-refuse; DND/STOP/suppressed dropped + count spoken; "ignore DND" → L4 block + audit; consent ≤7d enforced. | revert; bulk outreach parks (default-deny) until restored. |

**Wave-C exit gate:** full §12 lifecycle executes end-to-end against a **mock `/api`** with the real adapter set;
async run goes queued→succeeded on Hatchet (and degrades cleanly when Hatchet is unset); voice state machine passes
on stubs with PIN hygiene proven; compliance gate refuses the always-block set. Still **zero** live-platform impact.

---

## 4. WAVE D — DASHBOARD UI (Core_2-ported, Test-Console-first, dormant-safe)

> Goal: the complete rich AI-Manager dashboard, **all Core_2-ported** (iron reuse rule), every page dormant-safe so it
> looks premium with the backend OFF. **Runs fully in parallel with Waves B/C** (different repo, needs only the frozen
> §10 API contract). Maps to `aim-ui-spec.md` build order. Repo: `C:\Users\kunal\Desktop\caps\famit-panel`.

| Unit | Deliverable (under `famit-panel/app/ai-manager/`) | Model | Order / depends on | Isolation/regression GATE | Rollback |
|---|---|---|---|---|---|
| **D1** | **Shell** — `_shared.tsx` `AimHeader` (PageHeader + pill tab-rail, mirror Billing) + `riskVariant/statusVariant/RiskBadge`; extend `_lib.ts` with the full §10 surface (`ReadResult` union, dormant→`NoFound`); nav: promote "AI Manager" to a collapsible group. | sonnet | FIRST (UI track) | `next build` passes; nav group renders role-gated; existing page's dormant pattern preserved; **no Core_2 component reinvented** (uses real `Table/NoFound/Modal/Tabs/Search/Card/Button`). | revert; existing single page still works. |
| **D2** | **Test Console** `/ai-manager/test` (BUILD FIRST per master §14/§26) — `MessagesPage/Chat` port; NLU-result card per turn; inline confirm/cancel; PIN `Modal`; example chips from §23. | **opus** (the flagship page, must feel premium) | after D1 | renders premium with backend OFF (dormant `NoFound` + static command vocabulary); blocked L4 → red "Refused" bubble; wrong PIN reveals nothing. | revert page. |
| **D3** | **Overview** `/ai-manager/overview` — `HomePage`+`Products/OverviewPage/Overview` KPI strip; recent sessions/risky actions; quick-test deep-link. | sonnet | after D1 (parallel D4–D9) | dormant = existing premium "coming soon" explainer; loading skeletons; per-card error isolation. | revert page. |
| **D4** | **Command History** `/ai-manager/commands` + **Session Detail** `/ai-manager/sessions/[id]` — `Income/StatementsPage/Transactions` + `Filters`; transcript thread + command chain + audit + action-runs; PIN masked. | sonnet | after D1 (parallel) | filters persist in URL; PIN/secrets masked everywhere; dormant `NoFound` + sample legend. | revert pages. |
| **D5** | **Pending Approvals** `/ai-manager/approvals` — `Products/CommentsPage`; Needs-confirm/PIN/review tabs; approve opens PIN `Modal`; bulk approve still PIN-gated; feeds nav count. | sonnet | after D1 (parallel) | each approve PIN-gated; dormant "nothing pending". | revert page. |
| **D6** | **Setup** `/ai-manager/setup` + **Authorized Users** `/ai-manager/users` + **Numbers** `/ai-manager/numbers` — `SettingsPage` sections + `CustomerListPage` table + Modal; absorbs existing `RegisterForm`. | sonnet | after D1 (parallel) | spend-cap/PIN-threshold changes surface 403→"needs step-up PIN"; PIN never rendered; dormant read-only. | revert pages. |
| **D7** | **Add-ons A** — Live Command Stream `/live` + Risk & Audit Analytics `/risk` (recharts, real aggregates only — no fabricated deltas). | sonnet | after D1 (parallel) | charts render from real aggregates; dormant `NoFound`. | revert. |
| **D8** | **Add-ons B** — Capability Catalog `/capabilities` (static §11 map + grants) + Spend Guard `/spend` (`Income/EarningPage` money screen) + Voice Session Player `/sessions/[id]/play`. | sonnet | after D1 (parallel) | catalog static-always-renders; spend low-balance amber banner; player PIN-masked transcript. | revert. |
| **D9** | **UI acceptance pass** — every page verified dormant-safe (backend OFF → premium `NoFound`/legend, never error wall); risk colour language centralized; secret-masking audited across pages. | sonnet | after D2–D8 | the dormant-safe acceptance bar met on **all 13 pages**; `next build` clean; no bespoke `data-table/state-block/SegBtn`. | n/a (verification unit). |

**Wave-D exit gate:** all 13 pages render premium with the backend OFF; Test Console is the proof surface; reuse rule
honored (real Core_2 components only); zero business logic in components (lives in `_lib`).

---

## 5. WAVE E — INTEGRATION + LIVE TEST + SECURITY HARDEN + DEPLOY (gated, reversible)

> Goal: wire the service to the live monolith + panel and prove it inert-then-working, WITHOUT a window where the live
> platform regresses. Everything ships as **un-applied diffs + a founder HOWTO**; `AIM_ENABLED=0` keeps the platform
> byte-identical until the founder flips it. Maps to architecture C-A14. **Contains the single global `caller.py`
> serialization chokepoint.**

| Unit | Deliverable | Model | Order / depends on | Isolation/regression GATE | Rollback |
|---|---|---|---|---|---|
| **E1** | **Monolith mint-scoped-token route** — `POST /api/internal/mint-scoped-token` in `caller.py` (service-token-ONLY; mints `auth.issue_pair(tenant)` for a verified caller so the monolith RLS re-enforces tenant on the executing side). **SERIALIZED `caller.py` unit — one agent, no parallel caller.py edits.** | **opus** (live monolith edit, security-critical) | after Wave C; **serialize with E5 + any other caller.py wave** | service-token-only (any other caller 403); with the route added but unused, **live `/api` byte-identical** (additive route); forged service token rejected. | `git revert` the single caller.py commit; route is additive so revert is clean. |
| **E2** | **nginx routing** — add `location /api/ai-manager/ { proxy_pass http://<backend-priv>:8290/; }` on the panel vhost (kept commented/disabled until cutover). | sonnet | after E1 | with the location **commented**, panel unchanged; when enabled, `/api/ai-manager/*` reaches `:8290`, NOT `caller.py`. | comment the location + `nginx -s reload`. |
| **E3** | **systemd install** — install the 3 units (api enabled, worker + voice **installed-disabled**); `.env` from the founder HOWTO; `ensure_schema()` applies `ai_manager_*` to the live PG (additive, idempotent). | sonnet | after E2 | `famit-aimanager` runs `:8290` localhost-only; **worker/voice stay disabled**; schema apply creates only `ai_manager_*` (no live table altered); `/status`→`{enabled:false}`. | `systemctl disable --now famit-aimanager`; drop `ai_manager_*` (additive). |
| **E4** | **Live safety re-proof on the box** — run `test_tenant_isolation` (token-layer forge matrix + RLS probes) + step-up-replay (A's token on B's execute → 403) + no-double-spend against the **live PG/wallet** (test tenants, rows deleted after). | **opus** (live security gate — the go/no-go) | after E3 | cross-tenant leak = **0** on live; step-up replay = 403; concurrent double-execute charges **once**; negative control proves the tests bite. **Any leak = red, do not enable.** | n/a (read/probe + cleanup; no enable yet). |
| **E5** | **Retire the in-process `/ai-manager` router** — once the service owns the data, remove/neuter the dormant `ai_manager.endpoints` mount in `caller.py` (nginx already wins the prefix). **Part of the SAME serialized `caller.py` unit as E1.** | sonnet | bundled with E1 (one caller.py agent) | with the in-process router removed, the nginx `/api/ai-manager/` route serves the service; **no panel route 404s** (service is the source of truth); JSONL→PG backfill verified. | `git revert` the caller.py commit (restores the in-process router). |
| **E6** | **Founder HOWTO + need.md cross-ref** — click-by-click: paste `AIM_SERVICE_TOKEN`/`AIM_PG_DSN`/DID/`AIM_INBOUND_TRUNK_ID`/Hatchet token, set `AIM_ENABLED=1`, reload nginx; per-vendor `profiles.enabled` rollout. | sonnet | after E4 | a non-technical founder can follow it end-to-end; every blocker maps to a need.md card. | n/a (doc). |
| **E7** | **Real-call / real-command live test** — enable for ONE pilot vendor; run a Test-Console command end-to-end (parse→policy→PIN→execute→audit) and, once the DID is live, ONE real inbound voice command; verify the immutable audit row. | **opus** (final acceptance) | LAST; after E6 + founder creds | one authed command executes + settles + audits on live; voice path (if DID present) completes S0→S_END; **disable → platform byte-identical** (prove inert). | set `AIM_ENABLED=0` (instant revert to dormant); per-vendor `profiles.enabled=false`. |

**Wave-E exit gate (= product acceptance):** on the LIVE box, with `AIM_ENABLED=0` the platform is byte-identical;
with it ON for a pilot vendor, one real command runs the full governed lifecycle and lands an immutable audit row;
tenant isolation + step-up replay + no-double-spend all green on live; instant rollback via the flag.

---

## 6. MODEL ROUTING (why opus where it's used)

**opus** is reserved for correctness-critical or hard-reasoning units (per the global rule "don't burn opus on
grep-and-report"): **B5** (PIN crypto), **B6** (dual-LLM/injection boundary), **B7** (risk-matrix — the security
crux), **B12** (orchestrator lifecycle), **C7** (money path + the known ads bug), **C9/C10** (voice safety + latency-
safe 2nd persona), **C11** (compliance/legal exposure), **D2** (flagship Test Console UI), **E1** (live monolith
edit), **E4** (live security go/no-go), **E7** (final acceptance). **sonnet** does the mechanical scaffolding, CRUD,
routers, gap adapters, async plumbing, and the dormant-safe UI pages. **No haiku** — every unit has a real correctness
test, so the floor is sonnet.

---

## 7. CROSS-CUTTING INVARIANTS (every unit must preserve — do not regress)

1. **Tenant is ALWAYS token-derived**, never a body/query field — at the service edge AND on the executing side (the
   scoped tenant token re-auths the monolith under RLS). Forge `vendor_id` in a body → ignored.
2. **The LLM never authorizes.** NLU only classifies/extracts into the §22 JSON (a quarantined reader). `classify_risk`
   + `PolicyEngine.decide` are pure code and authoritative; the model's `safe_to_execute`/`risk_level` are discarded.
3. **Money fails CLOSED.** No wallet → treat funds as 0 → block. Prepaid vs prepaid_wallet are SEPARATE balances,
   never summed. Reserve-before-execute, settle actual, release on fail, idempotent on idem_key.
4. **PIN never persisted/logged/spoken-into-transcript.** Argon2id per-user hash (pepper from `var/secret`); recorder
   paused around PIN turns; masked `****` everywhere; grep-the-rows test = 0 hits.
5. **Compliance is never PIN-overridable.** DND/STOP/consent/calling-window are L4-block if "ignored"; blocked refs
   dropped, not contacted; every decision audited.
6. **Everything audited** to the immutable PG `events` leg with the verified tenant as actor; secret-shaped keys
   scrubbed; money-mutating audit rides inside the wallet txn.
7. **Dormant + reversible by construction.** `AIM_ENABLED=0` (+ per-vendor `profiles.enabled`) keeps the live
   platform byte-identical; schema apply is additive `IF NOT EXISTS`; voice/Hatchet workers installed-disabled; the
   live outbound `agent.py`/`capsy` and the rest of `caller.py` are untouched until the single serialized E1/E5 unit.
8. **Reuse, never rebuild** (UI): real Core_2 components only; (backend): port the proven `state_machine`/`catalog`/
   bridges, don't re-derive lookalikes.

---

## 8. FOUNDER-SIDE BLOCKERS (appended to need.md — none block Waves B/C/D or the Test-Console path)

| # | Blocker | Blocks | Workaround until provided |
|---|---|---|---|
| 1 | **Dedicated inbound DID/phone number on VoBiz/SIP** + **inbound SIP trunk** in LiveKit (existing `ST_fmtVmNJmpzKa` is OUTBOUND-only) + an **inbound dispatch rule** routing that DID → `agent_name="manager"`. Env: `AIM_VOICE_DID` + `AIM_INBOUND_TRUNK_ID`. **VoBiz must use TCP** (UDP = 0 responses). **The DID must be DLT-registered** (TRAI/TCCCPR). | Live Flow-1 inbound VOICE. | Chat/Test-Console path works fully without it; voice ships dormant (`sip:not_configured`). |
| 2 | **Raise DigitalOcean droplet limit (3/3 used)** — needs a card on file + a support request "3→8". | True EXTRACTION of the service to its own box. | Co-located on the backend box now; extraction is a 2-env-URL change later, not a rebuild. |
| 3 | **Paid Groq (and/or Cerebras) API key** — `console.groq.com → API Keys → Billing`. | Low-latency NLU + smarter replies under load; confirm Groq `strict:true` structured-output model coverage at voice latency. | `MockLLM` keyword stub runs every offline test with zero keys; free Groq works for low volume. |
| 4 | **Meta WhatsApp Cloud API creds** — Phone number ID + permanent token + approved template. | The WhatsApp CHANNEL + `analytics.send_report`/`whatsapp.send` execution. | Dormant `not_configured` until set; the rest of the engine is unaffected. |
| 5 | **Hatchet cross-box reachability** — open `hatchet-fw` tcp/7077 from the backend box priv IP + set `SERVER_GRPC_BROADCAST_ADDRESS=10.122.0.3:7077` + the client token in the service `.env`. | Durable async `action_runs` (bulk call/WA, creative packs, kill-losers). | Bounded inline executor handles small jobs; large jobs mark `not_configured`, never crash. |
| 6 | **DTMF over VoBiz (verify on-box)** — confirm the TCP trunk forwards RFC2833/SIP-INFO DTMF end-to-end. | Leak-proof DTMF PIN entry over voice. | Falls back to recording-suppressed spoken-PIN, or OTP via SMS/WA. |

> Items 1–4 already have founder cards in `need.md` (DID is new — added below). 5–6 are on-box engineering verifications
> the build wave performs, surfaced here so the founder knows what "voice live" depends on.

---

## 9. CRASH-SAFE EXECUTION PROTOCOL (how the build waves actually run)

- **One verifiable unit at a time, committed before the next.** Each unit above has its own test (the GATE column);
  run the test, record IN-PROGRESS→DONE in a `STATE.md`, commit, then start the next. Never batch many edits and verify
  at the end.
- **WORKLOG.md + git are durable truth** on resume — read them first, reconcile, verify the last unit's test before
  building on it.
- **One agent per file/domain.** The 5-way parallel fan-out in Wave B (B4/B5, B6, B7, B8, B9) and the per-adapter
  fan-out in Wave C are safe ONLY because they own disjoint files. The UI track (Wave D) is a separate repo entirely.
- **The `caller.py` chokepoint (E1+E5) is a single serialized unit owned by one agent** — never run it parallel with
  any other wave that edits `caller.py` (ads_engine/workflow/booking/media activations, etc.).
- **Total build units: 39** (B1–B12 = 12, C1–C11 = 11, D1–D9 = 9, E1–E7 = 7).

---

## 10. CONFORMANCE TRACE (master spec → wave/unit)

§4 flows → C2/C3 (lifecycle) + C9/C10 (voice Flow 1) · §6 risk L0–L4 → B7 · §7 security (identity/PIN/authz/confirm/
spend/compliance/audit) → B4/B5/B7/B8/B9/C11 · §8 DB models → B2/B3 · §9 services → B6(NLU)/B7(Policy)/B5(Auth)/
B8(CostGuard)/B9(Audit)/C2(Router)/C9(Voice)/B12(CommandEngine) · §10 APIs → C4 · §11 intents → B6/B7 + C1/C5/C6/C7
adapters · §12 lifecycle → B12 · §13 Hinglish → C9/C10 + D2 · §14 UI → Wave D · §15 workflow draft → C6 · §16 creative
→ C5 · §17 ads → C7 · §18 lead/call → C1 + C11 · §19 wallet → B8 · §20 multi-tenancy → B3 + E4 · §22 NLU JSON → B6 ·
§24 acceptance → wave exit gates · §25 tests → the GATE column of every unit · §26 impl order (Test Console FIRST) →
C3/D2 prioritized · §28 final deliverable → E6 HOWTO.
