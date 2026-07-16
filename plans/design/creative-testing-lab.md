# DESIGN SPEC — Creative Testing Lab (`droplet_work/creative/testinglab/`)

> **Status:** EXECUTION-READY. A build agent implements this verbatim, ONE verifiable UNIT at a
> time, running the offline acceptance test before the next.
> **NO git** (the orchestrator commits). **NEW files ONLY under `droplet_work/creative/`.**
> **DO NOT edit `caller.py` / `agent.py`** (backend spine; final wiring deferred — endpoints below
> are *defined*, not mounted). Every integration is **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS**: a
> no-op returning `{"status":"not_configured"}` that **NEVER raises** until creds exist — exactly
> like `droplet_work/whatsapp.py` (the canonical pattern, verified on disk 2026-06-09).
> **Verifiable OFFLINE** — the acceptance test makes **ZERO** live external calls and needs **no
> sibling module on disk**.

Research date: **2026-06-09**. Reuse seams verified against `C:\Users\kunal\Desktop\caps\droplet_work\`.

---

## 0. WHAT THIS IS — and the ONE sentence that makes it non-redundant

The **Creative Testing Lab** is the **cross-creative SCOREBOARD + decision loop**. It compares every
creative — banner / video / **headline / landing / CTA / WhatsApp angle** — by
**impressions · clicks · CTR · leads · CPL · conversion · WhatsApp-replies · call-bookings ·
revenue**, on ONE table; **flags weak creatives for regeneration**; and **duplicates/scales winners
into paid**. It powers the `Creative Studio → Testing Lab` sub-page.

> **THE KEYSTONE (state it loud — it is the whole reason this module exists separate from the
> ads-engine):** the **unit of analysis is the CREATIVE-DNA (the creative-tag), JOINED ACROSS
> CHANNELS — not the paid ad-variant.** The ads-engine (`creative-ads-engine.md`) already owns
> per-*paid-variant* CTR/CPC/CPL/ROAS, the bandit, and kill/scale/reallocate. If our unit were the
> ad-variant, we would be a fourth copy of that metrics layer. Instead our row is one **creative
> concept** keyed by its **channel-invariant DNA** (`{angle, hook_style, cta, persona, language,
> offer_emphasis}` — drawn from the tag taxonomy `creative-creative-batch.md` §2.4 minted and
> **explicitly deferred to "downstream ads-analytics"**; the channel-varying fields `asset_kind` /
> `format` are **breakdown attributes, NOT part of the identity** — see §5.1), and we **unify its
> performance across PAID + WhatsApp + VOICE-CALL + ORGANIC**
> into a single scoreboard row. The same hook that ran as a paid ad AND a WhatsApp angle AND a
> landing headline becomes **one ranked row**; the ads-engine only ever sees the paid instance.

**Existence proof, task-grounded (not a clever reading):** the founder's metric list includes
**WhatsApp-replies** and **call-bookings**. Those are **not paid-ad metrics** — no ad SDK reports
them. That list *forces* the cross-channel scope, which the per-paid-variant ads-engine structurally
cannot provide. That is why this module is a distinct pillar.

> **What does Testing Lab compute that the ads-engine cannot?** *A per-creative-DNA scoreboard that
> unifies paid + WhatsApp-reply + call-booking + organic-lead + revenue signals on the tag key, plus
> the regenerate/promote decision loop back into `creative-batch` and the ads-engine.* That sentence
> is the spine; everything below serves it.

---

## 0.1 REUSE vs NET-NEW (the boundary table — the #1 thing that keeps this non-redundant)

| Concern | Owner | Testing Lab's relationship |
|---|---|---|
| **Paid spend rails, bandit, kill/scale/reallocate, per-paid-variant CTR/CPC/CPL/ROAS, the spend-cap breaker, approval gate, the autonomous loop** | **`creative-ads-engine.md`** (`creative/` ads engine) + **`automation-ads.md`** | **CONSUME — never re-implement.** We **READ** the ads-engine's persisted `var/creative/variant_metrics.jsonl` + `experiment_status()` + `attribution_rollup()`. We run **no** bandit, touch **no** ad-platform API, move **no** money. |
| **Creative GENERATION** (hooks/copy/banners/videos/3D/landing/WA angles) + the **creative-tag taxonomy** + the master brief | **`creative-creative-batch.md`** (`creative/batch/`) (text/briefs) + the media studios | **CONSUME the tags; HAND BACK regeneration requests.** We generate nothing. We read each variant's tag set and EMIT a "regenerate this DNA" handoff that `creative/batch/` drains. |
| **Leads / CRM / call-bookings / WhatsApp-replies / revenue / analytics** | the **existing spine** (`caller.py` routes `/leads`, `/analytics`, `/whatsapp/log`, call/booking records) + `whatsapp.py` | **READ via the SAME loopback seam the ads-engine's `spine_link.py` established** (authenticated localhost loopback + a service token). We add **no** lead/call/WhatsApp store; we read the spine's and join on the creative-tag. |
| **NET-NEW (what THIS module owns)** | — | the **cross-channel JOIN on the creative-tag** (§4); the **unified scoreboard + composite ranking + weak/winner classifier with a significance gate** (§5, the core); the **two gated DECISION HANDOFFS — regenerate→batch, promote-winner→ads-engine-DRAFT** (§6); the **`Creative Studio → Testing Lab` sub-page** (§8). |

> **We add NO spend layer, NO bandit, NO generator, NO new lead/call/WA store.** We are a
> **read-join-rank-decide** module. Two outputs only: a **regenerate** handoff and a **promote-to-paid
> DRAFT** handoff. Both are **gated by inheritance** (§6.3) — we never spend and never launch.

### 0.2 The autonomy ⇄ approval reconciliation (resolved explicitly, mirrors ads-engine §0.3)

The brief says "duplicate/scale winners **into paid**" — i.e. new money. We reconcile "autonomous
testing" with "human-approved spend" by **owning only the read/decide half and inheriting the gate**:

| Action | Autonomy | Why safe |
|---|---|---|
| Rank creatives, compute the scoreboard | **fully autonomous** | read-only; spends nothing |
| **Flag a weak creative → regenerate** | **fully autonomous** | emits a handoff to `batch`; generating a *draft* creative costs only batch's own (separately gated) media budget, never ad spend |
| **Promote a winner → paid** | **autonomous PROPOSE, human-gated LAUNCH** | we call ads-engine `propose_experiment` which lands a **DRAFT at `pending_approval`** (its §3 contract). The **approval/step-up gate lives in the ads-engine**, not here. We hand off a draft; a human approves the launch there. **We never trip live spend.** |

> This is "fully autonomous analysis + draft promotion; human-approved live spend." Defensible, not
> hype. The honest line: **promoting a winner produces a DRAFT experiment, not a live campaign.**

---

## 1. CHOSEN TOOLS + WHY (web-researched 2026-06-09; ACTIVE, cited §12; none abandoned)

**Headline decision (settled; web-verified 2026-06-09, §12).** Two distinct categories exist, and
**neither gives us a self-hostable ad-creative scoreboard to adopt**:

1. **Self-hostable OSS experimentation engines** — **GrowthBook** (MIT, self-host, Bayesian +
   frequentist engines, warehouse-connected) and **PostHog** (OSS, self-host, A/B + multivariate +
   feature flags). These are **product / feature-flag experimentation** tools (split *users* on flags,
   analyze in your warehouse) — they do **not** ingest ad-platform creative metrics or tag creatives
   by DNA. *Genuinely useful seam:* GrowthBook's frequentist/Bayesian significance test could later
   **harden** our §1.2 sample-gate if we ever want a true p-value — noted as an **optional** upgrade,
   not a dependency.
2. **Ad-creative analytics** — the whole category (**Motion, Segwise, AdCreative.ai, VidMob, CreativeX,
   Marpipe, Madgicx**) is **proprietary SaaS**, subscription, built around *their* ad-data warehouse,
   **none self-hostable**. (Confirmed 2026-06-09: searches returned zero self-hostable OSS ad-creative
   analytics engine.) Notably **Segwise's multimodal element-tagging → bottom-funnel-metric mapping**
   validates the *tag → metric* scoreboard concept this module implements — but as a closed SaaS we
   cannot adopt it, and it is per-channel ad data, not our cross-channel (paid+WhatsApp+voice) join.

**So this module is COMPOSED from primitives we already have**, not adopted:

> **Reuse the existing tag taxonomy (batch) + read the existing metrics (ads-engine + spine loopback)
> + a small DETERMINISTIC scoring/ranking pass we own (composite score + significance gate) — ZERO
> new vendor, ZERO new SDK, ZERO new key.**

### 1.1 The scoreboard JOIN + ranking — **a deterministic pure-Python pass we own (~200 lines)**
Comparing creatives by a composite of CTR / CPL / conversion / WhatsApp-reply-rate / call-booking-rate
/ ROAS, normalized and weighted, with a min-sample gate, is **explainable arithmetic**, not ML. We own
it because (a) the real per-campaign ML is the platforms' auto-bidding (ads-engine §1.3), (b) the
cross-variant budget decision is the ads-engine's bandit, and (c) what's left — *which creative DNA is
winning across channels, and is the sample big enough to act* — is deterministic, auditable, and
**offline-testable**. Pure `random`-free arithmetic + sorting; `numpy`/`scipy` are an **optional**
accelerator imported defensively (`try/except → None`), never required.

### 1.2 Statistical-significance gate — **REUSE the min-sample discipline (anti-noise, load-bearing)**
A creative is declared **weak (→regenerate)** or **winner (→promote)** ONLY after it clears a
**minimum-sample gate** (impressions ≥ `MIN_IMPRESSIONS`, default 1000; conversions/leads ≥
`MIN_CONVERSIONS`, default 15 — same constants the ads-engine §1.3 and `automation-ads.md` §5.4 use).
Below the gate a creative is **"insufficient_data"** — never flagged weak, never promoted. This is the
difference between a real testing lab and a coin-flip; a regeneration loop that churns on 3 clicks
would waste the founder's media budget.

> **Statistical-confidence honesty (anti-hype):** the composite ranking is a **practical heuristic**
> (normalized weighted score over rate metrics), NOT a frequentist p-value or Bayesian posterior — the
> ads-engine's bandit owns the Bayesian variant-selection math. The Testing Lab's job is *comparison +
> a sample-sufficiency floor + a clear weak/winner band*, with **every decision logged with its
> sample counts and the rule that fired** (§4.4 `lab_decisions.jsonl`). We do not claim "statistically
> significant winner at 95%"; we claim "ranked, sample-gated, explainable." (§11.)

### 1.3 No new LLM / media vendor
Regeneration **text/media is produced by `creative/batch/`** (which already routes the in-house LLM
seam + media studios). Testing Lab emits a **regeneration request**; it generates nothing and
introduces **no LLM/media key.** (§6.1.)

### 1.4 The metric sources are all ALREADY in the system — we only JOIN them
| Signal | Source (already exists / specced) | How we read it |
|---|---|---|
| impressions, clicks, CTR, CPC, spend, CPL, conversions, ROAS (PAID) | ads-engine `var/creative/variant_metrics.jsonl` + `experiment_status()` / `attribution_rollup()` | read the persisted JSONL + call the read-only fns (injected) |
| leads (all channels) | spine `GET /leads` (loopback) | join lead→creative-tag by tracking tag / utm / `variant_id` |
| WhatsApp-replies | spine `GET /whatsapp/log` (loopback) — `whatsapp.py` already logs sends/inbound | reply-rate per WA-angle variant by the angle's `variant_id` tag |
| call-bookings | spine call/booking records (loopback `GET /analytics` / `/stats`) | booking-rate per creative that sourced the lead |
| revenue | spine `GET /analytics` (loopback) + ads-engine `attribution_rollup` | revenue per creative-tag where conversion value exists |

We do **not** pull any of these directly from a vendor; every source is the spine's or the ads-engine's
**already-normalized** output. This is the cheapest, most honest design: **a join, not a re-ingest.**

---

## 2. ARCHITECTURE & PACKAGE LAYOUT (NEW; ALL under `droplet_work/creative/testinglab/`)

> **Sub-package, NOT flat.** Matches `creative/batch/` and `creative/landing/`. (The ads-engine spec's
> flat `creative/*.py` layout is a pre-existing inconsistency; we do **not** propagate it — flat
> `config.py`/`store.py`/`__init__.py` would collide with the batch/landing sub-packages.)

```
droplet_work/creative/testinglab/
  __init__.py            # import-safe with empty env; public surface re-export
  README.md              # what it does, cred list, how to run the offline test
  config.py              # env reads + *_configured() gates (whatsapp.py style)
  models.py              # Pydantic v2: CreativeRow, ChannelMetrics, ScoreCard, Decision, HandoffRef
  links/
    __init__.py
    ads_link.py          # READ the ads-engine's metrics: variant_metrics.jsonl + experiment_status/attribution_rollup (injected; fake fallback)
    batch_link.py        # READ creative variants+tags from creative/batch (injected); EMIT regenerate handoff
    spine_link.py        # READ loopback /leads /analytics /whatsapp/log /stats (service token, dormant); NEVER imports caller.py
  join.py                # build the per-creative-DNA row: gather tag → all-channel signals, join on variant_id/tag
  score.py               # composite score + normalization + weak/winner banding (pure, deterministic)
  gate.py                # significance gate (MIN_IMPRESSIONS / MIN_CONVERSIONS) -> insufficient_data | eligible
  scoreboard.py          # THE CORE: assemble + rank + classify -> ScoreCards (the sub-page's data)
  decide.py              # weak->regenerate handoff ; winner->promote-to-paid DRAFT handoff (gated by inheritance)
  store.py               # atomic JSON/JSONL under var/creative/testinglab/ (mirrors batch/landing store)
  service.py             # ORCHESTRATION facade: the pure callables the spine wires later (§3)
  endpoints.py           # FastAPI APIRouter — DEFINED here, MOUNTED later by the spine (deferred)
  tests/
    __init__.py
    fixtures/            # fake paid snapshots + fake leads/WA-replies/call-bookings/revenue rows
    test_testinglab_offline.py   # ZERO-network acceptance test (§10)
```

**Import safety & packaging (PINNED — matches the spine's flat `droplet_work/`-as-root convention,
verified against `caller.py:35-37` bare imports and the sibling specs):** reach spine deps by **bare
name** (`import audit`, `from config import get`); reach siblings **inside `try/except`**
(`try: from creative.batch import regenerate_request except Exception: ... = None`;
`try: from creative.adsengine import propose_experiment, experiment_status except Exception: ... = None`
— resolved against whatever the ads-engine module is finally named). Every link resolver **falls back
to a fake/dormant source** so the package imports cleanly and the offline test runs with **zero
network whether or not any sibling exists.** No module-level network, no `require()` at import.

### 2.1 On-disk reuse seams (VERIFIED 2026-06-09 — code against these real symbols)
| Reuse | Symbol (verified) | Use |
|---|---|---|
| Dormancy pattern | `whatsapp.py` `_cfg()` / returns `{"status":"not_configured"}` / `# noqa: BLE001` never-raises / lazy `httpx` | copy shape for every link resolver |
| Immutable audit | `audit.record(actor, action, object_type, object_id, …, meta=)` (L60), `audit.tail(limit, action_prefix=)` (L102), `audit.init(path)` (L36) — append-only JSONL, never raises | write `creative.lab.*` actions; read for the sub-page |
| Config resolver | `config.get(key, default)` (L100), `config.require(key)` (L107), `config.source()` (L118) — Doppler-over-env | read all knobs (a later `.env` paste works, no code change) |
| Secret hygiene | `vendors.redact(secret)` (first/last-4) | redact the loopback service token in logs |
| Loopback read seam | the ads-engine `spine_link.py` posture (authenticated `http://127.0.0.1:<port>/leads|/analytics|/whatsapp/log`, `AIMANAGER_SERVICE_TOKEN`, dormant-until-set) | **reuse the same token + the same loopback pattern**; do not invent a second one |

---

## 3. PUBLIC INTERFACE — `service.py` (the pure callables the spine wires later)

`status` vocabulary:
`not_configured | ok | insufficient_data | dry_run | regenerate_queued | promote_drafted |
blocked_not_eligible | error:<...>`

```python
def scoreboard(tenant_id: str, *, scope: dict | None = None,
               ads=None, batch=None, spine=None, now=None) -> dict
    # THE CORE READ. scope = {"campaign_id"|"batch_id"|"product_id", "window":"7d", "channels":[...]}.
    # 1) batch_link  -> creative variants + their tag sets (the rows to score)
    # 2) ads_link    -> per-paid-variant metrics (impr/clicks/CTR/CPC/CPL/conv/ROAS/spend)
    # 3) spine_link  -> leads, WhatsApp-replies, call-bookings, revenue (loopback)
    # 4) join.build  -> one CreativeRow per creative-DNA, signals merged across channels on the tag key
    # 5) gate.apply  -> insufficient_data | eligible   6) score.rank -> composite score + weak/winner band
    # Returns {scorecards:[...sorted...], summary, flags:{weak:[...], winners:[...], insufficient:[...]}}.
    # PURE + offline-safe. Reads only; NEVER spends, NEVER launches. Audited (creative.lab.scoreboard).

def flag_weak(tenant_id: str, *, scope=None, ads=None, batch=None, spine=None) -> dict
    # Run scoreboard -> for each WEAK creative that CLEARED the significance gate, EMIT a regenerate
    # handoff to creative/batch (batch_link.regenerate_request). Idempotent per (creative_tag, window).
    # Audited (creative.lab.regenerate). Never generates anything itself.

def promote_winner(tenant_id: str, creative_id: str, *, scope=None, ads=None, batch=None) -> dict
    # For a WINNER that cleared the gate, call the ads-engine propose_experiment(...) to create a
    # DRAFT/pending_approval paid experiment (duplicate/scale into paid). Returns the draft's id +
    # status="promote_drafted". DOES NOT approve/launch (the ads-engine gate owns that). Audited.

def decisions(tenant_id: str, *, scope=None) -> dict   # the immutable decision log (regenerate/promote) for the sub-page
def health() -> dict                                   # {ads:..., batch:..., spine:...} link status map (read)
```

All have `_async` twins where the spine loop calls them. `ads`, `batch`, `spine`, `now`, and the store
read/write fns are **injected** (default to real impls) so the offline test runs with fakes and **zero
network**.

---

## 4. DATA MODEL (NET-NEW — the cross-channel join; files under `var/creative/testinglab/`)

### 4.1 `CreativeRow` — ONE row per creative-DNA (the join output; this is the net-new artifact)
```json
{
  "creative_id": "cr_<dna-hash>",            // hash of the CHANNEL-INVARIANT dna ONLY (see §5.1)
  "tenant_id": "<org>",
  "dna": {"angle":"urgency","hook_style":"question","cta":"book_now",
          "persona":"sme_owner","language":"hi","offer_emphasis":"discount"},  // the identity (hashed)
  "instances": [                              // the per-channel breakdown — asset_kind/format live HERE, NOT in the id
    {"variant_id":"vr_a","asset_kind":"banner",  "format":"feed",  "channel":"paid"},
    {"variant_id":"vr_b","asset_kind":"wa_angle","format":"text",  "channel":"whatsapp"},
    {"variant_id":"vr_c","asset_kind":"landing", "format":"hero",  "channel":"organic"}
  ],
  "variant_ids": ["vr_a","vr_b","vr_c"],      // every channel instance of this DNA (paid + WA + landing)
  "batch_id": "ba_...", "campaign_id": "...",
  "channels": {
    "paid":     {"impressions":0,"clicks":0,"ctr":0.0,"cpc_minor":null,"spend_minor":0,
                 "leads":0,"cpl_minor":null,"conversions":0,"revenue_minor":null,"roas":null},
    "whatsapp": {"sends":0,"replies":0,"reply_rate":0.0},
    "voice":    {"leads":0,"calls":0,"bookings":0,"booking_rate":0.0},
    "organic":  {"impressions":0,"leads":0}
  },
  "by_format": {"banner":{...per-format rollup...},"video":{...}},  // optional breakdown: "wins as banner, flops as video"
  "totals": {"leads":0,"conversions":0,"revenue_minor":null,"impressions":0},
  "sample": {"impressions":0,"conversions":0,"eligible":false}   // significance-gate inputs/result
}
```

### 4.2 `ScoreCard` — the ranked, classified view (the sub-page renders these)
```json
{
  "creative_id":"cr_...","dna":{...},"formats":["banner","wa_angle","landing"],  // identity + which formats it ran as
  "metrics":{"ctr":0.0,"cpl_minor":null,"conversion_rate":0.0,"wa_reply_rate":0.0,
             "call_booking_rate":0.0,"roas":null,"revenue_minor":null},
  "composite_score": 0.0,                     // normalized weighted score (§5.2); higher = better
  "rank": 1,
  "band": "winner|strong|average|weak|insufficient_data",
  "reasons": ["ctr top-decile","cpl below median","sample >= gate"],   // explainability
  "recommended_action": "promote|regenerate|hold|wait_for_data"
}
```

### 4.3 `MetricsSnapshot` REUSED from the ads-engine for the paid channel
The paid block mirrors the ads-engine's `MetricsSnapshot` shape verbatim (`provider, campaign_ref,
spend_minor, impressions, clicks, conversions, cpl_minor, ctr, cpc_minor, revenue_minor, roas,
currency, fetched_ts`). `cpl_minor=None`/`revenue_minor=None` ⇒ no conversion/value tracking ⇒ the
ROAS/CPL terms self-disable and the score falls back to **CTR + WhatsApp-reply-rate +
call-booking-rate** (engagement signals) — we never fabricate a conversion or revenue (same discipline
as ads-engine §4.3 / `automation-ads.md` §1.5).

### 4.4 `var/creative/testinglab/` files
`scoreboards/<scope_hash>.json` (latest scoreboard, atomic write) · `lab_decisions.jsonl`
(append-only: every weak-flag + promote with `{creative_id, action, band, composite_score, sample,
rule_fired, ts}` — explainability + idempotency source) · `handoffs.jsonl` (append-only regenerate +
promote handoff rows the siblings drain, §6). Append-only logs mirror `audit.py`'s immutability.

---

## 5. THE SCOREBOARD + CLASSIFIER — `scoreboard.assemble()` (THE CORE; deterministic; offline-testable)

```
scoreboard(tenant, scope, ads, batch, spine, now):
  1. ROWS:    batch_link.variants(scope) -> list of creatives + tag sets (the universe to score)
  2. PAID:    ads_link.metrics(variant_ids) -> per-paid-variant MetricsSnapshot (read JSONL + fns)
  3. NONPAID: spine_link.signals(scope) -> leads, wa_replies, call_bookings, revenue (loopback)
  4. JOIN (join.build): for each creative-DNA, merge ALL channel instances on the creative-tag/variant_id
              -> one CreativeRow with channels.{paid,whatsapp,voice,organic} + totals + sample
  5. GATE (gate.apply): eligible = impressions >= MIN_IMPRESSIONS AND conversions(or leads) >= MIN_CONVERSIONS
              -> below gate => band="insufficient_data", action="wait_for_data" (NEVER weak, NEVER promote)
  6. SCORE (score.rank): for ELIGIBLE rows compute composite_score (§5.2), normalize, sort desc, assign rank
  7. BAND:    top band -> "winner" (action promote) ; bottom band + cleared gate -> "weak" (action regenerate)
              middle -> strong/average (hold). Bands by configurable percentile cuts (§5.3).
  8. RECORD:  write scoreboards/<hash>.json ; audit.record(creative.lab.scoreboard) ; return ScoreCards + flags
  (PURE read; mutates only our own var/ files; spends nothing, launches nothing.)
```

### 5.1 Cross-channel JOIN (the net-new heart) — the identity key is CHANNEL-INVARIANT (load-bearing)
> **The identity hash MUST exclude channel-varying fields, or the keystone breaks.** A build agent
> who hashes the full tag set (with `asset_kind`/`format`) gets a **different id per channel** → three
> rows for one concept → §10.2 fails and the module degenerates into the per-variant duplicate of the
> ads-engine. So:
>
> `creative_id = hash(dna)` where **`dna` = the channel-invariant concept dims ONLY**
> (`angle, hook_style, cta, persona, language, offer_emphasis`). **`asset_kind`, `format`,
> `variant_id`, `batch_id`, `channel` are per-INSTANCE breakdown attributes** (stored under
> `instances[]` / `channels.*` / `by_format`), **never** in the identity hash.

The batch's tag taxonomy guarantees the same concept hashes equal across channels. Join keys: **paid**
by `variant_id` → ads-engine metrics; **leads/WhatsApp/voice** by the lead/message's tracking tag →
`variant_id` → `creative_id` (the ads-engine's `attribution.py` already stitches lead→variant by the
tracking tag; we **read** that stitch and roll it up to the DNA). A concept that appears as a banner +
a WhatsApp angle + a landing headline yields **ONE** `CreativeRow` aggregating all three — the thing
the ads-engine cannot produce. This is also a **feature, not just a merge:** the `by_format` breakdown
lets the lab say *"`urgency+book_now` wins as a banner, flops as a video"* — concept-level identity,
format-level diagnosis.

### 5.2 Composite score (deterministic, weighted, normalized — explainable)
`composite = Σ wᵢ · normalize(metricᵢ)` over the available rate metrics, default weights
(`LAB_WEIGHTS`, env-tunable): `conversion_rate 0.30 · cpl 0.20 (inverted, lower=better) · ctr 0.15 ·
roas 0.15 · wa_reply_rate 0.10 · call_booking_rate 0.10`. Each metric **min-max normalized within the
eligible cohort** (so it is a *relative* ranking, honestly labeled). Missing metrics (no conversion
tracking / channel absent) **drop out and their weight redistributes** — the score never penalizes a
creative for a channel it never ran in, and never invents a value. Pure arithmetic; deterministic given
the same rows.

### 5.3 Banding (configurable percentile cuts, not magic thresholds)
`LAB_WINNER_PCT` (default top 20%) → **winner**; `LAB_WEAK_PCT` (default bottom 20%) → **weak**;
middle → strong/average. A creative enters winner/weak **only if eligible** (§5 step 5). Cuts are
config so the founder tunes aggressiveness; defaults are conservative.

### 5.4 Safety properties (mirror the siblings): read-before-decide; the significance gate prevents
flagging/promoting on noise; the score never fabricates a metric; every band/decision is logged with
its sample counts and the rule that fired (`lab_decisions.jsonl`); decisions are idempotent by
`(creative_id, scope_hash, window)`; the module mutates only its own `var/` files and emits handoffs —
it **cannot** spend or launch (that authority lives behind the inherited gates, §6.3).

---

## 6. THE TWO DECISION HANDOFFS — `decide.py` (the loop back into the system)

> Testing Lab's *output* is **two handoffs**, both **gated by inheritance** (we own the decision, the
> sibling owns the irreversible action). This is how "flag weak for regeneration" and "duplicate/scale
> winners into paid" happen **without** this module ever generating a creative or spending a rupee.

### 6.1 Weak → REGENERATE (handoff to `creative/batch/`)
For each **weak + gate-cleared** creative, `decide.flag_weak` writes a **regenerate handoff** to
`handoffs.jsonl` and calls `batch_link.regenerate_request(creative_id, tags, reason, scope)` (the
batch's existing fan-out — it re-runs Phase-1 text/brief, or Phase-2 media behind **its own** approval
+ spend gate). Testing Lab generates **nothing**; it tells batch *which DNA underperformed and why*
(the tag dimensions to vary). If `creative/batch/` is absent ⇒ handoff is recorded as
`{"status":"module_absent"}` and the row is logged for the sub-page — no error, no network.

### 6.2 Winner → PROMOTE-TO-PAID (handoff to the ads-engine as a DRAFT)
For each **winner + gate-cleared** creative, `decide.promote_winner` calls the ads-engine
`propose_experiment(tenant, dropdown_selection=<from the winning DNA + scope>)` which (per its §3
contract) persists a **DRAFT experiment at `status="pending_approval"` and touches no platform.** We
return `{status:"promote_drafted", experiment_id}`. **This is the difference from batch's initial
fan-out:** batch proposes the *untested* batch; **we promote the empirically-validated winner** — a
duplicate/scale candidate backed by real cross-channel performance. The **launch still requires the
ads-engine's human approval/step-up** (its Inv B). If the ads-engine module is absent ⇒
`{"status":"module_absent"}` handoff recorded; no spend, no network.

### 6.3 Why this is safe (the inheritance argument, stated plainly)
- We **never** call an ad-platform API → we **cannot** spend.
- Promote produces a **DRAFT** → the **ads-engine approval gate** (firewall step-up on
  `approve_experiment`) is the only path to live spend, and it is **unchanged and not ours**.
- Regenerate produces a batch request → the **batch's own approval + spend cap** gates Phase-2 media.
- The only thing we own is **the decision + its audit trail.** Every handoff is logged immutably; a
  `LAB_DRY_RUN=1` flag (default ON) makes `flag_weak`/`promote_winner` compute and log the decision
  **without emitting the handoff** (preview + the offline-test path).

---

## 7. HOW IT CONNECTS — ads → leads → CRM → voice → WhatsApp → analytics (the revenue loop)

Testing Lab is the **measurement + feedback junction** of the loop — it reads the *outcome* of every
channel and feeds the *decision* back to the front:

```
  creative/batch  ──generates──►  variants (tagged)  ──►  ads-engine (paid) ─┐
        ▲                                                 whatsapp.py (WA)   ─┤ run in market
        │ regenerate handoff (§6.1)                       caller.py (voice)  ─┤
        │                                                 landing (organic)  ─┘
        │                                                          │
        │                          ┌──────────── outcomes ─────────┘
        │                          ▼
   ┌────┴──────────────  TESTING LAB  ◄── READS: ads-engine variant_metrics.jsonl + attribution_rollup
   │  (join on creative-DNA,          ◄── READS: spine loopback /leads /analytics /whatsapp/log /stats
   │   rank, gate, classify)
   │          │
   │          ├── winner ──► promote_winner ──► ads-engine propose_experiment (DRAFT, human-gated launch)
   │          └── weak  ────► (loop back up to creative/batch to regenerate)
   └── scoreboard + decisions ──► Creative Studio → Testing Lab sub-page (§8) + audit.tail("creative.lab")
```

- **ads → leads → CRM:** we **read** the ads-engine's already-stitched lead→variant attribution and
  roll it up to the creative-DNA; we add no lead store.
- **WhatsApp:** WA-angle creatives' **reply-rate** comes from `whatsapp.py`'s send/inbound log
  (loopback `/whatsapp/log`); a winning WA angle can be promoted, a weak one regenerated.
- **Voice:** **call-booking-rate** per creative comes from the spine's call/booking records — the
  "did this creative produce a lead that booked a call" signal, which no ad SDK reports.
- **analytics / billing:** `scoreboard` + `decisions` feed the sub-page; `audit.tail("creative.lab")`
  is the immutable decision history. **We add no meter** — we spend nothing; the cost of any
  regeneration/promotion is metered by `batch`/`ads-engine` when *they* act.

**Honest dependency:** the cross-channel join is only as complete as the tracking tags. Where a channel
lacks a tag linking a lead/reply/booking back to a `variant_id`, that signal is reported as
`unattributed` for that creative (counted in a tenant-level bucket, never mis-assigned). We never guess
which creative drove an untagged lead.

---

## 8. THE CREATIVE-STUDIO SUB-PAGE THIS POWERS

Creative Studio is a **sidebar SECTION** following the **Billing multi-page pattern** (verified:
`Billing` is a sidebar dropdown group with children routes `/billing/{overview,vendors,explorer,
audit,plan}`). Creative Studio mirrors this; the children are owned by their modules: `batch`
(generator), `gallery`, `landing`, the ads-engine's `autonomous-ads`, and **`testing-lab` (THIS
module)**.

> **This module powers `Creative Studio → Testing Lab` (`/creative-studio/testing-lab`).** It renders
> the **cross-creative SCOREBOARD**: every creative as a ranked row with CTR / CPL / conversion /
> **WhatsApp-reply-rate** / **call-booking-rate** / ROAS / revenue side-by-side across channels;
> winner/weak/insufficient **bands** with the **reasons**; a **"Regenerate weak"** action (→ batch)
> and a **"Promote winner to paid (draft)"** action (→ ads-engine, lands a draft for human approval);
> and the immutable **decision log**. Backed entirely by the §3 `service.py` callables via the §9
> endpoints. (Backend spec only — the frontend page is a separate UI unit; this doc names and
> contracts it.)

> **Nav reconciliation (avoid collision):** the ads-engine §8 floated a tentative `analytics` child.
> **We claim the distinct `testing-lab` route** for the *cross-creative comparison + regenerate/promote*
> surface; any pure paid-spend analytics stays under the ads-engine's `autonomous-ads`. No overlap.

---

## 9. ENDPOINTS (DEFINED here, MOUNTED later by the orchestrator — DO NOT edit `caller.py`)

`router = APIRouter(prefix="/creative/lab", tags=["creative-testing-lab"])`, `manager`-scoped except
reads. `endpoints.py` guards `try: from fastapi import APIRouter except Exception: router = None`.

| Method/Path | → service fn | Auth |
|---|---|---|
| `GET  /creative/lab/scoreboard` (query: scope/window/channels) | `scoreboard` | manager (read) |
| `POST /creative/lab/flag-weak` | `flag_weak` | manager |
| `POST /creative/lab/promote/{creative_id}` | `promote_winner` | manager/admin |
| `GET  /creative/lab/decisions` | `decisions` | manager (read) |
| `GET  /creative/lab/health` | `health` (link status map) | public (read) |

Docstring wiring note (deferred): the spine will `app.include_router(router)` and may add a
`scheduler_loop` tick calling `scoreboard`/`flag_weak` every `LAB_POLL_MINUTES` (default 60) — **NOT
done here.**

---

## 10. OFFLINE ACCEPTANCE TEST (`tests/test_testinglab_offline.py` — ZERO network)

Run (cwd `droplet_work/`): `python -m creative.testinglab.tests.test_testinglab_offline` or
`pytest droplet_work/creative/testinglab/tests/ -q`. With an **empty env**, monkeypatching
`httpx`/SDKs to a sentinel that **raises if called** (proves zero network while dormant), and feeding
**fixture** fake sources (paid snapshots + fake leads/WA-replies/call-bookings/revenue rows), it
asserts:

1. **Import-safe & dormant:** `import creative.testinglab`; `health()` reports each link
   `not_configured|module_absent`; `scoreboard`/`flag_weak`/`promote_winner`/`decisions` each return a
   `status` in `{not_configured, ok, dry_run, insufficient_data}`, raise nothing, make **no** network call.
2. **Cross-channel JOIN (the keystone):** given one concept (same `dna`: angle/hook_style/cta/persona/
   language/offer_emphasis) present as a **paid banner** variant AND a **WhatsApp angle** AND a
   **landing headline** — i.e. **different `asset_kind`/`format` per instance** — `scoreboard` produces
   **exactly ONE** `CreativeRow` (asserts `len(rows)==1`: the three differing `asset_kind`/`format`
   values did **not** split it), whose `channels.paid`/`channels.whatsapp`/`channels.organic` are all
   populated, `variant_ids` lists all three, and `by_format` breaks them out. This is the regression
   test for the §5.1 identity-hash rule — proving the ads-engine-impossible unification.
3. **WhatsApp-reply & call-booking metrics present:** the ScoreCard exposes `wa_reply_rate` and
   `call_booking_rate` computed from the fake WA-log + booking rows (the metrics no ad SDK reports).
4. **Significance gate (anti-noise, load-bearing):** a creative with `conversions=3` /
   `impressions=200` → `band:"insufficient_data"`, `action:"wait_for_data"`, and is **NOT** flagged
   weak and **NOT** promoted; a creative with `impressions>=1000` & `conversions>=15` is eligible.
5. **Ranking correctness:** with crafted fixtures, the higher composite-score creative ranks above the
   lower; a missing-metric creative (no conversion tracking) is scored on the remaining metrics with
   weights redistributed (no fabricated conversion/ROAS), and is not unfairly penalized.
6. **Weak → regenerate handoff (gated by inheritance):** a gate-cleared bottom-band creative →
   `flag_weak` records a `regenerate` handoff via an injected fake `batch_link`; with `creative/batch`
   absent → handoff `{"status":"module_absent"}`, **no generation, no network, no raise.**
7. **Winner → promote DRAFT (gated by inheritance):** a gate-cleared top-band creative →
   `promote_winner` calls an injected fake ads-engine `propose_experiment` and returns
   `status:"promote_drafted"` with the draft id; the fake records the call as a **DRAFT/pending_approval
   only** — `approve_experiment`/`set_budget`/`set_status` are **never** called (no spend, no launch).
8. **Dry-run:** `LAB_DRY_RUN=1` → `flag_weak`/`promote_winner` compute & log the decision but emit
   **no** handoff (assert the fake batch/ads-engine are not called).
9. **No-conversion-tracking fallback:** all paid snapshots `cpl_minor=None`/`revenue_minor=None` →
   ROAS/CPL terms self-disable; the score still ranks on CTR + WA-reply-rate + call-booking-rate; no
   fabricated revenue.
10. **Idempotency & audit:** re-running the same `flag_weak`/`promote_winner` scope produces **no**
    duplicate handoffs/decisions; every scoreboard/flag/promote writes a `creative.lab.*` row via an
    injected fake audit sink.
11. **Unattributed honesty:** a lead/reply with no creative tag is bucketed as `unattributed`, never
    assigned to a creative.
12. **Never-raises fuzz:** malformed scope (empty, bad campaign_id, non-dict), zero creatives, garbage
    metrics each return an `error:`/`insufficient_data` dict, **no exception.**

Exit non-zero on any failure (orchestrator-gateable).

---

## 11. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

> **Testing Lab's OWN net-new creds = effectively ZERO.** It introduces **no ad-platform key, no LLM
> key, no media key** — it reads what the ads-engine + spine already produce. It builds and passes its
> offline test with **none** of the below (dormant-until-creds). All blank ⇒ graceful read of
> fake/empty data; nothing spends, nothing launches.

### 11.1 The one reused connector (NOT a new cred)
- `AIMANAGER_SERVICE_TOKEN` — the **same** admin/manager loopback token the ads-engine's `spine_link`
  uses (a real tenant access token minted server-side via `auth.issue_pair()`, never logged/committed)
  so Testing Lab can READ `/leads` `/analytics` `/whatsapp/log` `/stats` over the authenticated
  loopback. **Reused, not re-issued.** Absent ⇒ Testing Lab runs on injected/fake data and the
  sub-page shows "connect to enable cross-channel scoring."

### 11.2 Upstream creds it BENEFITS from (owned by siblings — not set here)
The richness of the scoreboard depends on the **siblings'** creds being set (the founder sets these in
*those* modules' cred lists, not here):
- **Paid metrics** (impr/clicks/CTR/CPC/CPL/conv/ROAS) ⇒ the **ads-engine / `automation-ads.md`** creds
  (Meta + Google Ads). Absent ⇒ paid columns are empty; the lab still scores on WhatsApp/voice/organic.
- **Revenue/ROAS** ⇒ Meta Pixel+CAPI / Google conversion action (owned by the ads-engine). Absent ⇒
  score falls back to engagement metrics; ROAS column shows `blocked_no_conversion_tracking`.
- **WhatsApp-reply data** ⇒ `whatsapp.py`'s Meta WhatsApp Cloud creds (already in the repo's cred list).
- **Creatives to score** ⇒ `creative/batch/` (no cred — works offline).

### 11.3 Module flags (founder-tunable, safe defaults)
`LAB_DRY_RUN=1` (default — decisions logged, **no** handoff emitted), `MIN_IMPRESSIONS=1000`,
`MIN_CONVERSIONS=15`, `LAB_WINNER_PCT=20`, `LAB_WEAK_PCT=20`, `LAB_WEIGHTS` (JSON of the §5.2 weights),
`LAB_POLL_MINUTES=60`, `LAB_WINDOW_DEFAULT=7d`.

---

## 12. HONEST REAL-vs-HYPE

| Claim | Reality |
|---|---|
| "Compares every creative across all channels" | **Real — this is the genuine net-new value.** It unifies paid + WhatsApp-reply + call-booking + organic-lead + revenue on the creative-DNA, which the per-paid-variant ads-engine structurally cannot. |
| "Statistically sound winners/losers" | **Sample-gated + explainable, NOT a 95% p-value.** No creative is flagged weak or promoted until it clears the min-sample gate; the composite score is a normalized weighted heuristic, honestly labeled — the Bayesian variant math lives in the ads-engine's bandit, not here. |
| "Auto-regenerates weak creatives" | **It REQUESTS regeneration** from `creative/batch/`; batch generates (and gates its own media spend). The lab generates nothing. |
| "Auto-scales winners into paid" | **It DRAFTS a paid experiment** (`propose_experiment` → `pending_approval`); the **ads-engine's human approval gate** is the only path to live spend. We never spend a rupee. |
| "Cross-channel attribution" | Only as real as the tracking tags. Untagged leads/replies are bucketed `unattributed`, never mis-assigned. We never guess which creative drove an untagged outcome. |
| "Self-hosted, no vendor lock-in" | **Real** — zero new vendor/SDK/key; pure read-join-rank-decide over the system's own data. |
| "Works offline" | The join, score, gate, banding, decision logic, idempotency, and audit are pure logic and fully offline-tested. Signal *richness* needs the siblings' real creds; the **safety + decision machinery does not.** |

---

## 13. BUILD ORDER (one verifiable UNIT each; test after every unit)

1. `config.py` + `store.py` + `models.py` (Pydantic) + `links/{ads,batch,spine}_link.py` resolvers
   (fake/dormant fallbacks) + package skeleton → **import-safe, dormant; test §10.1**.
2. `join.py` (cross-channel JOIN on the creative-DNA) → **the keystone test §10.2-10.3**.
3. `gate.py` (significance gate) → **unit-test §10.4 in isolation**.
4. `score.py` (composite score + normalization + banding) → **test §10.5, §10.9**.
5. `scoreboard.py` (assemble + rank + classify) wired to injected fake sources → **the core read test
   §10.2-10.5, §10.11**.
6. `decide.py` (`flag_weak` regenerate handoff + `promote_winner` DRAFT handoff, dry-run, idempotency)
   → **test §10.6-10.8, §10.10**.
7. `service.py` facade + `endpoints.py` (router DEFINED, FastAPI-guarded, NOT mounted) + `__init__.py`
   exports + full `test_testinglab_offline.py` green. **Gate.**
8. Document the deferred spine seams (router mount + scheduler tick + handoff drain) in `endpoints.py`
   docstring — **do not touch `caller.py`/`agent.py`**.

Ship 1–5 first: the entire cross-channel scoreboard + significance-gated classifier, fully tested, with
no external dependency and no dependency on whether the ads-engine/batch siblings are built yet.

---

## 14. SOURCES (2026-06-09)
- **Self-hostable OSS experimentation engines (product/feature-flag — NOT ad-creative analytics; the
  optional significance-test upgrade path):** GrowthBook (MIT, self-host, Bayesian+frequentist) —
  growthbook.io/insights/best-ab-testing-tools-developers, vwo.com/blog/open-source-ab-testing-tools ;
  PostHog (OSS, self-host A/B+multivariate) — posthog.com/blog/best-open-source-ab-testing-tools.
- **Ad-creative analytics landscape (ALL proprietary SaaS — confirms "no self-hostable OSS equivalent
  in 2026", verdict §1):** Motion (motionapp.com — visual creative-analytics hub) ; Segwise
  (segwise.ai/blog/best-ad-creative-analysis-tools-2026, top-10-ai-tools-ad-creative-analysis-2026 —
  multimodal element→metric tagging, validates the tag→metric concept) ; AdCreative.ai ; VidMob ;
  CreativeX ; Marpipe ; Madgicx (madgicx.com/blog/creative-testing-tools) ;
  admetrics.io/en/post/best-automated-creative-testing-platforms ;
  newform.com/guides/best-meta-ad-creative-testing-tools-2026. (Searched 2026-06-09; no self-hostable
  OSS ad-creative scoreboard returned.)
- **Creative-testing practice (tag→metric attribution, isolate-one-variable, min-impression
  thresholds, winner/loser banding):** segwise.ai/blog ; motionapp.com.
- **Multi-armed-bandit / Thompson sampling for ad allocation** lives in the **ads-engine**, not here —
  we consume its output (`design/creative-ads-engine.md` §1.3, §5).
- **Significance / min-sample discipline (impressions≥1000, conversions≥15):** mirrors
  `design/creative-ads-engine.md` §1.3 and `design/automation-ads.md` §5.4 (standard A/B min-sample
  practice; platform CPL docs: developers.facebook.com/docs/marketing-api, developers.google.com/google-ads).
- **Creative-tag taxonomy (the join key):** `design/creative-creative-batch.md` §2.4 (minted there,
  deferred to "downstream ads-analytics" — fulfilled here).
- **In-repo prior art (verified on disk 2026-06-09):** `droplet_work/whatsapp.py` (dormancy + WA
  send/inbound log), `audit.py` (`record`/`tail`/`init` L36/60/102), `config.py` (`get`/`require`/
  `source` L100/107/118), `vendors/__init__.py` (`redact`), `auth.py` (`issue_pair`); the loopback read
  seam from `design/creative-ads-engine.md` §2.1 `spine_link.py`; the Billing multi-page sidebar
  pattern this sub-page mirrors; sibling specs `design/creative-{ads-engine,creative-batch,landing-
  builder}.md` and `design/automation-{ads,aimanager,marketing}.md`.

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09. On-disk reuse seams re-verified (all real): `audit.record/tail/init`
(L60/102/36), `config.get/require/source` (L100/107/118), `whatsapp.py` dormancy (`{"status":
"not_configured"}`, `# noqa: BLE001`, lazy `httpx`), `auth.issue_pair` (L128), `vendors.redact` (L26),
`caller.py` bare imports. Verdict: **GO with the fixes below folded.** Nothing breaches dormancy or
spend-safety; the module owns **no** spend/launch/network primitive of its own, every sibling-contract
mismatch is caught by a `module_absent` fallback, and the offline test passes on injected fakes. The
fixes below are mandatory for **correctness of the keystone** (FIX 1) and for **not misleading the
build agent** on forward-integration seams (FIX 2–4).

### FIX 1 (BLOCKER-class correctness — the gate silently kills the keystone for non-paid winners)
**Problem.** §5 step 5 / line 304 define the gate as `eligible = impressions >= MIN_IMPRESSIONS AND
conversions(or leads) >= MIN_CONVERSIONS`. But §4.1 stores non-paid volume in **separate** fields:
WhatsApp in `channels.whatsapp.sends`, voice in `channels.voice.calls`, organic in
`channels.organic.impressions`. `sample.impressions` is **nowhere defined as unified cross-channel
exposures** — it is paid impressions only. Consequence: a creative that ran **only as a WhatsApp angle**
(or only as a voice script, or only organic) has `sample.impressions ≈ 0`, **can never clear the gate**,
and is therefore **never promotable and never flaggable-weak** — directly contradicting §7 ("a winning
WA angle can be promoted, a weak one regenerated") and the whole cross-channel keystone. The §10.4 test
only exercises the paid path (`impressions=200`→insufficient; `impressions>=1000`→eligible), so the
**offline test goes green while the keystone is broken.**

**Fix (fold into §1.2, §4.1, §5 step 5, §10.4):**
- `gate.py` is **channel-aware**. Define `sample.exposures = paid.impressions + whatsapp.sends +
  organic.impressions + voice.calls` (unified cross-channel exposure count) and `sample.actions =
  totals.conversions OR totals.leads OR (whatsapp.replies + voice.bookings)` (the channel-appropriate
  outcome). Eligibility = `sample.exposures >= MIN_EXPOSURES AND sample.actions >= MIN_ACTIONS`.
- Per-channel min-sample floors (a 1000-impression paid floor is wrong for WhatsApp/voice volumes):
  `MIN_EXPOSURES` defaults `{paid:1000, whatsapp:200, voice:100, organic:500}`; a creative clears the
  gate if **any single channel it ran in** clears that channel's floor **and** `sample.actions >=
  MIN_ACTIONS` (default 15, but `MIN_ACTIONS_WA`/`MIN_ACTIONS_VOICE` tunable lower since reply/booking
  volumes are smaller). The old global `MIN_IMPRESSIONS=1000`/`MIN_CONVERSIONS=15` remain the **paid**
  floor only.
- §4.1 `sample` block becomes `{"exposures":0,"actions":0,"per_channel":{...},"eligible":false,
  "eligible_channels":[...]}` so the decision is auditable per channel.
- **§10 adds test §10.4b (the missing keystone regression):** a creative that ran **only as a WhatsApp
  angle** with `sends>=200` and `replies>=15` and **zero paid impressions** MUST be `eligible` and
  MUST be promotable/flaggable; a voice-only creative with `calls>=100`/`bookings>=15` likewise. Without
  this assertion the offline test does not cover the keystone. Exit non-zero if a non-paid-only creative
  cannot clear the gate.

### FIX 2 (forward-seam — `batch_link.regenerate_request` is NOT a callable the batch spec exposes)
The batch spec (`creative-creative-batch.md` §3) exposes `generate_batch / get_batch / list_batches /
approve_batch / reconcile_batch / killswitch / generate_text / image_generate` — there is **no
`regenerate_request`**. §6.1's phrase "the batch's existing fan-out" is **aspirational, not a verified
contract.** Fold: `batch_link.regenerate_request(...)` is a **NEW seam this module DEFINES and the batch
must later honor** — implement it as a **handoff-row write to `handoffs.jsonl`** that `creative/batch/`
drains (the durable, decoupled path), NOT a direct function call into a symbol that does not exist.
Until batch implements a drainer, the handoff persists and `health()` reports `batch:module_absent`.
Record this as an explicit cross-module TODO the batch spec owner must accept.

### FIX 3 (forward-seam — the concrete import guess `creative.adsengine` is WRONG)
§2 guesses `try: from creative.adsengine import propose_experiment, experiment_status`. The ads-engine
spec puts its public surface at the **top of the `creative` package itself** (`droplet_work/creative/`,
`import creative`; callables live in `creative/service.py` re-exported from `creative/__init__.py`).
There is **no `creative.adsengine` module.** Since Testing Lab itself lives at `creative.testinglab`,
the correct resolver is `try: from creative import propose_experiment, experiment_status,
attribution_rollup` (or `from creative.service import ...`), still inside `try/except → None`. Fold the
correct path; keep the dormant fallback. (Coexistence note: the ads-engine owns flat `creative/*.py`
incl. `creative/__init__.py`; Testing Lab adds the **sub-package** `creative/testinglab/`. Whoever
builds second MUST NOT clobber the shared `creative/__init__.py` — append exports, never overwrite.)

### FIX 4 (forward-seam — `propose_experiment` signature shape mismatch)
The ads-engine signature is `propose_experiment(tenant_id, dropdown_selection: dict, ...)` where
`dropdown_selection = {"product_id"|"campaign_id", "platforms":[...], "test_budget_total_minor": int,
"objective": ...}`. §6.2 passes `dropdown_selection=<from the winning DNA + scope>` — but a DNA tag set
has **no `platforms` / `test_budget_total_minor` / `product_id`**. Fold: `promote_winner` MUST construct
a **valid `dropdown_selection`** by carrying `product_id`/`campaign_id` from `scope`, defaulting
`platforms` from the winning DNA's paid instances (the channels it already proved on), and **omitting
`test_budget_total_minor`** (the human sets budget at the ads-engine approval step — a DRAFT at
`pending_approval` does not require it). Document that the budget is **deliberately deferred to the
approval gate**, reinforcing "we never set spend."

### FIX 5 (residual, inherited — least-privilege on the loopback token)
`AIMANAGER_SERVICE_TOKEN` is a full admin/manager tenant token, reused here for **read-only** loopback
(`/leads /analytics /whatsapp/log /stats`). Testing Lab does not introduce it (it inherits the
ads-engine's `spine_link` token) and never writes via it, so this is **not a net-new risk** — but record
it as a **residual owned by the spine seam**: a future hardening should mint a **read-scoped** loopback
token for analytics consumers rather than reusing the manager token. No code change here; flagged for the
spine seam owner.

### Confirmed-OK (no change needed)
- **Spend/ToS safety: real.** No ad-platform API touched anywhere; ToS exposure is entirely inherited
  from the ads-engine/`automation-ads`. `LAB_DRY_RUN=1` default-ON is a correct second belt.
- **3D: no hype.** 3D appears once, in the reuse-boundary table, correctly attributed to batch/media
  studios; Testing Lab treats it as just another `asset_kind` breakdown attribute.
- **Autonomous-bidding hype: correctly disclaimed.** The Bayesian/bandit math is explicitly the
  ads-engine's; §12 labels the ranking "sample-gated + explainable, NOT a 95% p-value." Honest.
- **OSS active/maintained: moot.** Zero new vendor/SDK/key. GrowthBook (MIT)/PostHog are named only as
  an **optional future** significance-test upgrade, never a dependency — so their maintenance status
  cannot block or break this module.
- **Async pattern: sound.** `_async` twins mirror `whatsapp.py`'s `Client`/`AsyncClient` prior art;
  injected `ads`/`batch`/`spine`/`now` keep the offline test zero-network.
- **Identity-hash (channel-invariant DNA): correct as written** (§5.1) — do not re-open.
