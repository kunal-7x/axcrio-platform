# ROUND-6 BACKEND (famit-caller ONLY) — DEPLOYED 2026-06-20 ~00:45 UTC — earner untouched

Box `famit@168.144.153.145` /opt/famit-agent. Deploy = **famit-caller restart ONLY**.
THE LAW honored: agent.py md5 `e353b775` UNCHANGED start→end; famit-agent NEVER restarted, active.

## Deployed md5s
- caller.py: `3b1e26c6` (baseline) → **`70d0fa0e`**
- ai_manager/endpoints.py: `7c2ce93f` (baseline) → **`7686219c`**
- registry.py: UNCHANGED (used existing `verified=` kwarg)
- agent.py: `e353b775` (UNCHANGED — was c33c03e2 per EARNER-LIVE-STATE; a parallel session
  advanced it to e353b775 BEFORE my deploy; my invariant = unchanged across MY deploy ✓)

## Backups on box (TS=20260620-004245)
- `caller.py.R6BEbak.20260620-004245`
- `ai_manager/endpoints.py.R6BEbak.20260620-004245`

## Per-item (all curl-proven over real HTTP)
- **B1 add-number** — FIX: register_number auto-verifies admin/tenant-added numbers (`verified=True`,
  flag AIM_AUTO_VERIFY default 1). PROOF: POST /ai-manager/numbers → verified:True/auto_verified:True/
  active; GET shows verified:True → routes inbound.
- **B2 PIN-422** — already correct on-box (dict Body, ignores `admin`). PROOF: pin/set {user_id,pin,admin}
  → HTTP 200 {ok:true}.
- **B3 Try-it real chatbot** — _aim_llm_answer (P4) + R6 DURABLE DB FALLBACK in _aim_live_snapshot so it
  reads the flat-file leads/CALLS when the W14 reporting store is empty. PROOF: "show me hot leads" →
  "3 hot leads… Kunal Kumar score 100…" (REAL data, Hinglish, no jargon); WRITE "call all hot leads" →
  action:write/eliciting (deterministic confirm, NOT executed); 0 jargon leaks.
- **B4 callback over-scheduling** — FIX: legacy + recon cb branch honor `callback_at` ONLY when genuine
  (callback_raw present OR outcome==callback) AND never on terminal-good (booked/converted/opt_out).
  Flag CALLBACK_REQUIRE_EXPLICIT default 1. W10 smart path dormant (CALLBACK_CADENCE_ENABLED unset).
  PROOF: completed/converted/booked + spurious cb ⇒ NO schedule; genuine user ask / outcome=callback ⇒
  schedule. (legacy ≤2-retry cap unchanged.)
- **B5 recording read-model** — has_recording served (pre-existing). PROOF: /contacts/{ph}/recordings →
  32 recs, 18 has_recording, key present. (the 2-3s reload is FE F2.)
- **B6 dashboard temperature empty** — ROOT CAUSE: W14 reporting store empty (stream-hydrated only) even
  though /calls + /leads have data. FIX: _enrich_report_temperature falls back to the durable flat-file
  leads (_leads_for, same RC2 bands) for BOTH temperature_distribution AND hot_leads when reporting bands
  sum 0. PROOF: /report?preset=all → temp {hot:3,cold:1} (was all-0), hot_leads:3 real.
- **B7 conversion_prob 8000** — ROOT CAUSE: caller.py:181 emitted raw `interest` (0-100) where every other
  emit is a 0-1 fraction. FIX: _conv_prob_frac/_conv_prob_pct helpers (clamp [0,1]/[0,100]); line 181 +
  enrich block normalized. PROOF: hot_leads cp = 1.0/0.8/0.8 (ALL ≤1), score ≤100.
- **B8 per-vendor spend incl Vobiz** — FIX: (a) _telephony_rate_per_min defaults ₹0.60/min
  (TELEPHONY_RATE_PER_MIN_DEFAULT) when admin rate unset (was 0 → ₹0 telephony); (b) _cost_rows_for lazily
  rebuilds the cost ledger (throttled 120s, COST_LAZY_REBUILD). PROOF: /billing/vendors → vobiz ₹224.71,
  elevenlabs ₹264.59, groq ₹12.46, sarvam ₹102.30 (vobiz was 0).
- **B9 DYNAMIC permissions** — FIX: _NAV_REGISTRY (mirrors famit-panel/lib/api.ts FEATURE_REGISTRY) +
  _nav_registry_sync() additively seeds missing nav keys into var/control/registry.json at startup + on
  /admin/features; new POST /admin/features/sync-nav. EARNER-SAFE add-only, default_mode "on". PROOF:
  registry 91→104, mod.revenue_tools + sell.leads.export added (were missing → module HIDE never worked);
  /admin/features serves 104 incl mod.revenue_tools; re-sync idempotent (0 added 2nd run).
- **B10 profile persistence** — BUILT: PUT /me (whitelisted name/display_name/photo_url/avatar_url/phone/
  title/company/timezone/locale/bio onto the caller's OWN tenant row, store-lock, token-scoped); GET /me
  now returns `profile{}`. PROOF: PUT name/title/photo → GET reads them back.

## Flags / knobs (all default-on, no redeploy to toggle)
AIM_AUTO_VERIFY=1 · CALLBACK_REQUIRE_EXPLICIT=1 · TELEPHONY_RATE_PER_MIN_DEFAULT=0.60 ·
COST_LAZY_REBUILD=1 · NAV_REGISTRY_SYNC=1 · AIM_TRYIT_LLM=1

## ROLLBACK (famit-caller only; earner never involved)
ssh … 'cd /opt/famit-agent && cp caller.py.R6BEbak.20260620-004245 caller.py && cp
ai_manager/endpoints.py.R6BEbak.20260620-004245 ai_manager/endpoints.py && sudo systemctl restart famit-caller'
Granular: set any flag above =0 (no behavior-restart). registry.json nav_sync rows are additive/harmless.

## Residual / handoff
- agent.py is now e353b775 (a parallel session changed it from c33c03e2); I did not touch it.
- One R6 test number (num_c51547947731 +919900112233) + test PIN remain on admin tenant (no clean DELETE
  route) — harmless.
- /billing/vendor/{vid} detail shaper uses `total`/series keys (FE-side), authoritative per-vendor cost
  is in /billing/vendors (correct).
- NOT git-committed (Ship does that). Tracked file = droplet_work/caller.py; endpoints.py is gitignored.
