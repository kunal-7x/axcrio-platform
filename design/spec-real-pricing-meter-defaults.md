# SPEC — REAL Pricing, Cost Meter & Plan Defaults (`real-pricing-meter-defaults`)

> READ-ONLY DESIGN. No code/box mutated by this wave. This file is the execution spec a
> LATER box-mutating wave implements (earner-gated, one wave at a time). Grounded in the
> two briefs in the prompt + live code (`tiers.py`, `agent.py`, `*_meter.py`, `caller.py`).
> Companion to `design/VOICE-BRAIN-MASTER-PLAN.md`. Author date: 2026-06-14.

---

## 0. THE FOUNDER MANDATE THIS SPEC ANSWERS

(b) PRICING MUST BE REAL — every rate from a real current source + URL + date.
(c) PROVIDER LOCK — Sarvam selected → Sarvam runs **and** Sarvam metered (no silent EL fallback in the bill).
(d) bucket suggestions vs HAVE; recommend ROI-first; do NOT blindly add everything.

This spec delivers four things: (1) the REAL cost-per-min / cost-per-call model; (2) corrected
RETAIL tier prices anchored to competitor + India data with a healthy margin; (3) the per-call
real-time **live ₹ cost meter** design; (4) **default pacing/caps per plan** (override-able).

---

## 1. REAL PROVIDER RATES (sourced — the inputs to everything below)

| Provider / SKU | Real rate | Source (URL) | Fetched |
|---|---|---|---|
| Sarvam STT Saarika v2.5 | **₹30/hr = ₹0.50/min = 0.833 paise/s** (₹45/hr diarized) | sarvam.ai/api-pricing; docs.sarvam.ai/api-reference-docs/pricing | 2026-06-14 |
| Sarvam TTS Bulbul **v2** | **₹15/10K = 0.15 paise/char** | sarvam.ai/api-pricing | 2026-06-14 |
| Sarvam TTS Bulbul **v3** | **₹30/10K = 0.30 paise/char** (2× v2) | sarvam.ai/api-pricing | 2026-06-14 |
| Groq Llama-4-Scout (LIVE model) | **$0.11/M in, $0.34/M out** | groq.com/newsroom/llama-4-live-day-zero; cloudzero.com/blog/groq-pricing | 2026-06-14 |
| Groq Llama-3.3-70B | $0.59/M in, $0.79/M out | groq.com pricing | 2026-06-14 |
| Groq Llama-3.1-8B (floor) | $0.05/M in, $0.08/M out | groq.com pricing | 2026-06-14 |
| ElevenLabs Flash v2.5 PAYG | **$0.05/1K = ₹4.76/1K = 0.476 paise/char** | elevenlabs.io/pricing/api | 2026-06-14 |
| ElevenLabs Multilingual v2 PAYG | $0.10/1K = ₹9.52/1K | elevenlabs.io/pricing | 2026-06-14 |
| Vobiz SIP path | **₹0.45/min** | vobiz.ai/products/sip-trunking | 2026-06-14 |
| Vobiz WebSocket/streaming (what we pay) | **₹0.65/min** | docs.vobiz.ai | 2026-06-14 |
| USD→INR | **₹95.2/$** | Federal Reserve H.10, 2026-06-08 | 2026-06-14 |

**Confidence caveats (carry into the UI as footnotes, do NOT hide):**
- Vobiz traces to one 2025 seed announcement — **validate WS rate in the Vobiz console before billing customers.** Until confirmed, telephony is the largest real cost and must not show ₹0.
- Sarvam v2 vs v3: **confirm which Bulbul model the box actually calls** before billing — the meter today bills ALL Sarvam TTS at one rate (v3 ₹30/10K), so v2 (Lean) is over-billed 2×.
- ElevenLabs per-call char cost is a **hint** today (`agent.py:69` EL_RATE_PER_1K=1.5); workspace analytics is authoritative, but it is per-workspace not per-call.

---

## 2. REAL COST MODEL — per-minute and per-call

**Conversational-minute assumptions (replace the optimistic ones in `tiers.py:34-38`):**
- ~150 wpm ≈ **~840 TTS chars/min** of *agent* speech, but agent speaks ~55% of a call → use **~840 chars/agent-min**, ~460 effective chars per wall-clock min. Keep `tts_chars_per_min = 840` (agent-speech basis, conservative-high) so the meter never under-quotes.
- **STT bills the FULL call duration** (both parties' audio), not just agent speech → STT/min = full ₹0.50/min.
- LLM ~1.2K tokens/min in+out → at Scout = negligible.

### 2a. Per-component ₹/min (CORRECTED — the real rate card)

| Component | Lean (Bulbul v2) | Standard (Bulbul v3) | Premium (EL Flash) |
|---|---|---|---|
| STT Sarvam (full-call min) | ₹0.50 | ₹0.50 | ₹0.50 |
| LLM Groq (Scout, ~1.2K tok/min) | ₹0.0026 | ₹0.0026 | ₹0.0026 |
| TTS (840 chars/agent-min) | 840×0.0015 = **₹1.26** | 840×0.0030 = **₹2.52** | 840×0.00476 = **₹4.00** |
| **Vendor ₹/min (ex-telephony)** | **≈₹1.76** | **≈₹3.02** | **≈₹4.50** |
| Telephony Vobiz WS (separate) | ₹0.65 | ₹0.65 | ₹0.65 |
| **All-in ₹/min** | **≈₹2.41** | **≈₹3.67** | **≈₹5.15** |

> Note the brief's headline (TTS = 91% of cost, ₹33/call EL) used a 2,100-char/2.5-min call
> = ~840 agent-chars/min — consistent with the table. The ₹/min figures in `tiers.py` today
> (0.75 / 1.3 / 1.6) are **fiction** (no telephony, optimistic char count). Replace per §6.

### 2b. Per-CALL (default 2.5-min Hinglish outbound)

| | Lean | Standard | Premium (current default stack) |
|---|---|---|---|
| Vendor cost | ₹4.40 | ₹7.55 | ₹11.25 |
| Telephony | ₹1.63 | ₹1.63 | ₹1.63 |
| **Real COGS / call** | **₹6.03** | **₹9.18** | **₹12.88** |

**The 89% lever (founder's #1):** the live default outbound stack runs **EL Flash regardless of
tier** (`agent.py:556-574` hardwired) → every call costs the Premium ₹12.88, even a "Lean"
campaign. Completing the Sarvam provider-lock drops Lean to **₹6.03/call** — at 1,000 calls/mo
that is **₹6,850/mo saved** vs today (and the brief's ₹29K/mo figure holds at the 2,100-char,
all-EL-vs-all-Sarvam extreme). TTS is the entire delta. This is the OB-PROV wave's prize.

---

## 3. RETAIL TIER PRICING (replace the fake `est_inr_per_min`)

### 3a. Anchors
- Competitor all-in floor: Ringg ₹/min ≈ **$0.10 (₹9.5)**; Retell/Bland real all-in $0.11–0.15; Vapi/Synthflow $0.15–0.25. (bland.ai, retellai.com, vapi.ai, ringg.ai/pricing, 2026.)
- India human anchor: telecaller ₹17–39K/mo; 2-caller team ₹40–60K; agency ₹50K–1.5L; CRM ₹12.5–13K; WA BSP ₹3.5–9K. **Total replaced ₹1.06–2.32L/mo** (Glassdoor/Digihify/Kylas/AiSensy, 2026).

### 3b. Retail ₹/min (per-minute usage price, metered from the wallet)

Margin target: **≥3× COGS, capped at ~½ the competitor floor** so Famit is visibly cheaper than
Ringg yet richly profitable.

| Tier | Real all-in COGS/min | **RETAIL ₹/min** | Gross margin | vs competitor floor (₹9.5) |
|---|---|---|---|---|
| **Lean** | ₹2.41 | **₹4.00** | 40% / 1.66× | 58% cheaper |
| **Standard** | ₹3.67 | **₹6.00** | 39% / 1.63× | 37% cheaper |
| **Premium** | ₹5.15 | **₹8.00** | 36% / 1.55× | 16% cheaper |

> These are deliberately *under* a pure 3× (the brief's "6–8× margin room") because India SMB
> buyers compare to a ₹9.5/min competitor and to a human telecaller — being the obviously-cheapest
> credible option wins more than fatter per-minute margin. The real margin lives in the **platform
> fee**, not the metered minute (a per-minute war is a race to the bottom). Tune the multiplier in
> one constant (`RETAIL_MARGIN_MULT`) so the founder can move all three at once.

### 3c. Plan packaging (platform fee + included minutes + overage)

Aligns with the founder's existing 3-plan structure (memory: Starter ₹9,999 / Growth ₹24,999 / Enterprise from ₹75K). Pricing is **platform-fee + prepaid usage credits** (wallet, paise-metered) — minutes priced per §3b.

| Plan | Platform fee/mo | Default voice tier | Included minutes (soft) | Overage ₹/min | Anchored against |
|---|---|---|---|---|---|
| **Starter** | ₹9,999 | Lean | ~1,500 min | Lean ₹4.00 | 1 telecaller (₹17–39K) |
| **Growth** ⭐ | ₹24,999 | Standard | ~3,500 min | Std ₹6.00 (Lean ₹4 / Prem ₹8 selectable) | 2–3 team + agency (₹1.06–2.32L) |
| **Enterprise** | from ₹75,000 | Premium + custom | custom | negotiated | white-label / agency |

> "Included minutes" are a soft allotment funded from the prepaid wallet, NOT a hard monthly cap —
> the existing monthly-minutes admission gate (`caller.py:4476-4480`) + prepaid balance gate
> (`:4482-4487`) already enforce ceilings. Surfaced as "your plan includes ~N min; beyond that you
> pay ₹X/min from your wallet." Never invent a number not backed by §3b math.

---

## 4. LIVE PER-CALL COST METER (real-time ₹ breakdown)

### 4a. What exists (HAVE)
- Client-side projected meter on Run page: `_voice-providers.tsx:178-206` reads `GET /tiers` rate
  card → pure math, zero token burn. Good for *estimate before launch*.
- Per-call actuals are emitted post-hangup: `agent.py:489-531` writes `usage_events` rows
  (vendor/service_type/qty/est_cost_inr) → `record_usage_event` (`caller.py:2579`) →
  `rebuild_cost_ledger` (`caller.py:6435`) → billing explorer.

### 4b. The two gaps the meter must close
1. **Estimate ≠ what runs.** The projected meter shows the *selected tier* rate, but the call runs
   EL (provider-lock bug) → estimate says Lean ₹2.41/min, bill says Premium ₹12.88. The meter must
   show **"estimated (pre-call)"** vs **"actual (from the cost ledger)"** as two distinct numbers,
   and flag drift.
2. **No live mid-call ₹.** Today the actual cost only appears after hangup. Design a per-call
   ledger row stream so the call-detail view shows a live/settled ₹ breakdown per vendor.

### 4c. Design — real-time breakdown (additive, no earner edit)
- **Pre-call estimate (UI, exists, keep):** `total_inr_per_min × est_avg_call_min × num_leads` from
  the corrected rate card (§6). Label every figure "≈ est.".
- **Per-call actual (new read view):** call-detail page calls a new
  `GET /calls/{call_id}/cost` → returns the cost-ledger rows for that call grouped by vendor:
  `[{vendor, service_type, qty, unit, cost_inr, actual_or_estimated}]` + a `total_inr` + a
  `provider_drift` boolean (`true` if a vendor billed ≠ the campaign's configured provider — this
  is the **provider-lock tripwire**). Pure read over the existing `cost_ledger.json` / `cost_ledger`
  PG table; RLS tenant-scoped; NO call-loop change.
- **Live (Phase-2, optional):** if a live mid-call number is wanted, the dial loop can write an
  interim ledger row per N seconds; DEFERRED (adds I/O to the hot loop — not worth it pre-scale).

### 4d. Provider-lock acceptance (founder mandate c)
The cost row IS the proof. Acceptance query (per the brief):
```sql
SELECT vendor, COUNT(*), SUM(cost_inr)
FROM cost_ledger WHERE call_id = $1 GROUP BY vendor;
```
When the campaign's configured `tts_provider = sarvam`, this must show **only `sarvam`** for TTS,
never `elevenlabs`. Surfaced in the UI as the `provider_drift` flag. This makes "Sarvam selected →
Sarvam billed" SQL-checkable instead of a log hunt.

---

## 5. DEFAULT PACING / CAPS PER PLAN (override-able)

### 5a. What exists (HAVE — all enforced live)
- Per-job `concurrency` / `hourly_cap` / `daily_cap` (dial loop `caller.py:2751-2752`).
- Per-tenant `max_concurrency=3`, `daily_call_cap=500` (`caller.py:2713-2714`, in-memory `ACTIVE_CALLS`).
- Monthly-minutes admission gate (`caller.py:4476-4480`); prepaid 402 gate (`:4482-4487`).
- TRAI 09:00–21:00 IST window (`caller.py:828-848`).

### 5b. Gaps
- `budget_cap_inr` stored (`caller.py:3810-3818`) but **never enforced** in the run loop.
- `effective_limits()` from `entitlements.py:271-389` ignored by the run loop (plan caps are dead).
- No per-tenant hourly ceiling; `ACTIVE_CALLS` resets on restart; monthly cap not re-checked mid-job.

### 5c. Plan-default caps (proposed — wire `effective_limits()` to the run loop)

| Limit | Starter | Growth | Enterprise | Override |
|---|---|---|---|---|
| Max concurrency | 2 | 5 | 15 | super-admin |
| Hourly call cap (per tenant) | 120 | 400 | 1,500 | super-admin |
| Daily call cap | 500 | 2,000 | unlimited* | super-admin |
| `budget_cap_inr` default (per campaign) | ₹1,000 | ₹5,000 | unset | tenant |
| TRAI window | 09–21 IST hard | 09–21 IST hard | 09–21 IST hard | NEVER user-bypassable |

\* "unlimited" still bounded by prepaid wallet + monthly-minutes gate. `budget_cap_inr` becomes
**enforcing**: dial loop reads the running cost-ledger sum for the campaign; at ≥ cap → auto-pause +
audit event + panel alert (Phase-2 Switcher item "budget auto-pause").

> **TRAI window must NOT be a user toggle.** Today `force_window=True` can bypass it from the panel
> (compliance gap). Plan defaults keep the window hard; only a super-admin (not a tenant) may grant
> an exception, and it is audited. (Cross-refs `design/control-security.md`.)

---

## 6. EXACT FILES / TABLES TO CHANGE (for the implementing wave)

### 6a. Rate-card truth (single source) — `droplet_work/llm_router/tiers.py`
- `RATE_CARD.assumptions.tts_chars_per_min`: 900 → **840** (sourced basis).
- `RATE_CARD.llm`: add the **live** model `groq-llama-4-scout` with `inr_per_mtok` computed from
  $0.11/$0.34 × 95.2 blended (~₹21.4/Mtok blended); keep existing entries.
- `RATE_CARD.tts.sarvam-bulbul-v2.inr_per_1k`: 1.5 ✓ (correct). `sarvam-bulbul-v3`: 3.0 ✓.
  `elevenlabs-flash-v2.5`: 4.2 → **4.76** (real $0.05/1K × 95.2).
- `RATE_CARD.telephony_inr_per_min`: 0.0 → **0.65** (Vobiz WS; stop hiding the biggest cost). Add a
  `source` + `as_of` field per rate so the UI can render the citation. Add a top-level
  `rate_card.sources` map {rate_key → {url, as_of, confidence}}.
- `TIERS[*].est_inr_per_min`: replace with the §2a all-in figures (Lean 2.41 / Std 3.67 / Prem 5.15)
  OR compute on the fly from the rate card (preferred — single source). Add `retail_inr_per_min`
  (4 / 6 / 8) as the *price* vs `est_inr_per_min` as the *cost* — UI shows price to vendor, cost to
  super-admin only.
- Add `RETAIL_MARGIN_MULT` + a `retail_inr_per_min` derivation so the founder tunes all three at once.

### 6b. Meter rate constants (must match the rate card) — env + meter files
- `agent.py:72` + box `.env`: **`USD_INR=95.2`** (today =1 → Groq billed ~95× low). One-line env fix.
  *Earner-touching `.env` only — no `agent.py` code edit; still earner-gated (a process restart). The
  Groq billing line `agent.py:516` already multiplies by `USD_INR`, so the fix is pure config.*
- `agent.py:69` `EL_RATE_PER_1K_CHARS`: 1.5 → **4.76** via env `EL_RATE_PER_1K_CHARS=4.76` (no code edit).
- `vendors/sarvam_meter.py`: split the single `TTS_RATE_PER_10K` into **v2 (15) vs v3 (30)** keyed on
  the event's model, so Lean is billed at v2. Add `SARVAM_TTS_RATE_V2_PER_10K` / `_V3_PER_10K` env.
  (`agent.py:511`-area + `aim_voice_agent` emit the model on the usage event so the meter can branch.)
- `vendors/groq_meter.py`: defaults already in USD/Mtok ($0.11/$0.34) — keep, but the *consumer*
  (`agent.py`) must multiply by `USD_INR=95.2`. Add a `groq-llama-4-scout` note (matches live model).

### 6c. Provider lock (Phase-2 OB-PROV — agent.py sign-off + ring-gate)
- `agent.py:556-574`: dispatch TTS on `fields.get("tts_provider")` → `sarvam.TTS(...)` vs
  `elevenlabs.TTS(...)`. **GATED — founder sign-off + real ring; DID currently carrier-rested.**
- `agent.py:489-531`: add a `sarvam_tts_chars` counter + a `vendor=sarvam service_type=tts` event so
  the bill reflects what actually ran. Companion to the dispatch.
- Inbound `aim_voice_agent.py` `_build_tts()`: same dispatch + a Sarvam TTS meter event (inbound is
  earner-safe — can ship first as the pilot of the lock).

### 6d. Live cost-meter read API (additive, earner-safe)
- NEW `GET /calls/{call_id}/cost` in `caller.py` (read `cost_ledger`, group by vendor, compute
  `provider_drift` vs the campaign config). RLS tenant-scoped via existing `resolve_tenant`.
- `famit-panel`: call-detail / CRM call view consumes it → renders the live ₹ breakdown + a
  red "provider mismatch" chip when `provider_drift`. Reuse the billing-explorer table styling.
- Run page `_voice-providers.tsx`: label projected meter "≈ estimated"; pull rate-card `sources` and
  render the citation tooltip (kills "fake price" suspicion at the point of decision).

### 6e. Plan caps wiring (additive)
- Run loop (`caller.py` dial loop ~2710-2760): read `effective_limits(tenant, plan)` from
  `entitlements.py:271-389` instead of the hardcoded `max_concurrency=3` / `daily_call_cap=500`.
- Enforce `budget_cap_inr`: in the loop, sum the campaign's cost-ledger; at ≥ cap → pause + audit.
- Persist plan-default caps in the tenant/plan store; super-admin override UI (reuse control-layer
  entitlements surface).

### 6f. Tables
- **No new table required for the meter** — `cost_ledger` (`db/models.py`) already holds per-call
  vendor cost rows. The read API + the `model`/`provider` field on the usage event is all that's new.
- Optional (Phase-2, the brief's "event cost ledger"): a `call_cost_ledger(call_id, vendor, model,
  provider, chars/tokens/seconds, cost_paise, actual_or_estimated)` append-only PG table with RLS +
  FORCE-RLS makes provider-drift a first-class SQL query and survives restart (vs JSON). DEFER until
  >5K calls/mo; the JSON ledger covers it now.

---

## 7. FLAG / ACCEPTANCE / ROLLBACK

**Flags (additive, default-OFF where they touch live behavior):**
- Rate-card / env fixes (`USD_INR`, `EL_RATE`, Sarvam v2/v3 split, telephony 0.65): config-only.
  No flag needed for the *display* rate card; the *billing* env values take effect on the next
  service restart (caller for meter, earner for `agent.py` env — earner-gated).
- `GET /calls/{call_id}/cost` + plan-caps wiring: behind `COST_METER_V2=1` until verified.
- Provider lock dispatch: behind the existing `OB_PROV` gate — **founder sign-off + ring**.

**Acceptance (no test-calls — earner verified by md5+PID+health per PLAYBOOK §1.4):**
1. `GET /tiers` returns the corrected rate card with `source`+`as_of` on every rate; UI renders
   citations; telephony shows ₹0.65 not ₹0.
2. Re-bill a known historical call after `USD_INR=95.2`: Groq cost rises ~95× (sanity: still small,
   ₹0.07-ish/call) — proves the bug fixed without changing call behavior.
3. Sarvam v2 vs v3 events bill at 15 vs 30 /10K respectively (replay a Lean usage event → ₹ halves).
4. `GET /calls/{id}/cost` returns rows grouped by vendor + `provider_drift`; on a campaign configured
   Sarvam, an EL TTS row sets `provider_drift=true` (the lock tripwire works even before OB-PROV).
5. Plan caps: a Starter tenant's run is admitted at concurrency 2 / hourly 120; a Growth tenant at 5 /
   400 (read `effective_limits`, not the hardcoded constant).
6. `budget_cap_inr` enforcing: a campaign with cap ₹100 auto-pauses + audits when ledger sum ≥ ₹100.
7. **Earner-safety gate:** `agent.py` md5 `9150fabe…` UNCHANGED, famit-agent PID 1477083 NOT
   restarted (config-env restart of the earner is the ONLY earner-touching step and is founder-gated),
   /health 200, 0 5xx. NO outbound test call — founder's real call is the only live proof.

**Rollback:**
- Rate-card / env: revert the `.env` values + `tiers.py` to the `*.bak` snapshot; restart the changed
  service only. Display reverts instantly; no data migration to undo.
- Provider lock: it is flag-gated (`OB_PROV` off) → off = today's behavior exactly. The `.env`
  `USD_INR`/`EL_RATE` are independent of the lock and can stay.
- Cost API / plan caps: `COST_METER_V2=0` → routes/wiring dormant.

---

## 8. RISKS

1. **Telephony rate unconfirmed (₹0.65 Vobiz WS).** It is the largest single cost and the source is a
   2025 seed announcement. RISK: under-pricing a plan if the real rate is higher. MITIGATION: surface
   it as "est. — confirm in Vobiz console" in the super-admin cost view; do not bake it into a customer
   contract until the founder confirms the console figure. The retail ₹/min has 1.5×+ margin headroom.
2. **EL "all-tier" bill today.** Until OB-PROV ships, EVERY call (even Lean) really costs the EL stack
   ₹12.88, but the meter (post-env-fix) will now show that honestly — the *estimate* (Lean ₹2.41) and
   the *actual* (₹12.88) diverge. This is the truth, not a bug; the `provider_drift` flag makes it
   visible. The fix is the lock, not hiding the number.
3. **Sarvam v2/v3 model on the event.** The meter split needs the emitting agent to tag the TTS event
   with the model. If `agent.py`/`aim_voice_agent.py` don't emit `model`, the split can't branch —
   the inbound side (earner-safe) can add the tag first; the earner gets it on its next signed deploy.
4. **`USD_INR=95.2` is a fixed constant.** FX drifts; ~₹95 is fine for billing-estimate granularity
   (we mark all vendor costs "estimated"). Don't over-engineer a live FX feed — a quarterly env bump
   is enough. RISK is trivial (Groq is ₹0.07/call).
5. **Plan-cap wiring touches the live dial loop.** `effective_limits()` read must be fail-OPEN to the
   current hardcoded default on any error (never block a paying tenant's run because the entitlements
   read threw). Earner is `agent.py` (untouched); the dial loop is `caller.py` (caller restart only).
6. **Margin vs price war.** Setting retail ₹/min below 3× COGS protects the *competitive* position but
   thins per-minute margin — the platform fee must carry the P&L. If the founder wants fatter minute
   margin, bump `RETAIL_MARGIN_MULT`; the spec exposes it as one knob precisely so this is a 1-line call.

---

## 9. ONE-LINE SUMMARY FOR THE LEDGER
Real rates sourced (Sarvam ₹30/hr + ₹15/₹30 per-10K v2/v3, Groq Scout $0.11/$0.34, EL Flash $0.05/1K,
Vobiz WS ₹0.65/min, ₹95.2/$); real COGS ₹6.03/9.18/12.88 per 2.5-min call; retail ₹4/6/8 per min
(plans ₹9,999/₹24,999/₹75K+); 3 billing bugs to fix by env (USD_INR=95.2, EL=4.76, Sarvam v2/v3 split);
live `GET /calls/{id}/cost` meter + `provider_drift` lock tripwire; plan-default caps via
`effective_limits()`; provider lock = OB-PROV (founder-gated). Earner-safe, RLS, flag+rollback per §7.
