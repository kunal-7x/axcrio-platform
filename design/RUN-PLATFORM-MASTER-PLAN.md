# 🎯 RUN-PLATFORM MASTER PLAN — voice preview fix + REAL pricing + provider-lock + crazy Run UI + phased earner-safe roadmap

> **Synthesized 2026-06-14** from 6 design agents + 6 red-team agents (preview-fix-correctness, provider-billing-correctness, pricing-accuracy, earner-safety, over-engineering-critic, plus the inventory + design fan-out). READ-ONLY synthesis — this doc + ledger pointers are the only writes. Folds in EVERY red-team fix; the red-team OVERRODE the original designs on three load-bearing points (preview root cause, retail margin, ledger-is-the-bill).
>
> **READ-ORDER for any agent continuing this:** (1) `caps/PLAYBOOK.md` (earner rules) → (2) `caps/MASTER_PLAN.md` + `design/VOICE-BRAIN-MASTER-PLAN.md` (what the brain is) → (3) `design/VOICE-BRAIN-STATE.md` + `AGENT_LEARNINGS.md` (W1 DONE, P0-LEAK **DONE+DEPLOYED**) → (4) THIS doc → (5) the per-topic design specs (`design/spec-real-pricing-meter-defaults.md`).
>
> **🟥 GROUND-TRUTH RECONCILIATION (the single most important fact for the next agent):** `AGENT_LEARNINGS.md` top entry proves **P0-LEAK is DONE + DEPLOYED + RE-VERIFIED (2026-06-14, commit `4db497f`)** — it is NOT "QUEUED" (the stale line in `VOICE-BRAIN-STATE.md:50` predates the deploy). The cross-tenant `caller.py`/`memory.py` collision risk that gated this whole plan **is resolved**. Live box now: `caller.py` md5 `992c08ff1a1fd2cb4c998eef09546335`, `memory.py` `cb70e1d7…`, `aim_voice_agent.py` `5a93096d…`, **`agent.py` (earner) still `9150fabe…` UNCHANGED, famit-agent PID 1477083 never restarted.** So the preview-fix + provider-lock waves below can sequence next with NO outstanding shared-file collision.

---

## 0. EXECUTIVE SUMMARY (≈25 lines — read this, skip nothing else if pressed)

1. **The voice preview is STILL silent because the EL preview bytes are served with `Content-Type: text/plain`** (proven live on the box by the red-team — the brief's "`audio/mpeg`" was fabricated; `curl -L` ignores content-type and gave a false green). Safari/iOS refuses `text/plain` for `<audio src>` → silence; Chrome sometimes sniffs but not via a redirect. The cross-origin 307 the original design blamed is a **non-cause**. **FIX = backend full-buffers the tiny (≤32 KB) EL clip and returns it same-origin with `media_type` FORCED to `audio/mpeg` (never echo upstream `text/plain`), handle BOTH EL hosts (`storage.googleapis.com` + signed-expiring `api.us.elevenlabs.io`), drop `Accept-Ranges`; client gets a real `.catch` + `<audio onError>` + a "Preview unavailable" caption, and NO `preload="none"`.**
2. **REAL cost-per-call (corrected, sourced 2026-06-14) for a 2.5-min call:** with the live earner running EL Flash for **every** tier today, a call costs **≈ ₹9–13** (EL-dominated). After the provider-lock drops Lean/Std to Sarvam Bulbul: **Lean ≈ ₹6.0 · Standard ≈ ₹9.2 · Premium ≈ ₹13–24** (Premium stays EL → its true cost is the red-team's corrected EL *effective* rate, 3–6× the $0.05 headline). Telephony (Vobiz) is **UNVERIFIED** — must be pulled from the founder's real Vobiz CDR, never quoted as sourced.
3. **Corrected retail tier prices (margin lives in the platform fee, NOT a per-minute war):** **Lean ₹4/min · Standard ₹6/min · Premium ₹8/min**, sold inside **Starter ₹9,999 / Growth ₹24,999 / Enterprise ₹75K+** monthly platform fees. ⚠️ Red-team verdict: at the founder's real EL volume **Premium ₹8/min is BELOW true Premium COGS** → Premium is a platform-fee-funded loss-leader OR its retail must rise; Lean/Std margin (~40%) holds **only if** the unverified Vobiz rate is real. Do NOT ship these as guaranteed prices until Vobiz CDR + the founder's actual EL plan tier are confirmed.
4. **Provider-lock = "Sarvam selected → Sarvam invoked AND billed."** Today `agent.py:556` hardwires `elevenlabs.TTS()` for every tier and bills `vendor=elevenlabs` unconditionally; Sarvam Bulbul is never invoked outbound. **The fix is a pure `resolve_providers(fields)` leaf-fn in `prompt.py` driving BOTH plugin construction AND the metering `vendor` field**, inbound-first (buildable now), outbound flag-gated `OB_PROV_ENABLED=0` (earner — needs founder sign-off + a real ring; DID is carrier-rested).
5. **🟥 Red-team killer the founder must hear:** the **money actually charged is `_charge_call` = duration × flat `rate_per_min`** (`caller.py:2537,2544`) which **ignores `vendor` entirely** — the provider-lock makes the *dashboard/cost-ledger* truthful, not the *invoice*. So "Sarvam billed" is true in observability today; making it true on the wallet is a separate (deferred) F4-wallet wiring. State this plainly; don't over-claim.
6. **3 real billing bugs, all env-fixable (NOT "config-only, no restart" — they need the next NATURAL earner restart):** `USD_INR=1` → set `95.2` (Groq ~95× undercharged); `EL_RATE_PER_1K=1.5` → `4.76`; Sarvam single TTS rate → split v2 ₹15/10K vs v3 ₹30/10K. On inbound these apply now (unit restartable); on the outbound earner they apply only at the founder-signed ring-wave.
7. **Quick-wins first:** (W-A) the 2 env billing fixes + (W-B) the preview stream fix + (W-C) the provider-lock metering-label + honest cost meter — all small, mostly inbound/panel, earner-safe. THEN the crazy Run UI inline upgrades. Everything OB-PROV / wallet-wiring / new-tables is DEFERRED behind the DID un-rest + founder sign-off.
8. **Earner gate is NOT `agent.py` md5 alone** — the earner re-renders through shared `prompt.py` every dial; any `prompt.py` edit (the resolver) MUST gate on `droplet_work/_golden/verify_golden.py` exit 0 (byte-identical flag-off) + a FRESHLY-captured live box md5 (the hardcoded `9150fabe` is the *box* value; local disk is `1a154ea1` — re-baseline from the box, never trust a constant).

---

## 1. THE REAL PRICING TABLE (every rate sourced, with the red-team corrections)

> **Founder mandate (b): every number from a real current source with a URL + date. The red-team independently re-verified each rate and FAILED three. Those three are flagged 🟥/🟧 and must NOT be quoted as "sourced" until confirmed.** Companion detail: `design/spec-real-pricing-meter-defaults.md`.

### 1a. Per-component vendor rates (sourced 2026-06-14)

| Component | Provider · model | Rate | Source (URL + date) | Confidence |
|---|---|---|---|---|
| STT | Sarvam Saarika v2.5 | **₹30 / hr** (= ₹0.50/min) | docs.sarvam.ai/api-reference-docs/pricing · 2026-06-14 | ✅ VERIFIED verbatim |
| TTS | Sarvam Bulbul **v2** | **₹15 / 10K chars** | docs.sarvam.ai/.../pricing · 2026-06-14 | ✅ VERIFIED |
| TTS | Sarvam Bulbul **v3** | **₹30 / 10K chars** | docs.sarvam.ai/.../pricing · 2026-06-14 | ✅ VERIFIED |
| LLM | Groq Llama-4-Scout-17B | **$0.11 in / $0.34 out per Mtok** | groq.com/pricing + cloudzero.com/blog/groq-pricing · 2026-06-14 | ✅ VERIFIED |
| TTS | ElevenLabs Flash v2.5 | headline **$0.05/1K** = ₹4.76 — but **effective $0.15–0.30/1K (₹14–29)** at real volume | elevenlabs.io/pricing · 2026-06-14 | 🟧 **HEADLINE ONLY** — credit-based + mandatory monthly sub; $0.05 is the asymptotic floor at Business-tier full utilization. Use the founder's ACTUAL plan tier. |
| Telephony | Vobiz SIP (WS) | **₹0.65/min = FABRICATED** | docs.vobiz.ai (publishes NO per-min rate) · 2026-06-14 | 🟥 **UNVERIFIED — must pull from the founder's real Vobiz console CDR/invoice.** Never quote as sourced. |
| FX | USD → INR | **₹95.2** | Fed H.10 / market June-2026 (₹94.95–95.88; Jun-13 ₹95.21) | ✅ VERIFIED |

### 1b. Real COGS per 2.5-min call (corrected — `tiers.py` figures are fiction)

> Chars/min ≈ 840 (TTS), STT = whole-call min, LLM ≈ per-turn tokens. `tiers.py:55` hides telephony at ₹0 — the largest real driver. **All-in numbers below CONDITIONAL on the two flagged rates.**

| Tier | STT | LLM (Groq) | TTS | Telephony (⚠ unverified) | **All-in /min** | **Per 2.5-min call** |
|---|---|---|---|---|---|---|
| **Lean** (Sarvam Bulbul v2) | ₹0.50 | ₹0.07 | ₹1.26 | ₹0.65? | **≈ ₹2.41** | **≈ ₹6.0** |
| **Standard** (Sarvam Bulbul v3) | ₹0.50 | ₹0.07 | ₹2.52 | ₹0.65? | **≈ ₹3.67** | **≈ ₹9.2** |
| **Premium** (ElevenLabs Flash) | ₹0.50 | ₹0.07 | **₹4.0 headline / ₹12–24 effective** | ₹0.65? | **≈ ₹5.15 headline / ₹13–24 TRUE** | **≈ ₹12.9 headline / ₹13–24 TRUE** |

**🟥 The live truth today:** the earner runs **EL Flash for EVERY tier** (`agent.py:556` hardwired) → a "Lean" call really costs the Premium figure. The provider-lock (OB-PROV) is what makes Lean actually cost ₹6 — a real ~₹6,850/mo saving at 1K calls.

### 1c. Retail tiers (replaces the fake `est_inr_per_min` 0.75/1.3/1.6 in `tiers.py:70/81/92`)

| Tier | Retail /min | Monthly platform fee | Anchored against |
|---|---|---|---|
| **Lean / Starter** | **₹4/min** | **₹9,999/mo** | India telecaller ₹17–39K/mo |
| **Standard / Growth** ⭐ | **₹6/min** | **₹24,999/mo** | 2–3-person team ₹60K–1.2L/mo |
| **Premium / Enterprise** | **₹8/min** | **₹75K+** | full team + agency ₹1.06–2.32L/mo |

**🟥 Red-team margin corrections (do NOT ship as guaranteed prices):** (i) Premium ₹8/min is **below true Premium COGS** once EL is costed at its real effective rate → Premium is a **platform-fee-funded loss-leader**, state it explicitly or raise the retail. (ii) Lean/Std ~40% margin holds **only if** the unverified Vobiz ₹0.65 is real — if India outbound telephony is actually ₹1.5–2/min, Lean margin collapses to ~15% or negative. (iii) The "competitor floor ₹9.5/min" anchor is inflated — the honest competitor band is **₹5.7–9.5/min** (Ringg enterprise ₹5.71, Retell base ₹6.67, Bland ₹8.57; ringg.ai/pricing, retellai.com, ringlyn.com 2026). Drop "obviously cheapest" at Premium. **Margin lives in the platform fee, not the per-minute rate.**

### 1d. Default pacing / caps per plan (sane defaults, DID-protective)

| Plan | concurrency | hourly_cap | daily_cap | monthly_min gate |
|---|---|---|---|---|
| Starter | 1–2 | 60 | 200 | plan entitlement |
| Growth | 2–3 | 120 | 500 | plan entitlement |
| Enterprise | 3+ (negotiated) | 240 | custom | custom |

Audience-aware override (`_pacing-defaults.ts`, pure fn, never overrides a manual edit): audience ≥200 → conc 3 / hourly 120; 26–199 → conc 2 / hourly 60; ≤25 → conc 1 / no cap. **These are DEFAULTS the founder can edit** — they protect the single DID from the 486-spam that carrier-blocked it. Enforcement of plan caps (the dead `effective_limits()` at `entitlements.py:271-389`) + `budget_cap_inr` is **DEFERRED** to the OB-PROV/dial-loop wave (over-engineering-critic K2: don't build enforcement for a loop the DID-block prevents from running).

---

## 2. THE PREVIEW FIX (corrected root cause — the red-team OVERRODE the original design)

**Original design said:** cross-origin 307 to GCS breaks `<audio>`. **Red-team proved live this is a NON-cause** (browsers follow cross-origin 307 for `<audio src>` fine; Cloudflare doesn't strip it). **THE REAL ROOT CAUSE: the EL preview bytes are served `Content-Type: text/plain`** (proven on both EL hosts live). Safari/iOS refuses `text/plain` for `<audio src>` → silent `MEDIA_ERR_SRC_NOT_SUPPORTED`; Chrome only sometimes sniffs, and not through a redirect. The original "curl proof" was a false green (curl ignores content-type).

### The fix (folds in ALL preview-fix-correctness corrections)

**Backend — `droplet_work/caller.py` voice-preview EL branch (live route `:3676-3720`, redirect at `:3716`):**
- Resolve `preview_url` via the EL `/v1/voices` lookup (cache the `voice_id→preview_url` map, **TTL < the signed-URL lifetime**; re-resolve on a `403`/`410` from the signed host — `api.us.elevenlabs.io` URLs are signed+expiring).
- Handle **BOTH** host shapes (`storage.googleapis.com` AND `api.us.elevenlabs.io/v1/voices/.../previews/audio?payload=…`) — do NOT branch on "is it GCS".
- **Full-buffer the clip** (≤32 KB) server-side via `httpx.AsyncClient` (hard 5 s timeout) and return `Response(content=<bytes>, media_type="audio/mpeg")` — **content-type FORCED to `audio/mpeg`, never echo upstream `text/plain`** (this is the load-bearing line). Full-buffer > streaming for a tiny clip — sidesteps range/chunk-stall. **Do NOT advertise `Accept-Ranges`** if not honoring ranges.
- On upstream non-200 / empty / HTML-error-as-200 → explicit `502 {"error":"upstream preview empty"}`, never a silent redirect.
- Sarvam branch (`:3704`) keeps the WAV `FileResponse` (already `audio/wav`, works — proven `200 audio/wav 206380 B`). Reconcile the `.mp3` docstring (`:3679`) ↔ `.wav` code. Only 7 speakers pre-hosted → on a missing speaker return explicit `404 {"error":"speaker_not_prehosted","speaker":vid}` so the UI caption is specific.

**Frontend — `famit-panel/app/run/_voice-providers.tsx`:**
- Line 228-230: replace the black-hole `.catch(()=>setPlayingId(""))` with `.catch((err)=>{console.error("voice preview failed",v.voice_id,voiceProvider,err); setPlayingId(""); setPreviewError(v.voice_id);})`.
- `<audio>` (line 328-333): add `onError` handler → `setPreviewError`. **Do NOT add `preload="none"`** (red-team Failure 4: with a slow proxy it lets Safari treat the load as non-gesture → autoplay-block). Keep `src`-set + `play()` in ONE synchronous gesture tick.
- New `previewError` state → render a small "Preview unavailable — retry" caption (Core_2 token style) next to the row's ▶. Converts every silent failure into a visible, debuggable one.

**Acceptance (the only truth = founder HEARS it, PLAYBOOK #2):** per provider AND across **Chrome + Safari/iOS**: HTTP `200` + `content-type: audio/mpeg` (NOT `text/plain`) + **byte-sniff first 3 bytes ∈ {`ID3`, `\xFF\xFB`, `\xFF\xF3`} (MP3) or `RIFF` (WAV)** (the `>10000` size gate is satisfiable by a 16 KB HTML error page — insufficient) + the founder's ear on a Premium(EL) AND a Lean/Std(Sarvam) voice. **Flag: NONE** (over-engineering-critic T2 + earner-safety F5 reconciled — the route is no-spend/no-PII; the streaming-proxy is strictly better; rollback is `restore caller.py.PVbak + restart famit-caller`). **Earner-safe:** non-earner route, no `agent.py`, no spend; restart `famit-caller` ONLY, `/health 200`, 0 5xx. **Sequence: AFTER P0-LEAK (DONE) — no collision remains; this is now next-eligible.**

---

## 3. THE PROVIDER-LOCK (invoked + billed — with every red-team gap closed)

**Principle:** the selected `{stt, llm, tts}` triple is the one INVOKED and the one BILLED — no silent EL fallback; a down provider FAILS VISIBLY (default) or uses a pre-consented backup that is **billed as the backup that ran**.

**The pivot:** a single pure `resolve_providers(fields)` leaf-fn (in `prompt.py`, imported by both agents) returns the actually-constructed triple as a dict, and that SAME dict drives BOTH plugin construction AND the metering `vendor` field. One source of truth → invoke and bill can't diverge.

### Red-team-mandated gaps (provider-billing-correctness) — ALL folded in

| # | Gap | Resolution in this plan |
|---|---|---|
| F1 | **The wallet charge (`_charge_call`, `caller.py:2537,2544`) = duration × flat rate, ignores `vendor`** | **Scope the lock to OBSERVABILITY/cost-ledger only**; tell the founder the invoice is flat-per-minute by design until F4 wallet is wired to calls (Gap §12 — DEFERRED). `provider` drift = an audit signal, not yet an invoice correction. Do NOT over-claim "Sarvam billed on the invoice." |
| F2 | counter, provider-stamp, dispatch shipped separately = half-wired bug | **Atomic invariant:** rename `el_tts_chars`→`tts_chars`, set `usage["tts_provider"]=ctl["active_tts_provider"]` at construction, and switch dispatch — all in ONE commit. Never a subset. |
| F3 | STT persisted-but-unread (latent silent-fallback) | Either drive STT from the resolver too, OR **declare STT/LLM hardwired and hide the choice in the UI** — don't persist a config the engine ignores. |
| F4 | LLM model from env not `fields`; one flat rate for any model (7× spread) | Add `llm` to the resolver with per-model rate keys (mirror TTS v2/v3), drive `groq.LLM(model=…)` from it — OR declare LLM model fixed and stop persisting a selectable one. |
| F7 | `tts_chars` counted from assistant *text* at item-add, not delivered audio → overcounts interrupted utterances | Count from a synthesis/playout callback (bytes synthesized), not text length. |
| F8 | scalar counter can't represent a mid-call consented swap (the case the mandate cares most about) | Accumulate **per-provider** (`tts_chars_by_provider: dict`), emit one TTS event per provider that ran. |
| F9 | room→tenant join failure orphans cost to wrong tenant / "admin" | Acceptance gate asserts `tenant_id` correctness too; orphan→admin is a monitored alarm, not a silent bucket. |
| F10 | **Inbound emits ZERO usage events** → the inbound acceptance query returns 0 rows | The inbound lock makes the *session-log* truthful NOW; a fully-metered inbound call (`record_usage_event` emission) is a SEPARATE additive unit to queue. State honestly: inbound lock = truthful label, no bill exists yet. |
| F11 | `agent.py` md5 is a FALSE gate (earner re-renders via shared `prompt.py`) | Gate = `_golden/verify_golden.py` exit 0 (byte-identical flag-off) + a unit test `resolve_providers({}) ≡ hardwired EL triple` + freshly-captured live box md5. Resolver MUST be pure/side-effect-free leaf. |

### Scope split (earner-safe)

| Leg | File | Status | Flag |
|---|---|---|---|
| **Inbound** | `droplet_work/aim_voice_agent.py:385` `_build_tts` + `:2307` call + `:2652` `_slog.start` | **BUILD NOW** (label-truthful) | `INBOUND_PROV_LOCK=1` (env-toggle revert) |
| **Outbound** | `droplet_work/agent.py:556` TTS + `:489-531`/`:735` metering | **GATED — DEFERRED** (earner; needs founder sign-off + ring; DID rested) | `OB_PROV_ENABLED=0` → forces EL triple = byte-identical to today |
| **Preview** | `caller.py` voice-preview | covered in §2 | — |

**Constructor isolation (earner-safety F3):** the inbound `_build_tts(prov)` dispatch lives **IN `aim_voice_agent.py` only**, NOT in any module `agent.py` imports. Only the *resolver* (pure data) is shared via `prompt.py`. The outbound `:556` dispatch stays a separate gated inline block whose flag-OFF path is **byte-identical** to today's `elevenlabs.TTS(...)`.

**Fail-visible (over-engineering-critic D2 trim):** Phase-1 = **FAIL VISIBLE only** (log `tts_construct_failed`, flip the panel health dot). The full consented-backup + mixed-vendor-billing machinery is **DEFERRED** to when OB-PROV ships and a provider can actually go down mid-call.

**Billing-bug honesty (earner-safety F4 / provider-billing F6):** `USD_INR=95.2`, `EL_RATE_PER_1K=4.76`, Sarvam v2/v3 split take effect only on the **next NATURAL earner restart** — they are earner-gated for OUTBOUND (same bucket as OB-PROV), and "NOW" only for the restartable inbound unit. Until the founder-signed ring-wave, label the cost meter "estimate pending earner restart." **Verify which Bulbul version inbound actually calls before building the Sarvam meter split** (over-engineering-critic T3).

---

## 4. FOUNDER-CALL FEATURE ROADMAP — every suggestion bucketed (HAVE / ADD-NOW / ADD-LATER / SKIP)

> Founder mandate (d): bucket each suggestion vs what we HAVE; recommend ROI-first; do NOT blindly add everything. Layer tags: FE/BE/DB/AI.

| # | Feature | Bucket | Layer | One-line reason |
|---|---|---|---|---|
| 1 | Voice preview audible | **ADD-NOW** | FE+BE | The silent bug; §2; quick-win #1. |
| 2 | Real cost meter (sourced rates, telephony shown) | **ADD-NOW** | FE+BE | Kills fake-price fury; depends on the env rate-card fix landing first. |
| 3 | 3 env billing fixes (USD_INR/EL/Sarvam-split) | **ADD-NOW** | BE | One-line env each; ~95× Groq undercharge is live. |
| 4 | Provider-lock metering label (vendor=ran) inbound | **ADD-NOW** | BE+AI | Makes "Sarvam selected→Sarvam billed" structurally true in the ledger. |
| 5 | Provider-lock outbound dispatch | **ADD-LATER** | AI | Earner; gated OB_PROV; needs sign-off + ring; DID rested. |
| 6 | Exclude "already-called in this campaign" toggle | **ADD-NOW** | FE+BE | Data exists (`calls.campaign_id`); pure audience filter; zero infra. |
| 7 | Per-voice / per-agent comparison view | **ADD-NOW** | FE+BE | `voice_id` is on every call row; a 30-line `groupBy`; high ROI. |
| 8 | CPL (cost-vs-qualified) at campaign level | **ADD-NOW** | FE+BE | Join `/billing/explorer` total ÷ qualified; no new DB. |
| 9 | Funnels analytics page | **ADD-NOW** | BE | Backend fully built (`funnels/analytics.py`); 1-line router mount. |
| 10 | Honest pacing defaults (audience+tier) | **ADD-NOW** | FE | Pure fn; protects the single DID from 486-spam. |
| 11 | Inbound post-call extraction (summary/interest/objections) | **ADD-LATER** | AI | Reuse outbound `_summarize()` Groq; inbound-safe; needs the inbound-metering unit alongside. |
| 12 | `build_system_prompt_v2` fully shipped (W1 land) | **ADD-LATER** | AI | W1 deployed v2 to the box; local disk still v1 — reconcile in the W1 follow-up, not here. |
| 13 | DID pool / rotation + 486-storm auto-rotate | **ADD-LATER** | BE | The single hardcoded DID enabled the spam-block; ~30-line env round-robin; needs a clean DID first. |
| 14 | Vobiz 10-IP allowlist fix | **ADD-LATER** | BE | Config-only; required before inbound SIP works; founder/infra step. |
| 15 | Budget cap ENFORCEMENT + `effective_limits()` wiring | **ADD-LATER** | BE | Dial-loop is earner+DID-blocked; ship as warn-only now, enforce in the OB-PROV wave (K2). |
| 16 | Run Report deep-linked page + charts | **ADD-LATER** | FE+BE | Needs a `/run/report/{jobId}` route + cost-ledger `provider` column that don't exist; surface 2-3 rows INLINE now instead (D1). |
| 17 | F4 wallet wired to calls (real per-call charge) | **ADD-LATER** | BE+DB | The invoice is flat-rate today; wiring is the real "Sarvam billed on invoice" fix (F1). |
| 18 | KB/RAG corpus populated + voice-RAG wiring | **ADD-LATER** | BE+AI | Substrate built+correct, corpus EMPTY; needs a campaign-save→ingest hook + voice path. |
| 19 | New `call_events` append-only table | **SKIP (use existing)** | DB | Immutable PG `events` leg ALREADY exists (`audit.py:100-112`) + inbound `ai_manager_sessions`/`_turns` rows — emit lifecycle events into the existing leg, don't build a 3rd surface (K1). |
| 20 | `call_cost_ledger` per-interaction table | **TRIM → ADD-LATER** | DB | Keep `provider`/`configured_provider`/`model`/`cost_paise` (the lock query); DROP per-row FX-milli/sub-paise precision until real money moves (D3); wallet not wired yet. |
| 21 | `thread_key` memory-hook column | **SKIP-here** | DB | Add it IN the memory wave when its schema is known; premature forward-compat (D4). |
| 22 | Consented-backup / mixed-vendor TTS billing | **ADD-LATER** | AI | No live multi-provider swap to consent to yet; Phase-1 = fail-visible only (D2). |
| 23 | Recording consent spoken ("yeh call record…") | **ADD-LATER** | AI | Designed not in any prompt; live compliance gap; prompt-only add. |
| 24 | TRAI NDNC national DND scrub | **ADD-LATER** | BE | Live legal exposure for promotional calls; medium ROI, Phase-2. |
| 25 | DLT / 140-series DID registration | **FOUNDER-ACTION** | — | Not code; founder must register with Vobiz. |
| 26 | DPDP delete-cascade (`DELETE /leads` → calls/transcripts/WA/memory) | **ADD-LATER** | BE+DB | Compliance gap; additive cascade; Phase-2. |
| 27 | 5-row pre-flight checklist | **TRIM → 2 rows** | FE | Keep window + balance (real gates); fold provider-lock into the banner; drop warn-only budget row (T1). |
| 28 | Geo heatmap | **SKIP** | FE | No location field on leads — the data doesn't exist. |
| 29 | Call funnel time-series / trend line | **SKIP-now** | FE | Single snapshot is enough; defer. |
| 30 | ML pickup-time / lead-scoring / A-B split UI / 6sense intent | **SKIP** | AI | Needs scale+labelled data (<5K calls/mo today); premature. |
| 31 | Eval harness (provable voice changes) | **ADD-LATER** | AI | Spec-only; high-leverage for every future voice change; MASTER_PLAN P1. |
| 32 | Inbound business-hours gate | **ADD-LATER** | BE | Inbound answers any hour; small additive gate. |
| 33 | Script versioning / rollback | **ADD-LATER** | BE+DB | Append-only `cid_versions/` dir; low-risk; after W1 lands. |

---

## 5. THE CRAZY RUN UI (additive on the existing flow — NOT the new report page yet)

> Keep the live 4-step stepper (already shipped, `app/run/_stepper.tsx`). Compose ported Core_2 primitives only, Inter Display, zero raw hex. **Over-engineering-critic verdict folded in: surface analytics INLINE, do NOT build the deep-linked Run Report page until the backend route + cost-ledger `provider` column land.**

| Step | Crazy-level addition | Build now? |
|---|---|---|
| ① Campaign & Audience | "Exclude already-called" toggle; speed-to-lead chip on hot leads | **NOW** (#6, #10) |
| ② Voice & Providers | **Provider-lock banner** (3 honest states: LIVE / CONFIG-ONLY / MISMATCH — driven by a backend `ob_prov_live` flag, default false → CONFIG-ONLY); **REAL cost breakdown** (4-row sourced table, telephony SHOWN, `ⓘ` source tooltips); preview error caption (§2) | **NOW** (after rate-card fix) |
| ③ Pacing & Handoff | Smart pacing-defaults chip (one-click apply, §1d); budget-cap field labelled "warn-only Phase-1"; window/TRAI status row | **NOW** |
| ④ Review & Launch | **2-row pre-flight** (window + balance — the real gates; T1 trim); inline post-run rows (voice used + cost-so-far + qualified) | **NOW** |
| — Run Report page | per-voice compare + CPL + provider-audit, recharts | **DEFER** (#16 — surface inline instead; build the page when `/run/report/{jobId}` + `provider` column exist) |

**Provider-lock banner states (the founder's #1 demand, made honest+visible):** LIVE (`ob_prov_live:true`) = "Sarvam will run + be billed every call"; **CONFIG-ONLY (today's truth)** = "You selected Sarvam. Voice+tier saved now. The live engine still runs ElevenLabs until the provider-lock wave ships (founder sign-off + clean DID)"; MISMATCH (Run Report only) = "⚠ configured Sarvam but EL ran on N calls." When OB-PROV ships, the banner flips to LIVE with zero UI rework.

**Cost meter dependency gate:** the breakdown is only as honest as `/tiers rate_card` → **ship the env rate-card fix (W-A) BEFORE this FE** (else it displays sourced-but-wrong numbers — the exact fury inverted). Hard sequencing gate.

**FE acceptance:** `npx tsc --noEmit` 0 errors in `app/run/**`+`lib/api.ts`; every new backend route 404'd → page renders identically to current LIVE (dormant-safe); zero raw hex (grep `#` → 0); Core_2 primitives only. **Rollback:** revert the 2 edited files + delete new files + restart famit-panel only. NO earner exposure (agent.py untouched, famit-agent never restarted).

---

## 6. PHASED, EARNER-SAFE BUILD ROADMAP

> **Iron rules (PLAYBOOK + VOICE-BRAIN-STATE):** ONE box-mutating wave at a time; inbound-first; NEVER `agent.py` without founder sign-off + a real ring (DID carrier-rested); the earner gate is `_golden/verify_golden.py` exit 0 + a FRESHLY-captured live box md5 (NOT the hardcoded `9180fabe` constant — re-baseline from the box every time) + famit-agent PID 1477083 unchanged + /health 200 + 0 5xx + NO ring. P0-LEAK is **DONE+DEPLOYED** → no shared-`caller.py` collision remains.

### QUICK-WINS FIRST (small, earner-safe, founder's two pains):

**✅ WAVE A — DONE (2026-06-14) — env billing fixes + provider-lock metering label (inbound) + funnels mount**
- `.env` on box: `USD_INR=95.2`, `EL_RATE_PER_1K_CHARS=4.76`, `SARVAM_TTS_RATE_V2_PER_10K=15`, `SARVAM_TTS_RATE_V3_PER_10K=30`. Backups `.env.Abak.20260614-073247`.
- `droplet_work/vendors/sarvam_meter.py`: v2/v3 TTS split (commit `9e18231`).
- `droplet_work/prompt.py`: pure `resolve_providers` leaf at `:148-219` (commit `ab6777c`). Golden 5/5 exit 0 before+after.
- `droplet_work/aim_voice_agent.py`: inbound wiring behind `INBOUND_PROV_LOCK` (commit `ab6777c`).
- Funnels: `build_router` already mounted in `caller.py` (token-derived tenant, 11 routes, FEATURE_FUNNELS=1 LIVE). Fix #7 PASS (body tenant_id ignored; all routes 401-without-token).
- `INBOUND_PROV_LOCK=1` set in `/etc/systemd/system/aim-voice-agent.service.d/vendor-script.conf` (alongside VENDOR_SCRIPT_INJECT=1, CTX_CACHE=1). INBOUND proc env confirmed (PID `2525014`). Earner proc ABSENT (PID `1477083`).
- EARNER GATE PASS: agent.py md5 `9150fabe…` UNCHANGED · famit-agent PID `1477083` NOT restarted · /health `{"status":"ok","checks":{"db":{"ok":true},"redis":{"ok":true},"livekit":{"ok":true}}}` · 0 5xx · NO ring.
- **Rollback:** revert `.env` lines; remove `INBOUND_PROV_LOCK=1` from drop-in; restore `*.Abak.*`.
- **NOTE (honest):** the env rates apply to INBOUND now; OUTBOUND earner only on its next founder-signed ring-wave. The lock fixes the COST-LEDGER label — the wallet INVOICE is still flat-rate `_charge_call` (GATED Wave G).

**✅ WAVE B — DONE (prior deploy agent — verified complete, commit already in history)**
- Voice preview fix was deployed in a prior wave (preview route returns `audio/mpeg` full-buffered, no `preload="none"`, real `.catch`). Marking DONE per Wave B state in ORCHESTRATOR.

**WAVE B-OPEN — voice preview fix (§2) — RESIDUAL OPEN if not yet confirmed by founder**
- **Scope:** backend full-buffer + force `audio/mpeg` + both EL hosts + 502-on-empty; FE real `.catch` + `onError` + caption, no `preload="none"`.
- **Files:** `droplet_work/caller.py` (voice-preview route only); `famit-panel/app/run/_voice-providers.tsx`.
- **Flag:** none. **Acceptance:** §2 (Chrome+Safari `200 audio/mpeg` + byte-sniff + founder's ear on EL & Sarvam). **Rollback:** restore `caller.py.PVbak` + restart `famit-caller`; restore panel backup.

**WAVE C — crazy Run UI inline upgrades + REAL cost meter (FE, after W-A rate-card)**
- **Scope:** §5 inline additions (provider-lock banner CONFIG-ONLY, sourced cost breakdown w/ telephony, exclude-called toggle, pacing-defaults chip, 2-row pre-flight, inline post-run rows, voice-compare + CPL inline).
- **Files:** `app/run/page.tsx`, `_voice-providers.tsx`, `lib/api.ts` (additive), new `_provider-lock.tsx`/`_cost-breakdown.tsx`/`_pacing-defaults.ts`.
- **Flag:** `RUN_REPORT_ENABLED` client const. **Acceptance:** §5 (tsc 0, dormant-safe, zero hex). **Rollback:** revert 2 files + delete new + restart famit-panel. NO earner exposure.

### THEN (DEFERRED — gated on DID un-rest + founder sign-off):
- **WAVE D (earner, founder-signed + ring):** OB-PROV outbound dispatch (`agent.py:556`) + per-provider `tts_chars_by_provider` metering (F8) + outbound env rates take effect on the signed restart. Gate: golden byte-diff flag-off, ring rings before+after.
- **WAVE E:** DID pool/rotation + 486-storm auto-rotate + Vobiz 10-IP allowlist (needs a clean DID).
- **WAVE F:** inbound post-call extraction (summary/interest/objections) + the inbound `record_usage_event` emission unit (F10) → makes the inbound provider-lock a real bill.
- **WAVE G:** F4 wallet wired to calls (F1 — the real invoice fix) + `call_cost_ledger` trimmed table (provider/configured/model/cost_paise) + budget-cap enforcement.
- **WAVE H:** compliance (recording-consent prompt, NDNC scrub, DPDP cascade); Run Report page + cost-ledger `provider` column; eval harness; KB corpus + voice-RAG.

---

## 7. KEY FILE:LINE MASTER REFERENCE (live box ground truth, 2026-06-14)

| Concern | Location |
|---|---|
| Preview EL redirect (the bug) | `droplet_work/caller.py:3716` `return RedirectResponse(pu)` |
| Preview Sarvam FileResponse (works, the model) | `caller.py:3704-3706` (`.wav`; docstring `:3679` wrongly says `.mp3`) |
| Preview client black-hole catch | `famit-panel/app/run/_voice-providers.tsx:228-230` |
| Preview `<audio>` missing onError | `_voice-providers.tsx:328-333` |
| Provider-lock TTS hardwired (earner) | `droplet_work/agent.py:556` |
| Metering unconditional vendor=el | `agent.py:489-531`, char counter `:735` |
| **The REAL charge ignores vendor** | `caller.py:2537 _call_cost`, `:2544 _charge_call`, decrements `:2570` |
| USD_INR=1 bug | `agent.py:72` + `vendors/groq_meter.py` |
| Sarvam single TTS rate | `vendors/sarvam_meter.py:14` |
| tiers.py fictional figures | `llm_router/tiers.py:55` (telephony ₹0), `:70/81/92` (est_inr_per_min) |
| resolver lands here (pure leaf) | `droplet_work/prompt.py` (`build_system_prompt` at `:253`) |
| Inbound TTS construct + slog | `aim_voice_agent.py:385 _build_tts`, `:2307`, `:2652 _slog.start` |
| Immutable events leg ALREADY exists | `droplet_work/audit.py:100-112` |
| Inbound session rows ALREADY stored | `aim_voice_agent.py:1836-1837,1974` |
| budget_cap stored, unenforced | `caller.py:3900-3907` |
| **EARNER GATE (the REAL one)** | `droplet_work/_golden/verify_golden.py` exit 0 + fresh box md5 (NOT a constant) + PID 1477083 + /health 200 |

**Pricing sources:** [Sarvam](https://docs.sarvam.ai/api-reference-docs/pricing) · [Groq](https://www.cloudzero.com/blog/groq-pricing/) · [ElevenLabs](https://elevenlabs.io/pricing) · [Vobiz docs — NO rate](https://docs.vobiz.ai/introduction) · [Ringg](https://www.ringg.ai/pricing) · [Retell](https://www.retellai.com/blog/ai-voice-agent-pricing-full-cost-breakdown-platform-comparison-roi-analysis) · [Ringlyn 2026](https://www.ringlyn.com/blog/ai-voice-agent-pricing-per-minute-2026/) · USD/INR Fed H.10 June-2026 ₹95.2. All fetched 2026-06-14.
