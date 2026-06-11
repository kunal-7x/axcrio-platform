# VERIFY-LIVE — Meta / WhatsApp facts the spec depends on

> Research date: **2026-06-11** (June 2026). Purpose: confirm the live external-platform
> facts that GROWTH-OS contracts + the campaign-compiler + signals service are built against
> (P1 contracts-first). Every `⚠ VERIFY-LIVE` in `GROWTH-OS-BUILD-SPEC.md` that touches Meta
> is resolved here with sources + exact endpoint/payload shapes. Re-verify at build time of
> each connector — Meta versions roll ~quarterly.
>
> Legend: **CONFIRMED** = spec assumption holds. **CHANGED / SHARPENED** = the spec text was
> stale or imprecise; the corrected fact + what to change in contracts is given.

---

## 1. Meta Marketing API current version  (spec §10.1, §23 say "v25+")

**CONFIRMED + SHARPENED.** As of June 2026 the current/latest Marketing + Graph API version is
**v25.0** (released **18 Feb 2026** in this cadence). **v26.0 lands ~September 2026** (next quarterly).
So "v25+" in the spec is correct *today*; pin connectors to **`v25.0`** now, with a canary CI gate
for the v26.0 bump (§22). Do NOT hardcode "latest" in the path — pin the version string.

Notable v25.0 breaking changes that affect us:
- `smart_promotion_type` field **removed** from campaign creation (v25.0+).
- `metadata=1` query param **ignored** in Graph v25 (removed by May 2026).
- Async ad-report failures now return `error_user_msg` / `error_user_title` + `error_subcode` —
  surface these in the connector's degraded-mode logs.
- Post/Page Reach, Video Impressions, Story Impressions metrics **deprecated June 2026** → migrate
  insights to new **Media Views / Media Viewers** metrics. (Affects warehouse insight pulls, not Phase 0.)

Sources: developers.facebook.com Marketing API changelog (versions); Social Media Today (Meta MAPI v25 update); Swipe Insight (Graph/MAPI v25).

---

## 2. ASC / AAC deprecation → Sales / Leads / App objectives w/ Advantage+ default  (spec §10.1, §23)

**CONFIRMED, with EXACT timeline + the migration field names the compiler must NOT use.**

Timeline (this is the load-bearing part):
- **v24.0 (8 Oct 2025):** legacy **ASC** (Advantage+ Shopping) + **AAC** (Advantage+ App) creation/update
  APIs **blocked for new campaigns**.
- **v25.0 (Q1/Feb 2026):** breaking — **ASC/AAC campaign creation prohibited across ALL API versions**
  (90-day enforcement after v24 → ~**19 May 2026** the legacy path is dead even on old versions).
- **v26.0 (~Sep 2026):** remaining live ASC/AAC campaigns get **paused**.
- Reverting to **v23.0 or earlier** is the ONLY way to touch legacy APIs — do not design around that.

**What replaces them:** the unified **Advantage+** campaign structure under the standard objectives
**Sales, Leads, App** (Advantage+ is now a *setting/automation layer on the objective*, not a separate
campaign type). "Advantage+ Sales Campaign (ASC)" was renamed from "Advantage+ Shopping" and now spans
e-commerce sales, lead-gen, and app installs.

Three Advantage+ automation levers (the compiler models these as flags, default-ON):
**Advantage+ budget (CBO)**, **Advantage+ audience**, **Advantage+ placements**.

Migration fields (for documentation only — GROWTH-OS builds *net-new* campaigns, so it never migrates):
- `migrate_to_advantage_plus` field on the **/copies** endpoint (copy+migrate, new campaign id) or in-place POST.
- Ineligible: campaigns using `existing_customer_budget_percentage`, or ASC ad sets with **50+ ads** (post-v25).

**→ SPEC CHANGE / SHARPEN:** §10.1 says "ASC-era rules" for the Phase-1 compiler — **drop that phrasing.**
There is no ASC API to target anymore. Build the compiler to emit a **standard `OUTCOME_SALES` /
`OUTCOME_LEADS` / `OUTCOME_APP_PROMOTION` campaign** with the Advantage+ levers ON by default. The
existing-customer cap (10–25%) the spec mentions is the `existing_customer_budget_percentage` knob and
applies to **Sales** objective only.

Sources: developers.facebook.com blog "Upcoming ASC and AAC MAPI deprecation, Migration Options" (8 Oct 2025);
ppc.land (unified API structure for Advantage+); Swipe Insight (ASC/AAC deprecation in MAPI v25); bir.ch (Advantage+ Sales 2026 guide).

---

## 3. Advantage+ audience / placements defaults (Threads, Audience Network, "GA")  (spec §10.1, §23)

**CONFIRMED — with one correction.**

- **Advantage+ audience: ON by default**; manual audience stacks only for restricted/special-ad-category cases. ✔ matches spec.
- **Advantage+ placements: ON by default**, auto-distributing across **Facebook, Instagram, Messenger,
  Threads, and Meta Audience Network**. **Threads is a default placement** — global rollout **completed
  Jan 2026** (now includes carousel + Advantage+ catalog ads on Threads; catalog defaults to single-image/carousel on Threads).
  Advertisers can manually opt out of Threads. ✔ matches spec.

**→ SPEC CORRECTION:** the spec twice writes "**Threads/GA placements**" and "incl Threads/GA". **"GA" is
not a Meta placement.** Meta's auto-placement surface is FB / IG / Messenger / **Threads** / **Meta Audience
Network (MAN)**. There is no "Google/GA" inside Advantage+ placements (Google Display is a different
*platform*, handled by connector-google, not Meta). Treat "GA" in the spec as a typo for **Audience Network**.
Fix the contract enum to: `["facebook","instagram","messenger","threads","audience_network"]`.

Sources: blog.adnabu.com (Advantage+ Placements 2026); almcorp.com + jumpfly.com (Threads global Jan 2026); Meta dev docs (Threads catalog defaults).

---

## 4. ★ Conversions API for Business Messaging (CTWA) — endpoint + ctwa_clid payload  (spec §8.4, §11.2, FLAGSHIP)

**CONFIRMED — exact shapes captured. This is the crown-jewel signal path; build it to the letter.**

### 4a. Inbound WABA webhook → the `referral` object (where ctwa_clid is born)
On the **first inbound** WhatsApp message after a CTWA-ad click, the `messages` webhook carries a
**`referral`** object. Exact fields (ingestion must persist all, key on `ctwa_clid` + `source_id`):

```jsonc
"referral": {
  "source_url":   "https://fb.me/...",   // Meta URL of the ad/post
  "source_id":    "<AD_ID>",             // the Meta ad id  ← attribute to this ad
  "source_type":  "ad",                  // "ad" | "post"
  "headline":     "...",
  "body":         "...",
  "media_type":   "image",               // "image" | "video"
  "image_url":    "...",
  "video_url":    "...",
  "thumbnail_url":"...",
  "ctwa_clid":    "<CLICK_TO_WHATSAPP_CLICK_ID>"   // ★ Meta's GCLID-equivalent for WhatsApp
}
```
`ctwa_clid` appears **only on the first message** of the conversation — ingestion MUST persist it on the
journey/person immediately (§6.3 correlation_id) so later sale/qualify events can re-key to it.

### 4b. Outbound: send a business-messaging conversion event keyed on ctwa_clid
**Endpoint:**
```
POST https://graph.facebook.com/v25.0/{DATASET_ID}/events?access_token={TOKEN}
```
(`{DATASET_ID}` = the Events Manager dataset / pixel id, NOT the WABA phone-number id.)

**Payload (exact):**
```jsonc
{
  "data": [{
    "event_name":       "Purchase",            // or "Lead" | "QualifiedLead" (custom) | "Schedule" | ...
    "event_time":       1675999999,            // unix seconds, ≤ 7 days after the click
    "action_source":    "business_messaging",  // ★ REQUIRED exact value
    "messaging_channel":"whatsapp",            // ★ REQUIRED exact value
    "event_id":         "sha256(journey_id+ladder_step)",  // our dedup key (§11.3)
    "user_data": {
      "page_id":   "<PAGE_ID>",                // ★ REQUIRED, inside user_data
      "ctwa_clid": "<CTWA_CLID from referral>" // ★ REQUIRED, inside user_data
      // + optional hashed em/ph/fn/ln/ct/st/zp/external_id for higher EMQ
    },
    "custom_data": { "currency": "INR", "value": 78 }   // value=lead_score on Lead; order_value on Purchase
  }],
  "partner_agent": "growth-os"
}
```

**Hard CTWA limits (the spec did not state these — ADD to contract + governor):**
- **Exactly ONE CAPI event per ad-click event** for CTWA (you cannot stack multiple events against the
  same click). → the signals service must pick the **deepest single event** per click, or send the ladder
  on **distinct** triggers. This constrains the §11.1 event-ladder design for the CTWA path.
- **7-day window:** events sent **> 7 days after the click are dropped**. → latency budget is days, but
  also a hard expiry; the dispatch log must drop/flag stale CTWA events.
- Both `action_source:"business_messaging"` **and** `messaging_channel:"whatsapp"` are mandatory — miss
  either and the event fires but attributes to nothing (silent failure).

**→ SPEC CHANGE:** §11.1 ("event ladder per journey … Lead → QualifiedLead → Schedule → Attended → Purchase",
all via CAPI) is correct for **pixel/web + offline**, but for the **CTWA path specifically** the
"1 event per ad-click + 7-day window" rule means you cannot send the full 5-step ladder to *business_messaging*
against one ctwa_clid. Resolution: for CTWA journeys, send the **single most valuable event** reached
(Purchase > QualifiedLead > Lead) keyed on ctwa_clid within 7 days; mirror the full ladder to the **standard
web/offline dataset** where multi-event is allowed. Document this fork in `signals` and the
`signal_dispatch.schema.json`.

Sources: developers.facebook.com "Conversions API for Business Messaging"; Meta "messages webhook reference" (referral object); stape.io (exact endpoint + payload); woztell + seresa.io + digitalmicroenterprise (1-event/7-day limits, required fields); Twilio changelog (Click-ID callback param).

---

## 5. EMQ / dedup / learning-phase health thresholds  (spec §8.4, §11.3, §23)

**CONFIRMED — with an honesty caveat to bake into the Signal Health card.**

- **EMQ scale = 1–10** per event type (labels Poor/OK/Good/Great), measured via the **Dataset Quality API**
  (`/{dataset_id}` quality fields). Meta does **not** publish an official "8 = good" cutoff. Practitioner
  consensus: aim **≥6**, and **8+ shows diminishing returns** (8.5 vs 9.5 is marginal). The spec's
  **EMQ ≥ 8 on the optimization event** is a *defensible, slightly aggressive* internal target, not a Meta
  rule. **→ KEEP ≥8 as our internal green bar, but label it "our target, not Meta-official"** in the
  Signal Health card (P5 honesty); alert/remediate below 6 as spec says.
- **Dedup**: pixel↔CAPI deduplication keys on a shared **`event_id`** (+ event_name). Our invariant
  `event_id = sha256(journey_id + ladder_step)` (§11.3) is the right mechanism. Dedup-rate ≥90% target is
  ours, reasonable. There is a **`Dataset Quality API`** to read dedup/match metrics programmatically —
  wire it into the EMQ report job rather than scraping Events Manager.
- **Learning phase**: **~50 optimization events per ad set per rolling 7-day window** to exit; falling below
  50 in any 7-day window re-enters learning. **"Learning Limited"** = config can't produce 50/wk → structural
  fix needed (consolidate ad sets, shallower event, raise budget). ✔ matches spec §23 "Learning-Limited<30%"
  and the §10.1 "budget floor ≥5× target CPA" (which exists precisely to make 50/wk feasible). Confirmed
  still true in 2026.

Sources: developers.facebook.com "Dataset Quality API"; upstackdata + triplewhale + niblin + customerlabs (EMQ 1–10, ≥6/≥8); adlibrary.com + modernmarketinginstitute + cometly (50 events/7-day rolling, Learning Limited).

---

## 6. Entity-ID creative-similarity suppression (~60%)  (spec §1.2(2), §15.4, §23)

**CONFIRMED.** Meta's **Andromeda** retrieval stage clusters creatives by visual+thematic similarity under
a shared **Entity ID**. **Creative Similarity Score > 60% triggers retrieval suppression** — near-duplicate
ads collapse into ONE entity and compete as a single concept (launch 100 look-alikes → ~10 get meaningful
delivery; duplicates can get near-zero spend regardless of bid). Variation must be **meaningful at the
visual/audio/structural level** — different copy on the same hero image / same template does NOT escape
clustering. This directly validates the spec's moat #2 + the creative-QA Entity-ID rubric (§15.4: block
launch sets scoring <8/10 on the 5-axis concept/format/visual/hook/headline diversity rubric; flag same
first-4-token headline / same hero / same 0–3s hook). **No change** — build the QA gate exactly as specced.

Sources: recharm.com (60% threshold + Andromeda entity clustering); ppcblogpro.com (similarity penalties); chatterbuzzmedia + admove + segwise (Andromeda 2026 strategy).

---

## 7. App-level + BUC rate-limit headers (X-Business-Use-Case-Usage)  (spec §5.3, §23)

**CONFIRMED — exact header + error codes captured for the rate-limit governor.**

`X-Business-Use-Case-Usage` is a **JSON-encoded** response header on BUC-rate-limited calls, keyed by
**business-object-id (ad-account id)** → array of objects (up to **32 per response**). Exact fields per object:

```jsonc
{
  "<AD_ACCOUNT_ID>": [{
    "type":                            "ads_management",   // BUC type
    "call_count":                      0,    // % of the call-count quota used (0–100)
    "total_cputime":                   0,    // % of cpu-time quota (throttles when it hits 100)
    "total_time":                      0,    // % of total-time quota
    "estimated_time_to_regain_access": 0,    // minutes blocked when throttled
    "ads_api_access_tier":             "standard_access"   // "development_access" | "standard_access"
  }]
}
```
Throttle fires when **any of call_count / total_cputime / total_time reaches 100(%)**. The governor (§5.3)
should back off **before** 100 (e.g. ≥90%) and respect `estimated_time_to_regain_access` for the cooldown.

**Rate-limit error codes** (the governor's backoff triggers):
- **App/platform level:** code **4** (app limit), **17** (user limit), **32** (pages-API user/app limit),
  **613** (custom rate limit).
- **BUC level:** code **80004** = Ads Management throttling (also 80000/80001/80002… for Insights/Pages/IG/Custom-Audiences).
- Also keep the spec's **error_subcode 2446079 / transient code 2** handling for Insights.

Companion headers: **`X-Ad-Account-Usage`** (per-ad-account % util + `reset_time_duration`) and
**`X-App-Usage`** (app-level % util). Standard-access tier gets materially higher quotas than
development-access — business verification + Marketing API standard access is a **founder blocker** to lift
before scale (already noted in spec §206 founder-blockers).

**→ SPEC CONFIRM:** §5.3's "Backoff on Meta 17/4/613 + X-Business-Use-Case-Usage headers" is correct; ADD
**80004** (the actual BUC/ads-management code) and the **call_count/total_cputime/total_time/estimated_time_to_regain_access**
field set to the governor contract.

Sources: developers.facebook.com Graph API + Marketing API rate-limiting docs; adamigo.ai + stitchflow + get-ryze (BUC headers, tiers, error codes).

---

## 8. (Bonus, confirmed in passing) WhatsApp per-message India pricing  (spec §16.1, §23)

**CONFIRMED + freshened to Jan-2026 numbers.** Per-message billing since **1 Jul 2025** (conversation-based
pricing dead; on-prem dead). India rates effective **1 Jan 2026**: **Marketing ≈ ₹0.8631/msg** (up ~10% from
₹0.7846), **Utility ≈ ₹0.115/msg**, **Authentication ≈ ₹0.115/msg** — **Meta base rates only**; **+BSP markup
($0.003–$0.010)** and **+18% GST** on top. **CTWA → all messages (incl templates) FREE for 72h**; standard
24h customer-service window free for non-template. ✔ matches spec §16.1 (₹0.86 marketing / ₹0.115 utility).
**→ Update the cost-meter default** to the **Jan-2026 ₹0.8631** marketing rate (spec said ₹0.78–0.88 range).

Sources: developers.facebook.com WhatsApp pricing; ycloud (Jul-2025 change); messagebot.in + aisensy + uniquedigitaloutreach (India Jan-2026 INR rates + BSP + GST).

---

## SUMMARY OF SPEC CHANGES (what contracts/compiler must reflect)
1. **Pin `v25.0`** (current); canary-gate the **v26.0 (~Sep 2026)** bump. ("v25+" is fine today.)
2. **Drop "ASC-era rules"** in the Phase-1 compiler — legacy ASC/AAC APIs are dead (creation blocked
   v25, ~19 May 2026 across all versions; paused v26). Emit **standard Sales/Leads/App objectives with
   Advantage+ levers ON by default**.
3. **"GA" is NOT a Meta placement** — it's a typo for **Audience Network**. Auto-placement enum =
   FB/IG/Messenger/**Threads**/**audience_network**. Threads default-ON since Jan 2026.
4. **CTWA CAPI:** `POST /v25.0/{DATASET_ID}/events`, `action_source:"business_messaging"` +
   `messaging_channel:"whatsapp"`, `page_id`+`ctwa_clid` **inside user_data**. **Hard limit: 1 event per
   click + 7-day window** → CTWA path sends the single deepest event (not the full ladder); mirror the
   full ladder to the web/offline dataset.
5. **EMQ ≥8 is OUR target, not Meta-official** (Meta = 1–10 scale, no published cutoff; ≥6 practical,
   8+ diminishing). Label honestly in the Signal Health card. Read EMQ/dedup via the **Dataset Quality API**.
6. **Learning phase 50 events / rolling-7-day** confirmed → keeps the ≥5× CPA budget floor honest.
7. **Entity-ID 60% similarity suppression** confirmed → build the §15.4 QA diversity gate as specced.
8. **Rate-limit governor:** add BUC error code **80004** + fields **call_count/total_cputime/total_time/
   estimated_time_to_regain_access/ads_api_access_tier** + companion **X-Ad-Account-Usage / X-App-Usage**;
   back off at ≥90%, honor estimated_time_to_regain_access.
9. **WhatsApp cost-meter default** → Jan-2026 **₹0.8631 marketing / ₹0.115 utility/auth**, +BSP +18% GST,
   CTWA 72h free.
