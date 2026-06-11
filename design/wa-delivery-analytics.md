# WHATSAPP CAMPAIGN ▸ **DELIVERY · ANALYTICS · LEARNING** — Execution-Ready Design Spec

> **Module id:** `wa-delivery-analytics`  ·  **Role in the pipeline:** the **SEND-SIDE** of the AI WhatsApp
> Campaign Builder — *audience → schedule → deliver → track → analyze → learn → reuse winners*.
> **Date:** 2026-06-11  ·  READ-ONLY DESIGN wave (writes this doc only; **no app code, no `caller.py`/
> `agent.py`/`whatsapp.py` edits, no deploy, NO git**). Research verified inline + §15.

> **What this doc OWNS vs. what it CITES (the seam discipline — do not duplicate siblings):**
> - **Generation** (banner/template AI) → `creative-image-banner-studio.md`, `CREATIVE_STUDIO_MASTER_PROMPT.md` §8/§13.
> - **Per-recipient WhatsApp SEND PRIMITIVES** (media/interactive/template shapes, upload-once `media_id`,
>   suppression, per-message meter, status-webhook ingest) → **`creative-whatsapp-creative.md`** (the
>   `transport.py`/`meta.py`/`suppression.py`/`meter.py`/`status_hook.py` layer). **I REUSE its `send_kit`,
>   I do not re-implement the wire format.**
> - **The unified gen/approve/search contract + the cross-platform Asset Library** → `creative-studio-integrations.md`.
> - **The audience filter model** (stored ∪ uploaded-batches → temperature → manual → minus suppression) →
>   **`spec-run-campaign.md` §3** — I PORT it verbatim, swapping "dial" for "WhatsApp send".
>
> **My net-new surface:** a **campaign-scale send ORCHESTRATOR** (`wa_campaign`) that selects an audience,
> schedules + paces a blast across the live Meta Cloud API under the 24h-session/template rules + quality/
> rate/DND compliance, ingests delivery/read/reply/click signals, rolls them into a **per-template+creative+
> audience analytics** model, and runs the **learning loop** that surfaces, clones, and reuses winning combos.

---

## 0. THE ONE-PARAGRAPH MODEL (read first)

A vendor finishes the AI Campaign Builder (campaign → AI template → banner from Creative Studio → preview →
approve). This module takes that **approved `CampaignDraft`** and runs the send-side: it **resolves an
audience** (the run-campaign filter model — all / hot-warm / uploaded file / manual / segment — minus
DND/opt-out), lets the vendor **schedule** it (now / at a time / drip / per-recipient best-time / recurring),
then a durable **Sender** walks the audience and, **per recipient, decides the WhatsApp path** — free-form
inside an open 24h session, else an approved **template** (UTILITY-biased) — calling the sibling
`creative-whatsapp-creative.send_kit()` for the actual wire send. Every send is tagged
`campaign_id+template_id+creative_id(variant_id)+recipient` so when Meta's **status webhook** returns
`sent/delivered/read/failed` and the **inbound webhook** returns replies/STOP/clicks, each signal **attributes
to the exact (template × creative × audience) cell**. Those cells aggregate into the **Analytics** plane
(sent → delivered → read → replied → clicked → booked → converted, with rates + cost + ROI), and the
**Learning loop** ranks cells, **surfaces winners**, writes performance back to the Asset Library
(`creative.update_metrics`/`set_status(winner)`), and offers **clone / optimize / repurpose** so the next
campaign starts from what actually won. Everything is **dormant-until-creds, never-raises, RLS-tenant-scoped,
wallet-metered, audited** — the same discipline as every sibling.

```
 CampaignDraft(approved)            ┌──────────── DND / opt-out suppression (every recipient, EVERY send) ────────────┐
        │                           │                                                                                  │
        ▼                           ▼                                                                                  │
 ┌─────────────┐   ┌──────────────────────────┐   ┌───────────────────────┐   ┌───────────────────────────────────┐  │
 │  AUDIENCE   │──►│        SCHEDULER         │──►│        SENDER         │──►│   Meta Cloud API (live)           │  │
 │ all/temp/   │   │ now·at·drip·best-time·   │   │ per-recipient path     │   │ session→free-form | else TEMPLATE │  │
 │ upload/     │   │ recurring + pacing/caps  │   │ pick → send_kit()      │   │ (UTILITY-biased, approved)        │  │
 │ manual/seg  │   │ + quality-tier throttle  │   │ (sibling primitive)    │   └───────────┬───────────────────────┘  │
 └─────────────┘   └──────────────────────────┘   └───────────────────────┘               │ wamid                    │
        ▲                                                                                   ▼                          │
        │  segment reuse                                              ┌──────────────── WEBHOOKS ──────────────────┐   │
        │                                                            │ status: sent/delivered/read/failed          │   │
 ┌──────┴──────────────────────────┐                                 │ inbound: reply / STOP / button-click / CTA  │───┘
 │  LEARNING  (rank·surface·reuse) │◄──── per-cell rollup ◄──────────┤  → attribute to campaign×template×creative  │
 │  clone / optimize / repurpose   │      ANALYTICS plane            └─────────────────────────────────────────────┘
 │  winners → Asset Library winner │      sent→deliv→read→reply→click→book→convert · CTR · cost · ROI
 └─────────────────────────────────┘──────► next campaign starts from winning template+creative+audience
```

---

## 1. CHOSEN TOOLS + WHY (researched 2026-06, verified §15)

| Need | Choice | Why (evidence) | Cost / licence |
|---|---|---|---|
| **WhatsApp delivery wire** | **REUSE `creative-whatsapp-creative.send_kit()`** over Meta Cloud API | The sibling already owns media/interactive/**template** send shapes, upload-once `media_id`, suppression, per-message meter, status webhook. Re-implementing = duplicating a designed module | reuse |
| **Durable campaign send (resume after crash)** | **Hatchet (F3)** durable workflow — one `wa_campaign_run` workflow, a child step per recipient batch | A 5k-recipient blast paced over hours MUST survive a worker restart; F3 is already the platform's durable spine (`mod-orchestration-hatchet`). Dormant → in-process loop when no token (the workflow-studio pattern) | reuse (self-host) |
| **Audience resolution** | **REUSE the run-campaign filter model** (`spec-run-campaign.md` §3) | Founder already approved + specced: stored ∪ uploaded-batches → temperature (hot ≥70/warm 40-69/cold <40) → manual override → minus DND. Identical to voice run-campaign; only the action changes | reuse |
| **Credit/cost gate** | **REUSE `wallet.py`** (F4 reserve→settle/release, INR paise, idempotent) | Campaign cost is estimable up-front (Σ per-recipient category rate); reserve the estimate, settle actuals from the meter, refund unused. No new money path | reuse |
| **Per-message cost truth** | **REUSE the sibling `meter.py`** (`vendor="whatsapp_creative"` usage_events) | Already meters service=₹0 / marketing≈₹0.86 / utility≈₹0.11–0.145 / **authentication** by the category each send used; flows into the live billing UI | reuse |
| **Analytics store** | **`wa_campaign_*` Postgres tables (FORCE-RLS, admin-GUC)** — counters + a slim event log | Aggregation + ranking needs SQL, not JSONL scans; mirrors `ai_manager_*`/`ai_asset_*` schema discipline. Local-first counters; DO Spaces not needed (text/numbers) | self-host PG (free) |
| **Analytics + learning UI** | **PORT Core_2 `Income/*` + `Customers/OverviewPage` + `MessagesPage`** | Founder rule: never build UI from scratch — port the reference kit (tabbed analytics = `OverviewPage`/`Income`; KPI tiles; recharts; table+badges). No invented charts | reuse |
| **DND / consent ledger** | **REUSE `suppression.py` + a `wa_optin` flag** (sibling `context.enrich` surfaces `wa_marketing_optin`) | STOP/opt-out + India DLT/DND posture already in the sibling; I add the campaign-level consent gate + audience exclusion + per-recipient frequency cap | reuse + thin add |

**2026 Meta Cloud API facts that shape the SEND-SIDE (verified §15):**
- **Billing is per-MESSAGE by category** (since 2025-07-01): **service** (free, only inside an open
  customer-initiated 24h session), **utility** (≈₹0.11–0.145), **marketing** (≈₹0.86 India), **authentication**
  (OTP — never sent here). A cold campaign blast is almost always **template** = billed.
- **The 24h session is opened ONLY by an inbound customer WhatsApp message** (or a click-to-WA ad), never by us.
  So a campaign to a list of contacts who haven't messaged recently is a **template send** for each of them.
- **Approved templates are required + are Meta's gate.** We cannot conjure one; the founder creates + Meta
  approves (cred). `hello_world` is test-number-only (per `WHATSAPP_GOLIVE.md`). A campaign **cannot launch on a
  template that is not `APPROVED`** — the builder must read template status from Meta and block otherwise.
- **Quality rating + messaging limits are Meta-governed and per-WABA-number.** Tiers cap **business-initiated**
  unique recipients/24h: **1K → 10K → 100K → unlimited**, raised automatically as quality stays high. A spammy
  blast tanks the rating (GREEN→YELLOW→RED) and can **pause** the number. **The pacing layer MUST respect the
  current tier cap + throttle to protect quality** — this is the single most important send-side compliance rule.
- **Per-conversation pricing is gone; marketing-template *frequency capping* by Meta exists** (Meta itself
  limits how many marketing templates a user receives) — so our own per-recipient frequency cap both protects
  the user and avoids Meta-dropped sends.

---

## 2. AUDIENCE SELECTION — the SEND-SIDE audience (PORT run-campaign §3, WhatsApp-adapted)

The audience model is **identical to the voice run-campaign** (the founder already approved it) — only the
terminal action changes from "dial" to "WhatsApp send", and two WhatsApp-specific gates are added (consent +
session-state preview). **Reuse the exact filter pipeline; do not invent a parallel one.**

### 2.1 The five source modes (the founder's list) — composable layers, not exclusive screens
```
BASE POOL  = (stored leads from /leads)  ∪  (leads from selected uploaded batches: CSV + XLSX)
      ↓ TEMPERATURE   hot score≥70 · warm 40–69 · cold<40 · tag=… · custom Range band   (live counts per chip)
      ↓ SEGMENT       saved named segment (e.g. "Whitefield hot buyers") — a stored filter spec, reusable
      ↓ MANUAL        if vendor hand-picked rows → exactly those; else everything that passed
      ↓ minus  CONSENT+DND   opt-out/STOP list  ∪  no-WA-marketing-optin (for marketing templates)  ∪  frequency-capped
      ↓
   AUDIENCE PREVIEW:  "N contacts will be messaged"  +  breakdown chips  →  Schedule/Send
```
- **`all`** = the whole stored set. **`temperature` (hot/warm)** = the exact `app/leads` bands. **`upload`** =
  one or many uploaded batches (the `GET /leads/batches` list, CSV+XLSX, already specced). **`manual`** = the
  Customers-pattern row-select table. **`segment`** = a *named saved filter* (net-new for WhatsApp, §2.3).
- The preview count is computed **client-side over real lead rows** (truthful — the leads page's never-fabricate
  rule); the resolved **`recipient_ids`** are sent to the campaign, so *preview == who gets messaged*.

### 2.2 Two WhatsApp-specific audience gates (net-new vs. voice)
1. **CONSENT / session-state preview (the gate voice doesn't need).** WhatsApp marketing to a contact who never
   opted into WhatsApp marketing is a **Meta-policy + India-DLT/DND risk** (folded from `creative-whatsapp-
   creative.md` RED-TEAM B4). So the audience preview **classifies each recipient** before send:
   - **open 24h session** (recently messaged us) → **free-form, ₹0 SERVICE** path available.
   - **closed + `wa_marketing_optin=true`** → MARKETING/UTILITY template path (billed).
   - **closed + NO opt-in on record** → **excluded from MARKETING by default** (hold for approval, or send only
     a UTILITY-framed template if the content legitimately qualifies — "you asked us to send details"). The
     category is driven by **genuine intent, never chosen to dodge cost** (mis-categorization is a Meta violation).
   The preview shows: `"412 contacts · 38 open-session (free) · 290 opt-in template · 84 excluded (no opt-in/DND)"`.
2. **FREQUENCY CAP.** A per-recipient `WA_CAMPAIGN_MAX_PER_CONTACT_PER_WEEK` (default e.g. 2 marketing) excludes
   anyone already messaged this week — protects the user, the quality rating, and avoids Meta-dropped sends.

### 2.3 Segments (net-new, reusable) — a saved audience definition
A **segment** = a named, stored **filter spec** (`{source, temps[], tag, batch_ids[], custom_band, optin_required}`),
not a frozen list — so it stays live (re-resolves against current leads at send time). Segments are first-class
reusable assets (the founder's "reuse" theme): create from the current builder filter ("Save as segment"),
pick from a Select in the next campaign, see its live count, and the analytics plane reports **per-segment**
performance so a winning audience is reusable exactly like a winning template.

### 2.4 Reuse map (audience)
| Audience piece | Reuse from | Adapt |
|---|---|---|
| stored ∪ uploaded batches, temp bands, manual table, preview | `spec-run-campaign.md` §3/§4 + `components/Table`/`Tabs`/`Select`/`FieldFiles`/`Range` | swap dial→send; add consent column |
| DND / STOP / opt-out exclusion | `creative-whatsapp-creative.suppression.py` + caller `_WA_OPTOUT_WORDS` | run BEFORE preview AND again per-send (never trust a stale preview) |
| `wa_marketing_optin` flag | sibling `context.enrich` | drive the consent gate + category default |
| saved segment spec | net-new `wa_campaign_segments` row (RLS) | store filter JSON, re-resolve at send |

---

## 3. SCHEDULING — when + how fast the audience is reached

### 3.1 Schedule modes (vendor-chosen at launch)
| Mode | Behaviour | Backed by |
|---|---|---|
| **Send now** | enqueue immediately; pacing still applies | Sender starts at `now` |
| **Schedule at** | start at a vendor-picked datetime (tenant TZ, IST default) | Hatchet `aio_sleep_until` / scheduled trigger |
| **Drip / batched** | N per hour over a window (e.g. 200/hr, 10:00–18:00) — warms a new number + protects quality | pacing engine §3.2 |
| **Best-time-per-recipient** | each recipient sent at *their* likely-active hour (learned from past read-time, §7.4); falls back to a tenant default window | scheduler reads `recipient.best_hour` |
| **Recurring** | weekly/monthly re-run of a **segment** (live re-resolve) — e.g. "every Monday 10:00 to new hot leads" | `CronCreate`-class routine / Hatchet cron; idempotent per occurrence |
| **Throttled-by-quality (always on)** | a hard pacing ceiling derived from the **current Meta quality tier + messaging limit** for the WABA number | quality-tier throttle §3.3 |

### 3.2 Pacing engine (protects deliverability + quality rating)
- **Caps:** `WA_CAMPAIGN_PER_MIN`, `WA_CAMPAIGN_PER_HOUR`, `WA_CAMPAIGN_DAILY` (per tenant + per WABA number).
  The Sender emits at most these rates; over-cap recipients **queue to the next window** (never dropped).
- **Calling-window / quiet-hours:** respect a tenant business-hours window + **India DND quiet-hours** (no
  promotional WhatsApp 21:00–09:00 by default) — promotional sends outside the window **defer**, not send.
- **Warm-up ramp:** a brand-new or recently-RED number ramps gradually (e.g. day1 ≤ tier×0.2) to rebuild quality.

### 3.3 Quality-tier throttle (the non-negotiable compliance ceiling)
Before/while sending, read the WABA number's **current messaging limit tier + quality rating** (Meta Graph
`phone_numbers` fields: `messaging_limit_tier`, `quality_rating`). The Sender **hard-caps unique
business-initiated recipients/24h at the tier cap** (1K/10K/100K/∞) and, if quality drops to **YELLOW/RED**,
**auto-throttles** (halve the rate) and **alerts** the founder (`PushNotification`/Telegram per FORTRESS). This
is the single rule that keeps the number alive — it overrides any vendor-set pacing that would exceed the tier.

### 3.4 Reuse
Scheduling is a thin layer over **Hatchet durability** (sleep-until, cron, resumable child steps) + the sibling
**rate caps**. No new scheduler service: dormant (no Hatchet token) → an in-process paced loop (the
workflow-studio "same interpreter in-process" fallback). Recurring uses the platform's routine/cron skill.

---

## 4. DELIVERY — the campaign Sender (orchestration over the sibling primitive)

The Sender is a **durable per-recipient walk** that **never re-implements the wire** — it calls
`creative-whatsapp-creative.send_kit(kit, to=recipient, inside_window=<detected>)` (or `send_creative_package`
for the kit-from-campaign shape). Per recipient it:

1. **Re-check consent/suppression** (never trust the stale preview) — opted-out/STOP/frequency-capped ⇒ skip,
   record `skipped:{reason}`, continue. **Legal + trust, non-negotiable.**
2. **Detect session state** — open 24h session ⇒ free-form path (₹0 SERVICE); else ⇒ **template** path
   (UTILITY-biased per consent, §2.2). The category is set by genuine intent, audited.
3. **Resolve creative** — the campaign's chosen template + attached banner (`creative.get`/library `url`,
   upload-once `media_id`); A/B variant assignment (§4.2).
4. **Wallet reserve→send→settle** — reserve the per-recipient estimate (template path only; SERVICE is ₹0),
   call `send_kit`, on success `settle` the metered actual, on failure `release` (refund). Idempotent by
   `(campaign_id, recipient_id, occurrence)` — a resumed run never double-sends or double-charges.
5. **Tag the send** — every `wamid` carries `campaign_id+template_id+creative_id(variant_id)+segment_id+
   recipient_id` so all downstream signals attribute exactly (§5/§6). Write the `wa_campaign_sends` row.
6. **Handle Meta errors gracefully** — `131047` (re-engagement required on a closed session) ⇒ fall back to the
   template path; `131049`/quality-pause ⇒ throttle + alert; template-not-approved ⇒ block + surface. Never raise.

### 4.1 Durability + idempotency
The Sender is a **Hatchet workflow** (`wa_campaign_run`) with one **child step per recipient batch**; each
recipient send is idempotent (key above), so a worker crash resumes mid-blast with **no duplicate sends** and
**no double-charge** (the wallet `ON CONFLICT` idempotency + the workflow-studio persisted-progress lesson).
Dormant (no Hatchet token / no Meta creds) ⇒ in-process loop / `not_configured` skip — never crashes.

### 4.2 A/B / multi-variant at send (the experiment substrate the learning loop needs)
A campaign may carry **k template/creative variants** (the master's "5 angles"). The Sender assigns each
recipient a variant — **random split** for a fresh test, or **performance-weighted** (a deterministic bandit:
over-weight the variant with the higher posterior read/reply rate once enough data exists, like the ads-engine
bandit). The variant id is on every `send` row so analytics measures **per-variant**, and the learning loop can
**auto-shift traffic to the winner mid-campaign** (under the pacing/quality ceiling, with an approval gate for
fully-autonomous mode). Default = manual 50/50; bandit is opt-in.

### 4.3 Reuse
| Delivery piece | Reuse from | Adapt |
|---|---|---|
| media/interactive/template send shapes, upload-once `media_id` | `creative-whatsapp-creative.transport`/`meta` | call, don't rebuild |
| suppression-before-send, meter-after-send, audit | sibling `suppression`/`meter`/`audit_hook` | per-recipient loop wraps them |
| durable resume, sleep/cron | Hatchet (F3) | one campaign workflow |
| wallet reserve/settle/release | `wallet.py` (F4) | per-recipient idempotent hold |

---

## 5. TRACKING — turning Meta webhooks into attributed signals

**Two webhooks, both already live** (per `WHATSAPP_GOLIVE.md` the endpoint `/api/whatsapp/inbound` is verified
and connected; the sibling `ingest_status` parses status). This module **routes** their payloads into the
campaign analytics model — it does **not** add a new public endpoint.

### 5.1 Signal sources → events
| Source (existing) | Raw payload | Campaign event(s) | Attribution key |
|---|---|---|---|
| **Status webhook** | `statuses[]`: `sent` / `delivered` / `read` / `failed`(+error) | `sent`, `delivered`, `read`, `failed{code}` | `wamid` → `send` row → `campaign×template×creative×segment×recipient` |
| **Inbound webhook** | `messages[]`: text / button / interactive reply | `replied`, `button_click`, `stop`(opt-out), `inbound` | match `recipient` + recent campaign send (24h) → the originating cell |
| **CTA-URL click** | a click on the booking/landing button (link with a tagged `?wa_send_id=`) | `clicked`, then `landing_view` | the tagged `wa_send_id` in the URL → the exact send |
| **Booking / conversion** | CRM booking row / funnel conversion carrying `wa_send_id` (or matched by phone+window) | `booked`, `converted`(+value) | `wa_send_id` first; phone+time-window fallback |

### 5.2 The funnel state machine (per send row)
```
queued → sent → delivered → read → replied ──► clicked ──► landing_view ──► booked ──► converted(value)
   │        │        │                                                                     ▲
   └─skipped(consent/cap)   └─failed{code}                          (each transition is monotonic, timestamped, idempotent)
```
- Each `send` row carries the latest funnel `state` + a per-state timestamp; webhook re-deliveries are
  idempotent (a `read` after `read` is a no-op). `failed` codes are bucketed (re-engagement / quality / invalid
  number / template-paused) for diagnostics.

### 5.3 Reply intelligence (lightweight, reuses the LLM seam)
An inbound reply is classified (the existing Groq/OpenRouter seam, dormant-safe) into
`interested | question | objection | stop | other` → drives (a) the opt-out path (STOP ⇒ suppress + exclude
forever), (b) a lead-intent signal to CRM, (c) optional **auto-handoff to the AI Manager** (`mod-ai-manager`)
to continue the conversation. Classification is a *signal*, never an autonomous send without the AIM's own gates.

### 5.4 Reuse
Status parsing = sibling `ingest_status`; opt-out words = caller `_WA_OPTOUT_WORDS`; reply classification = the
marketing LLM seam; CTA-click tagging = a `?wa_send_id=` param on the booking URL (the sibling already builds
the CTA URL — we just append the tag). No new webhook, no new vendor.

---

## 6. ANALYTICS — the metrics model (per template × creative × audience)

### 6.1 The data model (`wa_campaign_*`, FORCE-RLS, admin-GUC)
| Table | Grain | Key columns |
|---|---|---|
| `wa_campaigns` | one campaign | `id, tenant_id, name, objective, template_id, creative_batch_id, segment_id, schedule, status, est_cost_minor, spent_minor, created_at` |
| `wa_campaign_segments` | one saved audience | `id, tenant_id, name, filter_json, last_count, created_at` |
| `wa_campaign_sends` | **one recipient send** (the fact table) | `id, campaign_id, recipient_id, template_id, creative_id(variant_id), segment_id, category, est_cost_minor, actual_cost_minor, state, wamid, sent_at…converted_at, fail_code` |
| `wa_campaign_cells` | **rollup** per `(template_id × creative_id × segment_id)` | the counters + rates below; the analytics + learning unit of measure |
| `wa_campaign_events` | slim append-only log | `send_id, type, ts, meta` (for re-aggregation + audit) |

> `cells` is the heart: every metric, ranking, and learning decision is **per (template × creative × audience)
> cell** — exactly the founder's ask ("which template+banner+audience combos win").

### 6.2 The metrics (per cell, per campaign, per template, per creative, per segment)
**Volume + funnel:** `sent · delivered · read · replied · clicked · landing_views · booked · converted` (+ `failed`,
`skipped`, `suppressed`). **Rates (all derived, never fabricated):**
- **delivery rate** = delivered / sent
- **read rate** = read / delivered
- **reply rate** = replied / delivered
- **CTR** = clicked / delivered  (and click-through-on-read = clicked / read)
- **conversion rate** = converted / delivered ;  **booking rate** = booked / delivered
- **cost:** `spend = Σ actual_cost_minor` ;  **CPM-sent**, **cost-per-read**, **cost-per-reply**,
  **cost-per-click**, **cost-per-booking (CPL)**, **cost-per-conversion**.
- **ROI / ROAS** = (Σ converted value − spend) / spend, when conversion value is known (CRM/funnel); else
  surfaced as "value unknown" — **never invented**.
- **quality signals:** `failed_rate`, `block/stop_rate` (opt-outs ÷ delivered — a creative that drives opt-outs
  is a *loser even if read-rate is high*), and the WABA `quality_rating` trend during the campaign.
- **velocity:** time-to-first-read, time-to-reply (feeds best-time learning §7.4).

### 6.3 Dashboards (PORT Core_2 — no invented UI)
| View | Ports from | Shows |
|---|---|---|
| **Campaign overview** | `Customers/OverviewPage` (tabbed) + KPI tiles | top-line funnel (sent→converted) + spend + ROI + quality badge; trend chart (recharts) |
| **Per-template / per-creative leaderboard** | `Income/StatementsPage` table + `lib/badges` | rows = cells, sorted by the chosen metric; winner/loser badges; A/B lift |
| **Funnel chart** | `Income/EarningPage` chart pattern | sent→delivered→read→replied→clicked→booked drop-off |
| **Per-segment performance** | `Income/*` grouped table | which audience converts best (drives segment reuse) |
| **Spend / cost** | `Income/EarningPage` + the existing billing meter | per-category WhatsApp spend beside Groq/ElevenLabs/Vobiz |
| **Live send monitor** | `MessagesPage`/`run` live-status table | in-flight queue, sent/min, quality tier, throttle state |

All metrics are computed from real rows; **zero fabrication** (a metric with no data shows "—", not a guess) —
the leads-page never-fabricate rule applied to analytics.

### 6.4 Honest attribution boundary
Click + conversion attribution is **best-effort**: strongest when the booking carries the `wa_send_id` tag
(deterministic); weaker when matched by phone + time-window (a booking could come from another channel). The
dashboard **labels attribution confidence** (`tagged` vs `inferred`) and never claims a conversion it can't tie.
Last-touch by default; multi-touch is out of scope (honest, not faked).

---

## 7. THE LEARNING LOOP — surface, reuse, clone, optimize, repurpose winners

This is what turns the platform from a sender into a **learning marketer**. The loop reads the `cells` rollup
and acts; **it biases choices, it never invents facts** (master §20 text-accuracy).

### 7.1 Rank + surface winners (the founder's "surface winning templates")
A deterministic **score per cell** combining the metrics that matter, normalized + confidence-weighted:
```
cell_score = w_reply·reply_rate + w_click·CTR + w_book·booking_rate + w_conv·conversion_rate
             − w_optout·stop_rate − w_cost·norm(cost_per_conversion)        (Bayesian-smoothed for small N)
```
- Cells with too little data get an **honest "needs more data" badge** (Bayesian smoothing toward the segment
  mean — a 2-send cell is never crowned). Winners (high score, enough N) get a **★ Winner** badge and bubble to
  the top of the leaderboard + the template gallery. Losers (high stop-rate / low read) get a **caution** badge.
- The win is reported **at every grain**: best template, best creative/banner, best **template×creative combo**,
  best segment, and the best **(template×creative×segment) cell** — directly answering "which combos win".

### 7.2 Reuse winning templates (one-click, the founder's "reuse")
Winning **templates/creatives/segments are reusable assets** (clone/optimize/repurpose — master §27/§30):
- **Clone** — start a new campaign pre-filled with the winning template + creative + segment ("Run the winner
  again to new hot leads").
- **Optimize** — `creative.regenerate(creative_id, mode="more_like_winner", n=5)` (the integrations §3.4
  flywheel) — "5 more banners like the winner"; or `creative.edit` the winning template's copy for a tweak. New
  versions, never overwrite (master §41).
- **Repurpose** — push the winning banner/template to **another plane**: `creative.send_to_adbot` (run it as a
  Meta ad), or attach to a funnel/landing step — the asset is already cross-platform (integrations §6).

### 7.3 Write performance back to the Asset Library (close the cross-platform loop)
For each creative, the loop calls the integrations contract: `creative.update_metrics(creative_id,
{delivered, read, replied, clicked, bookings, conversions, stop_rate, ...})` and
`creative.set_status(creative_id, "winner" | "trashed")`. So the **Creative Studio's stage-1 prompt-builder
later reads `library.performance_summary`** and over-weights the winning **angle/style/CTA/language** for this
tenant+industry, down-weights rejected ones (integrations §7) — the next campaign's banners start smarter.
**Biases style, never invents a price/claim.**

### 7.4 Best-time + best-audience learning (continuous)
- **Best-time:** per recipient, learn the hour of past **reads/replies** → feed the best-time scheduler (§3.1).
- **Best-audience:** per segment, the conversion rate ranks segments; a high-converting saved segment is
  surfaced for reuse, a dud segment is flagged. Segment-level learning = the audience analog of template-level.
- **Per-angle win-rate:** the variant **angle labels** (benefit/urgency/social-proof/price-drop/scarcity, master
  §8) carry measured win-rates → the next batch over-weights the angle that historically converts for this
  vertical (integrations §7.1). Cold-start ⇒ industry-pack defaults (honest fallback).

### 7.5 Autonomy ladder (honest — human-gated by default)
| Level | Behaviour | Gate |
|---|---|---|
| **L0 Suggest** (default) | surface winners + recommend clone/optimize; human clicks | none — read-only insight |
| **L1 Mid-campaign bandit** | auto-shift traffic to the winning variant within a running campaign | under pacing/quality ceiling; opt-in toggle |
| **L2 Auto-reuse** | auto-launch a clone of a proven winner to a fresh matching segment | **approval gate + wallet ceiling + step-up** (PIN) — same firewall as any autonomous spend |
Never fire-and-forget marketing spend without a gate; the model proposes, the firewall/approval authorizes.

---

## 8. SECURITY / COMPLIANCE / DORMANCY POSTURE (every send respects)

- **Tenant from TOKEN, never body** — audience resolution, every `send`/`cell`/`segment` row, every analytics
  read run inside the tenant RLS GUC; a campaign can only message + measure its own leads (BOLA-guarded by id).
- **FORCE-RLS `wa_campaign_*`** (admin-GUC), zero-`%` DDL — mirrors `ai_manager_*`/`ai_asset_*`.
- **Consent + DND first-class** — opt-out/STOP suppression before EVERY send (not just preview); India DLT/DND
  quiet-hours; **no MARKETING template without `wa_marketing_optin`** (UTILITY-bias or hold-for-approval);
  STOP ⇒ permanent exclusion + audit. The compliance gate is non-negotiable.
- **Quality-rating protection** — the tier throttle (§3.3) is a hard ceiling; auto-throttle + founder alert on
  YELLOW/RED; warm-up ramp on a fresh/recovered number.
- **One money-path** — campaign credits via `wallet.py` (idempotent reserve→settle/release); per-message cost via
  the sibling meter; **no second WhatsApp spend door**. Estimate shown before launch ("≈ 290 templates ≈ ₹249.
  Continue?").
- **Approval is the spend firewall** — autonomous reuse/bandit-launch (L1/L2) requires approval + a rupee
  ceiling + step-up; default biases safe (human-approved, master §41).
- **Immutable audit, channel=`whatsapp`/`wa_campaign`** — every launch/send/skip/throttle/winner-promotion rows to
  `audit.py` (PG `events` leg); secrets redacted; never raises.
- **Dormant-until-creds everywhere** — no Meta token ⇒ the whole pipeline runs against the sibling `fake`
  transport (offline-testable: audience→schedule→send-shape→tracking→analytics→learning, ₹0, no network); no
  approved template ⇒ launch blocked with a clear reason; no Hatchet ⇒ in-process paced loop. Never crashes a
  webhook, a call, or a workflow.

---

## 9. ENDPOINTS (designed now; wired later by the orchestrator — DO NOT edit `caller.py`)

| Method/Path | Body / Query | Returns | Notes |
|---|---|---|---|
| `POST /wa-campaigns/preview-audience` | filter spec (`source,temps,batch_ids,tag,band,segment_id,manual_ids`) | `{count, breakdown:{open_session,optin_template,excluded}, recipients[]}` | client-truthful preview; consent-classified |
| `POST /wa-campaigns/segments` | `{name, filter_json}` | `{segment_id, count}` | save a reusable audience |
| `GET /wa-campaigns/segments` | – | `[{segment_id,name,count}]` | reuse list |
| `POST /wa-campaigns` | `CampaignDraft{template_id, creative_batch_id, audience/segment_id, schedule, variants[]}` | `{campaign_id, est_cost_minor, status}` | reserves wallet estimate; blocks if template not APPROVED |
| `POST /wa-campaigns/{id}/launch` | `{confirm, step_up?}` | `{status:"scheduled"|"running"}` | enqueues the Hatchet `wa_campaign_run`; pacing/quality applied |
| `POST /wa-campaigns/{id}/pause` / `/resume` / `/cancel` | – | `{status}` | durable control; refunds unsent reserve on cancel |
| `GET /wa-campaigns/{id}` | – | campaign + live funnel + spend + quality tier | the overview dashboard source |
| `GET /wa-campaigns/{id}/cells` | `?sort=score&grain=template\|creative\|segment` | the leaderboard rows | per-cell analytics + winner badges |
| `GET /wa-campaigns/analytics` | `?range&template_id&segment_id` | aggregated metrics | cross-campaign trends + winners |
| `POST /wa-campaigns/{id}/reuse` | `{cell_id, mode:"clone\|optimize\|repurpose", target}` | new draft / regen job / handoff | the learning-loop action |

Status + inbound webhooks arrive on the **existing** `/api/whatsapp/inbound`; the orchestrator routes status →
sibling `ingest_status` → this module's cell rollup, and inbound → reply-classify + opt-out + attribution. All
write paths audit + RLS-scope. **No new public webhook; no spine edit.**

---

## 10. BUILD / WIRING SEQUENCE (deferred — orchestrator owns; small verifiable units, dormant-safe)

1. **Audience resolver + consent gate + preview** (reuse run-campaign filters; add session/optin classification).
   *Test: a mixed list → correct open-session/opt-in/excluded counts; STOP excluded; preview==recipients.*
2. **`wa_campaign_*` schema + RLS** (campaigns/segments/sends/cells/events). *Test: cross-tenant read fails;
   FORCE-RLS proven; zero-`%` DDL.*
3. **Scheduler + pacing + quality-tier throttle** (Hatchet sleep/cron + caps + tier cap). *Test: 1k list paced to
   the cap; quiet-hours defer; quality RED halves rate; recurring re-resolves a segment.*
4. **Durable Sender** (per-recipient `send_kit` call, idempotent, wallet reserve/settle/release, A/B assign).
   *Test (fake transport): no double-send/charge on resume; `131047`→template fallback; SERVICE=₹0; variant tagged.*
5. **Tracking rollup** (status→funnel state; inbound→reply/STOP/attribution; CTA `wa_send_id` tag). *Test:
   sent→delivered→read→replied transitions idempotent; STOP suppresses; click ties to the exact send.*
6. **Analytics + dashboards** (cells rollup + the Core_2-ported views). *Test: rates derived correctly; no
   fabrication (empty cell shows "—"); per-segment + per-creative leaderboards correct.*
7. **Learning loop** (cell scoring + Bayesian smoothing + winner badges + `update_metrics`/`set_status` writeback
   + clone/optimize/repurpose). *Test: a low-N cell isn't crowned; winner writes back to the library; "more like
   winner" regen works; L2 reuse requires approval.*

Each unit is dormant-until-creds, offline-testable against the sibling `fake` transport, edits no spine file.

---

## 11. PROACTIVE "OUT OF THE BOX" ADDITIONS (founder invited these — proposed + prioritized)

| # | Addition | Value | Fit (no bloat) | Priority |
|---|---|---|---|---|
| 1 | **Winning-combo recommender on the builder** — when a vendor opens the WhatsApp builder, surface "Your best combo last month: *Template B × Banner 3 × Hot-Whitefield* — reuse?" | turns history into a one-click head-start | reads `cells`; pure analytics, no new engine | **P0** |
| 2 | **Auto-A/B on every campaign** — silently split 2 creatives, declare a winner, recommend scaling | continuous improvement with zero vendor effort | the §4.2 bandit already exists; just default-on at 50/50 suggest | **P0** |
| 3 | **Quality-rating guardian** — live tier/quality widget + auto-throttle + alert before a number gets paused | protects the founder's single most valuable asset (the number) | reads Meta `phone_numbers`; ties to pacing | **P0** |
| 4 | **Best-send-time learner** — per-recipient send at their active hour | higher read/reply with no extra spend | §7.4; reads existing read-time data | **P1** |
| 5 | **Drip/sequence campaigns** — send → wait → if-no-reply remind → if-clicked book — as a Workflow Studio template | nurtures, not one-shot blasts | the integrations §5 Flow-B template already drafted | **P1** |
| 6 | **Conversion-value ROI** — pull booking value from CRM/funnel for true ROAS per template | money-truth, not just engagement | needs the `wa_send_id` tag end-to-end | **P1** |
| 7 | **Negative-signal learning** — a creative that drives **opt-outs** is down-ranked even if read-rate is high | avoids "engaging but annoying" creatives that burn the list | already in the cell score (`stop_rate` penalty) | **P1** |
| 8 | **Template marketplace (cross-tenant, anonymized)** — top-performing template *structures* (not data) as starters | network-effect head-start for new tenants | anonymized cell structure only; opt-in, RLS-safe | **P2** |
| 9 | **Predictive audience** — "leads most like your past converters" as a suggested segment | better targeting from real conversion history | a similarity score over lead features; honest bias not magic | **P2** |

---

## 12. REAL-vs-HYPE (honest, bounded)

| Claim | Reality |
|---|---|
| "Blast a WhatsApp campaign to thousands in one click" | You select an audience and schedule; **delivery is paced + quality-throttled + DND/consent-gated**, and **cold contacts need an approved template** (Meta's gate). It is a compliant campaign sender, not an uncapped blaster. |
| "Send to anyone" | No — **opt-out/STOP excluded always**, **no MARKETING without opt-in** (UTILITY-bias or hold), India DLT/DND quiet-hours respected. Bias safe. |
| "Free WhatsApp sends" | Only inside an **open 24h session** (₹0 SERVICE). A cold campaign is **template-billed** (utility ≈₹0.11–0.145 / marketing ≈₹0.86); the estimate is shown before launch and metered honestly (`estimated:true`). |
| "It learns the winning template/banner/audience" | Real, deterministic: per-cell scoring (Bayesian-smoothed) ranks combos, surfaces winners, biases the next round, writes back to the library. It **does not guarantee a winner**, low-N cells aren't crowned, cold-start falls back to defaults, and it **never invents a price/claim** to "improve" a creative. |
| "Auto-runs the winner for you" | Only at the opt-in **L2 autonomy** with **approval + rupee ceiling + step-up**. Default is suggest-and-click. The model proposes; the firewall authorizes. |
| "Every conversion attributed" | Best-effort: **deterministic when `wa_send_id`-tagged**, inferred (labeled lower-confidence) when matched by phone+window. Never claims an un-tieable conversion. |
| "Won't get my number banned" | The tier throttle + warm-up + quality auto-throttle + frequency cap materially **protect** the rating — but **Meta governs quality + limits**; a determined misuse (or bad content) can still hurt it. We protect, we don't override Meta. |
| "Works today, offline" | The whole send-side (audience→schedule→send-shape→tracking→analytics→learning) is **offline-testable** against the sibling `fake` transport with ₹0/no network; only real **delivery** needs the Meta token + **an approved template** (cred), and richer creatives need the provider key. |

---

## 13. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

**Fully designed + offline-testable with NONE of these (dormant-until-creds).** Inherits the WhatsApp creds
already proven live in `WHATSAPP_GOLIVE.md`.

| # | What | Env / action | Needed for | Status (per WHATSAPP_GOLIVE.md) |
|---|---|---|---|---|
| 1 | Meta WhatsApp Cloud API (BSP) | `META_WA_PHONE_NUMBER_ID/TOKEN/BUSINESS_ACCOUNT_ID/VERIFY_TOKEN/APP_SECRET` | all sends + webhooks | **LIVE** (real send proven; box `.env` token must be updated to the new `EAA…`) |
| 2 | **≥1 approved template** (media header + body + CTA), ideally **a UTILITY + a MARKETING** | WhatsApp Manager → Message Templates → submit | **every cold campaign send** (the common case) | **PENDING** — only `hello_world` (test-only). **#1 blocker to launch a real campaign.** |
| 3 | Webhook subscribed to **`messages`** + the right callback URL | Meta → Configuration → `https://panel.famit.in/api/whatsapp/inbound`, token `evsaivoiceagent`, subscribe `messages` | delivery/read/reply/click tracking | endpoint **VERIFIED**; founder must subscribe `messages` |
| 4 | Confirm the WABA/number | "MedFlow" / +91 97550 40013 | sending identity | confirm it's the intended Famit number |
| 5 | Provider key for richer banners (optional) | OpenRouter / image-model key | AI banners in templates | **LIVE** (OpenRouter image-gen proven) |
| 6 | Caps/consent config (recommended) | `WA_CAMPAIGN_PER_MIN/HOUR/DAILY`, `WA_CAMPAIGN_MAX_PER_CONTACT_PER_WEEK`, DLT/quiet-hours, `WA_CAMPAIGN_DAILY_COST_CAP_INR` | pacing / quality / spend stop-loss | set in `/opt/famit-agent/.env` |

> **Minimum to launch a REAL campaign:** #1 (live) + **#2 — at least one approved template** (the gate) + #3
> (subscribe `messages`). Everything else (audience, scheduling, analytics, learning) works **today, offline**.

---

## 14. SUMMARY (15 lines — for the orchestrator)

1. This is the **SEND-SIDE** of the AI WhatsApp Campaign Builder: *audience → schedule → deliver → track →
   analyze → learn → reuse winners*. It **orchestrates** at campaign scale and **reuses** the sibling
   `creative-whatsapp-creative.send_kit()` for the actual wire — it never re-implements the Meta send format.
2. **Audience** = the founder-approved run-campaign filter model **ported verbatim** (stored ∪ uploaded CSV/XLSX
   batches → temperature hot≥70/warm40-69/cold<40 → segment → manual override → minus DND/opt-out), plus two
   WhatsApp gates: **consent/session classification** (open-session free vs opt-in template vs excluded) and a
   **per-recipient frequency cap**. **Segments are saved, live, reusable** audiences.
3. **Scheduling:** now / at-time / drip / **best-time-per-recipient** / recurring (re-resolves a segment), all
   under a **pacing engine + a hard quality-tier throttle** (the #1 deliverability-compliance rule) + quiet-hours/
   DLT — Hatchet-durable, dormant→in-process.
4. **Delivery:** a **durable per-recipient Sender** (Hatchet workflow, idempotent by campaign×recipient) that
   re-checks consent, **detects session state** (free-form SERVICE ₹0 vs billed TEMPLATE, UTILITY-biased),
   wallet-reserves→sends→settles/refunds, tags every `wamid` with campaign×template×creative×segment×recipient,
   and handles Meta errors (`131047`→template fallback, quality-pause→throttle+alert) without raising.
5. **A/B at send:** k variants per campaign, random or **performance-weighted bandit**, the substrate the
   learning loop measures and (opt-in) shifts traffic to the winner.
6. **Tracking:** the two **already-live** webhooks (status + inbound, per `WHATSAPP_GOLIVE.md`) route into a
   per-send **funnel state machine** (queued→sent→delivered→read→replied→clicked→landing→booked→converted), with
   reply classification (interested/question/STOP) reusing the LLM seam; **no new public endpoint**.
7. **Analytics:** a `wa_campaign_*` FORCE-RLS schema whose heart is the **`cells` rollup per (template × creative
   × audience)** — directly answering "which template+banner+audience combos win".
8. **Metrics:** sent→delivered→read→replied→clicked→booked→converted + delivery/read/reply/CTR/conversion/booking
   rates + cost-per-(read/reply/click/booking/conversion) + ROI/ROAS + **stop-rate** (opt-out penalty) + quality
   trend — **all derived, never fabricated** (empty cell shows "—"); attribution labeled `tagged` vs `inferred`.
9. **Dashboards** are **Core_2 ports** (Income/* tabbed analytics, OverviewPage KPIs, recharts funnel,
   leaderboard table+badges, live send monitor) — no invented UI, per the founder's hard rule.
10. **Learning loop:** a Bayesian-smoothed **cell score** ranks combos, **surfaces winners** (★ badge, low-N not
    crowned), penalizes opt-out-driving creatives, and feeds the next round.
11. **Reuse winners** (the founder's theme): one-click **clone** (re-run the winner), **optimize**
    (`regenerate(more_like_winner)` / edit copy), **repurpose** (`send_to_adbot` / funnel/landing) — winning
    templates, creatives, AND segments are reusable assets.
12. **Closes the cross-platform loop:** `creative.update_metrics` + `set_status(winner|trashed)` write WhatsApp
    performance back to the **Asset Library**, so Creative Studio's prompt-builder over-weights winning
    angle/style/CTA next time — **biases style, never invents facts**.
13. **Autonomy ladder (honest):** L0 suggest (default) → L1 mid-campaign bandit (opt-in, under quality ceiling) →
    L2 auto-reuse a proven winner (**approval + rupee ceiling + step-up** required). Never fire-and-forget spend.
14. **Security/compliance:** tenant-from-token, FORCE-RLS `wa_campaign_*`, **opt-out/STOP + DLT/DND + no-marketing-
    without-opt-in** enforced before every send, **quality-tier throttle**, **one wallet money-path** (estimate
    shown), approval = the spend firewall, immutable `whatsapp` audit, **dormant-until-creds + never-raises**.
15. **Reuse discipline:** adds **no** WhatsApp client, image engine, or ad adapter — it CONTRACTS the send-side
    orchestration over already-designed siblings; net-new = the `wa_campaign_*` analytics/learning model + the
    audience consent gate + the campaign scheduler/Sender. **Wiring is deferred** (orchestrator-owned, §10);
    every unit is dormant-safe, offline-testable, edits no spine file. **Blocker to a real launch: ONE approved
    Meta template (#2).**

### THE PIPELINE (one line)
`CampaignDraft(approved) → resolve AUDIENCE (filters − DND/consent) → SCHEDULE (now/at/drip/best-time/recurring,
paced + quality-throttled) → durable SENDER (per-recipient session-or-template, wallet-metered, tagged, A/B) →
Meta Cloud API → WEBHOOKS (status + inbound) → per-cell TRACKING (funnel state machine) → ANALYTICS
(template×creative×audience metrics) → LEARNING (rank·surface·write-back) → REUSE winners (clone/optimize/
repurpose) → next campaign starts smarter.`

### THE METRICS (one line)
`sent · delivered · read · replied · clicked · landing_views · booked · converted` (+ failed/skipped/suppressed) →
`delivery-rate · read-rate · reply-rate · CTR · booking-rate · conversion-rate` → `cost · cost-per-{read,reply,
click,booking,conversion} · ROI/ROAS` → `stop/opt-out-rate · failed-rate · quality-trend · time-to-read/reply` —
all **per (template × creative × segment) cell**, derived (never fabricated), attribution labeled tagged|inferred.

---

## 15. SOURCES (2026 web research + in-repo verification)

- https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-message-templates (template send; APPROVED gate)
- https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages (message types; statuses sent/delivered/read)
- https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks (status + inbound webhook fields; `messages`)
- https://developers.facebook.com/docs/whatsapp/messaging-limits (tier 1K/10K/100K/∞; business-initiated unique-recipient cap)
- https://developers.facebook.com/docs/whatsapp/api/phone-numbers (`quality_rating`, `messaging_limit_tier` fields)
- https://developers.facebook.com/docs/whatsapp/cloud-api/guides/quality-rating-and-messaging-limits (GREEN/YELLOW/RED; pause)
- https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing (per-message categories: service/utility/marketing/auth)
- https://www.blueticks.co/blog/whatsapp-business-api-pricing-2026 ; https://uniquedigitaloutreach.in/2026/02/16/whatsapp-business-api-pricing-in-2026-a-complete-guide/ (India Jan-2026 marketing ≈₹0.86, utility ≈₹0.11–0.145, service free)
- https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-cta-url-messages/ (CTA-URL click tracking)
- (in-repo, verified) `design/creative-whatsapp-creative.md` (send primitives reused), `design/creative-studio-integrations.md`
  (`creative.*` + Asset Library writeback), `design/spec-run-campaign.md` §3 (audience filter model ported),
  `WHATSAPP_GOLIVE.md` (live send + webhook proven; template #2 pending), `memory/brain/*` (F3 Hatchet, F4 wallet,
  `mod-ai-manager` reply-handoff).
</content>
</invoke>
