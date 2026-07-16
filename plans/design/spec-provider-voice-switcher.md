# SPEC — Per-campaign Provider + Voice Switcher (with free real-time preview + custom providers)

Decision-ready architecture (from read-only research, 2026-06-13). Build AFTER the resilience + handoff + ModelScope-image waves. Reuse-heavy; one box-mutating wave at a time; earner-gated.

## Load-bearing constraint (agent.py = the sacred earner)
Live `agent.py` (`/opt/famit-agent/agent.py`, md5 `9150fabe4ff62b4b4470f9a87df346e5`) builds the pipeline at entrypoint:
- **Voice** is ALREADY per-campaign: reads `fields.voice_id` (agent.py:485) → **switching voice within ElevenLabs needs ZERO agent.py change.**
- **STT/LLM/TTS PROVIDER** are hardcoded plugin constructors (`sarvam.STT` :510, `groq.LLM` :520, `elevenlabs.TTS` :485) → **switching the provider on OUTBOUND requires editing agent.py.**
- NOTE: local mirror `droplet_work/agent.py` is STALE (md5 `1a154ea…`) — trust the BOX for earner facts.

## Phase split
**PHASE 1 — SAFE, no earner touch (build first):** per-campaign voice + free preview + per-campaign config + custom-provider CRUD + the dashboard UI. Additive routes in `caller.py` + `llm_router` + frontend only.
**PHASE 2 — OB-PROV, GATED (separate, founder-approved):** edit agent.py to honor `fields.{stt,llm,tts}_provider` on OUTBOUND. Live revenue path → requires: founder sign-off; a `_build_pipeline(fields)` helper that is additive + DEFAULT-IDENTICAL (unset → byte-identical to today); a REAL in-window outbound ring-gate before+after (a ring = `inviteToRingingMs` in the livekit-sip log; needs Vobiz funded); agent.py md5 baseline + never-restart `famit-agent`. Inbound (`aim_voice_agent.py`) is safer to prototype but has no campaign.

## Free voice preview (no token burn)
- **ElevenLabs** `GET /v1/voices` returns `preview_url` (public GCS MP3) for all 26 voices — FREE. The existing `caller.py:/voices` route STRIPS it → un-strip = 1 line.
- **Sarvam (caveat — differs from assumption):** fixed speaker catalogue (v2: 7 names anushka/manisha/vidya/arya/abhilash/karun/hitesh; v3: ~39), selected by `speaker` string (NOT a voice_id), and **NO per-voice preview URL via API**. → pre-host a tiny one-time-generated sample set on the box (`var/voice_samples/sarvam/<speaker>.mp3`, super-admin generates once, ~1 short synth each), served via a proxy. No ongoing burn.
- **Proxy:** `GET /voice-preview?provider=&id=` → ElevenLabs streams/redirects its `preview_url`; Sarvam serves the pre-hosted clip. The panel `<audio>` Play button hits this.

## Backend (Phase 1 — caller.py additive + llm_router additive; agent.py untouched)
- B1 `GET /voices?provider=` → ElevenLabs `{voice_id,name,preview_url,accent,gender}` (un-strip); Sarvam static catalogue + `sample_url`.
- B2 `GET /voice-preview?provider=&id=` → proxy (above).
- B3 `GET /providers` → usable providers per role (built-in + custom), `kind` (stt/llm/tts) + `available` (≥1 live key). Reuse `key_store.list_all_masked()` + pool `available_count()`.
- B4 Custom-provider CRUD → extend `/admin/provider-keys*` (super-admin-gated, legacy-pw excluded, Fernet store) to accept `{kind, base_url, model}` for a new `custom` key-store section; `_PROVIDERS` becomes dynamic (built-ins + custom). Custom LLM works immediately (OpenAI-compatible base_url via `PoolLLM`); custom STT/TTS only if API-compatible (and OUTBOUND-gated behind OB-PROV).
- B5 Per-campaign persistence = NO new route — extend the `fields` object via existing `POST /campaigns/{cid}` (already writes voice_id) with `voice_id` + (later) `stt/llm/tts_provider`, `custom_provider_id`; add validation (voice exists for provider; provider has a live key).

## Frontend (Phase 1 — premium Core_2; sequence the panel deploy after other panel waves)
- F1 `lib/api.ts`: extend `Voice` (preview_url/accent/gender); add `getVoices(provider)`, `getProviders()`, `voicePreviewUrl()`; extend campaign fields typing. (most fns already exist — extend.)
- F2 Run page (`app/run/page.tsx`, already scroll-left/content-right Core_2 rail): NEW left-rail card **"Voice & Providers"** — 3 `<Select>` (STT/LLM/TTS provider from `getProviders()`, custom appears automatically) + a **Voice dropdown** = scrollable rows `[avatar] name · accent` + a **Play** button driving one shared `<audio>` at `voicePreviewUrl()`. Writes to campaign fields → `saveCampaign`. Dormant-safe. (Icon registry has no `play`/`speaker` — use a small inline triangle / `chevron`.)
- F3 Custom-provider UI → extend `/super-admin/api-keys` (Card grid + masked add-modal + Switch + 5s status dot) with an **"Add custom provider"** card (`name + kind + base_url + model + key`).

## Reuse map
REUSE: `caller.py:/voices` (+`/campaigns/{cid}` write, already writes voice_id), `llm_router/{key_store,provider_pool,pool_llm}` + `/admin/provider-keys*` + the API-Keys page, the Run-page Core_2 layout, ElevenLabs free preview_url, hot-reload pool + existing streaming. NEW: `/voice-preview` proxy, Sarvam pre-hosted samples, key-store `custom` section (kind/base_url/model), the "Voice & Providers" card, the custom-provider UI variant. OUTBOUND provider-honor = OB-PROV (Phase 2, gated).

---

## Lean<->Premium tier system + premium features

Decision-ready DEEPENING (read-only research + design, 2026-06-13). Goal per the founder: a **LEAN <-> PREMIUM** control for OUTBOUND calls where Lean = Sarvam (cheap) and Premium = ElevenLabs (premium) across BOTH STT and TTS, real-time, with a live ₹/min cost meter — the vendor feels fully in control of cost-vs-quality, like a big-company product. This section adds the tier model, the cost meter, an "impress" feature set (P1/P2) the founder did NOT ask for, and the Phase-1-safe vs OB-PROV reconciliation. **Conflict-free / agent.py-untouched: confirmed — every Phase-1 item below is additive (caller.py routes, llm_router config, frontend) and the only thing that needs the gated agent.py edit is the OUTBOUND STT/TTS PROVIDER swap, exactly the OB-PROV unit already defined above. The tier UI, the cost meter, the recommended-tier engine, budgets, A/B, voice features and provider-health are all Phase-1-safe.**

### 0. Research grounding (per-component cost / latency / quality — cite below)
All ₹ are list rates; the live wallet meters actuals. Conversation feel breaks above ~800 ms round-trip [Retell/softcery], so every tier is engineered to keep the TTS+LLM hot-path inside that budget.

| Role | LEAN (cheap) | STANDARD (balanced) | PREMIUM (best) |
|---|---|---|---|
| **STT** | Sarvam Saarika/Saaras `₹30/hr` = **₹0.50/min** (`$0.000092/s`) | Sarvam (same) | (Phase-2) premium STT if added; default keep Sarvam — STT quality gap is small for Indian-language phone audio, so Premium spends its budget on TTS, not STT |
| **TTS** | Sarvam Bulbul v2 `₹15 / 10K chars` (`₹1.5/1K`) | Sarvam Bulbul v3 `₹30 / 10K chars` (`₹3/1K`) | ElevenLabs **Flash v2.5** `~$0.05/1K chars` (~`₹4.2/1K`) — the *recommended low-latency model for live agents*, ~75 ms synth latency, 32 langs [ElevenLabs] (NOT v2/v3 Multilingual at `$0.10/1K` — those have higher first-token latency and are excluded from ElevenLabs' own Agents platform) |
| **LLM** | Groq `gpt-oss-20B`/`Llama-3.1-8B` (`~$0.05-0.15`/M in, 680-910 t/s, ~0.7-0.8 s TTFT) | Groq `Llama-3.3-70B` (`$0.59/M` in / `$0.79` out, 280-394 t/s) | Groq `Llama-3.3-70B` / `Kimi-K2` (premium reasoning) — same fast pool, picks the smarter model |
| **STT+LLM+TTS combined ~₹/min** (≈150 spoken words/min ≈ 900 TTS chars + ~1.2K LLM tokens) | **≈ ₹0.5 (STT) + ₹0.1 (LLM) + ₹0.14 (Bulbul v2 TTS) ≈ ₹0.75/min** | **≈ ₹0.5 + ₹0.5 + ₹0.27 ≈ ₹1.3/min** | **≈ ₹0.5 + ₹0.7 + ₹0.38 (EL Flash) ≈ ₹1.6/min** + per-min telephony (Vobiz, constant across tiers) |

Headline framing for the UI: **"Premium costs roughly 2x Lean per voice-minute — about ₹0.8 extra on a typical 1-minute call — for studio-grade ElevenLabs voice + the smartest model."** (Real money is dominated by Vobiz telephony, which is tier-independent — surface that honestly so the tier choice looks like the modest delta it is.)

### 1. The slider -> tier model (ONE control, 3 presets, Advanced override)
A single horizontal **LEAN — STANDARD — PREMIUM** segmented slider (3 stops, not a continuous drag — discrete presets read as a "product", a free drag reads as a toy and creates infinite untested combos). Names chosen against the SaaS "good/better/best" convention [Maxio/Schematic]; we use **Lean / Standard / Premium** (clear, on-brand, avoids the cheap-sounding "Basic").

Each stop is a named **preset bundle** that resolves to a concrete `{stt, llm, tts}` provider+model+voice triple:

```
LEAN     = { stt: sarvam/saarika, llm: groq/gpt-oss-20b,    tts: sarvam/bulbul-v2,  voice: <lean default speaker> }
STANDARD = { stt: sarvam/saarika, llm: groq/llama-3.3-70b,  tts: sarvam/bulbul-v3,  voice: <std default speaker>  }
PREMIUM  = { stt: sarvam/saarika, llm: groq/llama-3.3-70b,  tts: elevenlabs/flash-v2.5, voice: <premium EL voice> }
```

Presets live in a single source-of-truth config (`llm_router/tiers.py` Phase-1 additive, mirrored to a `GET /tiers` route) so the mapping is data, not code scattered across UI. Moving the slider writes ONE field to the campaign `fields`: `tier: "lean"|"standard"|"premium"` (plus, when Advanced is used, an explicit `{stt,llm,tts}_provider` + `voice_id` that OVERRIDES the preset). The campaign stores the tier name AND the resolved triple snapshot (so a later tier-config change never silently rewrites an in-flight campaign).

**Advanced mode** = a disclosure ("Advanced: choose each component") that expands the existing 3 per-role `<Select>` + Voice dropdown from F2. Picking the slider auto-fills those selects; touching a select flips the campaign to `tier:"custom"` and shows a subtle "Custom mix" chip. This is the big-company pattern: a simple slider for 95% of users, full manual control underneath for power users — exactly how cloud consoles expose instance "presets vs custom".

### 2. Live per-call cost meter + quality/latency indicator (THE hero, P1, Phase-1-safe)
Beneath the slider, a **live estimate strip** that recomputes instantly as the slider/selects change (pure client-side math from the `/tiers` rate card — no call placed, zero burn):
- **₹/min badge** (big number) — the combined STT+LLM+TTS estimate for the chosen mix, computed from the rate table in §0, shown as "≈ ₹1.6/voice-min".
- **Projected campaign spend** — `₹/min × est. avg call length (default 1.5 min, editable) × #leads in the campaign` -> "≈ ₹190 for 80 leads". This is the line that makes a vendor feel in control.
- **Quality badge** — Lean = "Good", Standard = "Great", Premium = "Studio" (token-toned pill); plus a **latency dot** (green "<800 ms, natural" for all three since we engineer inside budget; amber if a chosen custom mix uses a high-TTFT model like EL v3).
- **Savings-vs-Premium line** when not on Premium — "You're saving ~₹0.85/min vs Premium" (loss-aversion framing that still feels honest).
- **Telephony honesty footnote** — "+ ~₹X/min carrier (same on every tier)" so the vendor sees the tier delta is small relative to the call cost. All numbers are estimates labelled "≈"; the wallet shows the real charge.

### 3. Impressive features the founder did NOT ask for (curated, buildable on THIS stack)
Marked **P1** (build with the tier system) / **P2** (fast-follow). Each is grounded in components that already exist (key_store, provider_pool `available_count`, wallet, audit, the Run-page Core_2 rail, ElevenLabs free `preview_url`).

1. **Live cost meter + projected campaign spend** — §2. **P1.** The single most "big-company" feature; pure client math, zero risk.
2. **"Recommended tier" engine** — a quiet "Recommended for this campaign" badge on one stop, chosen from cheap heuristics already on hand: lead count (big list -> nudge Lean to protect budget), language (regional Indian language with weak EL coverage -> nudge Sarvam/Standard), wallet balance (low -> Lean), and goal if known (high-ticket/booking -> Premium). **P1** (heuristic) — feels like the product is advising you, the #1 "premium" perception lever.
3. **Cost guardrails / per-campaign budget cap** — optional "Stop campaign if spend exceeds ₹___" + a soft "warn at 80%". Enforced by the EXISTING wallet ledger + run_job's per-call charge loop (a pre-call balance/cap check is additive in caller.py `run_job`, NOT agent.py). **P1 for the warn/estimate; P2 for the hard auto-pause** (touches run_job; isolate + regression-gate, still NOT agent.py).
4. **A/B voice/tier test** — split a campaign's leads (e.g. 50/50 Lean-Sarvam vs Premium-ElevenLabs), then compare answer-rate / talk-time / booking-rate per arm from the existing call-outcome data. Makes the cost-vs-quality tradeoff *measurable*, not a guess. **P2** (needs run_job arm-tagging + a small results view; outbound provider swap = OB-PROV).
5. **Per-tier quality badges + sample-on-tier** — each slider stop carries its quality pill AND a Play button that previews the *tier's actual voice* via the free `preview_url` / pre-hosted Sarvam sample proxy (B2). "Hear the difference" before you spend. **P1** (rides the existing preview proxy).
6. **Real-time provider health / failover indicator** — a small status row "ElevenLabs ✓ · Groq ✓ · Sarvam ✓" driven by `provider_pool.available_count()` / the existing 5 s status dot. If Premium's TTS provider has zero live keys, the Premium stop shows "needs an ElevenLabs key" and the recommender steps down. Mirrors the API-Keys page dots. **P1.**
7. **Graceful auto-downgrade on provider outage** — if mid-campaign ElevenLabs keys all cool down, the FallbackAdapter pattern already in the LLM pool is extended conceptually to TTS: log + (optionally) fall back to Sarvam so the campaign never dies silently, surfaced as a banner "Premium TTS unavailable — running on Standard voice". **P2** (TTS failover = OB-PROV-adjacent, gated).
8. **Voice favorites / saved voice presets** — star a `{provider, voice_id}` (and name it, e.g. "Riya — warm Hindi") for one-click reuse across campaigns; stored in tenant brain like handoff config. **P1** (frontend + tiny brain field; no earner touch).
9. **Language-matched voice suggestion** — when the campaign language is set, auto-suggest voices that speak it well (EL accent/lang metadata + Sarvam's per-language speaker list), and grey/flag a mismatch ("this voice is English-only"). **P1** (uses the `/voices` metadata B1 already returns).
10. **Savings-vs-premium estimate** — §2 bullet; also a campaign-summary line "This campaign ran Lean and saved ~₹140 vs Premium." **P1** (math on stored tier + actual minutes).
11. **Per-call cost in the call log** — show the real ₹ each completed call cost (from the wallet transaction) next to its outcome, so the estimate is validated against reality and trust compounds. **P2** (join wallet txn to call rows).
12. **Spend-this-month vs last-month sparkline by tier** — a tiny analytics strip "You spend most on Premium voice; switching cold-lead campaigns to Lean would save ~₹X/mo." **P2.**

### 4. Reconciliation with Phase 1 (safe) vs Phase 2 (OB-PROV gated)
- **Phase-1-safe (build with the switcher, NO agent.py):** the slider + 3 tier presets + Advanced override UI; `/tiers` rate-card route + `tiers.py` config; the live cost meter + projected spend + savings line (§2); per-tier quality badges + sample play (rides B2 preview proxy); recommended-tier heuristic; provider-health indicator (rides `available_count`); voice favorites; language-matched suggestion; budget *estimate/warn*; per-campaign `tier` persistence via the existing `POST /campaigns/{cid}` fields write. **Within ElevenLabs, switching voice is already honored by agent.py:485 (`fields.voice_id`) — so a Premium-tier voice change is live TODAY with zero agent.py edit.**
- **Phase-2 OB-PROV (GATED, founder sign-off, ring-gate before+after, agent.py md5 baseline, never-restart `famit-agent`):** actually honoring `tts_provider=elevenlabs` vs `sarvam` (and STT/LLM provider) on the OUTBOUND leg — i.e. making the Lean/Premium *provider* swap take effect on a real call. This is precisely the OB-PROV unit already specified: an additive `_build_pipeline(fields)` helper that is DEFAULT-IDENTICAL (tier unset / `lean`-equals-today -> byte-identical pipeline), reading `fields.tier` -> resolved triple. The hard auto-pause budget cap (§3.3) and TTS auto-downgrade (§3.7) and A/B arm-tagging (§3.4) also live here (they touch run_job/the dial loop, still NOT the agent constructor — keep them in caller.py where possible).
- **Net:** the founder sees the FULL premium UI (slider, cost meter, badges, recommender, favorites) shipped SAFE in Phase 1; the single thing that waits for the gated OB-PROV unit is the moment the *outbound provider actually flips* — and even then, choosing a different ElevenLabs voice already works today. So the experience is ~90% deliverable without touching the earner.

### 5. Build-plan delta (additive to the Phase-1/Phase-2 split above)
- **B6 (Phase 1)** `GET /tiers` -> the rate card + the 3 preset triples + per-component ₹ rates (from `tiers.py`); single source of truth the UI reads for both the slider mapping AND the cost-meter math.
- **B7 (Phase 1)** extend `POST /campaigns/{cid}` validation to accept `tier` + optional `budget_cap_inr` + `est_avg_call_min`; persist the resolved triple snapshot alongside the tier name.
- **F4 (Phase 1)** Run-page "Voice & Providers" card gains the **LEAN/STANDARD/PREMIUM segmented slider** on top, the live **cost-meter strip** (₹/min + projected spend + quality pill + latency dot + savings line), the **Recommended** badge, the **provider-health** row, **voice favorites** (star), and the **Advanced** disclosure wrapping the existing 3 selects + voice dropdown. All token-pure Core_2; Icon registry has no `slider`/`star` -> compose the segmented control from `Button`/`Badge`, use `check-circle-fill` for the recommended tick and an inline outline star or `plus`-style affordance for favorites (grep the registry first, like prior waves).
- **F5 (Phase 1)** API-Keys page already surfaces provider health; add a tiny "Tiers" read-only card showing which tier each provider powers, so the super-admin sees the cost/quality map at a glance.
- **Phase-2 OB-PROV** absorbs: outbound provider flip via `_build_pipeline(fields.tier)`, hard budget auto-pause in run_job, A/B arm-tagging + results, TTS auto-downgrade failover. ALL gated, regression-ringed, default-identical.

### 6. Sources (research)
- Sarvam pricing (STT ₹30/hr, Bulbul v2 ₹15/10K, Bulbul v3 ₹30/10K, Sarvam LLM/translate): https://docs.sarvam.ai/api-reference-docs/pricing , https://www.sarvam.ai/api-pricing
- ElevenLabs pricing (Flash/Turbo $0.05/1K vs Multilingual v2/v3 $0.10/1K; credits): https://elevenlabs.io/pricing/api , https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/
- ElevenLabs Flash v2.5 (~75 ms, recommended for live agents, 32 langs): https://elevenlabs.io/blog/meet-flash , https://elevenlabs.io/docs/overview/models
- Groq pricing/latency (gpt-oss-20B 680-910 t/s; Llama-3.3-70B $0.59/$0.79, 280-394 t/s; gpt-oss-120B $0.15/$0.60, 0.74 s TTFT): https://www.cloudzero.com/blog/groq-pricing/ , https://artificialanalysis.ai/providers/groq
- SambaNova (OpenAI-compatible fallback, Llama-3.3-70B ~282-430 t/s, <200 ms TTFT class): https://artificialanalysis.ai/providers/sambanova , https://deploybase.ai/articles/sambanova-pricing-breakdown-cost-per-token-model-comparison
- Voice-AI per-minute + 800 ms naturalness threshold + per-component billing UX (Vapi/Retell/ElevenLabs): https://www.retellai.com/blog/vapi-vs-elevenlabs , https://softcery.com/ai-voice-agents-calculator , https://www.ringlyn.com/blog/ai-voice-agent-pricing-per-minute-2026/
- SaaS good/better/best 3-tier + economy/premium-economy/business framing: https://www.maxio.com/blog/tiered-pricing-examples-for-saas-businesses , https://schematichq.com/blog/the-tiered-pricing-playbook
