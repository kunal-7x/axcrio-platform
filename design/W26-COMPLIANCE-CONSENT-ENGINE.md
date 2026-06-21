# W26 — The Consent & Regulatory Engine (DESIGN)

> **Status:** DESIGN / doc-only. No code, no box mutation, `agent.py` untouched. 2026-06-18.
> **Owner wave:** W26 (India Regulatory & Consent Engine). **Consumes:** the two W26 law docs
> (`design/W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md` — the legally-precise spine — and
> `design/INDIA-TELECOM-AI-DISCLOSURE-LAW.md` — the conservative checklist). **Produces:** the
> spec the build waves implement. **Feeds:** W2 (the disclosure-line + block-list the brain must
> enforce), W12 (dial-path gates), W7/W9/W14 (DPDP retention/erasure/consent ledger).
> **Scope caveat:** engineering due-diligence, not legal advice. Counsel sign-off gates high-volume.

---

## 0. The one-paragraph verdict (read this first)

India 2026 law is the **immediate, existential threat to the live earner** — a complaint cluster or
scrub-audit can get the founder's *outgoing telecom service disconnected by operator action*,
regardless of code quality. The good news: **none of it requires the founder to break his rule.** No
in-force Indian law forces the words "I am an AI assistant." We satisfy the hard law on the
**calling/data layer** (DLT, number-series, DND-scrub, calling-hours, consent ledger, recording
notice, retention/erasure) and we turn the disclosure requirement into a **product feature**: a warm,
branded, one-line opener that is legally truthful and never robotic. The engine is a **server-side
dial-time gate** that rides existing primitives (`_in_window`, the suppression store, wallet/firewall
ACID, the immutable audit + FORCE-RLS DDL pattern) rather than reinventing them. **One hard gap to fix
immediately:** the live calling window default is **09:00–21:00 IST, which is illegal** (legal window
is 10:00–19:00) — §3.4 / §8 make this the first dial-path change.

---

## 1. Ground truth — what already exists in the live earner (don't rebuild)

Verified in `droplet_work/` (the live voice box source). The engine is **additive over these**, not a
greenfield system:

| Primitive | Where (live) | What it gives the engine |
|---|---|---|
| **Calling-window gate** | `caller.py:862 _in_window(fields)`, called in `run_job` (`caller.py:2852`); defaults `call_window_start=09:00 / call_window_end=21:00 / tz=Asia/Kolkata` (`caller.py:4250`) | A per-campaign window check **already wired into the dial loop**. The engine TIGHTENS its default + adds a legal **hard floor** (10:00–19:00) that a tenant cannot widen. |
| **Suppression / DND (tenant-local)** | `_suppressed_set(tenant_id)` (`caller.py:1526`); `suppression.json`; `suppression.add` AIM tool | A per-tenant opt-out list, checked in `run_job`. This is **opt-out, NOT the national NCPR/DND register** — the engine ADDS the NCPR scrub-before-dial on top, keeping this as the local opt-out layer. |
| **Per-tenant caps** | `run_job`: `max_concurrency`, `daily_call_cap` (default 500) | Pattern for a new **complaint-rate / abandonment guard** (§5). |
| **Wallet — ACID hold/charge** | `wallet.py`, `db/ddl_wallet.sql` (INTEGER paise, FORCE-RLS admin-GUC, idempotency, no-double-spend proven) | The **exact table+RLS template** the consent ledger reuses. The pre-dial hold point is the natural place to bolt the compliance gate. |
| **Firewall — PIN step-up** | `firewall.py` (salted-hash PIN, HS256 step-up token sub-bound) | Gates **destructive/override actions** — e.g. a founder override to dial a number that failed a soft gate is a step-up action, audited. |
| **Immutable audit** | `audit.py` (append-only JSONL + best-effort PG `events` mirror, `store.mirror_event`) | The **consent/disclosure/DND audit trail** writes here — append-only is exactly the UCC ~6-month evidence requirement. |
| **FORCE-RLS DDL pattern** | `db/rls.sql`, `db/ddl_wallet.sql` admin-GUC policy: `USING (current_setting('app.is_admin',true)='1' OR tenant_id = current_setting('app.tenant_id',true))` | Every new compliance table uses this **identical** shape — multi-tenant isolation comes for free, consistent with the platform. |
| **Configurable disclosure (already present!)** | `agent.py:218 _llm_opener(disclose, disclosure_phrase)`; `prompt.py:358 disclose_ai / ai_disclosure`; default phrase `"{company} की एक AI assistant"` | The brain **already** has a config-driven disclosure knob — but its **default phrase literally contains the banned "AI assistant"**, and it is a **soft prompt instruction, not control-flow**. W2's job (§7) is to swap the default to a compliant Tier-0 line and make the disclosure **structurally guaranteed**. |

**Implication:** ~60% of the dial-path scaffolding the engine needs already exists. The engine is
mostly (a) new tables (consent ledger, DLT registry, NCPR cache, compliance audit), (b) a single
**`compliance.preflight(tenant, lead, campaign)` gate** inserted at one point in `run_job` before the
SIP originate, and (c) the W2 brain changes to the opener.

---

## 2. Obligations ranked: NOW-mandatory (gate the earner) vs build-now vs track-only

Ranked by *how fast it can take the live earner offline*. Hard-law tags carry the source regime.

### TIER A — NOW-MANDATORY, gates every commercial dial (TRAI/TCCCPR, IN FORCE)
These are the conditions of being *allowed to dial at scale*. Missing any one is what gets a sender
penalised/suspended. **The engine must hard-block the dial if these fail.**

1. **DLT Principal-Entity registration + registered header + registered content-template envelope.**
   Block dial if the tenant (or Famit-as-sender-of-record) is not `dlt_status=active` with a
   registered header and at least one approved template. *(In force.)*
2. **Number series — NOT a 10-digit mobile.** Outbound CLI must be a registered **140-series**
   (promotional) or **1600/160-series** (transactional/service). **Dialing commercial AI calls from a
   plain 10-digit mobile is itself a violation** — audit the live earner's current trunk identity
   against this (§8 action item).
3. **NCPR/DND scrub-before-dial (national register, real-time).** Every number scrubbed against the
   National Customer Preference Register **before queueing**, not stale batch; register refreshed
   ≤30 days. Promotional calls to DND numbers prohibited (explicit, time-boxed consent can override).
4. **Calling-hours hard floor.** Commercial calls only **10:00–19:00 recipient-local**; BFSI/RBI
   collections **08:00–19:00**. Enforced **server-side at dial time**, per tenant/vertical. *(The live
   default of 09:00–21:00 is OUT OF BOUNDS — §3.4.)*
5. **Auto-dialer / robocall pre-notification.** The auto/predictive dialer must be **formally notified
   to the originating access provider in advance**. A registration-state flag the engine checks, not a
   per-call action.
6. **Auto-dialer use-and-purpose disclosure up front** (the *in-force* disclosure duty — about the
   *mechanism/purpose*, NOT the literal "I am an AI"). Delivered by the Tier-0 opener (§6), enforced as
   **control-flow in the brain** (§7).
7. **Two consents, fresh at dial time.** (a) TCCCPR consent to *place* the commercial call; (b) DPDP
   consent to *process* personal data. Consent windows are **short**: inferred consent = contract
   duration; explicit-transaction consent = **7 days**. **Check freshness AT DIAL TIME, not at import.**

### TIER B — BUILD-NOW, enforcement ramps to ~May-2027 (DPDP, IN FORCE staged)
Penalty plane is large-rupee (up to ₹250 cr) but ramps; the **infrastructure must exist before
high-volume**, so it is design-now:

8. **Recording consent + notice.** Disclose "may be recorded"; the Tier-0 opener carries the cue.
9. **Retention TTL + auto-purge.** Recordings/transcripts/derived data retained only as long as the
   stated purpose; auto-purge past TTL.
10. **Cascading right-to-erasure.** One erasure request must cascade across **recording + transcript +
    vector index + lead memory + WhatsApp logs** (§4.4).
11. **At-rest encryption + data residency** for recordings/transcripts/PII.
12. **Consent & disclosure audit kept ≥6 months** (UCC audit) — the append-only audit log.

### TIER C — TRACK-ONLY, do NOT gate on (advisory / draft / proposed)
13. **MeitY AI Governance Guidelines (Nov-2025)** — advisory; AI-vs-human transparency. Used as
    interpretive lens; the Tier-0 opener already satisfies its spirit. **No standalone fine.**
14. **MeitY SGI / deepfake rules (IT Amend Rules 2026, in force 20 Feb 2026)** — bind
    **intermediaries/platforms hosting synthetic *content***, **not** cleanly a live 1:1 phone call;
    the "10%-audio marker" was the dropped draft figure. Do **not** gate dialing on it. Even if a
    regulator stretched it, the cure is a *synthetic-voice prefix*, never the banned phrase.
15. **TRAI AI-specific self-identification mandate** — **PROPOSED / under consultation, NOT law.** The
    widely-repeated "AI must say it's AI within 15 seconds" is **vendor-blog only, unverified as
    regulation.** Build the **Tier-2 flip** (§6) so the day it lands it's a config change, not a code
    change — but ship Tier-0 as default today.

**Design rule:** the engine **fail-blocks** on Tier A, **fail-soft/log** on Tier B during ramp (block
on the few hard DPDP items like erasure-honoured), and **never gates on Tier C** (only prepares the
flip). HIDDEN/unknown registration state ⇒ **DENY fail-closed** (same posture as the control layer).

---

## 3. THE CONSENT & REGULATORY ENGINE — architecture

### 3.1 Shape: a server-side dial-time gate, not a microservice
The engine is a **module on the voice box** (`compliance.py`), called from **one point** in the dial
loop, backed by **4 new PG tables** (FORCE-RLS, admin-GUC, same as wallet). It is NOT a separate
service — latency and earner-safety demand the gate be in-process and fail-closed on Tier A. It reuses
`db.engine` (one txn per check), never opens a new pool — identical to how `wallet.py` rides P1.

```
run_job (caller.py:2852)  ── per lead, BEFORE create_sip_participant (caller.py:2951) ──►
    compliance.preflight(tenant, lead, campaign) -> Decision{allow|block|soft, reasons[], disclosure_ctx}
        ├─ A1 registration_gate(tenant)      DLT PE + header + template + autodialer-notify active?
        ├─ A2 number_series_gate(trunk)      CLI is 140/1600-registered, not a 10-digit mobile?
        ├─ A3 dnd_scrub(lead.number)         NCPR national register (≤30d fresh) + local suppression
        ├─ A4 window_gate(campaign, lead_tz) within 10:00–19:00 (BFSI 08:00) recipient-local HARD floor
        ├─ A5 consent_gate(lead, campaign)   place-consent fresh (inferred=contract / explicit=7d)?
        └─ B  recording_notice + retention policy resolved -> disclosure_ctx (brand, purpose, tier, record_cue)
    ─ ALLOW ─► wallet hold ─► create_sip_participant ─► (agent.py opener emits disclosure_ctx FIRST)
    ─ BLOCK ─► skip dial, record_call(outcome="blocked_compliance", reason), audit.record(...)
    ─ SOFT  ─► (Tier B during ramp) dial + flag + audit, surfaced in the panel compliance dashboard
```

**Earner-safety:** the gate is **additive and flag-gated** (`COMPLIANCE_ENABLED`, default OFF until
DLT/number-series are actually registered — turning it ON before registration would block ALL dials).
When OFF, `preflight` returns `allow` with a `compliance_unenforced=true` audit marker so we can prove
the resting build is byte-identical to pre-engine. **One box-mutating change at a time** with an
integrated real-call smoke before/after, per the earner-gate discipline.

### 3.2 Data model (4 new tables — FORCE-RLS, admin-GUC, INTEGER/TEXT, mirrors `ddl_wallet.sql`)

All use the platform RLS policy verbatim:
`USING/WITH CHECK ( current_setting('app.is_admin',true)='1' OR tenant_id = current_setting('app.tenant_id',true) )`,
`FORCE ROW LEVEL SECURITY`, `famit_app` = NOSUPERUSER/NOBYPASSRLS.

**(1) `consent_ledger`** — the authoritative, append-only consent record (the legal evidence).
```
consent_ledger(
  id BIGSERIAL PK,
  tenant_id TEXT NOT NULL,
  data_principal_ref TEXT NOT NULL,         -- hashed phone / lead_id (PII-min: store hash + lead_id, not raw)
  consent_type TEXT NOT NULL,               -- 'tcccpr_place_call' | 'dpdp_process_data' | 'recording'
  basis TEXT NOT NULL,                      -- 'explicit' | 'inferred' | 'legitimate_use'
  channel TEXT NOT NULL,                    -- 'web_form' | 'ivr_dtmf' | 'verbal_oncall' | 'whatsapp' | 'import'
  scope TEXT NOT NULL DEFAULT '',           -- campaign_id / purpose string
  granted_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NULL,              -- explicit-txn = +7d; inferred = contract end; null = until-revoked
  revoked_at TIMESTAMPTZ NULL,              -- revocation is a NEW row + stamp here (revocable, easy as giving)
  evidence_ref TEXT NOT NULL DEFAULT '',    -- pointer to recording/form-submission proving informed consent
  source_meta JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)  -- append-only: a revocation/refresh writes a NEW row; the engine reads the latest non-revoked, non-expired.
```
*Freshness check at dial time:* `consent_gate` selects the newest row for
`(tenant, principal, consent_type='tcccpr_place_call', scope=campaign)` where `revoked_at IS NULL AND
(expires_at IS NULL OR expires_at > now())`. No fresh row + DND-listed ⇒ BLOCK.

**(2) `dlt_registry`** — per-tenant registration state (drives A1/A2/A5 + sender-of-record).
```
dlt_registry(
  tenant_id TEXT NOT NULL,
  pe_id TEXT NOT NULL DEFAULT '',           -- Principal Entity id on the operator DLT
  pe_status TEXT NOT NULL DEFAULT 'none',   -- none|pending|active|suspended
  sender_of_record TEXT NOT NULL DEFAULT 'tenant',   -- 'tenant' | 'famit'  (liability decision, §9)
  headers JSONB NOT NULL DEFAULT '[]',      -- [{header, kind:'promo'|'service', status}]
  templates JSONB NOT NULL DEFAULT '[]',    -- [{template_id, variable_slots:[...], status}]
  cli_numbers JSONB NOT NULL DEFAULT '[]',  -- [{number, series:'140'|'1600', status}]
  autodialer_notified BOOLEAN NOT NULL DEFAULT false,  -- access-provider pre-notification done
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id)
)
```

**(3) `dnd_cache`** — NCPR/DND scrub cache (national register, ≤30d freshness).
```
dnd_cache(
  number_hash TEXT NOT NULL,                -- hash of E.164 (no raw PII at rest)
  category TEXT NOT NULL DEFAULT 'all',     -- promo categories the number opted out of
  listed BOOLEAN NOT NULL,
  refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (number_hash, category)
)  -- a stale row (refreshed_at < now()-30d) is treated as MISS -> re-scrub before dial.
```
*Operationally:* the NCPR scrub is via the operator/DLT DND-scrub API (per access provider). The cache
makes the dial-time check O(1) while honouring the ≤30-day refresh duty. **No raw number stored at
rest** — only a salted hash.

**(4) `compliance_audit`** — append-only decision log (rides the existing `audit.record` shape +
PG `events` mirror; this table is the queryable compliance projection for the panel dashboard).
```
compliance_audit(
  id BIGSERIAL PK, tenant_id TEXT NOT NULL,
  call_id TEXT NOT NULL DEFAULT '', campaign_id TEXT NOT NULL DEFAULT '',
  decision TEXT NOT NULL,                   -- allow|block|soft
  gate TEXT NOT NULL,                       -- registration|number_series|dnd|window|consent|recording
  reason TEXT NOT NULL DEFAULT '',
  disclosure_tier SMALLINT NULL,            -- 0|1|2 emitted on this call
  at TIMESTAMPTZ NOT NULL DEFAULT now()
)  -- ≥6-month retention (UCC audit). Never UPDATE/DELETE; erasure cascades scrub principal refs, not the decision row.
```

### 3.3 The preflight gate — order, fail-mode, latency
- **Order is cheapest-first / hardest-block-first:** registration (in-memory cached per tenant) →
  number-series (cached) → window (pure compute, recipient-local) → consent (1 indexed select) → DND
  (1 indexed select, else async re-scrub) → recording/retention policy resolution. Total budget
  **< 15 ms** typical (all reads are PK/indexed; registration+number-series cached in-process with a
  short TTL). DND cache-miss triggers a re-scrub which may add latency — for a cache-miss the engine
  **blocks-and-requeues** rather than dialing un-scrubbed (fail-closed on Tier A).
- **Fail-mode:** any Tier-A gate failure ⇒ `block` + audit + `record_call(outcome="blocked_compliance")`.
  DB error during a Tier-A check ⇒ **fail-closed block** (never dial on unknown compliance state).
  Tier-B (recording/retention) failure ⇒ resolve to the safe policy (recording-notice ON, shortest
  retention) and continue.
- **Idempotent + RLS-safe:** every check sets `app.tenant_id` GUC in-txn (admin ops set
  `app.is_admin='1'`), exactly like wallet — no superuser connection, FORCE-RLS still binds.

### 3.4 Calling-window: the live default is ILLEGAL — fix it
`_in_window` currently defaults **09:00–21:00 IST**. Legal commercial window is **10:00–19:00**
recipient-local (BFSI 08:00–19:00). The engine adds:
- A **legal hard floor** the tenant CANNOT widen: `effective = intersect(tenant_window, legal_window[vertical])`.
  A tenant configuring 09:00–21:00 is clamped to 10:00–19:00 at dial time.
- **Recipient-local** evaluation (not server IST) — derive tz from the lead's number/region; default
  Asia/Kolkata. (Live `_in_window` is IST-only — the engine extends it.)
- Recommended **safety buffer 10:30–18:30** as the *default* tenant window (tighter than the floor) to
  avoid edge-of-window complaints.

---

## 4. The Consent Engine — sub-systems

### 4.1 DLT header/template registry (A1)
- `dlt_registry` is the source of truth; a **panel super-admin screen** (W26 frontend) does CRUD on
  PE/header/template/CLI/notification state. **Block dial** unless `pe_status=active` AND a matching
  header AND ≥1 approved template AND `autodialer_notified=true`.
- **Template-vs-adaptive-brain reconciliation (the key tension):** register **variable-slot templates**
  — a template *envelope* with `{{slots}}` the LLM fills — so the adaptive brain operates INSIDE a
  registered structure and the free-form generation is not a content-template violation. The engine
  validates the campaign's bound `template_id` is approved; the brain is constrained to the slot
  schema. (W2 + W26 co-own; record the registered envelope shape per campaign.)

### 4.2 DND scrub-before-dial hook (A3)
- Two layers, both checked in `dnd_scrub`: **(1) NCPR national register** via `dnd_cache` (≤30d fresh;
  cache-miss ⇒ re-scrub + block-requeue) and **(2) local per-tenant suppression** (the existing
  `_suppressed_set` / `suppression.json` — opt-outs captured on-call "press 9 / say stop"). A hit on
  either ⇒ block (unless a fresh **explicit** consent row overrides NCPR for opted-in categories).
- On-call opt-out ("stop calling me") ⇒ immediate write to BOTH the local suppression store AND a
  `revoked` consent row, honoured on the very next dial (DPDP revocability).

### 4.3 Consent ledger (A5 / DPDP)
- Free/specific/informed/unambiguous/**revocable**, timestamped, **per-channel**, **per-consent-type**.
  Two distinct consents tracked separately (`tcccpr_place_call` vs `dpdp_process_data` vs `recording`).
- **Silence ≠ consent.** Import-time "consent" is `basis=inferred` (valid only contract-duration) or
  must be backed by `evidence_ref`. Explicit-transaction consent auto-expires **+7 days**. The dial-time
  `consent_gate` enforces freshness — **import is not a durable green light.**
- Revocation writes a new `revoked_at`-stamped row; "withdrawal as easy as giving" ⇒ a one-tap panel
  control + on-call opt-out both write here.

### 4.4 Recording consent + retention TTL + cascading right-to-erasure
- **Recording notice** is carried by the Tier-0 opener ("…may be recorded…"); a `recording` consent row
  is written when the call is recorded (ties to REC-B outbound egress already in `caller.py`).
- **Retention TTL:** per-tenant/per-purpose policy (default: recordings 90d, transcripts 180d, audit
  ≥180d for UCC). A scheduled purge job deletes past-TTL artifacts (recording object in Spaces +
  transcript JSON + vector-index rows).
- **Cascading erasure (the hard DPDP duty):** one erasure request for a `data_principal_ref` must
  cascade across **(a) recording object (Spaces), (b) transcript JSON, (c) vector/RAG index entries,
  (d) lead memory / context_store, (e) WhatsApp logs**. Implement as a single
  `erasure.cascade(principal_ref)` that fans out to each store with idempotent deletes, writes an
  audit row (the *fact* of erasure is retained; the data is gone), and is itself idempotent/resumable.
- **At-rest encryption + residency:** recordings/transcripts encrypted at rest; data kept in-region
  (DO blr1 already). No raw phone numbers in compliance tables — salted hashes only.

### 4.5 Calling-hours + abandonment/silent-call guard
- Window gate per §3.4 (legal floor, recipient-local).
- **Abandonment/silent-call discipline:** a single binding national % was **NOT verified** in the
  TCCCPR text reviewed — treat **low abandonment + no dead-air as a self-imposed control** (industry
  norm ≤3%), implemented as a per-tenant abandonment-rate monitor that alarms and throttles BEFORE the
  complaint threshold. **Flagged: confirm the exact figure with operator/counsel (§9).**
- **Complaint-rate monitor:** the earner-killer is **~3–5 complaints can disconnect the number**, and
  TRAI uses AI/ML to disconnect suspected-spam numbers **pre-complaint**. Add a monitor that tracks the
  rolling complaint signal and **alarms + auto-throttles the tenant BEFORE** the ≥5-in-10-days
  suspension threshold. This is the single most important *operational* control for earner survival.

---

## 5. THE DISCLOSURE-LINE RECONCILIATION (the product feature — spec for W2)

> **This section is the spec W2's brain MUST implement.** It resolves the founder's "never say I am an
> AI assistant" vs the disclosure duty into a **configurable product feature**, not a side to pick.

### 5.1 The principle
Comply on the **calling layer** (DLT/consent/number/window) — that is the real legal gate. Satisfy the
**transparency** expectation with a **branded identity + purpose + record-consent** opener that is warm,
fast, human-cadence, and **never contains the banned phrase**. The founder's real hatred — robotic,
apologetic, self-limiting "I am an AI assistant, I cannot…" bot-speak — **never appears**; the legal
auto-dialer-use-and-purpose duty is met; and the line is **flip-ready** to explicit AI disclosure the
day TRAI's proposed mandate lands (a config change, not a code change).

### 5.2 Three tiers (config-driven, per-tenant, per-jurisdiction, env-gated, default-safe)

**Tier 0 — Brand-identity opener (DEFAULT; founder-aligned; in-force-compliant).**
Names brand + purpose + record cue. No banned phrase. *This is the recommended default.*

**Tier 1 — "Digital assistant" safe-harbour cue (per-tenant toggle, recommended for cautious/regulated tenants).**
Adds a natural "<Brand>'s digital assistant" signal — future-proofs against the pending TRAI amendment,
still avoids "I am an AI assistant."

**Tier 2 — Explicit automated/AI line (DORMANT; flip the day a law/regulator/tenant requires it).**
A warm, prefixed "this is an automated voice assistant from <Brand>" line — still not the cold banned
sentence. Behind a flag so enabling is config, not code.

### 5.3 The recommended openers (EN + casual Hinglish + Hindi)

**Tier 0 (DEFAULT — recommend shipping this):**
- **EN:** *"Hi, this is Riya from {Brand} — I'm reaching out about the {product/enquiry} you looked at.
  Quick heads-up, this call may be recorded. Got a quick minute?"*
- **Hinglish (casual, default persona "Riya"):** *"Namaste! Main Riya, {Brand} ki taraf se — aapne jo
  {product} mein interest dikhaya tha usi ke baare mein baat karni thi. Ye call record ho sakti hai.
  Bas do minute?"*
- **Hindi:** *"नमस्ते! मैं रिया, {Brand} की ओर से बात कर रही हूँ — {product} के बारे में थोड़ी बात करनी
  थी। यह कॉल रिकॉर्ड हो सकती है। दो मिनट हैं आपके पास?"*

**Tier 1 (safe-harbour cue — "digital assistant"):**
- **EN:** *"Hi, you're speaking with {Brand}'s digital assistant, Riya — calling about the {product}
  you enquired about. This call may be recorded. Do you have a quick minute?"*
- **Hinglish:** *"Namaste! Main Riya, {Brand} ki digital assistant — {product} ke baare mein baat
  karni thi, aur ye call record ho sakti hai. Sirf ek minute?"*

**Tier 2 (dormant explicit-automated — flip-ready):**
- **EN:** *"Hi — quick note, this is an automated voice assistant from {Brand}, and it may be recorded.
  I'll be quick — is now an okay time to talk about {product}?"*
- **Hinglish:** *"Namaste! Ye {Brand} ki ek automated voice assistant hai aur call record ho sakti hai
  — bas ek minute {product} ke baare mein?"*

### 5.4 RECOMMENDED DEFAULT
**Ship Tier 0 as the platform default** (the Hinglish/Hindi pair as primary for the India-first base,
EN for English leads). It is **in-force-compliant** (brand identity + purpose + record-notice, which is
what TRAI actually requires today), **founder-aligned** (no "AI assistant," confident and human), and
the warmth lives in *voice + cadence + immediate value*, not in pretending to be a person.
**Tier 1 is the recommended toggle for regulated verticals (BFSI/insurance)** and cautious tenants.
**Tier 2 stays dormant** until TRAI's AI-disclosure amendment is notified — then it's a per-tenant
config flip with zero rebuild.

> **Note vs the conservative sister doc:** `INDIA-TELECOM-AI-DISCLOSURE-LAW.md` bakes "AI/automated"
> into its *default* line. Per the legally-precise analysis in `W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md`,
> that explicit-AI wording is **not required by any in-force law** and is the founder's banned register.
> We therefore make the explicit-AI variant **Tier 2 (dormant, available)** rather than the default —
> getting the conservative doc's safety as a one-flip option without forcing the banned phrase today.
> Counsel can elevate the default tier per tenant/vertical at sign-off.

### 5.5 Hard rules the brain (W2) MUST enforce structurally — not by prompt-hope
1. **Disclosure is control-flow, emitted FIRST.** The opener is produced by the **compliance/safety
   layer at the top of the brain priority stack**, before persona/script — so it is structurally
   guaranteed and a vendor script cannot talk past it. (Mirror the existing H8/H12 control-flow
   pattern, not a soft instruction.)
2. **The disclosure context comes from `preflight.disclosure_ctx`** — `{brand, purpose, tier,
   record_cue, jurisdiction, channel}` — never a hardcoded string in `agent.py`.
3. **Hard block-list (the founder's ban + anti-robotic):** the brain must NEVER generate *"I am an AI
   assistant / I'm a bot / I'm a virtual assistant / main ek AI hoon / मैं एक AI हूँ."* This is a
   generation-time filter, not a prompt suggestion.
4. **Truthful if challenged.** If asked "are you a real person / human?", the agent must NOT
   affirmatively claim to be human. It answers **warmly + value-forward** (e.g. *"I'm {Brand}'s
   assistant — but I can actually help you with {X} right now"*), satisfying truthfulness without the
   cold banned line.
5. **Remove the current default.** `prompt.py:358` / `agent.py:218` currently default the disclosure
   phrase to **`"{company} की एक AI assistant"`** — which **contains the banned wording** and is a
   **soft prompt instruction**. W2 must (a) change the default to the Tier-0 line, (b) make emission
   control-flow, (c) add the block-list. *(The knob already exists — W2 fixes the default + enforcement,
   it does not build the mechanism from scratch.)*
6. **Recording cue + opt-out path.** Where recording is on, the record cue is present; a "say stop /
   press 9" opt-out is offered and honoured immediately (writes suppression + revoked consent).

---

## 6. Wave map — how this engine maps to the build waves

| Wave | Owns | What it implements from this spec |
|---|---|---|
| **W26** (this engine) | The Consent & Regulatory Engine | `compliance.py` preflight gate; the 4 tables (`consent_ledger`, `dlt_registry`, `dnd_cache`, `compliance_audit`); DLT registry CRUD + super-admin panel screen; NCPR scrub hook; consent ledger; retention+erasure cascade; complaint/abandonment monitor; `COMPLIANCE_ENABLED` flag. **The dial-path gate.** |
| **W2** (voice brain) | The disclosure-line + block-list | §5: Tier 0/1/2 openers as `disclosure_ctx`; emit FIRST (control-flow); remove the `"…AI assistant"` default at `prompt.py:358`/`agent.py:218`; hard block-list; truthful-if-challenged; record cue. |
| **W12** (capacity / number-pool) | The dialing identity | Number-series enforcement (140/1600 registered CLI; reject 10-digit mobile); auto-dialer access-provider pre-notification; per-tenant identity ↔ registered header match; trunk audit (§8). Co-owns A2/A5 with W26. |
| **W7** (memory/context) | Lead memory in the erasure cascade | Expose `context_store` / lead-memory deletes to `erasure.cascade`; consent-freshness surfaced to the brain. |
| **W9** (recording) | Recording artifacts | Record-consent row on egress; recording retention TTL + purge; recording leg of the erasure cascade (Spaces object delete). Builds on REC-B egress already in `caller.py`. |
| **W14** (reporting/panel) | The compliance dashboard | Read `compliance_audit`: blocked-dials, consent coverage, DND-scrub freshness, complaint-rate gauge (alarm before suspension threshold), erasure-request queue + status. **Frontend CRUD for every compliance capability** (founder rule). |
| **W17** (eval) | Golden tests | Every call opens with a compliant identity+purpose line; **never** emits the banned phrase; record cue present when configured; correct per-jurisdiction/vertical tier; preflight blocks on each Tier-A failure; erasure cascade leaves no residue. |

---

## 7. Earner-safety + rollout posture (non-negotiable)
- **Flag-gated, default OFF** (`COMPLIANCE_ENABLED=0`) until DLT/number-series are actually registered —
  enabling the gate pre-registration would block 100% of dials. When OFF, `preflight` returns `allow`
  with an audit marker; resting build byte-identical to pre-engine.
- **One box-mutating change at a time**, each with an **integrated real outbound-call smoke** (a real
  number rings before AND after) + an immediate revert path; `agent.py` md5 unchanged until W2 lands its
  one opener change, itself env-gated default-OFF.
- **Fail-closed on Tier A, fail-soft on Tier B** during the DPDP ramp.
- **The single highest-leverage operational control** is the **complaint-rate monitor + auto-throttle**
  (§4.5) — it is what actually prevents the operator-disconnection earner-kill.

---

## 8. Immediate audit action (the live earner, today)
1. **Calling window:** live default `09:00–21:00` is **out of legal bounds** — clamp to 10:00–19:00
   (the §3.4 legal floor) as the first dial-path change.
2. **Dialing number identity:** audit the current trunk CLI — is it a **registered 140/1600-series**
   header, or a plain number? A 10-digit-mobile commercial dial is itself a violation.
3. **DLT registration state:** confirm whether Famit / each tenant is a registered PE with approved
   templates today; until then keep `COMPLIANCE_ENABLED=0` (don't block dials) but **do not run
   high-volume** until §9.1–§9.3 are resolved.

---

## 9. Founder / counsel decisions to record (non-blocking; recorded, not gating design)
1. **Sender-of-record:** is Famit the registered PE for all tenants (platform model), or per-tenant PE?
   Changes who eats the ₹10L / disconnection. **Recommend per-tenant PE for liability isolation, Famit
   as RTM/aggregator.** (Captured in `dlt_registry.sender_of_record`.)
2. **Counsel sign-off** on the exact suspension/disconnection clause (the "15-day" figure is
   **unverified** — real mechanism = complaint-triggered suspension of all telecom resources +
   up-to-2-year blacklist) **before high-volume**.
3. **Confirm the abandoned/silent-call cap** with operator/counsel (no single national % verified in
   the TCCCPR text; treat ≤3% as a self-imposed control until confirmed).
4. **Register the variable-slot template envelope** so the adaptive brain operates inside a registered
   template (§4.1) — not a content-template violation.
5. **Default disclosure tier per vertical** at counsel sign-off (Tier 0 default; Tier 1 for BFSI/insurance).

---

## 10. Recommended default disclosure line (the headline output for W2)
**Tier 0 (default), Hinglish primary:**
> *"Namaste! Main Riya, {Brand} ki taraf se — aapne jo {product} mein interest dikhaya tha usi ke baare
> mein baat karni thi. Ye call record ho sakti hai. Bas do minute?"*

**Tier 0, English:**
> *"Hi, this is Riya from {Brand} — I'm reaching out about the {product/enquiry} you looked at. Quick
> heads-up, this call may be recorded. Got a quick minute?"*

Founder-aligned (no banned phrase), in-force-compliant (brand + purpose + record cue), warm, and
flip-ready to Tier 1/2 by config. **This is the spec W2's brain must implement** (§5.5 rules).

---

### Sources
Grounded in the two W26 law docs (which carry the full primary citations): TRAI TCCCPR + 12-Feb-2025
amendment, Telecommunications Act 2023, DPDP Act 2023 + Rules 2025, MeitY SGI IT-Amend-Rules-2026 (in
force 20 Feb 2026, intermediary-scoped), MeitY AI Governance Guidelines (Nov-2025, advisory), and the
law-firm/industry analyses listed in `design/W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md` §8 and
`design/INDIA-TELECOM-AI-DISCLOSURE-LAW.md` Sources. Engineering due-diligence, not legal advice —
counsel sign-off (§9) gates high-volume.
