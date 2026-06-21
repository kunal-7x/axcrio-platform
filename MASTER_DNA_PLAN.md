# 🧬 MASTER_DNA_PLAN.md — THE BRAIN (read this first, post-compaction)

> **Purpose.** This is the single, faithful, compaction-proof DNA of the entire Famit / Axcrio
> product: the vision, every subsystem (what it is, **why it was born**, the key decisions/facts,
> and status), the ✅ done list, the 🏗️ pending night-build runlist, the ⛔ founder-gated blockers,
> the 📏 standing laws, and the 📖 read-order. It was assembled from 9 deep cluster digests
> (north-star, voice-brain, run-platform, control-security, aim-creative, infra-fortress,
> build-history, pending-queue, memory-brain, growthos-sales). **Long is intentional** — the founder
> is frustrated that summaries lose the *why*; this is a durable doc, not chat context.
>
> Synthesized 2026-06-14. Live state reconciled against `ORCHESTRATOR.md` + `TONIGHT-AUTONOMOUS-BUILD.md`
> at write time (P0-LEAK is now **DONE+DEPLOYED**; `design/RUN-PLATFORM-MASTER-PLAN.md` now **exists**).

---

## 1. THE STORY — vision + how the product got to today

### What Famit / Axcrio is
An **AI Revenue Workforce SaaS**, live at `panel.famit.in`. It replaces an SMB's entire front
office — telecaller team, marketing agency, WhatsApp salesperson, designer, ad-ops, CRM admin,
booking desk, support — and owns the **whole revenue loop**: **Ad → Lead → AI voice call (multilingual
Hindi+English) → WhatsApp follow-up → appointment booked → payment taken → conversion-signal fed back
to Meta/Google Ads.** Multi-tenant, paise-metered, immutable audit, super-admin control plane. The
destination is a billion-dollar, sellable, differentiated product; today it is a funded pilot with
**real** calls (~96), **real** campaigns (8), **real** billings (~₹68/mo meter, ~₹10/banner), and
**real** multi-tenant isolation (18/18 probes).

### Why it exists (the founder's discovery)
Indian SMBs bleed revenue because their front office is manual and unaffordable at scale. Every
existing tool owns ONE slice — Ringg/Bland/Vapi/Retell do voice only; AdCreative/Madgicx do creatives
only; CRMs (Kylas/LeadSquared/GHL) are records not a workforce. **Nobody owns the loop.** The moat is
exactly the cross-channel, post-click ownership: feeding Meta/Google the *actual revenue outcome* of
each conversation (call answered, appointment booked, sale made) via CAPI, so the ad algorithms
optimize for buyers who answer & pay — not "leads submitted." This is the **Revenue-Truth Signal Loop**.

### The architectural verdict — STRANGLE & EVOLVE, never rebuild
The live `caller.py` monolith (~5,400 lines) earns real money. A rebuild would repeat a prior
"90k-line mistake." The verdict (`ARCHITECTURE_DECISION.md`, locked, "the microservices debate is
settled"): a **modular monolith** as the control-plane, with each new capability added as a
self-contained `build_router(...)` + its own RLS schema, **flag-gated** so the resting (all-flags-off)
process is **byte-identical** to legacy. New capability is additive; old code is gradually strangled.
`store.py` (json/dual/pg modes) is the JSON→Postgres strangler seam. Extraction from the monolith
happens ONLY on a named machine-observable trigger (CPU >70% sustained, P99 >2s, team-coordination
overhead, or a genuinely divergent runtime like GPU/batch for the ads/video engine). **Four coarse
planes**, not microservices: (1) control-plane API (`caller.py` FastAPI `:8209`), (2) voice/media
plane (`agent.py` LiveKit worker — already its own process), (3) async spine (Hatchet, built, not yet
in the request path), (4) ads/video render engine (the one named future GPU service).

### The incidents that shaped the laws (rules written in blood)
- **The compromise (2026-06-08).** The old frontend box `famit-voice-2` was rooted and conscripted
  into an outbound DDoS botnet (~118k pps). DO disconnected it; the founder deleted it. The backend
  (DB, voice, keys) was on a *separate* box and survived. Response = the **FORTRESS** rebuild on a
  born-hardened box with **egress lockdown** as the #1 control (a box that can't send arbitrary
  outbound can't be weaponized even if rooted) + defense-in-depth + Cloudflare Full Strict.
- **The earner outage.** A shared-infra edit (firewall/SIP) for an *inbound* feature dropped 219
  outbound INVITEs and killed the live earner. → **NEVER touch the earner** (`agent.py`).
- **The DID carrier-block (2026-06-13 ~12:51 UTC).** Per-wave automated "earner test calls" spam-flagged
  the DID `+918071583488` with Vobiz; every call now returns immediate 486/480/603 with only
  `inviteToTryingMs` (carrier-rejected pre-ring). → **NO outbound test calls** (a real call is the
  founder's job). DID is resting; founder must contact Vobiz.
- **The "486 = it rang" misread.** Multiple waves "verified" a ring on a SIP `486 Busy` (carrier
  rejection pre-ring). A real ring = `inviteToRingingMs>0` / SIP 180 / 200 in the `livekit-sip` log,
  NOT the agent-join line. → **A green report ≠ a working product.**
- **The Groq TPD exhaustion.** All 6 Groq keys shared ONE org's 500k/day pool; heavy AIM testing
  starved the live brain → "thoda sa system slow hua hai" on every turn. A code revert does nothing
  to a depleted bucket. → **429 = quota (add capacity); 400 = code bug (fix/revert the tool).** Fix
  shipped: `FallbackAdapter([groq, openrouter-free])` + least-used key pool + per-key 429 cooldown.
- **The md5 false-safety signal.** "agent.py md5 unchanged = earner safe" was a *false proxy* — the
  earner re-renders through the SHARED `prompt.py` live on every dial. → the real gate is a
  **`prompt.py` GOLDEN-RENDER byte-diff** over the live campaigns' real `fields` (identical when new
  keys absent) PLUS md5/PID/health.
- **The session-death problem.** Max-plan limit resets, socket drops, and laptop-sleep kill in-flight
  agents mid-wave. → granular per-unit waves, commit per verified unit, compaction-proof ledgers,
  always launch the next wave before yielding.

---

## 2. EVERY SUBSYSTEM — what it is · why it was born · key facts · STATUS

> Legend: ✅ DONE (shipped+verified) · 🟡 PARTIAL · 🏗️ PENDING · ⛔ GATED-on-founder/external.

### A. The live voice earner (`agent.py` / famit-agent) — ✅ LIVE, SACRED
**What:** The outbound LiveKit voice worker that places revenue calls (Riya/Godrej-style). Vobiz SIP →
LiveKit SIP → `agent.py` → Sarvam STT (auto-detect) → Groq LLM (`llama-4-scout`, FallbackAdapter) →
ElevenLabs/Sarvam TTS. **Why born:** the product's beating heart — the live earner. **Facts:** md5
`9150fabe4ff62b4b4470f9a87df346e5` (the BOX value — re-baseline per wave, the local mirror `1a154ea1`
is STALE; never trust the literal constant), MainPID `1477083`, ActiveEnter `2026-06-10 19:58:18`,
trunks `ST_fmtVmNJmpzKa`/`ST_LH8ighJJtHSi`. Voice-within-ElevenLabs switching is ALREADY honored on
outbound via `agent.py:485` (`fields.voice_id`) — zero edit needed for EL voice choice. **Never edit /
never restart** without founder sign-off + a real ring.

### B. Modular monolith API (`caller.py` / famit-caller `:8209`) — ✅ LIVE
**What:** The FastAPI control-plane — tenant/auth/routes, the dial loop, CRM, run-campaign, WhatsApp,
the 9 flag-gated module mounts. **Why born:** the strangle-and-evolve seam; ~80% of `/api` already
shipped here. **Facts:** tenant ALWAYS from the auth token (`resolve_tenant`), never the body; every
per-op DB session `SET LOCAL app.tenant_id`; `famit_app` is `NOBYPASSRLS`. Resting all-flags-off ≈ 79
routes (byte-identical to legacy); all-flags-on = 90+. Mount order: ads → media → booking → payments →
support → forms → workflows → ai_manager → funnels. The capsy-venv trap: the running service uses
`/opt/capsy-agent/.venv` (NOTE: capsy, not famit; a decoy `.venv` exists under `/opt/famit-agent`).

### C. Postgres Keystone + RLS (P1 strangler) — ✅ DONE
**What:** PG 16 on the voice box, `famit_app` NOSUPERUSER + FORCE-RLS, dual-mirror (JSON authoritative,
PG mirrored, `shadow_diff==0` = convergence gate) across 9 stores. **Why born:** multi-tenancy +
analytics + relational querying without a risky cutover of the live JSON earner. **Facts:** admin
escape via `SET LOCAL app.is_admin='1'` GUC; bugs fixed = empty-snapshot dual-prune, suppression
composite-key shadow_diff, ledger per-tenant coalescing collision. 42/0 cross-tenant isolation.

### D. ACID Wallet + Action Firewall (F4) — ✅ DONE/LIVE
**What:** ACID credit ledger (`wallet.py`, 4 PG tables, INTEGER PAISE never float) + PIN/step-up
firewall (`firewall.py`, HS256 sub-bound, TTL 300). **Why born:** money custody must survive horizontal
scale — the in-RAM `asyncio.Lock` silently loses no-double-spend on a 2nd instance. Money-mutating
actions need a PIN gate a leaked access token alone can't clear. **Facts:** reserve = atomic
conditional `UPDATE … WHERE available_minor >= :amt RETURNING` (0 rows = insufficient, no race);
settle idempotent `INSERT … ON CONFLICT DO NOTHING` (blocking). PROVEN: 24-concurrent no-oversell;
neg-control oversells to −16000; `available+held == SUM(amount_minor)`. TWO SEPARATE BALANCES:
`billing.balance` (prepaid/postpaid) vs `wallet_accounts.available_minor` (prepaid_wallet) — **never
sum them.** `FIREWALL_ENABLED=true` set at CL-ACT.

### E. Foundation Control Layer (Tier-0 Super-Admin) — ✅ LIVE + ENFORCING (2026-06-11)
**What:** The founder's highest-priority system (above AI features): per-vendor **HIDE/LOCK/ON**
entitlements + plans + status + credits + act-as impersonation + immutable audit, enforced backend
(real) + frontend (cosmetic), via `/super-admin/*` (8 pages) + a `/me/entitlements` self-serve
endpoint. **Why born** (`Z.MD`, founder's voice transcript): about to onboard vendors and needed a
no-deploy lever to block non-payers, pilot features per-vendor, and hide pages — *"turn off, now that
vendor can't see call logs."* HIDE vs LOCK was the founder's own revenue instinct ("LOCK makes them
curious → upsell"). The `FamitCall2026` finding made it urgent. **Key decisions:** central
`entitlements.py` (no scattered `if vendor==x`), most-specific-wins fail-closed cascade (status →
override → plan → default → unknown=HIDDEN), backend is the ONLY boundary (ONE middleware,
**return-don't-raise** JSONResponse — raising inside `BaseHTTPMiddleware` leaks a 500), **HIDE→404 /
LOCK→402 / admin-plane→403** (three deliberate leak surfaces), real-time = 25s ETag short-poll (+ focus
+ route-change + self-heal on any 402/404), 7 PG tables (4 global no-RLS catalog + 2 FORCE-RLS
tenant-scoped + 1 admin audit), 91-key registry seeded 1:1 from the live nav. ROLE vs ENTITLEMENT are
two orthogonal axes; both must pass. `CONTROL_ENABLED` default OFF (resting byte-identical).
**Status residual:** panel `/login` mints a stateless hmac token (no jti) → suspension relies on the
STATUS FLOOR + login-block + JWT-refresh-revoke, not crypto-revoke (T15 still PASSES). **DEFERRED:**
C10 AI-Copilot in-prompt gate (T18 N/A; API already gates it), CI registry-drift guard (C12), Logto
Phase-2 admin-org authority. **Rollback:** restore `.env.CLbak.20260610-195647` + `/opt/famit-panel.CLbak.1781120589`.

### F. Control-Security (admin-plane threat model) — ✅ LIVE
**What:** The hardening of the sharpest knife. **Why born:** the explore found `caller.py:427`
`if cred == PW: return admin` — the bare `FamitCall2026` password is a **permanent, un-rotatable,
un-revocable, un-audited super-admin credential**. Before `/admin/*` shipped (cross-tenant write
power), this would be an admin-plane bypass. **Decisions:** `_is_super_admin = is_admin AND
auth_method != 'legacy_pw'` (the password keeps authenticating VENDOR-grade routes for back-compat but
is EXCLUDED from `/admin/*`; T2 PASS live incl. through Cloudflare → 403). `require_super_admin` is the
ROUTER-level gate (can't be forgotten on a new route). Act-as (impersonation) gated like root: PIN
step-up to enter, `read_only` by default (`_act_as_readonly_block` always-on middleware), ≤10-min TTL,
non-dismissible banner (`X-Act-As` header), enter+exit+expiry all on the IMMUTABLE PG `events` leg
with `real_admin` attribution, can't climb to admin (T11) or target another admin (T12). Audit on the
events leg (NOT the rotating JSONL — that gave a false "audited" signal once); `events.id` is a HASH,
`ORDER BY at` not `id`. **18 probes T1–T18 ALL PASS** (T18 N/A), run twice (in-proc + live HTTP).

### G. Voice-Brain epic (CORE HEART, inbound-first) — 🟡 PARTIAL
The megaplan to turn the inbound pipeline from "static 11-field template" into a real-human AI
telecaller across 5 needs. **Keystone discovery:** `build_system_prompt(fields)` (`prompt.py:253`) is a
pure function of `fields` — both agents render through it. So the migration is "enrich the fields dict
+ add fenced blocks in cache-safe positions," NOT "rewrite the brain."
- **W1 — Dynamic vendor script → adaptive persona — ✅ DONE+DEPLOYED+VERIFIED (5/5).** *Why born:* the
  product ignored vendors' real briefing scripts and spoke from a hard-coded template — unsaleable.
  *Facts:* `fields["raw_script"]` (MUST nest in `fields` — both consumers read only `fields`, a sibling
  no-ops silently at both agents); `build_system_prompt_v2` splices a fenced `<vendor_script>` block
  ONLY when raw_script present + flag on; lossy derived projections suppressed when authoritative;
  injection-guarded (close-tag escape + NFKC + canary + sandbox trust-tier inbound-only). Flag
  `VENDOR_SCRIPT_INJECT=1` via systemd drop-in on aim-voice-agent ONLY (earner env clean). Script
  Studio UI live (BUILD_ID `Ykm_1fVt267VDkPib8uVg`). Golden 5/5 byte-identical flag off+on.
- **B — Lossless full-context store @ <50ms — 🏗️ W2 PENDING.** *Why born:* an 8-page brief became 5
  JSON fields → the AI hallucinated outside them. *Decision:* 3-layer store (campaign_source verbatim
  PG RLS versioned → derived cache → optional chunks for oversize); inject DISTILLED (~800 tok) per
  turn, store lossless in PG; loaded ONCE at connect in the 200-400ms SIP window. **Red-team correction:
  there is NO existing Groq static-prefix cache to "preserve"** (SHARED_RULES sits mid-prompt;
  cross-campaign hit ≈0) → DROP the `[TID:]`-first-token + cache-hit gate; the real cost is 2 cold TCP
  round-trips → deploy pooled `voice_tools.py` first. Flag `CTX_CACHE`.
- **C — Real-human Hinglish + telecaller KB — 🟡 PARTIAL (MLV done; v2 register + FTS KB pending).**
  *Why born:* the AI sounded like "formal government Hindi" robot; no objection rebuttals. *MLV done:*
  see subsystem H. *Pending:* v2 Hinglish few-shots (NEW render path, never mutate `_flow_block`);
  seed `_global` telecaller corpus (~150-300 chunks) via `POST /kb/seed-telecaller`, FTS-only V1, fused
  into the single existing lookup (RRF, not 2× per turn); LiveKit `turn-detector` (Qwen2.5-0.5B INT8,
  Hindi 99.4% TP) — spec `design/voice-quickwins.md` ready.
- **D — Multi-channel relationship memory — 🟡 P0-LEAK done; W3 PENDING.** *Why born:* a returning
  caller was a stranger; WA had no call context. *P0-LEAK done* (subsystem below). *W3 pending:*
  `lead_memory` (`(tenant,phone)` PK) + `lead_episodes` (append-only voice+WA) FORCE-RLS; home-grown PG
  (<5ms) beats Mem0/Zep (50-150ms + PII-outside-India); durable post-call extraction (NOT
  fire-and-forget — LiveKit drains the worker → memory lost; use Hatchet/PG-outbox + `FOR UPDATE`);
  inject memory BEFORE the flow block ("Lost in the Middle"); CRM memory panel.
- **E — Blind-spot sweep — 🏗️ mostly PENDING.** Inbound eval bridge, inbound STT FallbackAdapter (P0
  dead-air on any WS hiccup), inbound memory-save at hangup, CRM `rebuild_timeline` to include episodes,
  rolling-history compression; compliance (DND/NDNC/TRAI-140/DLT/consent — founder-gated runtime
  blockers, not paperwork).

### H. MLV — Multilingual Adaptive Voice (inbound) — ✅ DONE+DEPLOYED (2026-06-14)
**What:** Inbound-only fix for two real-call bugs. **Why born:** founder spoke Hindi → AI Hindi; he
switched to English → AI stuck in Hindi; the opener stuttered. **Diagnosis:** the language PIN at
`aim_voice_agent.py:1480-1485` ("LANGUAGE = CASUAL HINGLISH: default to easy Hinglish") sat inside the
HIGHEST-PRIORITY block and beat the adaptive mirror rule. **Fix:** ADAPTIVE MIRROR rule ("reply in the
SAME language the caller just used; the MOMENT they switch mid-call, switch WITH them; no default, no
house style; never announce the language") + Pass-2 hardening (language-NEUTRAL greeting
`"Namaste{who}, this is {agent} from {company}… how can I help you today?"` — English question so the
AI's own opener no longer pins Hindi + FINAL LANGUAGE LOCK appended last for highest recency). STT was
already auto (`SARVAM_STT_LANG` unset = "unknown" = Sarvam auto-detect). **Verify:** 3/3 then 5/5
live-shape smoke PASS on real Groq llama-4-scout. Box md5 `3152539f…` == `_inbound_ref/aim_voice_agent.DEPLOYED.py`.
Final acceptance = a real inbound call.

### I. P0-LEAK — cross-tenant memory/WA hotfix — ✅ DONE+DEPLOYED+VERIFIED (2026-06-14)
**What:** Pure security fix (no feature). **Why born:** `memory.py:_path_for(phone)` stored all memory
at unprefixed `{phone}.json` shared across tenants (read by the earner at `agent.py:466`); the WA path
had the same flaw; unknown inbound WA → `ADMIN_ID` default poisoned the admin tenant. A live P0.
**Fix:** `_path_for(phone, tenant_id)` → `{tenant_id}/{phone}.json`; READ prefers the tenant path, else
the legacy flat file ONLY IF its stored tenant_id matches OR is empty (claim + migrate-on-read; a
legacy file owned by a DIFFERENT tenant is NEVER returned — **load-bearing check `memory.py:110-113`**);
unknown WA → `_unrouted` (`WA_UNROUTED_TENANT`), never ADMIN_ID; hardcoded "Riya" → `build_recap(agent_name=…)`.
**Verify:** T1/T2/T2b/T4/WA all PASS on the deployed code; full earner gate before+after PASS; restarted
famit-caller + aim-voice-agent ONLY. Commit `4db497f`. **RESIDUAL:** the OUTBOUND earner still runs the
old in-proc `memory.py` → it fully closes on ITS side at its own next deploy+ring (founder-signed W-OB);
returning-lead memory is NOT lost meanwhile (the tenant-checked fallback still loads correctly).

### J. Run-Platform cluster (the founder's hottest bugs) — 🟡 PARTIAL
- **Voice preview fix — ✅ DONE.** *Why born:* clicking Play was silent (no error). `<audio src=url>`
  can't send headers; the backend read auth only from headers. **NOTE — the cause was re-diagnosed in
  the RUN-PLATFORM-MASTER-PLAN:** the real failure is the backend serving EL bytes with
  `Content-Type: text/plain` → Safari/iOS refuse `<audio>` → silence (the earlier "307 redirect" + the
  "200 audio/mpeg curl proof" were WRONG/fabricated). The fix in the queue (Wave B) = backend
  full-buffer the ≤32KB clip + FORCE `audio/mpeg` (both EL hosts) + 502-on-empty + FE real
  `.catch`/`onError`/caption + byte-sniff (`ID3`/`\xFFxFB`/`RIFF`), no `preload="none"`. The `?t=`
  query-param auth path was added (scoped to the public-sample route only).
- **Run-page 4-step redesign — ✅ DONE.** *Why born:* a cramped 7-card single-scroll left rail. 4-step
  stepper (Campaign&Audience → Voice&Providers → Pacing&Handoff → Review&Launch) + sticky summary rail;
  `_stepper.tsx`; the ONLY new state is `step`; everything else moved verbatim. BUILD_ID `jcDEy4iclWbxS_zvVpvk0`.
- **Provider/Voice Switcher Phase-1 — ✅ DONE (6/6).** *Why born:* fake prices + provider must be
  honored+billed + can't hear preview. 3 tiers (LEAN ₹0.75 / STANDARD ₹1.3 / PREMIUM ₹1.6/min — EL
  Flash v2.5 chosen for $0.05/1K + ~75ms + EL's own live-agent rec); single source `llm_router/tiers.py`;
  campaign persists tier NAME + `tier_resolved` snapshot; free preview (EL `preview_url` un-strip / Sarvam
  pre-hosted WAV, zero burn); custom-provider CRUD (Fernet, super-admin, legacy pw→403). **Cost-meter
  residual:** `tts_chars_per_min=900` makes the custom-mix sum ~2.5× the headline → re-tune to ~330-360
  in `tiers.py` (pure data edit). **PRICING HONESTY (from the master plan):** Vobiz ₹0.65/min is
  FABRICATED (needs the founder's real CDR); Premium is below-COGS (loss-leader) — show ONLY sourced
  numbers.
- **Run-Campaign audience-builder UX (`spec-run-campaign.md`) — 🏗️ PENDING.** Composable filters (All /
  temperature hot≥70-warm-cold / by-upload / pick-manually) over one base pool, `lead_ids` explicit
  list, Excel(`.xlsx`) support (`pip openpyxl`), `batch_id` stamping, `GET /leads/batches`. PORT
  Core_2 (Select/Tabs/FieldFiles/Table); no dial-loop change.
- **OB-PROV (Phase 2) — ⛔ GATED.** Make `agent.py` honor `fields.{stt,llm,tts}_provider`. Needs founder
  sign-off + a default-identical `_build_pipeline(fields)` + a real in-window ring before+after (DID
  un-rested). `/tiers` returns `ob_prov_pending:true`.
- **RUN-PLATFORM-MASTER-PLAN.md — ✅ now WRITTEN** (`design/RUN-PLATFORM-MASTER-PLAN.md`, 2026-06-14):
  6 designs + 6 red-teams folded — preview-fix real cause, REAL pricing (Lean ₹4/Std ₹6/Prem ₹8/min;
  Vobiz unverified, Premium below-COGS), provider-lock (ledger label only; the wallet invoice is
  flat-rate `_charge_call` ignoring vendor — a separate deferred F4-wallet fix), 33-item feature-bucket
  table, the "crazy Run UI", phased earner-safe roadmap. Quick-wins **Wave A** (env billing fixes
  `USD_INR=1→95.2`, `EL_RATE=1.5→4.76`, Sarvam v2/v3 split + inbound provider-lock label + funnels mount)
  → **Wave B** (preview fix) → **Wave C** (Run UI + real cost meter).

### K. AI Manager (command brain) — 🟡 LIVE in-process; dedicated service PENDING
**What:** The highest-privilege human surface — a phone/chat command center. Authenticate (PIN) →
context → permission → fresh scoped PIN for risk → delegate to workforce role agents → execute across
modules → read back. **Why born:** the founder wanted to run the whole platform by voice while mobile,
verified+audited+spend-controlled. **Decisions:** 10-state machine S0–S9 (caller-ID is a HINT not a
credential; LLM fills slots only; risk is a DETERMINISTIC code table, the model's risk is DISCARDED);
`PolicyEngine.decide` pure fn fail-closed first-match (always-block → permission default-deny →
compliance NEVER-PIN-overridable → spend-ceiling BLOCK → bulk → risk → gate → default block); PIN =
Argon2id; PIN audio hygiene (`recorder.pause()` around every secret span, transcript `****`); IN-PROCESS
composition (not cross-plane HTTP); delegate to a WORKER role never bare `manager`. **Critical facts/bugs
(fixed):** StubPlanner reads `task['plan']` NOT `task['actions']` (the LLM driver `propose()` returns
None while dormant → StubPlanner always drives); `delegate.execute` must mint+thread `run_token` (else
empty Bearer → asset svc 401); `AIASSET_LOOPBACK_BASE` MUST = `http://10.122.0.4:8310` (VPC IP, not
127.0.0.1 — root cause of "creative commands don't work"); execute-truth fix (a done-but-parked module
now reports `executed:false`); voice tool-schema fix (strict-OFF — strict JSON marked every param
required → small llama-4-scout 400-stormed → dead air; `_strict_tool_schema=False` → 57→0 schema
rejections). **Status:** in-process module LIVE (state machine, 35 routes, PG `ai_manager_*` FORCE-RLS,
Test Console, creative wiring proven). **PENDING:** dedicated service `/opt/famit-aimanager/:8290`
(39-unit plan), multi-turn slot-filling (`S4.5 ELICIT`, `PendingCommand` — the single missing piece for
"run a campaign by phone"), inbound LiveKit voice front. **GATED:** inbound DID + Vobiz inbound trunk,
DO droplet limit raise, WhatsApp creds, paid low-latency NLU key.

### L. Creative Studio + AI Asset Service — ✅ backend LIVE; frontend PENDING
**What:** A campaign-aware AI design engine (designer+copywriter+ad-strategist) generating multi-angle
banner variants from campaign data — NOT a random image generator. Backend = dedicated service
`/opt/famit-aiasset` at `10.122.0.4:8310`, own venv/schema (`ai_asset_*` FORCE-RLS), Hatchet jobs, DO
Spaces, model-agnostic `Provider` ABC (OpenRouter first). **Why born:** generate ad creatives directly
from campaign data without re-briefing; the existing engine was BUILT but undeployed. **Decisions:**
2-stage pipeline (LLM brief → image render); **NO-INVENT validator** (fail-closed regex — a price/RERA/
phone/guarantee claim survives ONLY if verbatim in `ctx.fact_blob()`; proven live+offline); read live
`usage.cost`, settle ACTUAL; OpenRouter image via the same chat endpoint + `"modalities":["image","text"]`
(default `google/gemini-2.5-flash-image` ~$0.039/img); env var is the founder typo `OPNEROUTER_API_KEY`
(adapter reads both). **A4 LIVE PROOF:** 3 real banners from "Codename Joy 3.0" (Shapoorji), wallet
settled ACTUAL ₹10.14, isolation PASS, 4 box bugs fixed (old router.py missing openrouter; shared
"pending" idem key; missing PyJWT; admin-GUC wallet reserve). **Status:** A1-A4 + B3 (AIM wiring) + C3
(e2e) DONE. **PENDING:** the ENTIRE `app/creative/` frontend (GenerationLoader WebGL aurora +
CreativeSkeleton — gated on the famit-panel lane clearing), the LOWER `automation/` engines (video/
image/3D/ads — directory EMPTY), campaign-reader/scorer/versioning/Hatchet-async. **ONE blocker to a
browser demo:** the FE-box nginx `/api/assets/` proxy_pass is stale (needs repoint to `10.122.0.4:8310`
+ reload; needs FE-box root).

### M. WhatsApp (live send + AI template builder) — ✅ LIVE; residuals PENDING
**What:** Live WA send path + AI Meta-compliant template builder (11-step campaign workspace) + post-call
automation. **Why born:** the channel Meta monetizes hardest (CTWA +82% YoY); needed AI template-gen +
banner-attach + segmented send + per-cell analytics. **Decisions:** two-layer brain (LLM proposes,
deterministic `validate.py` is the authority on Meta grammar + category); NO-INVENT scrub. **Bugs fixed:**
FastAPI `Request` annotation under `from __future__ import annotations` → 422 (hoist imports to module
scope); `_meta_to()` strip leading `+` (Graph 404s on `+`); `is_text` flag (free-form was building a
template → #132001); DO Spaces ACL retry-without-ACL; real `META_WA_TOKEN`. **Status:** B1/B2/C2 LIVE
(real wamid proven; FEATURE_WHATSAPP=1; no-double-charge). **Residuals:** WB-2 partial-fallback FE fix
(P0), reply-brain deep context (needs per-person memory), `hot_lead_alert` cold template (Meta-gated),
banner-in-builder (interim DO Spaces `header_url`). Named-→numbered placeholder coercion still needed.

### N. The 9 mounted modules (booking/payments/support/forms/funnels/workflow/ads/media/lifecycle) — ✅ built+mounted, flag-OFF
**What:** A full SaaS feature surface, each a NEW dormant module. **Why born:** the B2B pitch needs the
whole front office; building behind flags lets them demo/activate without risking the earner.
**Pattern (every module):** DEFINED-NOT-MOUNTED → DORMANT-UNTIL-CREDS → additive schema (standalone
`schema.sql`, idempotent, manual apply) → **token-derived tenant** → provider-agnostic ABC. Key
per-module facts: **Booking** — anti-double-book is a DB partial-unique-index + `ON CONFLICT DO NOTHING`,
never read-check-write; own Base (not the shared crm-core Base — 0002 collision). **Payments** —
tenant-collects-from-CUSTOMER vs tenant-pays-Famit are DIFFERENT ledgers; webhook is signature-verified
not tenant-authed, always 200. **Workflow-studio** — n8n REJECTED (Sustainable-Use-License landmine);
ONE generic durable interpreter over a validated immutable JSON snapshot (NOT codegen-per-workflow);
3 safety layers (publish-time BUDGET-dominator check, run-time recompute-spend-from-resolved-args,
immutable audit); resume uses a FRESH attempt number. **Funnels** — compile to the workflow DSL; gate
BULK not just money (`cap_minor=0` = bulk-only no-wallet path). **Lifecycle** — underscore package name;
5 named segments; cycle_key idempotency; gate order consent→idem→cooldown→PIN→admission→budget→enqueue.
**Forms** — public submit inverts the tenant invariant (org from the unguessable `public_token`, never a
param); anti-abuse mandatory. **Security fix wave:** booking (X-Tenant-Id header), media-gen (body
tenant), funnels (body tenant) were cross-tenant holes → all refactored to token-deriving `build_router`.
**Status:** all 9 mounted, default OFF, resting byte-identical. PENDING per module: Alembic/schema apply
on live PG + flag-on + (for ads/payments) external creds.

### O. CRM Core + Business Brain/RAG — ✅ DONE
**What:** Unified person spine (contacts/identity/timeline + NBA) + per-tenant Business Brain JSON +
hybrid KB RAG (FTS sparse keyless always-works + pgvector dense dormant, RRF k=60). **Why born:** leads/
calls/WA were 3 silos (a lead calling twice = 2 people); the voice agent hallucinated product details.
**Facts:** phone-normalization bug class (raw-10 vs canonical split a person) → `regexp_replace(phone,
'\D','')`; pgvector was NOT pre-installed (`apt install postgresql-16-pgvector`); Sarvam has no
embeddings endpoint; `plainto_tsquery` 'simple' AND-logic missed stems → OR-of-terms `to_tsquery`. **KB
corpus is EMPTY** (0 rows) — but the INBOUND retrieval path is ALREADY WIRED + DEPLOYED (connect-prefetch
grounding `_format_grounding`→`_build_sales_instructions` + `lookup` tool + `pick_campaign` re-ground,
`aim_voice_agent.DEPLOYED.py:449/1527/1648`); it is inert only because the corpus is empty. The W4-RAG
activation design is now EXECUTION-READY: `design/RAG-MASTER-PLAN.md` (architecture + exact files +
flag/acceptance/rollback) + `design/RAG-INGESTION-PLAN.md` (`_global` telecaller corpus seed + per-campaign
collateral ingest, FTS-only V1) + `design/RAG-EVAL-SPEC.md` (p95-TTFT-regression<150ms + RAGAS-faithfulness≥0.85
+ RLS-cross-tenant gate). Seeding + the W2-cache grounding reuse + the `RAG_INJECT_ENABLED` gate = pending
item #12 (now scoped as VOICE-BRAIN W4).

### P. Infra — three-box FORTRESS topology — ✅ LIVE
**Why born:** the 2026-06-08 compromise. **Boxes (DO blr1, VPC `10.122.0.0/20`):**
- **famit-panel-2** `143.110.247.249`/`10.122.0.2` — born-hardened frontend, Cloudflare Full Strict
  (15 CF CIDRs only reach origin), DO Cloud Firewall **egress allow-list** (the headline control — a
  rooted box can't flush a cloud-layer firewall), nginx → `/api/assets/`→`10.122.0.4:8310`,
  `/api/`→`:8209`, `/`→`127.0.0.1:3001`. Born-hardened via cloud-init tag-attached firewall (no exposure
  window). Telegram alerts (founder must /start @axcrio_bot).
- **famit-livekit** `168.144.153.145`/`10.122.0.4` — the earner: famit-caller `:8209`, famit-agent
  (SACRED), famit-aiasset `:8310`, PG 16, Docker livekit-server/sip(Vobiz IP-locked `13.203.7.132`)/redis.
- **famit-hatchet** `68.183.94.38`/`10.122.0.3` — NOT in request path: Hatchet-lite (`:8888`/`:7077`) +
  Logto OIDC (`:3001`/`:3002`), all localhost-bound, egress-locked. **DO droplet limit = 3/3 FULL.**
- **Hatchet (F3) — ✅ deploy DONE; caller.py cutover PENDING** (gated on P1; token embeds broadcast
  address → regenerate AFTER setting `SERVER_GRPC_BROADCAST_ADDRESS`; hatchet-lite single container,
  Postgres-broker not RabbitMQ; SDK uses `input_validator=` not `input_type=`).
- **Logto (F4) — ✅ engine+console+org-token DONE; caller.py wiring PENDING** (no headless first-admin
  — founder created via console; M2M org-role must be a sibling MachineToMachine-type; ENDPOINT
  deferred until DNS; JWKS over VPC `10.122.0.3:3001`).
- **P0 secrets gate — ✅ DONE** (gitleaks v8 + pre-commit hook proven + CI `secrets.yml` active; git
  init'd, NOT pushed — founder must create the private GitHub repo).

### Q. Growth OS (flagship standalone ads monorepo) — 🟡 Phase-0 DONE; Phase-1+ PENDING
**What:** A standalone "AI Marketing Department" SaaS (separate monorepo, `growth-os/`); the live
platform is **Tenant Zero** over the **Origin Connector** (never a shared DB). **Why born:** Meta
Andromeda/GEM + Google PMax made creative-gen and campaign-setup no longer a moat; the only lever left
is **signal quality** — and Famit already owns the call/WhatsApp/booking/sale outcome to feed Meta/Google
quality-weighted CAPI events. **Decisions (P1-P12 LAW):** contracts-first (OpenAPI 3.1 + AsyncAPI 3, CI
drift-gated), event-sourced (no service reads another's DB), idempotency everywhere, **money sacred**
(no spend without a Budget-Governor-stamped, step-up-signed, hash-chained ActionPlan), every autonomous
action emits an Explanation BEFORE execution, never edit a live ad in place (resets learning → ship as
new ads). North-star = CPqL. Stack: Turborepo+pnpm/uv, NestJS(Fastify)+Python/FastAPI, Temporal,
Redpanda, Postgres 16, ClickHouse. **Status: Phase-0 DONE** — 25 frozen JSON schemas, 6 OpenAPI, 1
AsyncAPI, hash-chain ledger, NestJS core, Temporal HelloSaga, in-memory demo runs on the laptop.
**KNOWN BLOCKER:** `@growth-os/events` codegen BUILD FAILS (`<Name>Payload` vs `<Name>` from schema
`title`, + duplicate Explanation/CreativeDNA interfaces) — fix this FIRST. The 6-container stack has
never booted (DO 3/3 full). **Gated** on droplet raise + Meta Marketing API + WhatsApp template.

### R. Eval / Replay harness — 🟡 core DONE; box latency re-run PENDING
**What:** The offline gate that makes every future voice model/prompt change PROVABLE (highest-leverage
item). Standalone `eval/`, read-only on `var/`, structurally call-free. **Why born:** every voice change
was a guess; the carrier-block partly happened for lack of an offline path. **Facts:** 5 checks (latency
p95 BOX-ONLY hard gate; guard-violations zero-tolerance; language/monologue/judge no-regress vs a frozen
baseline); LLM judge is a PINNED separate model at temp 0, never the candidate (no circular eval). Teeth
proven offline (guard_bait → 12 violations; prompt_stripped → judge 2.545) independent of latency.
Baseline frozen (`llama-4-scout`, p95 1332ms). PENDING: re-run `--freeze-baseline` + `selftest_bad_model`
ON the box to exercise the latency half.

### S. Sales + Investor GTM materials — ✅ research+HTML DONE; no customer yet
**What:** Customer-facing sales proposal (interactive HTML) + VC investor deck + market-sizing/moat
research. **Why born:** product works but zero paying customers and no leave-behind. **Facts:**
positioning = "AI Revenue Workforce / Revenue OS" ("they sell you a tool and you still hire the team; we
sell you the team"); 3 tiers STARTER ₹9,999 / GROWTH ₹24,999 ⭐ / ENTERPRISE from ₹75k, each below the
human cost it replaces; ROI calculator (default 500 leads → ₹98,751 gain / 5.0× / ~6-day payback, floor
case still positive on salary−fee); REAL-only proof (96 calls/8 campaigns/~₹68mo/₹10 banner/18-18
isolation); raise amount + valuation = deliberate FOUNDER-TO-FILL. HTML self-contained, visual-QA passed.
TAM $240.6B AI-for-Sales 2030, India SAM ~$5B, SOM $40-90M ARR. **NOT done:** sent to / closed with any
real prospect.

---

## 3. ✅ DONE — the one-line story of what shipped (for context, not a build list)

- **The live earner** — outbound AI voice calls that earn real money; the heart, kept sacred.
- **Modular monolith + Postgres keystone + 42/0 RLS** — multi-tenant spine, JSON→PG strangled safely.
- **ACID wallet + firewall** — money custody that survives scale; no-double-spend PROVEN; PIN step-up.
- **Foundation Control Layer (LIVE+enforcing)** — the founder's no-deploy HIDE/LOCK/suspend/act-as
  control plane, born from "I want to turn off a vendor's call-logs page"; 18/18 isolation probes.
- **Control-Security** — closed the `FamitCall2026` permanent-admin-bypass on the admin plane.
- **W1 dynamic vendor-script → adaptive persona + Script Studio** — vendors' real scripts now drive the
  inbound agent; born from "the product ignored the vendor's brief."
- **MLV** — inbound now mirrors the caller's language mid-call; born from a real call where the AI stayed
  stuck in Hindi.
- **P0-LEAK** — closed a live cross-tenant memory/WA leak + the ADMIN_ID-poison default.
- **Run-page redesign + voice-preview fix + Provider/Voice Switcher Phase-1** — the founder's hottest UX
  bugs (cramped scroll, silent preview, fake prices, no provider control).
- **AI Manager (in-process, LIVE)** — run the platform by command, verified + PIN-gated + audited;
  creative banner commands generate real PNGs.
- **Creative Studio backend (A1-A4 + C3)** — real AI banners from campaign data, ~₹10 each, NO-INVENT
  validated, no-double-charge.
- **WhatsApp live + AI template builder** — real wamid; Meta-compliant AI templates with a deterministic
  validator.
- **9 dormant modules built+mounted** — the full front-office surface, flag-OFF, byte-identical resting.
- **CRM core + Business Brain + KB-RAG substrate** — unified person spine; grounding engine (corpus empty).
- **FORTRESS three-box infra** — born-hardened rebuild after the DDoS compromise; egress-locked,
  Cloudflare Full Strict.
- **Hatchet + Logto deployed** — durable spine + OIDC IdP standing by (not yet in the request path).
- **P0 secrets gate** — gitleaks + pre-commit hook so the leaked-`.env` class can't recur.
- **Growth OS Phase-0 contracts + core** — the flagship ads monorepo's frozen contracts + hash-chain
  ledger + demo loop.
- **Eval harness core + frozen baseline** — the gate that makes future voice changes provable.
- **Sales proposal + investor deck + GTM research** — real-only, honest, ready to hand to a buyer/VC.
- **Performance overhaul (6 units LIVE)** — pagination, react-query cache, virtualization, code-split,
  gzip 90%/10x, immutable static cache; born from "every click took 10-20s."
- **Recordings (REC-A/B/C + UI)** — inbound finalize-on-read + outbound auto-egress + unified API + CRM
  player.
- **LLM provider pool + hot-reload encrypted key store** — least-used pick + per-key 429 cooldown +
  Groq→SambaNova→OpenRouter fallback; born from repeated Groq-TPD dead-air.
- **Handoff / warm-transfer (HOFX/HCRB) + clean-handoff behavior rewrite** — bridge a human into the
  room (Pattern C), AI exits via `session.aclose()`, no AI-disclosure, names the person on the line.

---

## 4. 🏗️ PENDING BUILD CHECKLIST — the night-build runlist (NOT-DONE only, top-down)

> Earner-safety note applies to ALL: agent.py md5 (re-baseline from box) UNCHANGED + famit-agent PID
> 1477083 NOT restarted + caller `/health` 200 + 0 5xx + golden byte-diff identical (flag off) + NO ring.
> Restart ONLY famit-caller / aim-voice-agent / famit-panel. One box-mutating wave at a time.

### P0 — now/next
1. **RUN-PLATFORM Wave B — voice-preview real fix.** WHAT: backend full-buffer ≤32KB clip + FORCE
   `audio/mpeg` (both EL hosts) + 502-on-empty; FE real `.catch`/`onError`/caption + byte-sniff. WHY:
   the founder still can't hear preview (real cause = `Content-Type: text/plain`). Files: `caller.py`
   voice-preview route + `app/run/_voice-providers.tsx`. No flag. *Inbound/FE only.*
2. **RUN-PLATFORM Wave A — env billing + inbound provider-lock + funnels mount.** WHAT: `USD_INR=1→95.2`
   (Groq ~95× undercharged), `EL_RATE=1.5→4.76`, Sarvam v2/v3 split; pure `resolve_providers(fields)`
   leaf in prompt.py driving the inbound plugin build + metering label (flag `INBOUND_PROV_LOCK=1`);
   mount the funnels router (security). WHY: the cost ledger/dashboard is wrong; funnels is a
   mount-blocker. CAVEAT: fixes the LEDGER not the bill (wallet `_charge_call` is flat-rate → real
   billing = F4-wallet wiring, deferred). EARNER GATE: golden `verify_golden.py` exit 0 + FRESH box md5.
3. **RUN-PLATFORM Wave C — Run UI + real cost meter (FE).** Provider-lock banner, sourced cost breakdown,
   exclude-already-called toggle, pacing-defaults chip, inline voice-compare. `app/run/*`. PRICING
   HONESTY: show ONLY sourced numbers (Vobiz ₹0.65/min is fabricated; Premium below-COGS).
4. **Inbound never-silent apology guard (#29).** try/except in `aim_voice_agent.py` entrypoint → speak a
   graceful apology + clean hangup. WHY: a transient STT WS/DNS hiccup currently kills the job with
   SILENCE. *Inbound only.*
5. **Inbound STT FallbackAdapter (E/#30 sibling).** WHY: Sarvam singleton = P0 dead-air on any WS hiccup.
6. **WB-2 WhatsApp fallback cards (#50, P0, FE-only).** Treat `status="partial"` with suggestions as
   `ok:true`. Fix `app/whatsapp/_lib/waapi.ts`.

### P1 — big sequential builds
7. **Funnels/Media MOUNT-BLOCKER security fix (#7).** body-tenant → token `build_router` before serving
   `funnel_wiring`/`media_gen`. Must precede/accompany the Workflow wave.
8. **AIM Access + PIN (#6, `.wf/aim-access-and-pin.js` staged).** Repoint Setup tab → live
   `/ai-manager/numbers` CRUD + `POST /firewall/pin/change` (verify-old→set-new) + audit/grants/lockout.
9. **Workflow/Funnel execution (#8).** Human-language node labels + wire Trigger→leads→campaign→`/run` +
   ≥1 working template. Needs #7 first.
10. **W2 — context cache + pooled httpx (voice-brain).** `context_store.py` LRU+Redis+version-stamp +
    deploy pooled `voice_tools.py`. Flag `CTX_CACHE`. *Inbound only.*
11. **W3 — multi-channel memory (#13, keystone).** `lead_memory`/`lead_episodes` FORCE-RLS, durable
    post-call extraction (Hatchet/outbox + `FOR UPDATE`), WA episodes, CRM memory panel, inject before
    flow block. (P0-LEAK prerequisite already DONE.)
12. **RAG populate + wire (#12).** Seed `_global` telecaller FTS corpus via `POST /kb/seed-telecaller`;
    fuse into the single lookup; wire into inbound agent + WA reply brain. Corpus is currently EMPTY.
13. **W4 — Hinglish v2 register + telecaller KB + semantic turn-detector.** NEW render path (never mutate
    `_flow_block`); LiveKit `turn-detector` (`design/voice-quickwins.md` ready). *Inbound only.*
14. **Video Studio (#9).** prompt→video→preview→assets + add-API-key + manual upload + Images↔Videos
    toggle + attach to WA/Ads. (Manual-upload path works without a gen key.)
15. **Vault (#10).** PIN-gated per-vendor Fernet secret store; super-admin always-on; vendor
    hidden-by-default + toggle.
16. **Hardening Part 2 (#14).** Onboarding flow, billing/metering at scale, reliability/monitoring →
    sellable. (Part 1 done.)
17. **ai_asset go-wide (#15).** `/api/assets/raw` stream + per-tenant gate + events leg. (nginx proxy
    repoint is the FE-box-root-gated half.)
18. **Inbound recording Egress (#30).** `recording_url` column + LiveKit Egress on join + PAUSE around
    PIN + DO Spaces presigned. *Spaces creds present.*
19. **Inbound spend metering (#31).** Meter inbound minutes/handoff/templates/embeds into wallet/usage.
20. **DPDP delete-my-data endpoint (#33).** `POST /compliance/purge` cascading across memory/transcripts/
    leads/WA/AIM-sessions/Spaces. (Legal exposure.)
21. **Inbound analytics dashboard (#34).** containment/booking/transfer/hot/sentiment/language-mix.
    *FE + read queries only.*
22. **Mid-call `lead_is_hot` tool (#35).** Fire on buy-intent → mark hot real-time → trigger warm handoff.
    *Inbound only.*
23. **Warm-transfer no-answer fallback ladder (#36).** ring next → skip out-of-hours → voicemail-detect →
    logged callback + hot-WA + "team will call you back." Never a dead drop. (WA part Meta-gated.)
24. **Post-call workflow event (#37).** emit `call.completed` into the Workflow DSL.
25. **Customer-Mode "sales-in" inbound worker (#38, Mode A).** A separate inbound SALES brain (returning
    lead → memory+continue; new caller → DID→campaign→pitch). `design/CUSTOMER-MODE-BUILD-STATE.md`.
    *NEW worker, isolated.*
26. **Inbound warm-cache + pooled HTTP (#47).** Deploy pooled `voice_tools.py` + Redis hot-cache +
    pre-warm in the SIP window. Biggest latency win. *Inbound only.*
27. **Eval harness box re-run (#44).** `--freeze-baseline` + `selftest_bad_model` ON the box to exercise
    the latency half. Highest leverage — gates safe future voice changes.
28. **Run-Campaign audience-builder UX.** Composable filters + `lead_ids` + Excel + `batch_id`/`/leads/batches`.
29. **Cost-meter re-tune.** `tts_chars_per_min` 900→~330-360 in `llm_router/tiers.py` (pure data edit).

### P2 — forgotten / spec'd / lower urgency
30. **6 Creative sub-products** (specs ready, no caller.py/agent.py touch): Brochure/Catalog (WeasyPrint
    always-on, RERA-enforced), Creative-Batch (2-phase, creative-DNA taxonomy), Autonomous Ads Engine
    (bandit + spend tiers — propose/approve SAFE, real spend Ads-OAuth-gated), Landing-Page Builder
    (Python render core, local publish), 3D-Model (provider-gated), A/B Testing-Lab (cross-channel
    scoreboard — needs Creative-Batch first).
31. **LOWER `automation/` engines** (video/image/3D/ads/aimanager/marketing — directory EMPTY).
32. **Control-Layer C10** AI-Copilot in-prompt entitlement gate (T18).
33. **AIM step-up → runner approval-row wiring (#18).** Surface parked spend commands in the panel queue.
34. **Knowledge-gap + objection learning loop (#39).** Mine transcripts → draft KB chunks → curator UI.
    Needs #12 first.
35. **Switcher P2 (#20).** A/B voice-tier test, hard budget auto-pause, per-call ₹ in log, spend sparkline.
36. **Structured per-stage flow layer (#43).** greet→qualify→pitch→close stage agents. Needs eval harness.
37. **In-memory grounding bank (#45).** per-campaign objection/fact dict — cheaper interim for RAG.
38. **growth-os codegen fix (#22) → Integration Hub (#48) → Billing money-path + Gateway OIDC + Kafka SSE
    (#49).** Fix the `@growth-os/events` build first; then boot the 6-container stack.
39. **media_gen monolith retirement (#25).** After Video Studio + ai_asset go-wide.
40. **Hatchet caller.py cutover** (gated on P1) + **Logto caller.py wiring** (gated on DNS).
41. **CI registry-drift guard (C12)** — every nav href + router prefix must have a registry row.

---

## 5. ⛔ GATED-on-founder / external (do NOT build the blocked half; build the safe half + record)

- **DID `+918071583488` CARRIER-SPAM-BLOCKED** (Vobiz, since 2026-06-13 ~12:51 UTC). Blocks: campaign-run
  ring-proof, inbound-handoff final acceptance, OB-PROV, earner-LLM-fallback ring-gate. ACTION: rest the
  DID + Vobiz support (throttle/DLT-spam/suspension; rotate to a clean DID). NO test calls until cleared.
- **OB-PROV / earner-LLM fallback / outbound script-persona-memory (W-OB)** — require an `agent.py` edit
  → founder sign-off + a real in-window ring before+after.
- **Meta WhatsApp delivery** — payment 141006 + business verification + subscribe `messages` webhook +
  ONE approved real template (`FOUNDER-META-WHATSAPP-FIX.md`). Blocks WA delivery, `hot_lead_alert`,
  Submit-to-Meta, cold sends.
- **ModelScope ↔ Alibaba Cloud bind** (image key 401s; `FOUNDER-MODELSCOPE-BIND.md`).
- **Razorpay keys** — Payments dormant router + Credits/Billing (ON-HOLD until the founder asks).
- **Ads OAuth (Meta/Google)** — Ads Engine real spend + Ads flywheel + autonomous ads real spend.
- **DO droplet limit raise (3/3 full)** — AIM dedicated service + Growth OS 6-container stack + any new box.
- **FE-box root (`143.110.247.249`)** — the nginx `/api/assets/` proxy repoint (the one blocker to a
  clickable Creative-Studio browser demo) + Logto DNS nginx.
- **Video-gen API key** (fal.ai/Replicate/Wan) — Video Studio generation (manual upload works without).
- **3D-gen provider key** (Meshy/Tripo/Rodin or self-host GPU) — 3D studio generation.
- **External CRM keys** (Salesforce/HubSpot/Zoho) — CRM-sync adapters.
- **SambaNova Developer tier** — real LLM fallback (free tier 20/day too low).
- **GitHub private repo creation + push** — git is init'd locally, not pushed.
- **Cloudflare token re-scope** (bot-management + `auth` subdomain) — Logto DNS cutover.
- **Telegram @axcrio_bot /start + Bot Fight Mode toggle + burned-key rotation (ElevenLabs/Vobiz)** —
  fortress finishing tasks (not earning-blockers).

---

## 6. 📏 STANDING RULES (the founder laws + the why behind each)

1. **FULL AUTONOMY, day & night.** Build the WHOLE production-grade thing from a rough sketch; proactively
   ADD the features he forgot; reserve questions for genuine forks; ask ONLY via the AskUserQuestion tool
   (prose questions kill the session + burn ~30-40% on restart).
2. **Pipeline every task: Explore → Research → Design → Execute → Verify on the REAL flow.** A green
   subagent report is NOT a "done" — only the founder's real integrated use is truth. *Born from
   repeated "FIXED" claims that were broken on his real call.*
3. **Every backend capability ships with a FRONTEND control UI** (full CRUD + configure + test/preview,
   real-time, Core_2 kit, Inter Display, zero raw hex). *Born from repeated backend-only half-builds.*
4. **A green report ≠ a working product. A real ring = `inviteToRingingMs>0`/180/200 in livekit-sip, NOT
   the agent-join line.** *Born from reading 486-Busy as "it rang" for multiple waves.*
5. **NEVER touch the earner.** `agent.py`, the outbound trunks, the firewall, the SIP container — never
   edited/restarted for any new feature; every change additive+isolated+earner-regression-gated; inbound
   work lives in `aim_voice_agent.py`/`caller.py`. *Born from dropping 219 INVITEs on a shared-infra edit.*
6. **NO outbound test calls** — a real call is the FOUNDER's job. *Born from spam-flagging the DID.*
7. **Never burn the founder's PAID credits** (free providers; 1 test max). *Born from burning $5 OpenRouter.*
8. **Compaction-proof + crash-safe + granular waves; NEVER end a turn with zero waves running while the
   queue remains** (the completion notification re-fires the loop). Commit per verified unit; update
   ORCHESTRATOR + AGENT_LEARNINGS + NEXT-BIG-BUILDS. *Born from limit-resets killing near-finished waves.*
9. **Autonomy honesty** — the local CLI runs ONLY while the laptop is on + the session alive; only cloud
   routines (`/schedule`) survive sleep. Never imply 24/7 background work.
10. **Explore the real logs FIRST, don't assume root cause.** Trace any override/flag END-TO-END (UI→API→
    the toggle it controls). *Born from blaming code for window-gates, ₹0.19 Vobiz balance, Groq quota,
    carrier blocks, and the `force=true` vs `now` silent no-op.*
11. **FORTRESS deploy recipe** — build LOCALLY (on-box `next build` OOMs the 2GB box → temp 4G swapfile
    if on-box) → backup-first → md5-gate the scp before extract → atomic swap → chown deployuser → restart
    famit-panel ONLY → verify 200 + new BUILD_ID on loopback + edge. *Born from silent scp truncation +
    OOM.*
12. **Always presign Spaces URLs; HEAD-verify non-empty audio before presigning.** *Born from the
    private-URL→403-blank bug recurring across images/recordings/video, and a 486-busy 0-byte OGG.*
13. **Voice tools loose/strict-OFF; instructions IMPERATIVE same-turn; language = MIRROR the caller.**
    *Born from the small Groq model announcing instead of firing the tool, strict-schema 400-storms →
    dead air, and a Hinglish pin stopping language mirroring.*

**Cross-cutting invariants (apply everywhere):** tenant FROM TOKEN never body; money INTEGER PAISE never
float; ONE money path (hold-backend tag); fail-closed everywhere (unknown=HIDDEN, missing-creds=
not_configured); PORT Core_2 never approximate; the LLM is INPUT never the authority (risk/category/facts
are deterministic/verbatim); serialize on shared files (one agent per file — `caller.py`/`globals.css`/
`navigation.tsx`); md5-verify after every scp; the capsy-venv trap (`/opt/capsy-agent/.venv`); versions
not overwrites; REAL-only proof never fabricate; box is source of truth (the droplet_work mirror lags);
every voice-path wave runs an integrated turn-loop smoke; 429=quota(add capacity), 400=code bug(fix/revert).

---

## 7. 📖 READ-ORDER for any new / post-compaction session

0. **If resuming from a harness compaction:** Write the injected summary VERBATIM to
   `memory/session-summaries/<YYYY-MM-DD-HHMM>-<tag>.md` + index it (per `memory/session-summaries/README.md`).
1. **THIS file** (`MASTER_DNA_PLAN.md`) — full DNA.
2. **`ORCHESTRATOR.md`** — the live bird's-eye ledger (latest wave PLAN+OUTPUT+STATUS; always current).
3. **`AGENT_LEARNINGS.md`** — append-only mistakes/learnings (read before starting any wave).
4. **`TONIGHT-AUTONOMOUS-BUILD.md`** — the night-build loop + priority order + LIVE-NOW waves.
5. **`NEXT-BIG-BUILDS.md`** — the canonical 1-50 backlog (grind top-down).
6. **`PLAYBOOK.md`** — distilled "what I got wrong + the rule that prevents each."
7. **Then, per the wave's domain:** `MASTER_PLAN.md`, `ARCHITECTURE_DECISION.md`/`ARCHITECTURE.md`,
   `design/VOICE-BRAIN-MASTER-PLAN.md`, `design/RUN-PLATFORM-MASTER-PLAN.md`, `design/spec-control-layer.md`
   + `design/control-security.md`, the relevant `memory/brain/*.md` node + `memory/build_log/wave-*.md`,
   and the per-wave STATE file (`design/*-STATE.md`).

**Live state at synthesis (2026-06-14):** Last completed box-mutating waves = W1 → P0-LEAK (both
DONE+DEPLOYED+VERIFIED). RUN-PLATFORM-MASTER-PLAN written. Next box-mutating waves (in order): RUN-PLATFORM
B (preview) → A (env billing + provider-lock + funnels mount) → C (Run UI) → W2 → voice-brain memory →
then NEXT-BIG-BUILDS top-down. The earner gate runs before+after EVERY box-mutating wave.

---

*End of MASTER_DNA_PLAN.md — the durable brain. Keep it faithful; append, never compress away the why.*
