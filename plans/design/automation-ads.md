# DESIGN SPEC — Paid-Ads Automation (`droplet_work/automation/ads/`)

> Execution-ready spec for an **autonomous Meta + Google paid-ads module**: AI drafts /
> launches / optimizes campaigns from a brief, with **HARD spend caps**, **auto-pause on
> CPL breach**, and a **human approval gate** before anything goes live.
>
> **NO git** (orchestrator commits). **NEW files only under `droplet_work/automation/`.**
> **DO NOT edit `caller.py` / `agent.py`** — this module exposes pure callables + a
> deferred FastAPI router; final wiring into the spine is deferred (documented seam only).
> **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS**: every entry point returns
> `{"status": "not_configured"}` and **NEVER raises** until the founder pastes keys —
> exactly like `whatsapp.py` and the `automation/marketing/` sibling. Verifiable **offline**
> (no live external calls). Sits alongside `automation-marketing.md` (owned earned/email/SMS/
> social) — this doc owns **paid spend** only; zero overlap.

Research date: 2026-06-09. All chosen tools verified ACTIVE (release dates cited inline).

---

## 0. VERDICT & SCOPE (settled — do not relitigate)

**Verdict.** There is **no production-grade, self-hostable OSS "autonomous ad optimizer."**
What exists in 2026 is (a) the two **official, actively-maintained vendor SDKs** and (b) a
swarm of thin wrappers / MCP servers / Claude-Code "skills" that *ride those same SDKs*
(meta-ads-kit, claude-ads, NotFair, awesome-agentic-advertising — all 2025-2026, but each is
a wrapper or a prompt-pack, none is a self-hostable optimization engine you'd put money
behind). So the honest, durable architecture is **compose, don't adopt**:

> **Official SDKs (spend rails) + a small deterministic rules engine (the breaker/optimizer)
> + the existing in-house LLM seam (creative text) + the platforms' own auto-bidding
> (the actual ML optimizer).**

We DO NOT bundle any third-party "AI ads agent." We DO NOT self-host an optimizer (there is
nothing worth self-hosting; the real optimizer is Meta/Google auto-bidding, which is free and
better than anything we'd build). Self-host wins for the *marketing* suite (Listmonk/Postiz);
for *paid ads* it does **not** win — the rails are the platforms' APIs and the ML is theirs.
That is a real-vs-hype honesty point, stated up front (§9).

**The load-bearing thing here is money leaving the building with no human in the loop.** So
this spec is **spine-first**: the spend-safety invariant and its enforcement layers are
designed before the "AI creates ads" layer, which is the cheap, replaceable part on top.

### 0.1 THE INVARIANT (mirrors the wallet no-oversell invariant)

> **INVARIANT A — cumulative spend across a tenant's active ad campaigns can never
> *intentionally* exceed the configured hard cap.** No single layer guarantees this to the
> cent; it is enforced by **defense-in-depth** (§5), and the honest residual overshoot window
> is stated explicitly (§5.4, §9). The platform-native **daily budget** set via API at create
> time is the **real floor**; our local breaker is a **second** layer.

> **INVARIANT B — nothing goes live without a human.** AI output lands in a `DRAFT` /
> `PAUSED` campaign; activation requires an explicit human **approval** action (reuse the
> existing **firewall step-up** pattern — do not invent a new gate).

> **INVARIANT C — every AI decision and every spend/pause/activate event is appended to an
> immutable audit ledger** (reuse `audit.py`). No silent autonomous money moves.

### 0.2 The non-negotiable house contract (verified against `whatsapp.py`, `audit.py`, `config.py`)

1. Read config via `config.get(key, default)` (which is `os.getenv` + optional Doppler) —
   never read `os.environ` directly for secrets.
2. With creds absent, **every public function returns**
   `{"ok": False, "status": "not_configured", "provider": <p>, ...}` with **zero network I/O**
   and **never raises** (the `whatsapp.py` `meta_configured()` / `is_configured()` gate).
3. `httpx` is imported defensively (`try/except → None`); if missing, return
   `error:httpx_unavailable`, never crash on import.
4. Secrets are redacted in any log (first/last 4 only) — reuse `vendors.redact`.
5. Module imports cleanly with an **empty env** (import-safe + dormant-safe).
6. Sync **and** async public variants where the spine event loop will call it (the
   `send_whatsapp` / `send_whatsapp_async` pairing).

---

## 1. CHOSEN TOOLS + WHY (researched 2026-06; ACTIVE, none abandoned)

### 1.1 Meta — official **`facebook-business`** Python SDK (Marketing API)
- PyPI `facebook-business`; current major **v25.x** tracking **Marketing API v25 /
  Graph API v24-25**. Maintained by Meta; the canonical, supported path. (`pip install
  facebook-business`.)
- We use it for: AdAccount → Campaign → AdSet → AdCreative → Ad create/read, budget set,
  status flips (ACTIVE/PAUSED), and **Insights** (spend, results, CPL).
- **API version is an env knob** (`META_ADS_API_VERSION`, default newest GA at deploy ~`v25`)
  — because Meta ships ~quarterly and any hardcoded version rots. Verify current GA at deploy.

### 1.2 Google — official **`google-ads`** Python client
- PyPI `google-ads`, latest **31.0.0 (2026-05-13)**, Python ≥3.9. Maintained by Google.
- **Cadence changed Jan 2026 to MONTHLY releases**; up to 4 major API versions live at once,
  ~12-month support each. **v19 sunset 2026-02-11; v20 EOL ~Jun 2026; v21 EOL ~Aug 2026;
  v22 EOL ~Oct 2026.** ⇒ **DO NOT hardcode a version.** `GOOGLE_ADS_API_VERSION` env knob,
  default to the newest GA at deploy (≥`v22` as of mid-2026). The cadence guarantees any
  fixed number rots within a quarter; config removes the dependency on us being right today.
- We use it for: Campaign / AdGroup / Ad / Budget mutate, status flips, and
  `GoogleAdsService.search` GAQL for spend + conversions + CPL metrics.

### 1.3 Creative text — **reuse the existing in-house LLM seam; NO new vendor**
- Ad copy (headlines, primary text, descriptions, keyword ideas, A/B variants) is generated
  through the **existing `llm_router_processor` / Groq path** already in the spine. We add a
  thin `creative.py` that builds prompts and calls the existing seam via a small injected
  callable — **no new LLM dependency, no new key.** (Same decision as `automation/marketing/
  content.py`.)
- Creative **images**: out of scope here — defer to `automation/image/` (sibling spec). Ads
  module accepts an optional image asset id/URL but does not generate images itself. Honest
  note: self-hosting image-gen loses at low ad volume; not our problem to solve in this module.

### 1.4 The "optimizer" — **a small deterministic rules engine + platform auto-bidding**
- The real ML optimizer is **Meta Advantage+ / Google Smart Bidding** (free, on-platform,
  better than anything we'd build). We set the bid strategy to platform auto-bidding and let
  it optimize delivery.
- **On top** we run a deterministic `optimizer.py` rules pass (pause losers, shift budget to
  winners within the cap, flag creative fatigue) — explainable, auditable, offline-testable.
  No black-box "AI agent" makes spend decisions; rules + caps do, and every decision is
  logged with its reason.

### 1.5 Conversion / CPL tracking (load-bearing for auto-pause)
- **Meta:** CPL requires a **Pixel + Conversions API (CAPI)** event (`Lead`). The standalone
  Offline Conversions API was **discontinued 2025-05-14**; **unified CAPI is the only path.**
  We read CPL from **Ads Insights** (`cost_per_action_type` / `actions` for the lead action),
  not by computing it ourselves — single source of truth = the platform.
- **Google:** CPL requires a configured **conversion action** (and optionally offline
  conversion import for true qualified-lead CPL). We read `metrics.cost_per_conversion` and
  `metrics.conversions` via GAQL.
- **Honest dependency:** if the founder has NOT set up Pixel+CAPI / a conversion action, CPL
  is unmeasurable ⇒ the breaker **falls back to the spend-cap layer only** and the optimizer
  reports `status: "blocked_no_conversion_tracking"` for CPL rules. We never invent a CPL.

---

## 2. PACKAGE LAYOUT (new files only; nothing outside `droplet_work/automation/`)

```
droplet_work/automation/
  __init__.py                  # import-safe with empty env
  ads/
    __init__.py
    config.py                  # env reading + *_configured() gates (whatsapp.py style)
    providers/
      __init__.py
      base.py                  # AdProvider ABC: the provider-agnostic interface (§3.1)
      meta.py                  # facebook-business adapter; status()-gated, dormant-safe
      google.py                # google-ads adapter; status()-gated, dormant-safe
      noop.py                  # always not_configured — the default when nothing set
    creative.py                # ad-copy gen via INJECTED existing LLM callable (no new vendor)
    planner.py                 # brief -> CampaignPlan (deterministic skeleton + LLM copy)
    guardrails.py              # HARD caps, approval-gate state, CPL-breach breaker (§5)
    optimizer.py               # deterministic rules pass (pause/shift/fatigue)
    metrics.py                 # normalize Insights/GAQL -> common MetricsSnapshot (§4.3)
    meter.py                   # spend estimate (estimated, groq_meter.py style)
    store.py                   # JSON state under var/ads/ (read/write via injected fns)
    service.py                 # ORCHESTRATION facade: the pure callables the spine calls (§3.2)
    endpoints.py               # FastAPI APIRouter — DEFINED here, MOUNTED later by spine
  tests/
    test_ads_offline.py        # ZERO-network acceptance test (§8)
```

**Import safety:** vendor SDKs imported lazily *inside the adapter*, `try/except → None`.
With `facebook-business` / `google-ads` not installed AND no creds, the package still imports
and every call returns `not_configured`.

---

## 3. INTERFACES (exact signatures — a build agent codes to these)

`status` vocabulary (extends the marketing module's):
`not_configured | draft | pending_approval | active | paused |
blocked_cap_exceeded | blocked_cpl_breach | blocked_no_conversion_tracking |
blocked_not_approved | dry_run | error:<...>`

### 3.1 `providers/base.py` — the provider-agnostic interface (one API, many platforms)
```python
class AdProvider(ABC):
    id: str                                   # "meta" | "google" | "noop"
    def status(self) -> str: ...              # "configured" | "not_configured" | "error"
    # all methods return a dict, never raise:
    def create_campaign(self, plan: dict, *, paused: bool = True) -> dict: ...
    def set_budget(self, campaign_ref: str, daily_minor: int, lifetime_minor: int|None) -> dict: ...
    def set_status(self, campaign_ref: str, state: str) -> dict: ...   # "ACTIVE"|"PAUSED"
    def insights(self, campaign_ref: str, window: str = "today") -> dict: ...  # -> MetricsSnapshot
    async def ...  # async twins where the spine loop calls them
```
`meta.py` / `google.py` implement this against their SDK; `noop.py` returns
`{"status":"not_configured"}` for everything. `get_provider(name)` returns the configured one
or `noop`. **Mirrors `whatsapp.py`'s per-provider body-builder pattern, generalized to CRUD.**

### 3.2 `service.py` — the pure callables the spine wires later (the public surface)
```python
def propose_campaign(tenant_id: str, brief: dict, *, llm=None) -> dict
    # brief -> CampaignPlan via planner+creative; persists DRAFT; status="pending_approval".
    # NEVER touches a platform. Pure + offline-safe. Logs ai_decision to audit.

def approve_campaign(tenant_id: str, plan_id: str, actor: str, stepup_token: str) -> dict
    # Firewall step-up gate (Invariant B). On success: provider.create_campaign(paused=True),
    # set_budget(daily<=cap), then set_status ACTIVE. Audited. Honors dry_run/not_configured.

def poll_and_enforce(tenant_id: str, *, now=None, provider=None) -> dict
    # THE BREAKER. Pull insights for each active campaign -> MetricsSnapshot -> guardrails.
    # Pause any campaign breaching cap or CPL (min-sample met). Returns actions taken.
    # Deterministic; injectable metrics for offline test. Audited.

def optimize(tenant_id: str, *, dry_run=True, provider=None) -> dict
    # Deterministic rules pass (pause losers / shift budget within cap / flag fatigue).
    # dry_run returns the plan without mutating. Audited.

def pause_all(tenant_id: str, reason: str) -> dict   # kill switch
def status(tenant_id: str) -> dict                   # campaigns + spend vs cap + flags
```
All have `_async` twins where needed. `llm`, `provider`, `now`, and the store read/write fns
are **injected** (default to real impls) so the offline test runs with fakes and **zero
network**.

### 3.3 `guardrails.py` — the enforcement primitives
```python
def caps(tenant_id: str) -> dict          # {daily_cap_minor, lifetime_cap_minor, cpl_max_minor,
                                          #  cpl_min_conversions, poll_minutes}
def check_spend(snapshot, caps) -> dict   # {breach: bool, reason, headroom_minor}
def check_cpl(snapshot, caps) -> dict     # {breach: bool, reason} ; breach ONLY when
                                          #   conversions >= cpl_min_conversions AND
                                          #   cpl > cpl_max  (no pausing on tiny samples)
def require_approval(tenant_id, plan_id, actor, stepup_token) -> dict   # firewall step-up
```

### 3.4 `endpoints.py` — deferred FastAPI router (DEFINED, not mounted this phase)
`router = APIRouter(prefix="/ads", tags=["ads"])`, all handlers `manager`-scoped except reads:
- `POST /ads/campaigns/propose` → `service.propose_campaign`
- `GET  /ads/campaigns` / `GET /ads/campaigns/{id}` → `service.status`
- `POST /ads/campaigns/{id}/approve` (step-up) → `service.approve_campaign`
- `POST /ads/campaigns/{id}/pause` → `service.pause_all` (scoped)
- `POST /ads/optimize` (dry_run default) → `service.optimize`
- `GET  /ads/health` → provider `status()` map (public/read)
Wiring note in the docstring: the spine will `app.include_router(router)` and add a
`scheduler_loop` tick calling `poll_and_enforce` every `poll_minutes` — **NOT done here**.

---

## 4. DATA MODEL (files under `var/ads/`, JSON; same read/write seam as the spine)

### 4.1 `var/ads/plans.json` — proposed/approved campaigns
```json
{"plan_id","tenant_id","provider":"meta|google","brief":{...},
 "campaign":{"name","objective","audience","creatives":[...],"budget_daily_minor"},
 "status":"pending_approval|active|paused","campaign_ref":"<platform id|null>",
 "created_ts","approved_by","approved_ts","cap_minor","cpl_max_minor"}
```
### 4.2 `var/ads/spend_ledger.jsonl` — append-only spend snapshots (audit-adjacent)
One line per poll: `{ts, tenant_id, plan_id, spend_today_minor, spend_lifetime_minor,
conversions, cpl_minor, action:"none|paused_cap|paused_cpl"}`.
### 4.3 `MetricsSnapshot` (normalized across both platforms — the breaker's only input)
```python
{"provider","campaign_ref","window","spend_minor":int,"impressions":int,"clicks":int,
 "conversions":int,"cpl_minor":int|None,"currency":"INR","fetched_ts"}
```
Both adapters MUST emit this exact shape (Meta from Insights `actions`/`cost_per_action_type`;
Google from GAQL `metrics.cost_micros`, `metrics.conversions`, `metrics.cost_per_conversion`).
`cpl_minor=None` ⇒ no conversion tracking ⇒ CPL rule self-disables (`blocked_no_conversion_tracking`).

---

## 5. SPEND / APPROVAL / AUDIT GUARDRAILS — the spine (defense-in-depth)

### 5.1 Layer 1 — platform-native budget cap (the REAL floor)
At `create_campaign` we set the platform **daily budget** (and **lifetime budget** when
provided) via the SDK, capped to `caps.daily_cap_minor`. The platform itself will not spend
past its own daily budget. This is the strongest guarantee and it lives on the platform, not
in our process.

### 5.2 Layer 2 — local polling circuit-breaker (`poll_and_enforce`)
Every `poll_minutes` (default 30) we pull insights → `MetricsSnapshot` → `check_spend` /
`check_cpl`. On breach we call `set_status(PAUSED)` immediately and append to the spend
ledger + audit. Catches: misconfigured platform budget, runaway lifetime spend, CPL blowout.

### 5.3 Layer 3 — approval gate (Invariant B) + Layer 4 — audit (Invariant C)
Nothing activates without `approve_campaign` passing the **firewall step-up** (reuse existing
`firewall.py` step-up token bound to the actor — do NOT roll a new one). Every propose /
approve / pause / budget-shift writes an `ai_decision` + action event to `audit.py`.

### 5.4 CPL-breach rule — guarded so it is NOT hype
- **CPL** = cost per lead = `spend_minor / conversions` for the campaign window (or read
  directly from the platform's `cost_per_action_type` / `cost_per_conversion`).
- **Min sample:** pause on CPL ONLY when `conversions >= cpl_min_conversions` (default **15**)
  — never pause on 3 clicks / 1 lead. Below the sample, CPL is informational, not actionable.
- **Cadence:** poll every `poll_minutes` (default 30; configurable). Breach is evaluated on
  the rolling window snapshot, not a single spike.
- No conversion tracking ⇒ rule self-disables (`blocked_no_conversion_tracking`), breaker
  still enforces the spend cap.

### 5.5 HONEST residual-overshoot statement (the sentence the founder most needs)
> The platform **daily budget** (Layer 1) is the real cap. Our local breaker (Layer 2) is a
> **second** line of defense, and because it polls on an interval there is a **latency window
> between polls in which spend can overshoot the breaker's view** (the platform's own daily
> budget still bounds it). The local breaker therefore **reduces** overshoot risk and adds CPL
> protection the platform budget alone does not; it is **not** a to-the-cent guarantee on its
> own. Anyone who tells you a polling breaker guarantees the cap to the rupee is selling hype.

### 5.6 Guardrails summary table
| Guarantee | Mechanism | Default |
|---|---|---|
| No accidental spend | `ADS_DRY_RUN=1` + providers `not_configured` | ON (nothing spends) |
| Hard daily cap (floor) | platform daily budget set ≤ cap at create | enforced on activate |
| Cap breaker | `poll_and_enforce` pauses on snapshot ≥ cap | every 30 min |
| CPL breaker | pause when CPL>max AND conversions≥15 | min-sample guarded |
| Nothing live w/o human | firewall step-up on `approve_campaign` | required |
| Full audit | `audit.py` on every decision/spend/pause | always |
| Kill switch | `pause_all(tenant)` | one call |

---

## 6. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

> All blank today ⇒ module is a graceful NO-OP. The **non-obvious, lead-time** items are
> flagged ⏳ — these gate the founder's timeline and are the valuable part of this list.

### 6.1 Meta (Facebook/Instagram ads)
| Env var | What / where to get it | Notes |
|---|---|---|
| `META_ADS_APP_ID` / `META_ADS_APP_SECRET` | Meta App (developers.facebook.com) | reuse the WhatsApp app if same business |
| `META_ADS_ACCESS_TOKEN` | **System User** token (Business Settings) with `ads_management`, `ads_read`, `business_management` | long-lived, not a user token |
| `META_ADS_ACCOUNT_ID` | Ad Account id (`act_<digits>`) | the account that gets billed |
| `META_ADS_PAGE_ID` | the Facebook **Page** ads run from | ⏳ required to create ads |
| `META_BUSINESS_ID` | Business Manager id | for asset scoping |
| `META_PIXEL_ID` + `META_CAPI_TOKEN` | Pixel + **Conversions API** dataset token | ⏳ required for **CPL tracking**; offline-conversions API is dead (2025-05-14), CAPI only |
| `META_ADS_API_VERSION` | default newest GA (~`v25`) | verify at deploy |
| **On-platform** | Business Verification + **Advanced Access** App Review for `ads_management`/`business_management` (2026: ≥500 API calls / 15 days, <15% error over last 500) | ⏳⏳ **multi-day approval**; Standard access works for own account, Advanced needed for multi-tenant |
| **On-platform** | **Payment method on the Ad Account** | money is billed here, by Meta, to the founder |

### 6.2 Google Ads
| Env var | What / where | Notes |
|---|---|---|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | API Center under a **Manager (MCC)** account | ⏳⏳ **approval required** — starts Test→Explorer→**Basic**→Standard; production access needs review, lead time real |
| `GOOGLE_ADS_CLIENT_ID` / `GOOGLE_ADS_CLIENT_SECRET` | OAuth2 client (Google Cloud Console) | |
| `GOOGLE_ADS_REFRESH_TOKEN` | OAuth2 refresh token (one-time consent flow) | long-lived |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | the **MCC** customer id (no dashes) | manager account |
| `GOOGLE_ADS_CUSTOMER_ID` | the **operating** ad account id | the one that's billed |
| `GOOGLE_ADS_API_VERSION` | default newest GA (≥`v22` mid-2026) | DO NOT hardcode; monthly cadence |
| **On-platform** | a configured **conversion action** (+ optional offline import) | ⏳ required for CPL; else cap-only |
| **On-platform** | **Billing set up on the Google Ads account** | money billed here, by Google, to the founder |

### 6.3 Module flags (founder-tunable, safe defaults)
`ADS_DRY_RUN=1` (default — nothing spends), `ADS_DAILY_CAP_MINOR`, `ADS_LIFETIME_CAP_MINOR`,
`ADS_CPL_MAX_MINOR`, `ADS_CPL_MIN_CONVERSIONS=15`, `ADS_POLL_MINUTES=30`,
`ADS_REQUIRE_APPROVAL=1` (default — approval mandatory).

---

## 7. CONTROL FLOW — the whole product in one paragraph
Founder posts a **brief** → `propose_campaign` builds a deterministic campaign skeleton and
fills copy via the existing LLM seam → persists a **DRAFT** at `pending_approval`, audited,
**no platform touched** → founder reviews and calls `approve_campaign` (firewall step-up) →
provider creates the campaign **PAUSED**, sets daily budget ≤ cap, then flips **ACTIVE**,
audited → the deferred scheduler tick calls `poll_and_enforce` every 30 min, pulling
Insights/GAQL into a `MetricsSnapshot`, and **pauses any campaign breaching the cap or CPL
(min-sample met)**, logging every action → `optimize` (dry-run by default) proposes
pause-loser / shift-to-winner-within-cap moves the founder can apply. With no creds, every
step returns `not_configured` and the suite **cannot spend a rupee**.

---

## 8. OFFLINE ACCEPTANCE TEST (`tests/test_ads_offline.py` — ZERO network)
Asserts the invariants concretely (mirrors the wallet OVERSELL TEST — not hand-waved):
1. **Dormant guarantee:** with empty env, `propose_campaign` / `approve_campaign` /
   `poll_and_enforce` / `optimize` / `status` each return `status` in
   `{not_configured, dry_run}`, `ok is False/absent`, and **raise nothing**. Patch
   `httpx`/SDKs to a sentinel that raises if called → assert **never called** (proves zero
   network while dormant).
2. **Spend-cap breaker fires:** inject a fake `MetricsSnapshot` with
   `spend_today_minor >= daily_cap_minor` and a fake provider recording `set_status` calls →
   assert `poll_and_enforce` returns `action:"paused_cap"` and the fake provider received
   `set_status(PAUSED)` for that campaign.
3. **CPL breaker + min-sample guard:** (a) snapshot with `cpl_minor > cpl_max` and
   `conversions >= 15` → asserts `paused_cpl`. (b) **same CPL but `conversions = 3`** →
   asserts **NO pause** (min-sample guard holds — the key honesty test). (c)
   `cpl_minor = None` → asserts `blocked_no_conversion_tracking`, cap rule still active.
4. **Approval gate:** `approve_campaign` with a missing/invalid step-up token →
   `blocked_not_approved`, provider `create_campaign` **never called**; with a valid fake
   token → provider called with `paused=True` then `ACTIVE`.
5. **Audit:** every propose/approve/pause writes ≥1 line via an injected fake audit sink.
6. **Provider-agnostic parity:** both `meta` and `google` fake adapters produce the identical
   `MetricsSnapshot` keys, so the breaker is platform-blind.
Run: `pytest droplet_work/automation/tests/test_ads_offline.py -q` — all green, **no socket**.

---

## 9. HONEST REAL-vs-HYPE
- **REAL:** official Meta + Google SDKs (maintained, the supported rails); platform-native
  budget caps + auto-bidding (free, strong); LLM-generated ad copy (genuinely useful drafts);
  a deterministic, auditable breaker/optimizer; a hard approval gate. This composes into a
  legitimate "AI runs ads under guardrails" product.
- **HYPE / honest limits:**
  - There is **no magic OSS "autonomous optimizer"** — the real optimizer is the platforms'
    auto-bidding; we orchestrate, we don't out-ML Google/Meta.
  - The local breaker is **defense-in-depth, not a cent-perfect cap** (§5.5). The platform
    daily budget is the floor.
  - **CPL is only as real as the founder's conversion tracking.** No Pixel+CAPI / conversion
    action ⇒ no CPL ⇒ cap-only enforcement. We never fabricate a CPL.
  - "AI creates the whole ad" is **draft-quality**: copy is good, targeting/objective skeleton
    is rules-based, and a **human still approves**. It replaces ~80% of the grunt work, not
    the judgment.
  - **Lead time is real:** Google developer-token approval and Meta Advanced-Access App
    Review + Business Verification are multi-day, founder-side, and gate go-live (§6).
  - Self-hosting **does not win** for paid ads (unlike the email/social suite) — the rails and
    the ML are the platforms'.

## 10. BUILD ORDER (one verifiable UNIT each; test after every unit; commit per unit)
1. `config.py` + `providers/{base,noop}.py` + package skeleton → import-safe with empty env.
2. `guardrails.py` + `metrics.py` (`MetricsSnapshot`) → **unit-test the cap & CPL+min-sample
   logic in isolation** (no providers).
3. `service.poll_and_enforce` with injected provider/metrics → **the breaker test (§8.2-8.3)**.
4. `planner.py` + `creative.py` (injected LLM) + `service.propose_campaign` → DRAFT + audit.
5. `service.approve_campaign` with firewall step-up → approval-gate test (§8.4).
6. `providers/meta.py` then `providers/google.py` (lazy SDK import, dormant-safe) → parity
   test (§8.6); still `not_configured` with no creds.
7. `optimizer.py` (dry-run) + `meter.py` (estimated) + `endpoints.py` router (defined, not
   mounted) + full `test_ads_offline.py` green.
8. Document the deferred spine seams (router mount + scheduler tick) in `endpoints.py`
   docstring — **do not touch `caller.py`**.

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09 against the LIVE codebase (`droplet_work/`) and external sources.
**External facts all verified TRUE** — keep them; **four codebase references were wrong** and would
have stalled or misled a build agent. Fixes below are authoritative; where they conflict with the
body above, **these win**.

### Verified TRUE (no change needed)
- Meta **Marketing API v25** is real (Meta blog "Introducing Graph API v25.0 and Marketing API
  v25.0", Feb 2026); `facebook-business` actively maintained on PyPI/GitHub. §1.1 stands.
- Meta **offline-conversions API discontinued 2025-05-14, CAPI-only** — confirmed exactly. §1.5/§6.1 stand.
- **`google-ads` 31.0.0 (2026-05-13)**, monthly cadence (31.0.0 May / 30.1.0 Apr / 30.0.0 Mar /
  29.2.0 Feb), version-sunset story all confirmed. §1.2 + the env-knob design stand.
- **`audit.py`** (`record(actor, action, object_type, object_id, …, meta=)`, append-only JSONL,
  never raises), **`config.get`/`config.require`** (Doppler-over-env resolver), and
  **`vendors.redact`** (in `vendors/__init__.py`, first/last-4 masking) all EXIST as the spec
  assumes. Audit/redaction/config reuse is real. The `vendors/*` `status()` →
  `configured|not_configured|error` pattern exists and is the correct model.
- Dormant-until-creds + non-breaking + "does not touch `caller.py`/`agent.py`" is genuinely
  achievable; `whatsapp.py` proves the exact pattern (returns `{"status":"not_configured"}`,
  never raises, lazy/defensive `httpx` import). §0.2 items 2/3/5/6 stand.
- The §5.5 **residual-overshoot honesty statement is correct** — a polling breaker is NOT a
  cent-perfect cap; the platform daily budget is the floor. Keep it verbatim.

### FIX 1 — Invariant B's "firewall step-up" primitive **DOES NOT EXIST** (most serious)
The body references "reuse the existing **firewall step-up** pattern / `firewall.py` step-up token
— do not invent a new gate" (§0.1 Inv B, §3.3, §5.3, §3.2 `approve_campaign`). **There is no
`firewall.py` and no step-up / re-authentication mechanism anywhere in `droplet_work/`.** What
EXISTS is `auth.py`: HS256 JWT access tokens (15-min, claims `sub`/`role`/`is_admin`) + revocable
rotating refresh tokens + a `_VERIFY_PASSWORD(email, password)` callback into the tenant store.
→ **The approval gate is a primitive this module MUST BUILD, not "reuse."** Concrete spec:
`require_approval(tenant_id, plan_id, actor, stepup_token)` verifies a **fresh step-up token** that
the activation flow mints by re-checking the manager's password via `auth`'s existing
`_VERIFY_PASSWORD` (or by requiring a JWT whose `role=="manager"`/`is_admin` issued < N minutes ago,
i.e. `iat` freshness). Store the one-time `stepup_token` in `var/ads/stepup.json` (single-use, short
TTL), bound to `(actor, plan_id)`. This is INSIDE the module (new file `guardrails.py`), import-safe
and offline-testable with a fake verifier — it does not depend on a non-existent `firewall.py`.
Invariant B is preserved; only its *implementation source* changes from "reuse" to "build on
`auth.py`'s password-verify + JWT-role". The §8.4 approval-gate test is unchanged (inject a fake
verifier; invalid token ⇒ `blocked_not_approved`, `create_campaign` never called).

### FIX 2 — the `automation/` + `automation/marketing/` sibling **DOES NOT EXIST YET**
The body anchors to it repeatedly ("exactly like … the `automation/marketing/` sibling",
"same decision as `automation/marketing/content.py`", "Sits alongside `automation-marketing.md`").
**No `automation/` directory exists in `droplet_work/`** today. → These are **planned-sibling**
references, not live code to copy. **The authoritative live pattern to mirror is `whatsapp.py`
(dormant/no-raise sender) and `vendors/*` (`status()` + `redact` + dormant cost adapters)**, both of
which DO exist. Build the `automation/ads/` tree as NEW (the package layout in §2 is correct as a
greenfield create); do not block waiting for a marketing sibling. If `automation-marketing.md` is
built in the same wave, keep zero file overlap (it owns earned/owned channels, this owns paid spend).

### FIX 3 — name the LLM seam correctly (decision is right, label was loose)
§1.3 says "existing `llm_router_processor` / Groq path … via a small injected callable." The real
seam is the in-house **`llm-router` HTTP service** (`LLM_ROUTER_URL`, default
`http://llm-router:8111`), wrapped by `llm_router_processor.py`; ad-copy generation should hit its
**batch endpoint `POST /v1/llm/generate`** (the streaming `stream_text` endpoint is for live voice,
not copy drafting). → The "no new vendor / inject a callable into `creative.py`" decision is
**SOUND and unchanged**; just target `/v1/llm/generate` on `LLM_ROUTER_URL`. The injected-callable
keeps the offline test network-free (fake LLM fn).

### FIX 4 — house-contract citation nit (the rule is right, the "verified against" is wrong)
§0.2 item 1 says "read config via `config.get` … like `whatsapp.py`." In fact **`whatsapp.py` reads
raw `os.getenv`**, not `config.get`. The *recommendation* (`config.get`, so Doppler works) is the
**better** path and should stand — but attribute it to `config.py`/`caller.py` usage, **not** to
whatsapp.py. (Cosmetic: don't let a build agent "match whatsapp.py" and thereby use raw `os.getenv`.)

### Residual risks after fixes (disclose; none block GO)
- **R1 (founder/lead-time, real):** Google developer-token approval + Meta Advanced-Access App
  Review + Business Verification are multi-day and founder-side. Go-live is gated on these, not on
  our code. Already disclosed (§6, §9) — keep loud.
- **R2 (cost overshoot window, accepted):** the polling breaker's inter-poll latency window remains;
  the platform daily budget is the real floor. Disclosed (§5.5). Mitigate by always setting the
  platform daily budget ≤ cap at create time (Layer 1) — never rely on the breaker alone.
- **R3 (CPL realness):** CPL enforcement is only as good as the founder's Pixel+CAPI / conversion
  action. Absent that, the breaker self-disables CPL and runs cap-only. Disclosed (§1.5, §5.4) — keep.
- **R4 (multi-tenant billing/abuse):** all spend bills to the founder's own Meta/Google ad accounts
  via their payment method. In a multi-tenant world, a tenant proposing campaigns could drive the
  founder's spend — the per-tenant `daily_cap_minor`/`lifetime_cap_minor` + approval gate are the
  only abuse controls. **Recommend a global org-level spend ceiling** (sum across tenants) in
  `guardrails.caps`, not just per-tenant, before multi-tenant activation. (New, minor; add as a
  config knob `ADS_ORG_DAILY_CAP_MINOR`.)
- **R5 (token scope/leak):** Meta System-User token + Google refresh token are long-lived and
  high-privilege (`ads_management`). Store via the env/Doppler path only, never in `var/ads/*` JSON,
  and `redact` in all logs. Rotation is founder-side. Disclosed implicitly; make explicit.
- **R6 (API-version rot):** mitigated by the env knob, but a stale default that nobody updates will
  eventually 4xx after sunset. **Add a startup `health` warning** when the configured version is
  within ~30 days of its known EOL (cheap, optional). Non-blocking.

### VERDICT: **GO** — conditional on FIX 1–4 folded (above) before/while coding.
The architecture, dormancy, spend-safety spine, and all external facts are sound and honest. The
defects were *referenced-primitive accuracy* (a non-existent `firewall.py`, a not-yet-built
marketing sibling, a loosely-named LLM seam, one mis-citation) — none invalidate the design; all are
corrected here so a build agent codes against what actually exists. Build order §10 still holds, with
the §10.5 approval step now reading "build the step-up primitive on `auth.py`'s password-verify +
JWT-role freshness" instead of "reuse firewall.py".

---

### Sources (2026-06-09)
- Meta `facebook-business` SDK & Marketing API versions — github.com/facebook/facebook-python-business-sdk/releases ; developers.facebook.com/docs/marketing-api/marketing-api-changelog/versions
- Meta permissions / Advanced Access / Business Verification (2026 ≥500-call rule) — developers.facebook.com/docs/permissions ; developers.meta.com/blog/updates-to-ads-management-standard-access-feature
- Meta Conversions API (offline-conversions API discontinued 2025-05-14; CAPI only) — developers.facebook.com/docs/marketing-api/conversions-api
- Google `google-ads` 31.0.0 (2026-05-13), Python ≥3.9 — pypi.org/project/google-ads
- Google Ads API versions: v19 sunset 2026-02-11, monthly releases Jan 2026, v20/v21/v22 EOL Jun/Aug/Oct 2026 — developers.google.com/google-ads/api/docs/sunset-dates ; ads-developers.googleblog.com/2025/12/google-ads-api-v19-sunset-reminder.html ; ppc.land/google-ads-api-shifts-to-monthly-releases-starting-january-2026
- Google developer-token access levels & approval lead time — developers.google.com/google-ads/api/docs/api-policy/developer-token ; ads-developers.googleblog.com/2026/02/an-update-on-google-ads-api-developer.html
- OSS landscape (wrappers/MCP, no self-hostable optimizer) — github.com/jshorwitz/awesome-agentic-advertising ; github.com/TheMattBerman/meta-ads-kit ; github.com/AgriciDaniel/claude-ads
