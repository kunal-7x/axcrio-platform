# DESIGN SPEC — Marketing Automation Suite (`droplet_work/automation/marketing/`)

> **Status:** EXECUTION-READY. A build agent implements this verbatim, one UNIT at a time,
> committing + running the offline acceptance test before the next. **NON-BREAKING + crash-safe.**
> **NO git** (orchestrator commits). **NEW files only under `droplet_work/automation/`.**
> **DO NOT edit `caller.py` / `agent.py`** (backend spine; final wiring deferred to a later phase).
> Every integration is **PROVIDER-AGNOSTIC** + **DORMANT-UNTIL-CREDS**: a no-op that returns
> `{"status": "not_configured"}` and **NEVER raises** until the founder pastes keys — exactly
> like the existing `droplet_work/whatsapp.py` (the canonical pattern this spec mirrors).
> **Verifiable OFFLINE** — the acceptance test makes zero live external calls.

Date: 2026-06-09. Research sources are inline and listed in §11.

---

## 0. WHAT THIS REPLACES (the human teams) AND WHAT IT IS

Famit AI Revenue OS replaces ad/marketing/telecaller teams. The **voice telecaller** already
exists (`caller.py`/`agent.py` + LiveKit). The **WhatsApp** channel already exists
(`whatsapp.py`). **This module adds the rest of outbound marketing**: email, SMS, social posting,
and the **drip/sequence engine** that orchestrates multi-touch campaigns across all channels
(including the existing voice + WhatsApp) with content generation.

It is an **in-process Python package**, NOT a bundled heavyweight orchestrator. Rationale below
(§1.1). Heavy OSS engines (Listmonk, Postiz) are **optional self-hosted back-ends** that this
module talks to *through the same provider-agnostic adapter seam* — they are pointed at by env
vars and stay dormant until configured, identical to how `whatsapp.py` points at Meta/Gupshup.

### 0.1 The non-negotiable house contract (verified against `whatsapp.py`, `audit.py`, `config.py`, `vendors/groq_meter.py`)
Every public function in this module obeys ALL of:
1. **Never raises.** Wrap all I/O in `try/except Exception` → return a result dict. (`whatsapp.py:196`,
   `audit.py:98` both swallow with `# noqa: BLE001`.)
2. **Dormant-until-creds.** If the chosen provider's env vars are blank → return
   `{"ok": False, "status": "not_configured", "provider": <p>, ...}` with **zero network I/O**.
   (`whatsapp.py:254`.)
3. **Provider-agnostic.** A `provider` switch builds the request body per vendor; an unknown/blank
   provider falls to a `generic` flat-JSON POST. (`whatsapp.py:_build_body`.)
4. **Config via `os.getenv`**, read fresh inside the function (so a later `.env` paste + restart
   takes effect with no code change). Optional `config.get()` Doppler passthrough is automatic
   because `config.py` merges Doppler under `os.environ` at import — we just read env.
5. **`httpx` optional.** `try: import httpx except: httpx=None`; if `None` → `error:httpx_unavailable`.
   (`whatsapp.py:73`.) Same for any other 3rd-party import.
6. **Async + sync variants** where the FastAPI loop will call it (mirror `send_whatsapp` /
   `send_whatsapp_async`).
7. **Audit every mutating action** best-effort via the existing `audit.record(...)` (channel
   `"marketing"`), never letting an audit failure break the action (`audit.py` already swallows).

---

## 1. CHOSEN TOOLS + WHY (researched 2026-06; all ACTIVE, none abandoned)

### 1.1 Orchestrator decision — **build the sequencer in-process; do NOT bundle n8n/Windmill into the spine**
The task names n8n/Windmill/Listmonk/Postiz as candidates. Verdict after research:

- **n8n is the wrong license for Famit's business.** n8n ships under the **Sustainable Use
  License** (fair-code), which restricts "using the software's automation as a value proposition
  to external/3rd-party users." Famit's *entire business is selling automation to client tenants* —
  that is precisely the restricted case. Self-hosting it for internal ops is fine, but baking it
  into the product surface is a licensing landmine. ([n8n Sustainable Use License]; [Boolean&Beyond
  2026 comparison].)
  - **On the AGPL tools we DO adopt (Listmonk, Postiz; Windmill as an option):** their AGPLv3
    obligations attach only if Famit *modifies their source* and offers the modified service to
    tenants. We run them **unmodified, as separate services, reached over their REST APIs** — calling
    an AGPL service across a network boundary does not infect Famit's client code. This is exactly
    why the AGPL tools are safe here while n8n's *usage*-restricting fair-code license is not.
- **A general workflow engine (n8n/Windmill) is the wrong altitude for the *spine*.** The drip
  logic Famit needs is small, deterministic, and must be **idempotent + crash-safe + offline-testable**
  and tightly coupled to existing per-tenant state (leads, suppression, audit, billing). That is
  ~200 lines of file-backed state machine, not a separate stateful service with its own Postgres +
  queue to operate and secure. The existing codebase already proves this pattern (`caller.py`'s
  `scheduler_loop` + `retry_queue.json`). So: **the sequence engine is `sequencer.py` in this
  package.** (If the founder later wants a *visual builder* for non-developers, **Windmill (AGPLv3,
  MIT-friendly, scripts in Python) self-hosted on DO** is the recommended add-on — it can call this
  module's HTTP endpoints as steps. Recorded as a deferred option, not built now.)

### 1.2 Email — **Listmonk (self-hosted, AGPLv3) as the bulk engine; SES/Resend/SMTP as transports**
- **Listmonk v6.x** (latest v6.1.0, 2026-03-29; single Go binary + Postgres; **AGPLv3**) is the
  recommended self-hosted newsletter/transactional engine — the most-recommended OSS option in 2026,
  fastest to deploy, modern REST API. It runs **on DigitalOcean** (cost win vs SaaS list price).
  ([listmonk GitHub]; [Mailflow 2026 review].)
- Listmonk does not send SMTP itself end-to-end; it relays through an SMTP server. The cheapest
  high-deliverability relay at Famit's scale is **Amazon SES** (~$0.10 / 1k emails; ~$5 for 50k/mo
  vs Resend $20). **Resend** (modern API, React Email, managed deliverability) is offered as the
  zero-ops alternative. Plain **SMTP** (any host) is the universal fallback. ([forwardemail SES vs
  Resend 2026].)
- **Adapter design:** `MKT_EMAIL_PROVIDER ∈ {listmonk, ses, resend, smtp, generic}`. For bulk
  newsletters → `listmonk` (push a campaign via Listmonk API). For 1:1 transactional/drip touches →
  `ses` | `resend` | `smtp`. All dormant until their creds exist.

### 1.3 SMS — **MSG91 (India-native, DLT-built-in) primary; Twilio + generic fallbacks**
- **MSG91** is India's de-facto transactional SMS/OTP API: ~₹0.15/SMS (60–70% cheaper than Twilio's
  ~₹0.45), and critically **DLT (TRAI) compliance is built in**. Indian commercial SMS is **blocked
  by Jio/Airtel/Vi/BSNL unless sent on a DLT-registered route + template**, with ₹50k/template fines
  for violations — so DLT is not optional for Famit's market. ([Message Central 2026 pricing];
  [productgrowth MSG91 review].)
- **Twilio** kept as the global fallback (`MKT_SMS_PROVIDER=twilio`); **generic** flat POST for any
  other gateway. AWS SNS noted but not first-class (weaker India DLT story).
- **Adapter:** `MKT_SMS_PROVIDER ∈ {msg91, twilio, generic}`. **Guardrail:** every SMS send carries a
  `dlt_template_id` field; if `MKT_SMS_REQUIRE_DLT=1` (default for India) and it is missing → the
  send is **blocked with `status:"blocked_no_dlt_template"`** (no spend), surfaced to the founder.

### 1.4 Social — **Postiz (AGPL-3.0, self-host + public API) primary; Mixpost + Ayrshare + generic**
- **Postiz** (AGPL-3.0, Docker self-host, **real public REST API + MCP server**, 14+ networks: X,
  LinkedIn, Instagram, Facebook, TikTok, YouTube, Threads, Reddit, Mastodon, Bluesky, Pinterest,
  Discord, Slack, Dribbble) is the most credible 2026 OSS Buffer/Hootsuite alternative and is
  API-drivable from this module. ([postiz GitHub]; verified license + API + Docker via GitHub fetch.)
- **Mixpost** (self-host, one-time licence, no per-seat fee) offered as alt; **Ayrshare** (API-first
  SaaS, $149+/mo, for resellers who want zero self-host) as the managed alt.
- **Adapter:** `MKT_SOCIAL_PROVIDER ∈ {postiz, mixpost, ayrshare, generic}`. All dormant until creds.
- **Reality check (§9):** social posting to Meta/X/LinkedIn requires *each network's own app +
  OAuth tokens*, configured **inside Postiz**, not here. This module only schedules a post *through*
  Postiz; the per-network OAuth is a Postiz setup chore (called out in the cred list).

### 1.5 Content generation — **reuse the existing LLM seam; no new vendor**
Subject lines, SMS copy, social captions, drip-step bodies. The codebase already meters Groq/Sarvam
(`vendors/groq_meter.py`, `vendors/sarvam_meter.py`) and has an LLM router. Content gen calls the
**same LLM path** behind `MKT_CONTENT_LLM ∈ {groq, sarvam, none}`; with `none` (default until wired)
the generator returns the **caller-provided template unchanged** (pure pass-through, offline-safe).
No new LLM vendor is introduced. **Anthropic/Claude is NOT used here** (provider stays whatever the
spine already meters); if a future phase wants Claude for copy, it slots in as another `MKT_CONTENT_LLM`
value — out of scope now.

---

## 2. PACKAGE LAYOUT (new files only; nothing outside `droplet_work/automation/`)

```
droplet_work/automation/
  __init__.py                 # exports the public surface; safe to import with zero creds
  marketing/
    __init__.py
    channels/
      __init__.py
      email.py                # send_email() / send_email_async() — listmonk|ses|resend|smtp|generic
      sms.py                  # send_sms()   / send_sms_async()   — msg91|twilio|generic (+DLT guard)
      social.py               # post_social()/ post_social_async()— postiz|mixpost|ayrshare|generic
      voice_bridge.py         # thin shim: enqueue a voice touch as a campaign lead (NO caller.py import;
                              #   writes a hand-off JSONL the spine will later drain). Dormant by default.
      wa_bridge.py            # thin shim around whatsapp.send_whatsapp (already provider-agnostic+dormant)
    content.py                # generate(kind, template, vars) -> str  (LLM-or-passthrough)
    sequencer.py              # drip/sequence state machine: define→enroll→tick→advance (file-backed JSONL)
    guardrails.py             # spend caps, approval gate, dry-run, per-tenant rate limit, suppression check
    meter.py                  # cost estimation per channel (rate card; marked estimated) — groq_meter style
    store.py                  # tiny JSONL/JSON helpers (atomic write, append) scoped to var/marketing/
    endpoints.py              # OPTIONAL FastAPI APIRouter (NOT mounted by caller.py here; spine wires later)
    config_help.py            # returns the cred checklist + per-provider status (for a /marketing/status probe)
  tests/
    test_marketing_offline.py # the offline acceptance test (no network); also runnable as __main__
```

**Import safety:** `automation/__init__.py` and every submodule must import cleanly with an empty
env (the smoke test imports them). No module-level network calls, no `require()` at import.

**Packaging & imports (PINNED — verified against `caller.py`; get this wrong and §8 won't run).**
The spine runs **flat with `droplet_work/` as the sys.path root**: `caller.py` does
`import whatsapp`, `import audit`, `from config import get`, `from vendors import groq_meter`
(verified `caller.py:35,41-45,60,78`). So `vendors/` is a *subpackage referenced by bare name*
(`from vendors import …`), NOT `from droplet_work.vendors import …`. This module follows the
identical convention:
- Reach spine deps by **bare name**: `import audit`, `from whatsapp import send_whatsapp`,
  `from config import get`, `from vendors import groq_meter`. Do **not** prefix with `droplet_work.`.
- Reach sibling submodules within this package by **bare top-level name too**:
  `from automation.marketing.channels import email` (cwd = `droplet_work/`, so `automation` is a
  top-level importable package). Internally, prefer relative imports inside the package
  (`from .channels import email`, `from . import guardrails`) so the package is self-consistent
  regardless of cwd.
- **Test invocation (corrects the obvious trap):** run with cwd = `droplet_work/` as
  `python -m automation.tests.test_marketing_offline` — **not** `python -m
  droplet_work.automation.…` (that would put droplet_work's *parent* on the path and break the
  bare `import audit` / `from whatsapp import …` the spine itself relies on). The test file also
  defensively does `sys.path.insert(0, <droplet_work dir>)` at the top so it runs from any cwd.

---

## 3. INTERFACES (exact signatures — a build agent codes to these)

All return a **result dict** of shape:
`{"ok": bool, "status": str, "provider": str, "channel": str, "cost_est_inr": float, **extra}`
`status` vocabulary: `not_configured | blocked_no_dlt_template | blocked_cap_exceeded |
blocked_needs_approval | blocked_suppressed | dry_run | sent:<code> | queued:<id> | error:<...>`.

### 3.1 channels/email.py
```python
def send_email(to: str, subject: str, html: str, *, text: str = "",
               tenant_id: str = "", dry_run: bool | None = None,
               meta: dict | None = None) -> dict: ...
async def send_email_async(...) -> dict: ...
def email_configured() -> bool: ...                  # provider creds present?
# bulk path (Listmonk campaign), separate so 1:1 sends never touch Listmonk:
def send_bulk_email(list_id: str, subject: str, html: str, *,
                    tenant_id: str = "", dry_run: bool | None = None) -> dict: ...
```
Env: `MKT_EMAIL_PROVIDER`, plus provider sets —
- listmonk: `LISTMONK_URL`, `LISTMONK_USER`, `LISTMONK_TOKEN` (or basic auth), `LISTMONK_FROM`
- ses: `SES_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MKT_EMAIL_FROM`
- resend: `RESEND_API_KEY`, `MKT_EMAIL_FROM`
- smtp: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MKT_EMAIL_FROM`
- generic: `MKT_EMAIL_API_URL`, `MKT_EMAIL_API_KEY`, `MKT_EMAIL_FROM`

### 3.2 channels/sms.py
```python
def send_sms(to: str, text: str, *, dlt_template_id: str = "",
             tenant_id: str = "", dry_run: bool | None = None,
             meta: dict | None = None) -> dict: ...
async def send_sms_async(...) -> dict: ...
def sms_configured() -> bool: ...
```
Env: `MKT_SMS_PROVIDER`, `MKT_SMS_REQUIRE_DLT` (default `1`), plus —
- msg91: `MSG91_AUTH_KEY`, `MSG91_SENDER_ID`, `MSG91_ROUTE` (default `4`/transactional)
- twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`
- generic: `MKT_SMS_API_URL`, `MKT_SMS_API_KEY`, `MKT_SMS_FROM`

### 3.3 channels/social.py
```python
def post_social(text: str, *, channels: list[str] | None = None,
                media_urls: list[str] | None = None, schedule_at: str = "",
                tenant_id: str = "", dry_run: bool | None = None,
                meta: dict | None = None) -> dict: ...
async def post_social_async(...) -> dict: ...
def social_configured() -> bool: ...
```
Env: `MKT_SOCIAL_PROVIDER`, plus —
- postiz: `POSTIZ_URL`, `POSTIZ_API_KEY` (+ networks configured inside Postiz)
- mixpost: `MIXPOST_URL`, `MIXPOST_API_TOKEN`, `MIXPOST_WORKSPACE_UUID`
- ayrshare: `AYRSHARE_API_KEY`
- generic: `MKT_SOCIAL_API_URL`, `MKT_SOCIAL_API_KEY`

### 3.4 content.py
```python
def generate(kind: str, template: str, variables: dict | None = None) -> str:
    """kind ∈ {subject, sms, caption, email_body}. With MKT_CONTENT_LLM unset/'none',
    returns template with {{var}} substituted (pure, offline). With a configured LLM,
    rewrites template per `kind` tone limits (SMS<=160, subject<=78). NEVER raises;
    on LLM error returns the substituted template."""
```
Env: `MKT_CONTENT_LLM ∈ {none(default), groq, sarvam}`; reuses existing vendor keys, no new key.

### 3.5 sequencer.py  (the drip engine — deterministic, idempotent, crash-safe)
```python
def define_sequence(seq_id: str, steps: list[dict], *, tenant_id: str) -> dict:
    """steps: [{ "after_hours": 0, "channel": "email|sms|social|whatsapp|voice",
                 "template": "...", "subject": "...", "dlt_template_id": "...",
                 "stop_if": "replied|booked|opted_out" }, ...]  -> persisted to disk."""
def enroll(seq_id: str, contact: dict, *, tenant_id: str) -> dict:
    """contact: {phone,email,name,...}. Idempotent on (seq_id, tenant, phone|email):
       re-enroll is a no-op. Creates an enrollment row at step 0."""
def tick(*, now_epoch: float | None = None, tenant_id: str | None = None,
         limit: int = 500) -> dict:
    """Advance every enrollment whose next step is due (now >= enrolled_at + after_hours).
       For each due step: run guardrails -> dispatch via the channel adapter -> record
       attempt -> advance pointer (or stop on stop_if/opt-out). FULLY IDEMPOTENT:
       a step that already has a recorded attempt for this enrollment is skipped, so
       re-running tick() after a crash never double-sends. Returns a summary
       {processed, sent, skipped, blocked, errors}. NEVER raises."""
def opt_out(contact_key: str, *, tenant_id: str) -> dict: ...
def status(seq_id: str = "", *, tenant_id: str | None = None) -> dict: ...
```
`tick()` is what a cron / the spine's `scheduler_loop` will call every N minutes **later** (not
wired now). It is **pure w.r.t. the clock** (takes `now_epoch`) so the offline test can drive time
forward deterministically with zero sleeping and zero network (all channels dry-run/not_configured).

### 3.6 guardrails.py
```python
def precheck(channel: str, tenant_id: str, *, cost_est_inr: float,
             contact_key: str = "", needs_approval: bool | None = None,
             dry_run: bool | None = None) -> dict:
    """Returns {"allow": bool, "status": str, "reason": str}. Order of checks:
       1. suppression / opt-out  -> blocked_suppressed
       2. global kill switch MKT_PAUSE_ALL=1 -> blocked_paused
       3. dry-run (MKT_DRY_RUN=1 default, or per-call) -> dry_run (allow=False, no spend)
       4. approval gate: if MKT_REQUIRE_APPROVAL=1 and not approved -> blocked_needs_approval
       5. spend cap: today's tenant spend + cost_est > MKT_DAILY_CAP_INR -> blocked_cap_exceeded
       6. per-minute rate cap per channel -> blocked_rate
       else allow."""
def approve(batch_id: str, *, tenant_id: str, actor: str) -> dict: ...   # flips a pending batch live
def spend_today(tenant_id: str, channel: str = "") -> float: ...
```
Env (all have safe defaults): `MKT_DRY_RUN` (default `1` → nothing actually sends until the founder
flips it), `MKT_REQUIRE_APPROVAL` (default `1`), `MKT_PAUSE_ALL` (kill switch, default `0`),
`MKT_DAILY_CAP_INR` (default `500`), `MKT_RATE_PER_MIN_EMAIL|SMS|SOCIAL`.

> **Safety default = OFF.** With an empty `.env`, `MKT_DRY_RUN=1` and every provider
> `not_configured`, so the suite **cannot spend a rupee or send a message**. The founder
> consciously turns it on (creds + `MKT_DRY_RUN=0` + approve a batch). This is the spend guardrail.

### 3.7 meter.py  (cost estimation — `groq_meter.py` style, marked `estimated`)
```python
def estimate(channel: str, count: int = 1, **kw) -> float:   # INR, from a rate card
def summarize(usage_events: list[dict]) -> dict:             # roll up actual recorded sends
```
Rate card env (per unit, INR): `RATE_SMS_INR` (def 0.15), `RATE_EMAIL_INR` (def 0.002),
`RATE_SOCIAL_INR` (def 0.0). All `estimated: True` (no vendor billing API), same honesty flag as
`groq_meter.summarize`.

### 3.8 store.py
JSONL append + atomic JSON write helpers, all under `var/marketing/` (created on demand, like
`audit.init`). Files: `sequences.json` (defs), `enrollments.jsonl` (append-only state log),
`attempts.jsonl` (one row per actual/dry send — the idempotency + meter source), `suppression.json`,
`approvals.json`. **Append-only logs mirror `audit.py`'s immutability discipline.**

### 3.9 endpoints.py  (FastAPI router — DEFINED here, MOUNTED later by the spine, NOT in this phase)
A `from fastapi import APIRouter; router = APIRouter(prefix="/marketing")` exposing:
`GET /marketing/status` (per-provider configured? + guardrail settings, **no secret values** — like
`config.source()`), `POST /marketing/email|sms|social` (single send), `POST /marketing/sequence`
(define), `POST /marketing/enroll`, `POST /marketing/tick` (manual advance), `POST /marketing/approve`,
`GET /marketing/audit` (read marketing audit rows via `audit.tail(action_prefix="marketing")`).
**This file must import without FastAPI side effects and must not be imported by caller.py in this
phase** (the orchestrator wires it in a later, explicitly-scoped unit).

---

## 4. DATA MODEL (files under `var/marketing/`)

| File | Shape (one JSON / JSONL row) | Role |
|---|---|---|
| `sequences.json` | `{seq_id:{tenant_id, steps:[...], created_ts}}` | sequence definitions |
| `enrollments.jsonl` | `{enroll_id, seq_id, tenant_id, contact:{phone,email,name}, step_ptr, enrolled_epoch, status:enrolled\|done\|stopped\|opted_out}` | per-contact drip state (append latest-wins by enroll_id) |
| `attempts.jsonl` | `{enroll_id, seq_id, step_idx, channel, ts, status, provider, cost_est_inr, dry_run}` | **idempotency key** (enroll_id+step_idx) + meter source |
| `suppression.json` | `{contact_key: {ts, reason}}` | opt-outs / bounces / DND |
| `approvals.json` | `{batch_id:{tenant_id, approved_by, ts, channel}}` | approval-gate ledger |

Idempotency rule (the crash-safe core): before dispatching step `k` for enrollment `e`, scan
`attempts.jsonl` for a row `(e, k)`; if present, **skip** (already done). So a `tick()` killed
mid-batch and re-run never double-charges or double-sends. This is the same per-unit crash-safety
the global rules demand.

---

## 5. CONTROL FLOW — one drip step (the whole product in one paragraph)

`tick()` loads enrollments → for each due `(enroll, step)` not already in `attempts.jsonl`:
`content.generate(kind, template, vars)` → `meter.estimate(channel)` → `guardrails.precheck(channel,
tenant, cost, contact_key)`. If `allow=False` → record an `attempt` row with the block `status`
(no spend) and, for `dry_run`, advance the pointer; for `blocked_needs_approval`/`blocked_cap`,
**leave the pointer** so it retries after approval / next day. If `allow=True` → call the channel
adapter (`email.send_email` / `sms.send_sms` / `social.post_social` / `wa_bridge` / `voice_bridge`)
→ record the real `attempt` row → `audit.record(actor=tenant, action="marketing.<channel>.send",
channel="marketing", meta={...})` → advance `step_ptr` (or set `stopped` if `stop_if` matched).

---

## 6. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

> Until ANY of these are set the corresponding channel is a graceful no-op. **Nothing breaks if all
> are blank.** Provider is chosen per channel by the `MKT_*_PROVIDER` switch; only that provider's
> keys are needed. Paste into `/opt/famit-agent/.env` (or Doppler) and restart — no code change.

**EMAIL — pick ONE provider:**
- Listmonk (self-host, recommended bulk): deploy Listmonk on a DO droplet, then `LISTMONK_URL`,
  `LISTMONK_USER`, `LISTMONK_TOKEN`, `LISTMONK_FROM`. *(Founder action: spin droplet / `docker run`
  — a HOWTO is produced as a follow-up; the dev can do the deploy.)*
- Amazon SES (recommended transport behind Listmonk, or standalone): `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `SES_REGION`, verified sender/domain (DKIM/SPF), `MKT_EMAIL_FROM`.
  **Account chore:** AWS account + SES production-access request (out of sandbox) + domain verify.
- Resend (zero-ops alt): `RESEND_API_KEY`, verified domain, `MKT_EMAIL_FROM`.
- Plain SMTP (any host): `SMTP_HOST/PORT/USER/PASS`, `MKT_EMAIL_FROM`.

**SMS — pick ONE provider (India ⇒ MSG91):**
- MSG91: `MSG91_AUTH_KEY`, `MSG91_SENDER_ID`, plus **DLT registration**: register Famit as a DLT
  Principal Entity, register each SMS template, capture `dlt_template_id` per template. **This DLT
  step is mandatory in India** (carriers block non-DLT SMS). Without a `dlt_template_id` the suite
  refuses to send (guardrail), so no money is wasted on blocked routes.
- Twilio (global alt): `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` (+ DLT still needed
  for India numbers).

**SOCIAL — pick ONE provider:**
- Postiz (self-host, recommended): deploy Postiz (Docker on DO), then `POSTIZ_URL`, `POSTIZ_API_KEY`.
  **Per-network OAuth happens INSIDE Postiz** — the founder connects each account once (X, LinkedIn,
  Instagram/FB via Meta app, etc.). Each network = its own developer app + OAuth (a real account
  chore, not a single key). The hardest are Meta (Instagram/Facebook) and X (paid API tier).
- Mixpost (self-host alt): `MIXPOST_URL`, `MIXPOST_API_TOKEN`, `MIXPOST_WORKSPACE_UUID`.
- Ayrshare (managed alt, no self-host): `AYRSHARE_API_KEY` (paid plan).

**CONTENT (optional):** none needed — defaults to template pass-through. To enable AI copy, set
`MKT_CONTENT_LLM=groq` (or `sarvam`) — reuses the **existing** `GROQ_API_KEY` / `SARVAM_API_KEY`
the spine already has. **No new LLM account.**

**GUARDRAILS (optional, have safe defaults):** `MKT_DRY_RUN` (start `1`), `MKT_REQUIRE_APPROVAL`
(start `1`), `MKT_DAILY_CAP_INR` (e.g. `500`), `MKT_PAUSE_ALL` (kill switch). The founder flips
`MKT_DRY_RUN=0` only when ready to actually spend.

---

## 7. SPEND / APPROVAL / AUDIT GUARDRAILS (summary table)

| Guardrail | Mechanism | Default (empty `.env`) |
|---|---|---|
| **No accidental spend** | `MKT_DRY_RUN=1` + every provider `not_configured` | ON (nothing sends) |
| **Human approval** | `MKT_REQUIRE_APPROVAL=1`; batch sits `blocked_needs_approval` until `approve()` | ON |
| **Daily budget** | `MKT_DAILY_CAP_INR`; `guardrails.precheck` sums `attempts.jsonl` est cost/day/tenant | 500 INR |
| **Kill switch** | `MKT_PAUSE_ALL=1` blocks all sends instantly | OFF (available) |
| **Rate limit** | per-channel per-minute cap | sane defaults |
| **India SMS legality** | `dlt_template_id` required (`MKT_SMS_REQUIRE_DLT=1`) else `blocked_no_dlt_template` | ON |
| **Suppression** | opt-out / bounce check before every send | ON |
| **Audit trail** | `audit.record(action="marketing.*", channel="marketing")` → append-only `audit_log.jsonl`; readable via `audit.tail(action_prefix="marketing")` | ON |
| **Cost transparency** | `meter.estimate` on every send, `estimated:True` flag (no fake precision) | ON |

---

## 8. OFFLINE ACCEPTANCE TEST (`tests/test_marketing_offline.py` — ZERO network)

Runnable (cwd = `droplet_work/`) as `python -m automation.tests.test_marketing_offline` and under
pytest. (See the Packaging note in §2 — the `droplet_work.` prefix is deliberately NOT used; the
test self-inserts `droplet_work/` on `sys.path` so it runs from any cwd.) With an **empty
environment** it asserts:

1. **Import safety:** every module imports; `automation` package imports with empty env.
2. **Dormant-until-creds:** `email.send_email(...)`, `sms.send_sms(...)`, `social.post_social(...)`
   each return `status == "not_configured"`, `ok is False`, and **raise nothing**.
3. **Never-raises under garbage:** call each with `None`/wrong-type args → returns an `error:`/
   `not_configured` dict, no exception.
4. **DLT guard:** with `MKT_SMS_PROVIDER=msg91`, `MSG91_AUTH_KEY=x`, `MKT_DRY_RUN=0`, sending an SMS
   **without** `dlt_template_id` → `status == "blocked_no_dlt_template"`, no network attempted.
5. **Dry-run guard:** with a provider "configured" (dummy keys) but `MKT_DRY_RUN=1` → `status ==
   "dry_run"`, `ok is False`, **no httpx call made** (monkeypatch `httpx` to explode if touched).
6. **Spend cap:** set `MKT_DAILY_CAP_INR=0.001`, seed an attempt → next `precheck` →
   `blocked_cap_exceeded`.
7. **Approval gate:** `MKT_REQUIRE_APPROVAL=1` → `precheck` returns `blocked_needs_approval`; after
   `approve(batch)` → allowed.
8. **Sequencer determinism + idempotency:** define a 3-step sequence, `enroll` a contact, drive
   `tick(now_epoch=…)` forward across the `after_hours` boundaries in dry-run; assert exactly the
   right steps fire in order, `enroll` is idempotent (second enroll = no-op), and **re-running the
   same `tick()` twice produces no duplicate `attempts` rows** (crash-safety).
9. **Content pass-through:** `content.generate("sms", "Hi {{name}}", {"name":"A"}) == "Hi A"` with
   `MKT_CONTENT_LLM` unset (no LLM call).
10. **Audit wired:** a (dry-run) send appends a `marketing.*` row retrievable via
    `audit.tail(action_prefix="marketing")`.

The test uses a temp `var/marketing/` dir + temp audit file and **monkeypatches `httpx` to raise if
any code path tries a real call** while `dry_run`/`not_configured` — proving the dormant guarantee
mechanically, not by trust. Exit non-zero on any failure (so the orchestrator gates on it).

---

## 9. HONEST REAL-vs-HYPE

- **REAL now (offline-verifiable):** the adapter seam, dormancy, sequencer state machine,
  idempotency, all guardrails, cost estimation, audit. These are pure logic and tested without a network.
- **REAL but needs the founder's accounts (not hype, just chores):** email via SES/Resend/Listmonk,
  SMS via MSG91 (**+ mandatory DLT registration** — weeks of lead time possible in India), social via
  Postiz (**+ per-network OAuth apps**; Meta/Instagram review and X's paid API are the real friction).
- **HYPE to avoid:** "AI writes perfect on-brand copy autonomously" — content gen is template-anchored
  with optional LLM rewrite under length caps; it is an assist, not a hands-off copywriter. "Post to
  every network with one key" — false; each network is its own OAuth app inside Postiz. "Drip engine =
  needs n8n/Zapier" — false and license-risky for a reseller; the in-process sequencer is sufficient
  and safer. SES "just works" — no: domain auth (SPF/DKIM/DMARC) + production-access exit from sandbox
  are required or deliverability is poor.
- **Deliverability is a reputation game, not a code feature.** New sending domains land in spam until
  warmed. This module cannot fix that; it can only respect suppression and pacing (which it does).

---

## 10. BUILD ORDER (one verifiable UNIT each; test after every unit)

1. `store.py` + `var/marketing/` helpers (+ unit test of atomic write/append). 
2. `meter.py` (rate card) + `guardrails.py` (precheck/cap/approval/dry-run) + tests.
3. `content.py` (pass-through; LLM optional) + test.
4. `channels/email.py`, then `sms.py` (+DLT guard), then `social.py` — each dormant + tested.
5. `channels/wa_bridge.py` (wraps existing `whatsapp.py`), `voice_bridge.py` (hand-off JSONL only).
6. `sequencer.py` (define/enroll/tick/opt_out) + determinism/idempotency test.
7. `endpoints.py` (router defined, **unmounted**) + `config_help.py` + `__init__.py` exports.
8. `tests/test_marketing_offline.py` — the full §8 acceptance test green. **Gate.**

Wiring `tick()` into the spine's scheduler and mounting `endpoints.py` is a **separate, later,
explicitly-scoped phase** that touches `caller.py` — **out of scope here** (do not edit the spine).

---

## 11. SOURCES (2026, active projects only)

- n8n Sustainable Use License (fair-code; restricts automation-as-value-to-3rd-parties):
  https://docs.n8n.io/sustainable-use-license/
- n8n vs Activepieces vs Windmill (licenses: MIT / AGPLv3 / fair-code), Boolean & Beyond 2026:
  https://www.booleanbeyond.com/en/insights/n8n-vs-activepieces-vs-windmill-open-source-automation
- listmonk (AGPLv3, single Go binary + Postgres, v6.1.0 2026-03-29): https://github.com/knadh/listmonk
  ; Mailflow 2026 review: https://mailflowauthority.com/esp-reviews/listmonk-review
- Amazon SES vs Resend cost/deliverability 2026 (SES ~$0.10/1k; Resend managed DX):
  https://forwardemail.net/en/blog/amazon-simple-email-service-ses-vs-resend-email-service-comparison
- SMS India 2026 pricing + DLT mandate (MSG91 ~₹0.15, DLT built-in; non-DLT blocked, ₹50k fines):
  https://www.messagecentral.com/blog/sms-otp-pricing-india ;
  https://productgrowth.in/tools/engagement/msg91/
- Postiz (AGPL-3.0, public API, Docker, 14+ networks): https://github.com/gitroomhq/postiz-app
- Mixpost (self-host, one-time licence): https://mixpost.app/ ;
  Ayrshare (API-first reseller, $149+/mo): referenced via https://postiz.com/compare/ayrshare/mixpost

---

## RED-TEAM FIXES (folded)

> Adversarial review 2026-06-09. Every factual + code-contract claim in this spec was
> re-verified against primary sources before sign-off (results below). The spec is **GO**.
> The fixes here close real holes an attacker/careless-tenant hits; none of them block the
> build, but **RTF-1 and RTF-4 are must-fix BEFORE the founder flips `MKT_DRY_RUN=0` live.**

### What was verified TRUE (no change needed)
- **Code contract is real, not hallucinated.** Checked against the actual files:
  `whatsapp.py` is exactly the provider-agnostic / `not_configured` no-op / never-raises
  (`# noqa: BLE001`) / httpx-optional / async+sync / `_build_body` pattern this spec mirrors.
  `audit.record(actor=, action=, object_type=, channel=, meta=)` and `audit.tail(action_prefix=)`
  exist and never-raise. `groq_meter.summarize` returns `estimated: True`. **Import convention
  confirmed:** `caller.py:35 import whatsapp as wa_mod`, `caller.py:78 import audit as _audit_mod`
  (both inside a `try`), `caller.py:41-45 from vendors import …`, `caller.py:60 from config import
  get as …` — so the bare-name, no-`droplet_work.`-prefix rule in §2 is correct.
- **OSS tools are ACTIVE + correctly licensed (2026):** Listmonk AGPLv3, **v6.1.0 2026-03-29**,
  single Go binary + Postgres. Postiz AGPL-3.0, **v2.21.8 2026-05-22**, real public API + NodeJS
  SDK, 14+ networks, Docker. n8n SUL **does** restrict "n8n as the back-end to power a feature in
  your app" → real licensing landmine for a reseller; the in-process sequencer decision stands.
- **DLT mandate is real and load-bearing:** non-DLT commercial SMS is blocked at carrier level by
  Jio/Airtel/Vi/BSNL. The `blocked_no_dlt_template` guardrail is justified, not theatre.
- **Double-lock dormancy is real:** empty `.env` ⇒ every provider `not_configured` (zero I/O) AND
  `MKT_DRY_RUN=1`. Two independent gates must both be flipped to spend a rupee. Genuinely safe.

### RTF-1 — Multi-tenant shared-credential reputation poisoning (MUST-FIX before live) 🔴
The spec configures **ONE global cred set per channel** (one SES account, one MSG91 sender, one
Postiz with its OAuth apps) shared by all tenants. The per-tenant **spend** cap limits money, **not
reputation**: a single spammy/careless tenant can get the shared sending domain blocklisted, the SES
account into a bounce/complaint suspension, or the social OAuth app banned — **for every tenant at
once**. This is the central in-scope abuse risk and the original spec was silent on it.
- **Required before go-live:** EITHER per-tenant sender isolation (per-tenant SES configuration-set
  / verified subdomain, per-tenant MSG91 sender-id, per-tenant Postiz workspace) OR a hard
  per-tenant complaint/bounce-rate quarantine that auto-suppresses a tenant on threshold.
- **Spec change now (cheap, ships in this phase):** add env `MKT_TENANT_CREDS=0|1`; when `1`, all
  adapters resolve creds as `os.getenv(f"{KEY}__{tenant_id.upper()}")` first, falling back to the
  global key. Adapters stay dormant if neither is set. This makes per-tenant isolation a config
  choice, not a rewrite. Add a guardrail `precheck` check: `blocked_tenant_quarantined` when a
  tenant's recorded bounce/complaint ratio in `attempts.jsonl` exceeds `MKT_MAX_COMPLAINT_RATE`
  (default `0.05`). Until RTF-4 feeds real bounces, this is a manual flag in `suppression.json`.

### RTF-2 — Content-LLM spend escapes the dry-run/cap gate 🟠
§5 runs `content.generate()` **before** `guardrails.precheck()`. `generate()` is a **paid Groq/Sarvam
call** when `MKT_CONTENT_LLM≠none`. So in dry-run with AI copy enabled, every `tick()` still burns
LLM tokens to write copy that is then never sent — the "dry-run = nothing spends" promise is false the
moment a founder enables AI copy. (Default `none` is pass-through, which is why §8 tests pass — the
hole only opens on opt-in.)
- **Fix:** reorder control flow — **`guardrails.precheck()` runs FIRST**; `content.generate()` is
  called **only when `allow=True` and not a pure dry-run-discard path**. In `dry_run`, generate from
  the **template pass-through only** (force `MKT_CONTENT_LLM=none` semantics inside dry-run) so a
  dry-run can never invoke a paid LLM. Add §8 test 11: `MKT_CONTENT_LLM=groq` + `MKT_DRY_RUN=1` +
  monkeypatched LLM seam that explodes if called ⇒ tick completes, LLM never touched.

### RTF-3 — Spend cap is estimate-based and must accumulate WITHIN a tick 🟠
The cap sums **estimated** cost (no vendor billing API — honest, but approximate), and a single
`tick(limit=500)` could dispatch up to 500 sends. If `precheck` reads `spend_today` **once** at batch
start, one tick blows past `MKT_DAILY_CAP_INR`.
- **Fix (pin in §3.6/§5):** `tick()` maintains a **running in-loop accumulator**; each send re-checks
  `spend_today(tenant) + running_est + this_cost <= cap` and stops the tenant's batch at the boundary
  with `blocked_cap_exceeded` (pointer left in place, retries next day). The cap is an
  **estimate-based soft ceiling**, explicitly documented as such (it can overshoot by one send's
  est-vs-actual delta, never by a whole batch). Add §8 test 12: a tick with N due steps and a cap
  that admits only K (<N) stops at exactly K sends.

### RTF-4 — Opt-out / bounce INGESTION is undefined (legally required) 🔴
`suppression.json` + `opt_out()` exist, but **nothing specifies how SMS `STOP`, email unsubscribe,
or hard bounces actually ENTER suppression.** For India SMS (TRAI/DLT) and email (CAN-SPAM/GDPR/India
DPDP) honoring opt-out is a **legal obligation**, not a nicety. A suppression list nothing writes to
is security theatre.
- **Required follow-up unit (scoped, separate, still NEW files):** `channels/inbound.py` exposing
  webhook handlers `ingest_sms_stop(payload)`, `ingest_email_event(payload)` (SES SNS
  bounce/complaint/unsubscribe), `ingest_social_*` — each maps provider payload → `opt_out(contact_key)`
  / suppression write, never-raises, dormant until its webhook secret is set. The `endpoints.py`
  router gains `POST /marketing/inbound/{provider}` (still unmounted this phase). **Spend/sends MUST
  NOT go live before this exists** — flagged in §6 and §9.

### RTF-5 — Packaging nits that would break §8 at runtime 🟡
- §2 layout is missing `automation/tests/__init__.py` (and `automation/__init__.py` is implied but
  must exist) — without them `python -m automation.tests.test_marketing_offline` won't resolve.
  **Add both empty `__init__.py` files to the §2 tree.**
- `endpoints.py` does `from fastapi import APIRouter`. The import-safety smoke test (§8 test 1) must
  **NOT** blanket-import `endpoints.py`, OR `endpoints.py` must guard
  `try: from fastapi import APIRouter except Exception: router = None`. Choose the guard (matches the
  house "3rd-party import is optional" rule) so the package imports cleanly even if FastAPI is absent
  in a bare test env.

### Cred / cost reality folded into §6 (concrete 2026 numbers)
- **DLT is not just "weeks of lead time" (§9 understated it).** Entity (Principal) registration
  ~**₹5,900 + GST** one-time, ~**₹2,500–3,500/yr** annual maintenance, plus per-header and
  per-template approvals; **end-to-end 7–21 business days** before the first SMS can legally send.
  Budget this as a real account chore with money + multi-week lead time, not a same-day key paste.
- **SES headline ~$0.10/1k is real but the bill runs ~15–70% higher** once data transfer, event
  notifications, and (if used) dedicated IPs (~$24.95/IP/mo) are added; production-access (sandbox
  exit) + SPF/DKIM/DMARC are prerequisites or deliverability is poor. The `estimated:True` meter flag
  already hedges this; just don't quote $0.10 as the all-in number to the founder.
- **Self-host cost the cred list omits:** Listmonk and Postiz each need a DO droplet (Postiz wants
  ~2 GB+ RAM and a Postgres+Redis). Real recurring infra cost (~$12–24/mo combined), not "free."

### RESIDUAL RISKS after these fixes (accepted, documented)
1. Reputation/deliverability remains a **reputation game** outside code (domain warming, complaint
   rates) — RTF-1 limits blast radius but cannot guarantee inbox placement.
2. Spend cap stays **estimate-based** (no vendor billing-API truth) — soft ceiling, can drift by the
   est-vs-actual delta; reconcile against real invoices monthly.
3. Per-network social OAuth (Meta review, X paid API) remains founder account-chore friction, unchanged.
4. RTF-4 ingestion correctness depends on each provider's webhook payload shape — must be tested
   against live sandbox payloads before trusting suppression for compliance.
