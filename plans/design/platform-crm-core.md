# PLATFORM — CRM CORE (`crm-core`) — Execution-Ready Design Spec

> **What this is.** The foundational customer/lead/contact system for the Famit/Axcrio Autonomous
> Business OS: a per-person **Contact spine** on Postgres with a unified **timeline**
> (calls · WhatsApp · support · bookings · purchases), **lead stage/score**, a **Next-Best-Action**
> engine, **segmentation**, and **lifecycle triggers** (proactive re-engagement by service cycle).
> It UNIFIES the existing `leads` / `calls` / `transcripts` / `wa_threads` stores into one
> person-centric read model — without rebuilding any of them.
>
> **Audience:** a build agent that implements this verbatim, ONE unit at a time, crash-safe.
>
> **It sits ON TOP of P1-Postgres** (`design/p1-postgres.md`) and obeys its locked decisions
> (per-store MODE router, `data jsonb` catch-all, text PKs == app ids, ENABLE+FORCE RLS, GUC-scoped
> sessions, Alembic versioning, JSON-authoritative until `shadow_diff==0`). **It does NOT relitigate
> the P1 schema** — it adds NEW tables via a NEW Alembic revision (`0002_crm_core`) and reuses the
> existing scoring/finalize/scheduler/webhook machinery in `caller.py`. **The live site at
> https://panel.famit.in keeps earning the whole time.** Flag-off = byte-identical.

---

## 0. GROUND TRUTH (verified against live source — cite before you touch)

Box `famit@168.144.153.145` (`/opt/famit-agent/`), service `famit-caller` (uvicorn `caller:app`
:8209). Local working copy `C:\Users\kunal\Desktop\caps\droplet_work\`. Deploy = scp → box →
`sudo systemctl restart famit-caller`.

### 0.1 The reusable machinery (DO NOT reimplement — wire into it)

- **`caller.py:408 norm(n)`** — the canonical phone normalizer. Strips non-digits, drops a leading
  `0`, prefixes `91` to a bare 10-digit number, returns **`"+91XXXXXXXXXX"`** (or `""` if <11
  digits). This is the canonical form for `leads.phone`, `suppression`, `retry_queue`.
- **`caller.py:928 _update_lead_after_call(tenant_id, phone, score, outcome, …)`** — the ONE
  lead-score writer. Keeps the **MAX interest** ever seen + **MOST-RECENT outcome**; sets
  `score`, `hot = score>=70`, `last_outcome`, `last_call_at`. **Contact stage/score READS these
  fields — there is no second score.**
- **`caller.py:909 _classify_outcome(rec, tr)`** — outcome classifier
  (`no_answer|voicemail|no_human|answered|interested|callback|opt_out`).
- **`caller.py:~1521 _finalize_call(...)`** — the single post-call touch-point that composes:
  classify → update lead score → enqueue retry/callback → opt-out suppress → WhatsApp → webhook.
  It already emits webhook events `call.completed`, `lead.qualified`, `callback.scheduled`,
  `lead.opted_out`. **crm-core hooks the timeline writer HERE (one call), not into N call sites.**
- **`run_job(...)` dial loop** — the ONE outbound hot path. Gate order is fixed and load-bearing:
  **suppression-skip → calling-window → per-tenant concurrency cap → daily-cap → (prepaid) balance →
  dial.** Returns 202 out-of-window, 429 over monthly-minutes, 402 insufficient balance.
  **Lifecycle/NBA NEVER dials directly — it enqueues a single-lead job that re-enters this loop**
  (via the existing `_spawn_retry_job` / `_enqueue_retry` / `POST /run` paths), so every gate fires.
- **`scheduler_loop` (60s startup task)** — already dispatches due retries/callbacks via
  `_spawn_retry_job` and runs the reconciliation sweep. crm-core adds TWO cheap passes to this same
  loop (segment materialize + lifecycle-tick) — no new daemon.
- **Webhook emit pattern** — `_finalize_call` fires HMAC-signed events to `var/webhooks.json`
  subscribers, logged to `var/webhook_log.json`. crm-core adds events, never a parallel delivery
  engine.
- **`memory.py:34 parse_phone`, `:48 _path_for`** — memory + WhatsApp threads key by **digits-only**
  `re.sub(r"[^0-9]","")` → **`"91XXXXXXXXXX"` (NO `+`)**. See §1.1 — this mismatch is the single most
  dangerous silent bug in the whole spec.

### 0.2 P1 tables crm-core joins to (from `design/p1-postgres.md` §3)

`leads(id, org_id, phone, status, score, hot, last_outcome, last_call_at, added_at, data jsonb)`,
`calls(id, org_id, campaign_id, phone, outcome, answered, interest, room, started_at, data jsonb)`,
`wa_threads(org_id, phone, status, turns jsonb, …)` PK `(org_id, phone)`,
`campaigns`, `events` (the append-only audit ledger), `billing/ledger` (purchase/spend rows).
All are tenant-scoped (`org_id`), all under the `store.py` MODE router, all ENABLE+FORCE RLS.

### 0.3 P1 status gate (do not start the cutover before this clears)

P1 is mid-strangle: `leads` is at `STORE_MODES=leads:dual` with `shadow_diff(leads)==0` live; all
other stores still `json`. **crm-core's PG-backed timeline/segments read from the dual-mirrored PG
tables, so it is eventually-consistent off the mirror and MUST tolerate lag/absence** (§3.1). The
crm-core schema (Alembic `0002`) can land DDL-only at any time (zero behavior change); the read-model
turns ON only after `contacts`/timeline shadow-checks pass (§9).

---

## 1. THE LOAD-BEARING DECISION — CONTACT IDENTITY

A **Contact** is the **person spine**: one row per real human per tenant. Everything a person ever did
(calls, WhatsApp, support, bookings, purchases) hangs off it as a timeline; leads/deals hang off it
as forward-1:many (collapses to 1:1 today).

**Identity key (deterministic, no backfill mapping needed):**

```
contact_id = "ct_" + sha1(org_id + "|" + canonical_phone(phone))[:16]
```

- Keyed by **`(org_id, canonical_phone)`**. Every existing row (`leads`, `calls`, `wa_threads`,
  `suppression`, `retry_queue`, `memory`) already carries a phone + tenant ⇒ **the join key exists
  today**. No FK backfill, no migration mapping, no touching `leads`. This is the strangler win:
  every existing row already "knows" its contact by recomputing the hash.
- **Contact : Lead is 1:many forward** (a person can hold multiple deals over time). Today there is
  one lead per phone per tenant (`leads_org_phone_uq`), so it is 1:1 — but the model does not assume
  it. `leads` is **unchanged**; `GET /leads` returns exactly what it returns today.
- Phone is the only universal join key in the current data (no email/name on most rows). Email/extra
  identifiers, when later modules add them, become **additional** `contact_identity` rows pointing at
  the same `contact_id` (§3.2) — phone stays primary now.

### 1.1 ⚠ CANONICAL PHONE — THE SILENT-JOIN BUG (surface explicitly, fix once)

**Verified discrepancy in live source:**

| Store | Form | Source |
|---|---|---|
| `leads.phone`, `suppression`, `retry_queue` | `+91XXXXXXXXXX` (has `+`) | `caller.py:408 norm()` |
| `memory`, `wa_threads` file key | `91XXXXXXXXXX` (digits only, **no `+`**) | `memory.py:49`, `_wa_thread_path` |

A naive `leads.phone == wa_threads.phone` join **silently fails to unify a person's calls with their
WhatsApp** — the timeline would split one human into two. The fix is ONE canonicalizer used
everywhere crm-core computes `contact_id` or joins:

```python
def canonical_phone(p: str) -> str:
    """ONE canonical form for contact identity across ALL stores. Digits-only E.164 body,
    no '+'. Reuses caller.norm() so the +91/leading-0/10-digit logic stays single-sourced,
    then strips the '+'. Empty string if unjoinable."""
    n = caller.norm(p or "")          # -> '+91XXXXXXXXXX' or ''
    return n[1:] if n.startswith("+") else re.sub(r"\D", "", p or "")
```

- Canonical form chosen = **digits-only `91XXXXXXXXXX`** (matches the wa_threads/memory file-key form,
  so the WhatsApp/memory side needs zero change; the `+91` lead/call side is collapsed by stripping
  the `+`). `contact.phone_display` stores the `+91…` pretty form for the UI; `contact.phone_key`
  (the canonical) is what's indexed/joined/hashed.
- **Acceptance test §9 (a) exists specifically to prove this:** seed a phone that appears as `+91…`
  in leads and `91…` in a wa_thread, assert they collapse to ONE contact with BOTH events in the
  timeline. If that test is absent the spec is incomplete.

---

## 2. WHAT IT REUSES vs ADDS

**REUSES (zero or surgical change):**
- `norm()` (via `canonical_phone`), `_update_lead_after_call` (score/stage source of truth),
  `_classify_outcome`, `_finalize_call` (single hook point), `run_job` gate chain (all actuation),
  `scheduler_loop` (segment + lifecycle passes), the webhook engine, the P1 `store.py` MODE router,
  RLS/GUC session contract, Alembic, the existing `leads`/`calls`/`wa_threads`/`events` PG tables.
- `agent.py` cross-call memory is **untouched** (it self-keys by phone; crm-core just READS it as a
  timeline source via `memory.load_memory`).

**ADDS (all new, additive, flag-gated):**
- 4 new PG tables (`contacts`, `contact_identity`, `contact_timeline`, `segments`) +
  `lifecycle_rules` — via NEW Alembic `0002_crm_core` (never edits `0001`).
- `crm.py` — the crm-core service module (identity, timeline assembly, NBA, segment eval, lifecycle
  tick). Import-safe, graceful-degrade, mirrors the `auth.py`/`store.py` shape.
- A thin timeline writer call inside `_finalize_call` and the WA inbound handler (additive, one line
  each, behind `CRM_TIMELINE_WRITE` flag).
- ~9 read endpoints + 4 write endpoints under `/contacts*`, `/segments*`, `/lifecycle*` (all
  X-Auth, tenant-scoped, RBAC-gated).
- New webhook events: `contact.created`, `contact.stage_changed`, `segment.entered`,
  `lifecycle.triggered`.

---

## 3. SCHEMA — NEW Alembic revision `0002_crm_core`

> Conventions verbatim from P1 §3: `org_id text NOT NULL` on every tenant table; text PKs == app ids;
> `data jsonb` catch-all holds the full record; promote a column ONLY to index/filter/RLS on; every
> table ENABLE+FORCE RLS with an `(org_id …)` policy (§5); composite indexes lead with `org_id`.
> Timestamps `timestamptz` + a `*_raw text` mirror where the source JSON keeps an ISO string, so
> shadow_diff stays byte-comparable. Goes through `store.py` MODE router, **default `json`**.

### 3.1 `contacts` — the person spine

```sql
CREATE TABLE contacts (
  id            text PRIMARY KEY,                 -- ct_<sha1(org|phone_key)[:16]>
  org_id        text NOT NULL,
  phone_key     text NOT NULL,                    -- canonical digits-only 91XXXXXXXXXX (§1.1)
  phone_display text NOT NULL DEFAULT '',         -- pretty +91… for UI
  name          text NOT NULL DEFAULT '',
  email         text NOT NULL DEFAULT '',
  -- DERIVED projection (read-cache of the lead truth; NEVER a second source) --
  stage         text NOT NULL DEFAULT 'new',      -- new|contacted|engaged|qualified|booked|won|lost|dormant|opted_out
  score         integer NOT NULL DEFAULT 0,       -- mirror of leads.score (the authoritative value)
  hot           boolean NOT NULL DEFAULT false,
  last_outcome  text NOT NULL DEFAULT '',
  last_activity_at timestamptz,                   -- max(timeline.at) — drives lifecycle dormancy
  lifecycle_state text NOT NULL DEFAULT '',       -- e.g. 'awaiting_followup','cycle_due' (lifecycle engine)
  consent_call  boolean NOT NULL DEFAULT true,    -- false once suppressed/opted_out (compliance read)
  consent_wa    boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'       -- industry-pack fields, custom attrs, tags
);
CREATE UNIQUE INDEX contacts_org_phone_uq ON contacts (org_id, phone_key);
CREATE INDEX contacts_org_stage_idx ON contacts (org_id, stage);
CREATE INDEX contacts_org_score_idx ON contacts (org_id, score DESC);
CREATE INDEX contacts_org_lastact_idx ON contacts (org_id, last_activity_at DESC);
```

> **`contacts` is a read-model/projection, NOT a new source of truth.** `score`/`hot`/`last_outcome`
> are mirrored from `leads` (the authoritative writer is still `_update_lead_after_call`); `stage` is
> DERIVED (§4.1); `last_activity_at` is `max(timeline.at)`. The projector (`crm.project_contact`)
> recomputes these from the existing stores. If the projection lags or is wiped, **truth is
> reconstructable from leads+calls+wa** — no data lives ONLY here except UI niceties (name display,
> tags) in `data jsonb`. MODE: `json` or `dual`; **never `pg`** (it's derived; the source stores
> stay authoritative — same rule P1 applies to calls).

### 3.2 `contact_identity` — alias table (forward-proofing)

```sql
CREATE TABLE contact_identity (
  org_id      text NOT NULL,
  kind        text NOT NULL,            -- 'phone' | 'email' | 'external_id' | 'wa_id'
  value       text NOT NULL,            -- canonical for its kind
  contact_id  text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, kind, value)
);
CREATE INDEX contact_identity_contact_idx ON contact_identity (org_id, contact_id);
```
Today only `('phone', phone_key)` rows exist (1:1 with contacts). When booking/payment/portal modules
later attach an email or external CRM id to a known person, they INSERT an alias row → the timeline
unifies with **zero schema change**. Merge/dedupe (two phones, one human) is a §8 future op that
repoints alias rows + timeline `contact_id`; not built now, but the table makes it non-breaking.

### 3.3 `contact_timeline` — the unified per-person event stream

```sql
CREATE TABLE contact_timeline (
  id          text PRIMARY KEY,         -- DETERMINISTIC = 'tl_'+sha1(org|contact|kind|source_id|at)[:20]
  org_id      text NOT NULL,
  contact_id  text NOT NULL,
  kind        text NOT NULL,            -- call|whatsapp|support|booking|purchase|note|consent|campaign|system
  direction   text NOT NULL DEFAULT '', -- inbound|outbound|''
  source      text NOT NULL DEFAULT '', -- which store/module emitted it (calls|wa_threads|...)
  source_id   text NOT NULL DEFAULT '', -- the originating row id (call id, wa thread phone, etc.)
  title       text NOT NULL DEFAULT '', -- one-line label for the UI
  body        text NOT NULL DEFAULT '', -- summary / message text
  outcome     text NOT NULL DEFAULT '',
  amount      numeric(14,4),            -- for purchase/payment rows (revenue attribution)
  currency    text NOT NULL DEFAULT '',
  at_raw      text NOT NULL DEFAULT '',
  at          timestamptz NOT NULL,
  data        jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX timeline_contact_at_idx ON contact_timeline (org_id, contact_id, at DESC);
CREATE INDEX timeline_org_kind_at_idx ON contact_timeline (org_id, kind, at DESC);
```

> **The timeline is an eventually-consistent READ-MODEL, not a third copy of the data.** Two ways to
> populate, chosen per-`kind`:
> 1. **Live append (preferred, cheap, idempotent).** `_finalize_call` and the WA inbound handler each
>    call `crm.record_timeline(...)` ONCE with a **deterministic id** (`sha1` of the event identity),
>    so re-runs / the reconciliation sweep / replay can't double-insert (`ON CONFLICT DO NOTHING` —
>    same pattern P1 uses for `events`/`wa_log`). This is NOT a new double-write drift surface: the
>    authoritative call/WA record is still written by the existing code; the timeline row is a
>    derived projection with a deterministic key, reconstructable from the source store at any time.
> 2. **Backfill/rebuild (`crm.rebuild_timeline`)** — reads `calls.json` + `wa_threads/*` + `memory`
>    + `ledger` for a contact and UPSERTs deterministic rows. Used for the offline seed (§9) and to
>    self-heal after lag. Because ids are deterministic, rebuild is convergent with live-append.
> 3. **`kind ∈ {booking,purchase,support}`** have NO source store yet → those are **typed empty
>    slots**. When the Booking/Payments/Support modules ship, they call the SAME
>    `crm.record_timeline(kind='booking'|'purchase'|'support', …)` — no schema change, no new table.
>    This is how crm-core unblocks them: the slot is pre-cut.

**Relationship to the P1 `events` table (decided, not invented):** `events` is the **audit/security
ledger** (who-did-what to the system — append-only, immutable, for compliance). `contact_timeline` is
the **customer-relationship history** (what happened with this person). They are deliberately
SEPARATE: an admin deleting a contact is an `events` row; the contact's calls are `timeline` rows.
crm-core does NOT fork or duplicate the audit stream — it WRITES to `events` (via the existing audit
helper) for its own mutating actions (contact merge, manual stage override, lifecycle dispatch) and
READS nothing from it. No parallel audit engine.

### 3.4 `segments` — saved predicates (not a query engine)

```sql
CREATE TABLE segments (
  id          text PRIMARY KEY,         -- seg_<hex>
  org_id      text NOT NULL,
  name        text NOT NULL,
  definition  jsonb NOT NULL DEFAULT '{}',  -- the predicate AST (§6)
  member_count integer NOT NULL DEFAULT 0,
  materialized_at timestamptz,
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  data        jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX segments_org_idx ON segments (org_id);

CREATE TABLE segment_members (              -- materialized membership (optional cache)
  org_id      text NOT NULL,
  segment_id  text NOT NULL,
  contact_id  text NOT NULL,
  added_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, segment_id, contact_id)
);
CREATE INDEX segment_members_seg_idx ON segment_members (org_id, segment_id);
```

### 3.5 `lifecycle_rules` — proactive re-engagement by service cycle

```sql
CREATE TABLE lifecycle_rules (
  id            text PRIMARY KEY,        -- lc_<hex>
  org_id        text NOT NULL,
  name          text NOT NULL,
  trigger       jsonb NOT NULL DEFAULT '{}',  -- {type:'dormant_days'|'cycle_days'|'stage_age'|'segment_entered', value, segment_id?}
  action        jsonb NOT NULL DEFAULT '{}',  -- {type:'enqueue_call'|'enqueue_wa'|'set_lifecycle_state'|'notify', campaign_id?, template?}
  enabled       boolean NOT NULL DEFAULT false,  -- DEFAULT OFF (flag-off-is-byte-identical)
  require_pin   boolean NOT NULL DEFAULT true,   -- risky (spend/bulk) actions gate on PIN/approval
  budget_cap    numeric(14,4) NOT NULL DEFAULT 0,-- per-tick spend ceiling (0 = inherit tenant cap)
  last_run_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX lifecycle_rules_org_idx ON lifecycle_rules (org_id, enabled);

CREATE TABLE lifecycle_fires (              -- dedupe + audit of what fired for whom (idempotency)
  org_id      text NOT NULL,
  rule_id     text NOT NULL,
  contact_id  text NOT NULL,
  fired_at    timestamptz NOT NULL DEFAULT now(),
  cycle_key   text NOT NULL DEFAULT '',    -- e.g. '2026-Q2' so a quarterly cycle fires once per cycle
  job_id      text NOT NULL DEFAULT '',    -- the run_job/retry job it enqueued (traceability)
  PRIMARY KEY (org_id, rule_id, contact_id, cycle_key)
);
```
The `(rule_id, contact_id, cycle_key)` PK is the **idempotency guard**: a tick can run every 60s and a
rule fires AT MOST once per contact per cycle — no re-engagement storm.

### 3.6 RLS (verbatim P1 §5 pattern)
Add all six new tables (`contacts`, `contact_identity`, `contact_timeline`, `segments`,
`segment_members`, `lifecycle_rules`, `lifecycle_fires`) to the `0002` RLS loop: `ENABLE` + `FORCE
ROW LEVEL SECURITY`, policy `USING (current_setting('app.is_admin',true)='1' OR org_id =
current_setting('app.tenant_id',true))` with the same `WITH CHECK`. All reads go through the GUC-
scoped `session()/asession()`. `contacts`/`contact_identity`/`contact_timeline` key on `org_id`.

---

## 4. SERVICES (`crm.py`) — interfaces

Import-safe, graceful-degrade module (mirrors `auth.py`/`store.py`): if PG unavailable → identity +
projection fall back to reading the JSON stores directly; the timeline endpoint assembles a live UNION
on the fly from `calls.json`+`wa_threads`+`memory` (slower but correct) so the panel never breaks.

### 4.1 Identity + projection
```python
crm.contact_id(org_id, phone) -> str                 # deterministic, no DB hit
crm.upsert_contact(org_id, phone, name="", **attrs) -> Contact   # idempotent (UPSERT on org,phone_key)
crm.project_contact(org_id, phone) -> Contact        # recompute stage/score/hot/last_* from leads+timeline
crm.derive_stage(lead, timeline_tail) -> str         # pure fn; rules below
```
**Stage derivation (pure, deterministic, reads existing fields — NO new score):**
```
opted_out  if lead.status == 'opted_out' or contact in suppression
won        if any timeline.kind=='purchase'
booked     if any timeline.kind=='booking' (future module)
qualified  if lead.score >= 70 (== existing 'hot')
engaged    if last_outcome in {interested, callback} or any answered call
contacted  if any call exists (answered or not)
dormant    if last_activity_at older than tenant 'dormant_days' (default 45) and not won/booked
new        otherwise
```
Stage is a projection of the lead truth — it never writes back to `leads`.

### 4.2 Timeline
```python
crm.record_timeline(org_id, contact_id, kind, *, at, source, source_id, title="", body="",
                    outcome="", direction="", amount=None, currency="", data=None) -> None
    # deterministic id, ON CONFLICT DO NOTHING. Called once by _finalize_call + WA handler.
crm.rebuild_timeline(org_id, phone) -> int           # backfill/self-heal from source stores
crm.get_timeline(org_id, contact_id, limit=100, kinds=None) -> list[TimelineRow]   # newest-first
```

### 4.3 Next-Best-Action (rule-based default; LLM behind a flag + budget)
```python
crm.next_best_action(org_id, contact) -> NBA   # NBA = {action, reason, confidence, params, requires_pin}
```
**Deterministic engine (default, NO metered call):** a small ordered rule table over existing fields —
```
opt_out/suppressed         -> {action:'none', reason:'consent withdrawn'}        # hard stop, never actuate
callback_due (callback_at) -> {action:'place_call', params:{campaign_id}, requires_pin:true}
score>=70 & no recent WA   -> {action:'send_whatsapp', template:'qualified_followup', requires_pin:true}
interested & no_followup   -> {action:'send_whatsapp', template:'interested_recap'}
no_answer & attempts<max   -> {action:'retry_call'}  # already handled by retry_queue; NBA just surfaces it
dormant & cycle_due        -> {action:'reengage', params:{lifecycle_rule}, requires_pin:true}
new & in calling-window    -> {action:'place_call'}
else                       -> {action:'nurture'/'none'}
```
**Optional LLM enrichment (`CRM_NBA_LLM`, default OFF):** when ON, a BATCHED, budget-capped Groq pass
(reuse the existing one-shot Groq helper + a budget node) refines `reason`/ranking for a *segment* of
contacts on a schedule — **never per contact-read, never on a hot path** (this codebase repeatedly
bans metered calls on hot paths). Falls back to the rule engine on any error/over-budget.

### 4.4 Segments + lifecycle
```python
crm.eval_segment(org_id, definition) -> list[contact_id]      # compiles predicate -> ONE parameterized SQL
crm.materialize_segment(org_id, segment_id) -> int            # refresh segment_members (scheduler)
crm.lifecycle_tick(org_id=None) -> dict                       # scan enabled rules; ENQUEUE due actions
```

---

## 5. ACTUATION & SAFETY (the #1 guardrail)

**Lifecycle/NBA NEVER place calls or send WhatsApp directly.** `crm.lifecycle_tick` and any
"actuate NBA" endpoint **ENQUEUE through the existing gated paths only**:

```
lifecycle_tick / actuate-NBA
   └─ for each due contact:
        ├─ consent check (suppression + lead.status != opted_out)   # fail-closed
        ├─ idempotency: skip if lifecycle_fires has (rule,contact,cycle_key)
        ├─ require_pin/approval gate for RISKY actions (spend/bulk)  # AI-Manager PIN or workflow APPROVAL node
        ├─ budget gate (rule.budget_cap + tenant daily/minute caps)
        └─ ENQUEUE  ->  _spawn_retry_job / _enqueue_retry / POST /run   (single-lead job)
                         └─ run_job's loop re-applies: suppression -> window -> concurrency
                            -> daily-cap -> (prepaid) balance -> dial      # EVERY gate fires again
        └─ record lifecycle_fires row + emit lifecycle.triggered webhook + write events (audit)
```

Hard rules (platform-level, from the master spec): **no bulk dispatch / no spend / no DND-window
violation / no out-of-hours / no mass-call without (a) consent-clean contact, (b) PIN-or-APPROVAL on
risky actions, (c) a budget cap, (d) an immutable `events` audit row.** Because actuation re-enters
`run_job`, the calling-window, per-tenant concurrency cap, daily-call cap, monthly-minute cap, and
prepaid-balance checks are **physically impossible to bypass** — crm-core adds intent, not a new
dialer. A `dry_run=1` mode on `lifecycle_tick`/actuate returns the would-enqueue list WITHOUT
enqueuing (powers the §9 acceptance test and a "preview re-engagement" UI).

---

## 6. SEGMENTATION — predicate AST (stored, compiled to ONE SQL)

`segments.definition` is a small JSON predicate tree, compiled by `crm.eval_segment` to a single
parameterized `SELECT id FROM contacts WHERE … ` (RLS-scoped). NOT a general query language — a
fixed, safe field allow-list:

```json
{ "all": [
    {"field":"stage","op":"in","value":["qualified","engaged"]},
    {"field":"score","op":">=","value":70},
    {"field":"last_activity_at","op":"older_than_days","value":30},
    {"any":[ {"field":"data.city","op":"=","value":"Pune"},
             {"field":"data.tag","op":"contains","value":"2bhk"} ]}
] }
```
- Allow-listed fields: `stage, score, hot, last_outcome, last_activity_at, lifecycle_state,
  consent_call, consent_wa, created_at, data.<key>` (jsonb path). Ops:
  `=, !=, in, >=, <=, older_than_days, newer_than_days, contains, exists`. Anything off-list → 400.
- Every field maps to a parameterized fragment (no string interpolation of values → no SQL
  injection). `data.<key>` → `data->>'<key>'` with the key validated against `^[a-z0-9_]+$`.
- Segments power Campaigns ("call this segment"), lifecycle triggers (`segment_entered`), and
  analytics. Materialization (caching members) is OPTIONAL — the scheduler refreshes `member_count`
  + `segment_members` for active segments on a cheap cadence; live `eval_segment` is the source.

---

## 7. ENDPOINTS (all `X-Auth`, tenant-scoped, RBAC per existing `can(tenant, action)`)

Reads need `read`; writes need `write`; lifecycle enable / actuate are `write` + (for risky) PIN.
Admin sees all tenants (existing `is_admin` GUC). All additive — **no existing endpoint changes
shape** (flag-off-is-byte-identical).

- `GET  /contacts?stage=&hot=&segment=&q=&sort=&limit=` → `{contacts:[{id,phone_display,name,stage,score,hot,last_outcome,last_activity_at}], total}`
- `GET  /contacts/{id}` → `{contact:{…full…}, lead:{…}, nba:{action,reason,requires_pin}}`
- `GET  /contacts/{id}/timeline?kinds=&limit=` → `{timeline:[{kind,direction,title,body,outcome,amount,at}], contact_id}`
- `GET  /contacts/{id}/nba` → `{action,reason,confidence,params,requires_pin}`
- `POST /contacts/{id}` form (name,email,tags,data) → updates `contacts.data`/name (NOT lead truth) → `{ok}`
- `POST /contacts/{id}/actuate` form `pin?` → runs the contact's NBA through §5 gates; `dry_run=1` → preview. → `{enqueued|preview, job_id?}`
- `GET  /segments` / `POST /segments` (name,definition_json) / `DELETE /segments/{id}`
- `GET  /segments/{id}/members?limit=` → `{contacts:[…], count}` (live eval or cached)
- `GET  /lifecycle/rules` / `POST /lifecycle/rules` (name,trigger_json,action_json,enabled,require_pin,budget_cap) / `DELETE /lifecycle/rules/{id}`
- `POST /lifecycle/tick?dry_run=1` (admin/manager) → manual fire of the lifecycle pass (also runs every 60s in scheduler) → `{fired:[…], enqueued, skipped, preview?}`
- `GET  /contacts/admin/status` (admin) → `{contacts_count, timeline_rows, mode, last_rebuild, shadow_ok}`

New webhook events emitted via the existing engine: `contact.created`, `contact.stage_changed`
(payload `{contact_id,phone,from,to}`), `segment.entered`, `lifecycle.triggered`
(`{rule_id,contact_id,action,job_id}`).

---

## 8. WIRING INTO `caller.py` / scheduler (surgical, additive, flag-gated)

1. **Module init** — after `store.init(...)`, add the `auth.py`-style guarded `import crm; crm.init(_store, config)`; `_crm = None` on any failure (degrade to JSON-union timeline).
2. **`_finalize_call`** — ONE added line behind `CRM_TIMELINE_WRITE` (default ON once §9 passes, ships OFF): after the existing lead-update, `crm.record_timeline(org, crm.contact_id(org,phone), 'call', at=…, source='calls', source_id=rec['id'], title=campaign_name, body=summary, outcome=rec['outcome'], direction='outbound', data={'interest':interest,'room':room})` + `crm.project_contact(org, phone)` (cheap). Idempotent → the reconciliation sweep re-call is a no-op via deterministic id.
3. **WA inbound handler** (`POST /whatsapp/inbound`) + auto-followup — one `crm.record_timeline(kind='whatsapp', direction=…)` per message. Same flag.
4. **`scheduler_loop`** — add two cheap passes to the SAME 60s loop (no new daemon): (a) `crm.materialize_segment` for active segments on a slow cadence; (b) `crm.lifecycle_tick()` (enqueue-only, §5). Both wrapped in try/except so a crm error never stalls the existing retry/callback dispatch.
5. **Opt-out / suppression path** — when `_add_suppression`/optout fires, set `contacts.consent_* = false` + stage `opted_out` (one projector call). Keeps the compliance read on the contact accurate.

**DO NOT TOUCH:** `agent.py` voice path, `prompt.py`, `resolve_tenant`/auth, the `run_job` gate order,
`leads` write path (`_update_lead_after_call` stays the sole score writer), nginx, the P1 `store.py`
internals. crm-core is a consumer/projector + an intent layer, never a second writer of the core
records.

---

## 9. OFFLINE ACCEPTANCE TEST (no creds, no live calls, no spend)

Runs against a throwaway Postgres (or the JSON-union fallback) seeded from copies of `var/leads.json`
+ `var/calls.json` + `var/wa_threads/*` + `var/ledger/*`. `pytest tests/test_crm_core.py`. Gates:

- **(a) IDENTITY/CANONICALIZATION (the load-bearing one).** Seed a phone present as `+916375548830`
  in leads and `916375548830` in a wa_thread and `6375548830` raw in a call. Assert ALL collapse to
  ONE `contact_id`, and its timeline contains the call AND the WhatsApp event. **Proves §1.1.**
- **(b) TIMELINE ORDER.** A contact with 3 calls + 2 WA messages at known timestamps → `get_timeline`
  returns 5 rows strictly newest-first, correct kinds/direction. Re-running `rebuild_timeline` adds
  ZERO rows (deterministic-id idempotency).
- **(c) STAGE/SCORE = projection of lead truth.** A lead with `score=80,last_outcome=interested` →
  contact `stage='qualified', hot=true, score=80`. Changing the lead and re-projecting updates the
  contact; the lead file is byte-unchanged (no write-back).
- **(d) NBA deterministic.** Fixture contacts → expected actions (callback_due→place_call+requires_pin;
  score80→send_whatsapp; opted_out→none). No network/LLM call made (assert the Groq helper is never
  invoked with `CRM_NBA_LLM` OFF).
- **(e) SEGMENT.** `{stage in [qualified], score>=70}` over the seed returns exactly the expected ids;
  an off-allow-list field → 400; a malicious `data.x'; DROP` key → rejected by the `^[a-z0-9_]+$`
  guard (no injection).
- **(f) LIFECYCLE = ENQUEUE-ONLY, gated.** A `dormant_days=45` rule with `dry_run=1` returns the due
  contacts but **enqueues nothing**; with `dry_run=0` it routes through a MOCKED `_spawn_retry_job`
  and the test asserts (i) the mock was called (no direct dialer touch), (ii) an opted-out contact
  was SKIPPED, (iii) a second identical tick fires 0 (idempotency via `lifecycle_fires`), (iv) a
  `require_pin` rule without a PIN does NOT enqueue. **Proves zero un-gated dispatch.**
- **(g) FLAG-OFF BYTE-IDENTICAL.** With `CRM_*` flags off, `import caller` + the existing endpoint
  smoke (`/campaigns,/leads,/calls,/stats,/billing/overview`) return identical shapes; no
  `contacts*` table is read on those paths.
- **(h) RLS.** Raw connection as `famit_app`, `SET app.tenant_id='A'` → `SELECT * FROM contacts`
  returns only A's; switching to B returns only B's; cross-tenant timeline read = 0 rows.

---

## 10. DEPENDENCIES, GUARDRAILS, ROLLBACK

**Dependencies:** none new beyond P1's stack (SQLAlchemy 2.0 / asyncpg / psycopg2 / alembic /
greenlet — already added in P1). No vector/pgvector (that is RAG, Phase 2). No new third-party
service. Optional `CRM_NBA_LLM` reuses the existing Groq client. Active OSS leveraged conceptually
(NOT new deps): the **"unify identity by deterministic key + event timeline as a read-model off the
write stores"** pattern is the standard CDP/customer-360 approach used by open CDPs like
**RudderStack** and **Jitsu** (identity stitching + event timeline) — we implement the minimal,
Postgres-native subset rather than adopt a CDP, because our join key (phone) is already universal and
our scale (single-Postgres ladder, P1 §5) doesn't warrant a streaming CDP. Cite: RudderStack identity
resolution docs; Jitsu event-stream model; PostgreSQL RLS docs (already the P1 substrate).

**Feature flags (all default the safe way):** `CRM_TIMELINE_WRITE` (off→on after §9),
`CRM_NBA_LLM` (default OFF), `CRM_LIFECYCLE` (default OFF — no rule enabled until a tenant turns one
on AND it has require_pin/budget), per-store MODE for the 6 tables (default `json`). Flag-off =
byte-identical; that IS the rollback path.

**Crash-safe per unit (build order):** U1 Alembic `0002` DDL+RLS (zero behavior change) → U2 `crm.py`
identity+projection + offline tests (a)(c)(h) → U3 timeline writer + `_finalize_call` hook (flag off)
+ tests (a)(b) → U4 read endpoints `/contacts*` → U5 segments + endpoint + test (e) → U6 NBA engine +
endpoint + test (d) → U7 lifecycle rules + scheduler tick (enqueue-only) + test (f) → U8 backfill
`rebuild_timeline` + `/contacts/admin/status` + shadow-check → flip `CRM_TIMELINE_WRITE` ON in prod
after the §9 gate is green. Each unit: backup → small edit → instantiate-test → deploy →
regression-gate-200 → build_log → commit → flip DONE. A kill costs ≤1 unit.

**Rollback:** every PG read degrades to the JSON-union timeline (or empty), so a PG outage never
breaks the panel; setting all `CRM_*` flags off and MODEs to `json` returns the system byte-for-byte
to pre-crm-core. Alembic `downgrade` drops the 6 tables (the source stores are untouched, so nothing
is lost).

---

## 11. WHAT THIS UNBLOCKS

`crm-core` is the customer-360 substrate every people-facing module reads from:
- **CRM / Contacts / Leads modules** — the contact spine + timeline + stage IS these modules' data.
- **Lifecycle Trigger Engine** — proactive re-engagement (the lifecycle_rules + tick, gated).
- **AI Manager** — "call all hot leads", "today's hot contacts", per-contact context for any command
  now resolves to a contact + timeline + NBA.
- **Campaigns** — segment-driven targeting ("call segment X") instead of raw lead lists.
- **Next-Best-Action across modules** — one NBA per contact consumed by AI Manager, workflows, panel.
- **Conversation Intelligence** — the per-contact call/WA timeline is its corpus.
- **Revenue Attribution Ledger** — `purchase`/`payment` timeline rows with `amount` give per-contact,
  per-campaign revenue; the typed slots are pre-cut.
- **Booking/Payments/Support** — each gets a pre-cut `kind` slot in the timeline (zero schema change
  when they ship).
- **Segmentation, Workflow Builder, Analytics** — segments + timeline events are their inputs.

---

## RED-TEAM FIXES (folded)

> Adversarial review against live source (`droplet_work/caller.py`, `memory.py`, `store.py`) +
> `design/p1-postgres.md`. Each fix below is now BINDING on the build agent; where a fix changes a
> claim made earlier in this doc, **this section wins**. Verdict at the end.

### RTF-1 (NO-GO-if-unfixed) — spend admission is NOT re-applied on the enqueue path; §0.1/§5 overclaim

**Defect.** §0.1 and §5 assert that because lifecycle/NBA re-enter `run_job`, the prepaid-balance
(402) and monthly-minutes (429) gates are "physically impossible to bypass." **This is false, verified
against source.** The balance + monthly-minutes gates live ONLY in the `POST /run` admission handler
(`caller.py:2174-2187`). `run_job` (`:1618-1733`) contains only window → suppression → per-tenant
concurrency → daily-cap. `_spawn_retry_job` (`:3425-3437`) builds a `JOBS` entry and
`asyncio.create_task(run_job(...))` **directly, bypassing `/run`**; the scheduler's own retry dispatch
(`:3460-3468`) likewise re-checks only window + suppression. So **both** enqueue paths this spec names
for actuation (`_spawn_retry_job` / `_enqueue_retry`) provably skip spend admission. For the exact
concern this layer must satisfy — AI-workforce/AI-manager **spend safety** — leaning on a non-existent
`run_job` balance backstop is a spend leak, not a guardrail.

**Fix (reuse-consistent; does NOT relitigate `/run` or reorder `run_job`).** Extract `/run`'s
admission preamble into one helper and call it from BOTH `/run` and every crm actuation enqueue:

```python
# caller.py — extracted from POST /run (:2174-2187), single source of the spend-admission truth
def _admission_gate(tenant_id: str) -> dict | None:
    """Return None if the tenant may spend now, else the refusal {error,status}. Reuses the
    SAME primitives /run uses — no second meter, no drift."""
    tr = _tenant_by_id(tenant_id) or {}
    used_min = _tenant_usage(tenant_id, _month_iso())["minutes"]
    if used_min >= int(tr.get("monthly_minutes_cap", 5000)):
        return {"error": "monthly minutes cap reached", "status": 429}
    b = _billing_for(tenant_id)
    if b.get("plan") == "prepaid" and float(b.get("balance", 0) or 0) <= 0:
        return {"error": "insufficient balance", "status": 402}
    return None
```

- `POST /run` calls `_admission_gate` (behavior identical — pure extraction, regression-tested by
  §9(g)).
- `crm.lifecycle_tick` and `POST /contacts/{id}/actuate` **MUST call `_admission_gate(tenant_id)` and
  refuse-without-enqueue on a non-None result, BEFORE `_spawn_retry_job`.** The §5 gate chain is
  amended to: consent → idempotency → PIN/approval → **`_admission_gate` (balance + monthly)** →
  per-rule `budget_cap` → enqueue. The earlier "run_job re-applies balance" backstop sentence in
  §0.1/§5 is **struck** — it was never true; the crm side now owns this check explicitly.
- **New acceptance test §9(i):** a tenant over monthly-minutes AND a prepaid tenant at balance≤0 each
  yield `lifecycle_tick`/`actuate` → **0 enqueues**, refusal surfaced; flip the cap/balance →
  enqueues. This is the test that proves the spend guardrail actually holds.

### RTF-2 (scalability + budget enforceability) — batch the enqueue; do NOT fan out N single-lead jobs

**Defect.** §4.4/§5 enqueue per due contact via N× `_spawn_retry_job`. Two consequences: (a)
`lifecycle_rules.budget_cap` ("per-tick spend ceiling") is **unenforceable** across N independent jobs
— each job is unaware of the others' spend, so the per-tick ceiling is fiction; (b) N concurrent
`run_job` tasks each re-read `CALLS` and loop every 4s, which does not scale on the single-Postgres
ladder and contradicts the "scalable" claim.

**Fix.** `lifecycle_tick` collects the due, consent-clean, idempotent, PIN-cleared contacts into ONE
batch, calls `_admission_gate` ONCE, applies `budget_cap` against an **estimated batch cost** ONCE
(truncating the batch to fit the cap), then enqueues a **single bounded multi-lead job in the `/run`
shape** (concurrency/daily caps set from the tenant rec), not N retry jobs. `lifecycle_fires` rows are
still written per (rule, contact, cycle_key) for idempotency. This makes `budget_cap` real and keeps
one job per tick per rule instead of N.

### RTF-3 (PIN is unbuilt — fail closed, say so) — `require_pin` has no verifier in live source

**Defect.** Grep of `caller.py` for `pin|approval|approve|verify_pin` returns **no PIN/approval
primitive** — none exists today. The spec's `require_pin`/`POST /actuate?pin=` therefore checks a PIN
against nothing; "present" ≠ "verified." Test §9(f-iv) only asserts "no PIN → no enqueue," which a
no-op verifier also passes (theater).

**Fix.** Until the AI-Manager PIN/approval primitive ships, the PIN/approval gate is **fail-closed**:
any rule/action with `require_pin=true` (the default) **does NOT enqueue** from an unattended
`scheduler_loop` tick (no interactive PIN possible there) and **does NOT enqueue** from `/actuate`
unless a real verifier returns true. crm-core MUST NOT inline its own auth; it calls a single
`crm._pin_ok(tenant, pin) -> bool` that **returns False when the primitive is absent** (import-guarded,
like `_crm = None`). Risky actuation thus stays dark until AI-Manager wires the verifier — correct
default. Test §9(f) is strengthened: add **(v) WRONG pin → 0 enqueue** and **(vi) require_pin rule on a
scheduler tick (no PIN context) → 0 enqueue**. Without (v)/(vi) the PIN gate is unproven.

### RTF-4 (correctness nits — fold, don't over-index)

- **Table count is inconsistent and the Alembic unit must not miss one.** §2 says "4 new tables",
  §3.6 says "six" but then lists seven. The true count is **7**: `contacts`, `contact_identity`,
  `contact_timeline`, `segments`, `segment_members`, `lifecycle_rules`, `lifecycle_fires`. Alembic
  `0002_crm_core` MUST create **all 7** and add **all 7** to the RLS ENABLE+FORCE loop. (§2's "4" and
  §3.6's "six" are corrected to 7 here.)
- **`_classify_outcome` enumeration is incomplete.** Live `caller.py:909` + `_REAL_CONVO` (`:924`)
  also emit **`not_interested`**. Stage derivation (§4.1) and NBA (§4.3) must treat `not_interested`
  explicitly (→ stage stays `contacted`/`engaged` per answered-call rule; NBA → `nurture`/`none`, NOT
  a re-pitch), or a hot re-engagement could target someone who declined. Add `not_interested` to the
  §0.1 outcome list.
- **Circular-import guard.** `canonical_phone` calls `caller.norm`, but `caller.py` imports `crm`
  (§8.1). Resolve via the existing `auth.py`-style pattern: `crm` does a **lazy/injected** reference
  to `norm` (e.g. `crm.init(_store, config, norm=norm)` or a function-local import), never a
  top-level `import caller`. Otherwise `import caller` fails at boot and §9(g) flag-off-byte-identical
  breaks hard.
- **Gate-order wording.** §0.1 lists "suppression-skip → calling-window" but in `run_job` the
  **window check is the outer-loop gate (`:1652`), evaluated before** the inner suppression skip
  (`:1671`). Both fire; the ordering in prose is cosmetic but should read "calling-window →
  suppression-skip → concurrency → daily-cap" to match source.

### Residual risks (accepted, GO with eyes open)

1. **PIN dependency.** Risky actuation is dark until AI-Manager ships a real PIN/approval verifier
   (RTF-3). This is the safe failure mode, but it means "lifecycle auto-re-engagement with spend" is
   not live on day one — it's gated behind an unbuilt component. Honest scope: crm-core ships the
   spine + timeline + segments + rule-based NBA + **dry-run** lifecycle; spend-actuating lifecycle
   turns on only after the verifier lands.
2. **Projection lag during P1 dual-mode.** Per §0.3, crm reads off the dual-mirrored PG tables while
   P1 is mid-strangle; the timeline/contacts can lag the JSON truth. Mitigated by deterministic-id
   idempotent append + `rebuild_timeline` self-heal + JSON-union fallback, but a freshly-finished call
   may be momentarily absent from a contact's timeline. Acceptable for a read-model; not acceptable if
   any spend decision were made off it — and none is (spend re-checks `_admission_gate` against the
   authoritative meter, not the projection).
3. **Batch cost estimate is approximate** (RTF-2). `budget_cap` truncates the batch on an *estimated*
   per-call cost; actual spend is metered post-call by the existing `_charge_call`. The cap is a
   pre-spend ceiling, not a hard ledger lock — a long over-running batch could marginally exceed it.
   Bounded by the tenant daily-cap + monthly-minutes admission, so the blast radius is small.

### VERDICT: **GO** — conditional on RTF-1, RTF-2, RTF-3 being folded as written (they now are above).

The spec correctly reuses the built head-start (verified: `norm`, `_update_lead_after_call`,
`_classify_outcome`, `_finalize_call`, `run_job`, `scheduler_loop`, WA handler all exist and behave as
cited; it adds an additive Alembic `0002` + projection/intent layer, never a second writer of core
records), sits on the settled P1 architecture without relitigating it, and surfaces+fixes the real
phone-canonicalization silent-join bug. The one defect that, unfixed, would be a **NO-GO on the exact
spend guardrail the task asks about** — the balance/monthly admission gate not firing on the enqueue
path — is folded as RTF-1 with a dedicated acceptance test §9(i). With RTF-1–4 folded, scope is honest,
the design is non-breaking (flag-off byte-identical), and spend/PIN safety fail closed.

---

*Author: Staff Engineer. This spec composes on the settled foundation (Postgres + RLS + `store.py`
MODE router + Hatchet/scheduler + the planes) per `ARCHITECTURE_DECISION.md` and `design/p1-postgres.md`;
it reuses the existing scoring/finalize/scheduler/webhook machinery in `caller.py` and adds only an
additive, flag-gated projection + intent layer. No core record gets a second writer; all actuation
re-enters the existing gated dial path. Live site keeps earning; flag-off is byte-identical.*
