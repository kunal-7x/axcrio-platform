# VERIFY-LIVE — WhatsApp + Google Ads (research, June 2026)

> Scope: Phase-0 grounding for GROWTH-OS. Confirms the `⚠ VERIFY-LIVE` claims in
> GROWTH-OS-BUILD-SPEC §5.4, §10, §11, §16.1, §23. Purpose = pin exact rate cards,
> API shapes, and 2026 migration deadlines that the `signals`, `whatsapp`,
> `connector-google`, `ingestion`, and `budget-governor` (messaging twin) services
> must encode. Every figure carries a source. Re-verify before each platform build.

---

## PART A — WhatsApp Cloud API (India)

### A1. Per-message pricing model (effective Jan 1 2026)
WhatsApp shifted from **per-conversation** to **per-TEMPLATE-MESSAGE** billing on
2024-07-01, fully in force in 2026. On-prem API is dead; Cloud API only. India moved
to **local-currency (INR) billing on 2026-01-01**, with a ~10% marketing increase.

**Meta RAW rate card — India (INR, per delivered template message, pre-GST, pre-BSP markup):**

| Category | Meta raw rate (INR) | Notes |
|---|---|---|
| **Marketing** | **₹0.8631** | up from ₹0.7846 (pre-Jan-2026), ~+10% |
| **Utility** | **₹0.115–0.145** | free inside the 24h customer-service window (see A3) |
| **Authentication** | **₹0.115–0.145** | volume-tier discounts apply |
| **Service / session (free-form in window)** | **₹0** | not a template; free |

⚠ **PRICING DISCREPANCY RESOLVED** — initial search surfaced "₹1.09 marketing /
₹0.145 utility" (AiSensy pricing page). That is **BSP retail (Meta raw + AiSensy
markup)**, NOT Meta's rate. Meta's published raw India marketing rate is **₹0.8631**
(some sources round to ₹0.86). The BSP markup is typically **$0.003–$0.010/msg** for
large BSPs. **GROWTH-OS billing/cost-meter must store the Meta RAW rate** (₹0.8631
marketing, ₹0.115–0.145 utility/auth) and treat BSP markup + 18% GST as separate
add-on line items. The spec's §16.1 estimate ("marketing ≈₹0.78–0.88, utility/auth
≈₹0.115–0.15") is CORRECT against Meta raw; do not adopt the ₹1.09 retail figure.

**Volume-tier discounts:** utility + authentication per-message cost auto-decreases as
monthly chargeable volume rises (no discount tiers on marketing). Cost-meter should
model declining marginal utility/auth cost per tenant per month.

### A2. CTWA free 72-hour window (the FREE entry-point benefit)
- A conversation opened via a **Click-to-WhatsApp (CTWA)** ad (or other free
  entry-point) grants a **Free Entry Point (FEP) window: 72 hours, ALL message
  categories FREE** — including marketing templates.
- **Activation rule:** business must **respond within 24h** of the user's first
  message (template OR session msg) → FEP window opens, valid **72h from the user's
  first message** (some BSP docs say from the business's response; Meta's canonical =
  from the user-initiated entry-point message). After 72h, normal rate card resumes.
- This is **distinct from** the standard 24h customer-service window (A3).
- Reported performance: CTWA delivers materially lower CPL and higher conversion vs
  LP-form destinations (vendor benchmarks cite up to ~92% lower CPL / 3–5× reply rate;
  treat as directional, not Meta-published).
- **GROWTH-OS implication (§11.2, §16.3):** the journey orchestrator MUST front-load
  qualification inside the 72h free window — every template send keyed to a CTWA
  `ctwa_clid` is free for 72h. The cost-meter must zero-rate sends where
  `journey.source=ctwa AND now < first_touch + 72h`.

### A3. 24-hour customer-service window
- Any user inbound message opens/refreshes a **24h service window**. Each new user
  message **resets** it.
- Inside the window: **free-form (session) messages are FREE**; **utility templates
  sent in response are FREE**; marketing/auth templates are still charged.
- Service messages are never charged.

### A4. Per-user MARKETING frequency cap (Meta-enforced, global)
- Meta caps how many **marketing template** messages a **single user** can receive
  **across ALL businesses combined** in a rolling 24h window — currently **~2 per
  user per day** (ramping; Meta tunes the number per region/engagement).
- It is **per-user, NOT per-business**: another brand's sends can exhaust a user's
  daily budget so your send fails even if you're under your own quota.
- **Blocked send → Cloud API error code `131049`** ("message not sent as part of an
  experiment" / per-user marketing limit).
- **Scope:** marketing templates ONLY. Utility, authentication, and service messages
  are **exempt**.
- **GROWTH-OS implication (§5.4, §13.2 messaging governor):** treat `131049` as a
  soft, expected outcome — NOT a failure. Prefer utility/auth/service + the CTWA-free
  window for high-frequency journeys; reserve marketing templates. Track per-person
  marketing-send count and self-throttle to ≤1–2/day before Meta blocks.

### A5. Quality rating + messaging-limit tiers
- **Quality rating** (per phone number, surfaced in Business Manager):
  **Green** (high / eligible for tier upgrade) · **Yellow** (medium / warning, tier
  frozen) · **Red** (low / at risk, limit can be cut). Driven by blocks, spam reports,
  low engagement.
- **Messaging-limit tiers (24h unique-user, business-initiated):** unverified = 250 →
  verified Tier 1 = 1,000 → 10,000 → 100,000 → Unlimited. Upgrades gated on
  **volume + quality**; **Yellow freezes** the tier, **Red can reduce** it.
- **2026 changes:** since **Oct 2025**, limits are **shared across all phone numbers
  in one Meta Business Portfolio** (not per-number). Meta re-checks tier eligibility
  **every 6h** (was 24–48h). Unlimited-tier + stable quality → up to **1,000 MPS**.
- **GROWTH-OS implication (§5.4, §13.2):** the messaging-governor twin must (a) read
  per-number quality rating, (b) auto-throttle template pacing when rating → Yellow,
  (c) hard-brake marketing on Red, (d) treat the messaging limit as a
  portfolio-shared budget across all of a tenant's numbers.

---

## PART B — Google Ads

### B1. Enhanced Conversions for Leads (EC for Leads) — the quality loop
- **What:** an upgrade of Offline Conversion Import (OCI). You capture the **GCLID**
  (and **WBRAID** for iOS in-app clicks; **GBRAID** for iOS web) at lead time + store
  it with the lead in your CRM, then upload conversions back keyed on GCLID + **hashed
  first-party PII** (`user_identifiers`).
- **Identifiers & precedence:** when **both `gclid` and `user_identifiers` are sent,
  `gclid` takes precedence** and the user identifiers are ignored for matching (still
  send both for resilience). EC-for-Leads also matches **hashed PII against (a) the
  same data your Google tag collected on your site/lead-form, and (b) signed-in Google
  accounts that engaged with your ad** — so it can attribute even without a GCLID.
- **Hashing:** `user_identifiers` must be **normalized + SHA-256 hashed**
  (email, phone E.164, and address fields fn/ln/ct/st/zp/country). **A PII field is
  required, but it need not be email.** Raw PII never leaves unhashed.
- **The quality loop (§11.1, §11.3 mirror):** upload an initial conversion on lead
  capture, then **adjust the conversion as the lead climbs the ladder** (qualified →
  booked → sale) via **offline conversion ADJUSTMENTS** (restate value, or
  retract). This is the gclid/wbraid + hashed-PII loop that teaches Smart Bidding to
  optimize for *qualified/closed* leads instead of raw form-fills — exactly the
  GROWTH-OS signal-quality moat.
- ⚠ **CRITICAL 2026 MIGRATION DEADLINE:**
  - **From April 2026**, Google Ads accepts user-provided data simultaneously from
    **website tags + Data Manager + API** — no longer an either/or.
  - **From June 15 2026**, OCI **and** EC-for-Leads uploads are **MIGRATED to the
    Data Manager API and BLOCKED in the Google Ads API.** → `connector-google` MUST
    target the **Data Manager API** for conversion uploads, not the legacy
    Google Ads API `ConversionUploadService`. (Spec §3.4 / §10.3 — update before
    Phase 3 build.)

### B2. PMax / Demand Gen asset-diversity behavior
- **Ad Strength** scores 4 dimensions: **format diversity** (landscape + square +
  portrait + video), **asset quantity per format** (Google recommends **≥3 unique
  assets per aspect ratio**), **asset quality** (resolution/clarity/relevance),
  **text completeness** (headlines, descriptions, business name, CTA).
- **"Excellent" target:** ≥3 landscape (1200×628), ≥3 square (1200×1200), ≥3 portrait
  (960×1200), 9:16 vertical for Shorts, ≥1 video, full text.
- **Performance:** PMax asset groups at **Excellent vs Good ad strength see ~18–25%
  more conversions**; advertisers hitting ≥3 of the 4 dimensions see ~40% more
  conversions (Google internal).
- **2026 auto-gen:** Google now **auto-generates missing images/video/copy** for PMax
  asset groups — **override with human-approved assets** where brand fidelity matters
  (defaults skew generic/stock-like).
- **GROWTH-OS implication (§9.2 CreativeIntel, §12.4 mitosis, §15.4 QA):** our
  diversity matrix (angle×format×visual×hook×headline) maps directly onto Ad Strength.
  The Creative Studio must emit **≥3 distinct assets per required aspect ratio** + a
  9:16 video, and the campaign-compiler must FILL EVERY SLOT to hit Excellent — and
  must **disable/override Google's auto-gen** to protect Creative DNA learning.

### B3. Lead-form (asset) webhook delivery
- On submit, Google sends an **HTTP POST (JSON)** to your configured **Webhook URL**;
  validated by a **Webhook Key** (`google_key`) you set in the lead-form asset editor.
- **Payload fields:** `lead_id`, `user_column_data[]` (`{column_id, string_value}`),
  `form_id`, `campaign_id`, **`gcl_id`** (the click ID — vital for joining the lead to
  the exact ad click), `google_key`, `api_version`.
- **Dedup:** Google does **NOT guarantee once-only delivery** → dedup on `lead_id`.
- **Forward-compat:** parser MUST **ignore unknown fields** gracefully.
- **GROWTH-OS implication (§8.2 ingestion):** add a Google lead-form webhook front
  door alongside Meta leadgen + WABA — verify `google_key`, persist raw, dedup on
  `lead_id`, mint/propagate `correlation_id`, capture `gcl_id` for the EC-for-Leads
  loop (B1).

### B4. RESOURCE_EXHAUSTED quota handling
- Rate-limit violations → **`RESOURCE_EXHAUSTED`** / `RESOURCE_TEMPORARILY_EXHAUSTED`
  (often surfaced as HTTP 429).
- **Metering:** **Token-Bucket** algorithm, bucketed by **QPS per (client customer ID
  AND developer token)** — enforced **independently on both**; exact QPS varies with
  server load.
- **Handling:** **exponential backoff** — e.g. 5s → 10s → 20s. Mitigate by
  **batching** operations into single mutate calls (e.g. one `MutateAdGroupAds` with N
  operations) + bounding total concurrent tasks across all processes.
- **Developer-token access tiers** also cap daily operations (Test → Basic → Standard)
  — request Standard access before production volume.
- **GROWTH-OS implication (§5.3 rate-limit governor):** mirror the Meta governor for
  Google — Redis token-bucket **per (CID, developer-token)**, priority queue
  (`user_initiated > optimization_action > scheduled_sync > backfill`), batch mutates,
  exp-backoff on `RESOURCE_EXHAUSTED`, and pre-provision Standard developer-token
  access.

---

## C. NET CHANGES TO FOLD INTO THE SPEC
1. **WA cost-meter** = Meta RAW rates (₹0.8631 mktg / ₹0.115–0.145 util-auth), BSP
   markup + 18% GST as separate lines. Do NOT use the ₹1.09 BSP-retail figure.
2. **Zero-rate** sends inside CTWA 72h FEP and utility/free-form inside 24h window.
3. **Per-user marketing cap ~2/day, global**; error `131049` = expected, not failure;
   prefer utility/CTWA-free for frequency.
4. **WA limits are PORTFOLIO-shared** (since Oct 2025), quality re-checked every 6h.
5. **Google conversion uploads MUST move to Data Manager API by June 15 2026** (legacy
   Google Ads API path blocked). Build `connector-google` against Data Manager API.
6. **EC-for-Leads:** GCLID precedence over `user_identifiers`; loop = upload-on-capture
   + **offline conversion ADJUSTMENTS** up the ladder; SHA-256 hashed PII required.
7. **Ad Strength = ≥3 assets/aspect-ratio + 9:16 video + full text**; disable Google
   auto-gen to protect Creative DNA.
8. **Google lead-form webhook:** dedup on `lead_id`, verify `google_key`, capture
   `gcl_id`, ignore unknown fields.

---

## SOURCES
WhatsApp pricing / windows / caps / quality:
- Meta raw India rate ₹0.8631 (Jan 2026, +10% from ₹0.7846): https://www.chatondesk.com/whatsapp-marketing-pricing-update-india-january-2026/ , https://authkey.io/blogs/whatsapp-pricing-update-2026/ , https://www.go4whatsup.com/guides/meta-whatsapp-pricing/
- BSP-retail ₹1.09 (markup-inclusive, NOT Meta raw): https://aisensy.com/pricing
- Pricing model + 24h window + utility-free + volume tiers: https://blueticks.co/blog/whatsapp-business-api-pricing-2026 , https://chati.ai/blog/whatsapp-business-api-pricing-update-for-2026
- CTWA 72h free entry-point window: https://learn.doubletick.io/click-to-whatsapp-ctwa/understanding-the-72-hour-free-messaging-window-for-ctwa-leads , https://www.go4whatsup.com/guides/click-to-whatsapp-ads/
- Per-user marketing cap ~2/day + error 131049: https://m.aisensy.com/blog/meta-frequency-capping-for-whatsapp-marketing-messages/ , https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates/per-user-limits/
- Quality rating + tiers + Oct-2025 portfolio sharing + 6h re-check: https://chatarmin.com/en/blog/whats-app-messaging-limits , https://www.uptail.ai/blog/how-many-messages-can-you-send-on-whatsapp-business-limits-explained-for-2026 , https://developers.facebook.com/docs/whatsapp/messaging-limits/

Google Ads:
- EC for Leads (overview, gclid precedence, hashed PII, matching): https://support.google.com/google-ads/answer/15713840?hl=en , https://support.google.com/google-ads/answer/11021502?hl=en
- Offline conversion uploads / adjustments + June 15 2026 Data Manager API migration: https://developers.google.com/google-ads/api/docs/conversions/upload-offline , https://support.google.com/google-ads/answer/14274408?hl=en , https://www.customerlabs.com/blog/google-ads-wbraid-gbraid-offline-conversion-tracking/
- PMax / Demand Gen asset diversity + Ad Strength + 2026 auto-gen: https://support.google.com/google-ads/answer/9142254 , https://almcorp.com/blog/google-ads-performance-max-2026-strategy-guide/ , https://support.google.com/google-ads/answer/13704860?hl=en
- Lead-form webhook payload (gcl_id, lead_id dedup, google_key): https://developers.google.com/google-ads/webhook/docs/implementation , https://developers.google.com/google-ads/webhook/docs/overview
- RESOURCE_EXHAUSTED quota / token-bucket / backoff / batching: https://developers.google.com/google-ads/api/docs/best-practices/quotas , https://developers.google.com/google-ads/api/samples/handle-rate-exceeded-error , https://developers.google.com/google-ads/api/docs/productionize/rate-limits

_Verified June 2026. ⚠ Re-verify rate cards + the June-15-2026 Data Manager API cutover before the WhatsApp/Google connector builds._
