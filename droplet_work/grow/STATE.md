# Haptica Grow — module STATE

> Branch `feat/haptica-grow`. The autonomous **Ad → Lead → AI-qualify → SCORE →
> conversion-signal-back-to-Meta/Google** loop ("ElevateX / Growth-OS"), built as an
> ADDITIVE, FLAG-GATED module inside the modular monolith. The earner (`agent.py`) is
> never touched. Master design: `plans/GROWTH-OS-BUILD-SPEC.md`. Validation +
> phasing: the ElevateX docs (acquisition→qualification→feedback supply chain).

## Why this module exists (the moat)
Platforms optimize toward whatever conversion events you feed them. Every competitor
feeds them junk ("lead submitted"). We own the **voice-call + WhatsApp + booking + sale
ground truth** and feed it back as Conversions-API events with **value = lead-quality
score**, so Meta/Google hunt for people who *answer calls and buy*. (GROWTH-OS §11 /
ElevateX §5.) That feedback loop is the single highest-leverage, un-buyable piece —
so it is W1.

## W1 — Revenue-Truth Signal-Loop core  ✅ BACKEND GREEN (offline)
| file | role |
|---|---|
| `model.py` | canonical records/enums + event taxonomy + 2 hashes (unsalted `capi_hash` for platform match keys vs salted `principal_ref` at-rest, PII-min) |
| `config.py` | `GrowConfig.from_env()` — `FEATURE_GROW` gate + CAPI creds; **SHADOW by default** |
| `scoring.py` | **L5** transparent heuristic v1 (real-estate pack) → score 0-100 + tier hot/warm/investor/end_user/junk + reasons[] + confidence; features stored for v2 |
| `signals.py` | **L7 ★flagship** CAPI/Enhanced-Conversions dispatcher — event ladder (Lead→QualifiedLead→Schedule→Attended→Purchase), `event_id=sha256(journey\|step)` dedup, EMQ estimate, **shadow-safe** |
| `store.py` | FORCE-RLS facade (InMemory + lazy Pg) for scores/signals/journeys |
| `loop.py` | `GrowLoop` orchestrator + process singleton; the fire-and-forget `on_call_outcome/on_booking/on_sale` hooks (never raise into the call path) |
| `endpoints.py` | `build_router(resolve_tenant, can, need_auth, forbidden, …)` → `/grow/*` (token-derived tenant) |
| `db/ddl_grow.sql` | FORCE-RLS schema (grow_journeys / grow_lead_scores / grow_signals_log), org_id + admin-GUC RLS, append-only signals |
| `tests/` | 24 offline tests (11 scoring + 13 signals/loop), self-running, no net/creds |

**Acceptance (met):** `python -m grow.tests.test_scoring` + `test_signals` → PASS;
a HOT lead fires `Lead` + `QualifiedLead` CAPI events in SHADOW (logged payload, no POST,
hashed match-keys only, value=score); Signal Health card computes EMQ/dedup/ladder.

## Safety posture
- `FEATURE_GROW=0` default ⇒ router NOT mounted ⇒ byte-identical resting.
- Signals **shadow** until `GROW_SIGNALS_LIVE=1` + `META_CAPI_PIXEL_ID`/`META_CAPI_TOKEN`
  (founder-gated Meta CAPI creds). Until then it logs the would-send — zero live risk.
- agent.py untouched (md5 unchanged). caller.py change is additive + flag-gated only.
- Tenant always token-derived (no body-tenant hole). PII-min: raw phone/email never at
  rest; only salted `principal_ref` + masked tail; ledger holds match-key TYPES only.

## Wiring (W1b)  ✅
- Mount in `caller.py` behind `FEATURE_GROW` via `build_router` (see the module-mount block).
- One flag-gated, off-event-loop line at `_finalize_call` emits the call outcome into
  `grow.on_call_outcome` (never raises into the call path). caller.py +62 lines, additive only.

## Frontend (W1d)  ✅  — commit 8b9746d
- `famit-panel/app/grow/page.tsx` + colocated `_lib.ts` (dormant-safe `ReadResult` client,
  mirrors app/ads/_lib.ts). Tabs: Scored leads (tier badges + score + confidence + why
  chips + sales-ready), Signal ledger (Signal Health card + CAPI dispatch ledger), Try-it
  scorer (operator console, no persist/dispatch). Mode banner shadow/live. Registered
  `grow.signal_loop → /grow` under `mod.grow`. `tsc --noEmit` = 0 errors. No caller.py touch.

## W2 — L3 Speed-to-Lead orchestrator  ✅ BACKEND GREEN (offline)
The "60-second call" mechanism, honest (ElevateX §1): a consent-clean captured lead →
compliance preflight gate → fire WhatsApp + AI call in parallel, journey-threaded, with
capture→fire latency + <60s SLA recorded. The qualified call outcome then flows back into
the W1 scoring + CAPI loop — closing the loop.
| file | role |
|---|---|
| `orchestrator.py` | `Orchestrator.orchestrate(CapturedLead)` — SEAM-BASED: compliance gate + WhatsApp sender + voice caller are INJECTED. Defaults dormant-safe (compliance=unenforced when the engine is off; channels=skipped_no_config until wired). `make_compliance_gate()` auto-binds voice_ops.compliance.ComplianceEngine when COMPLIANCE_ENABLED. Never raises. |
| `model.py` (+) | `CapturedLead`, `ChannelResult`/`ChannelStatus`, `Orchestration`/`OrchStatus` |
| `store.py` (+) | `OrchestrationStore` (InMemory + lazy Pg); `make_stores` now 4-tuple |
| `loop.py` (+) | `on_lead_captured(...)` + orchestrator wired into `GrowLoop` (auto compliance gate) |
| `endpoints.py` (+) | `POST /grow/ingest` (write-gated) + `GET /grow/orchestrations` |
| `db/ddl_grow.sql` (+) | `grow_orchestrations` FORCE-RLS table |
| `tests/test_orchestrator.py` | 12 offline tests (dormant, fire-when-wired, compliance-block, SLA met/missed, journey threading, bad-sender resilience) |

**Acceptance (met):** 36 grow tests pass (11+13+12); `/grow/ingest` + `/grow/orchestrations`
mount; `on_lead_captured` runs end-to-end (dormant → no_channels, sla_met). The real channel
adapters (WhatsApp Cloud API send via voice_ops.whatsapp + outbound dial) are INJECTED at
wiring time — kept out of grow so the module stays offline-testable and avoids touching the
(concurrently-edited) shared caller.py. Integration wire-up: pass `whatsapp_sender`/
`voice_caller` to `GrowLoop`, and call `grow.on_lead_captured(...)` from the L1 webhook (W3).

## W3 — L1 Acquisition (consented capture)  ✅ BACKEND GREEN (offline)
The only high-yield *legal* B2C source (ElevateX §1/§2): ad → instant pre-filled form →
consent + submit → leadgen webhook. Turns each provider payload into a canonical
`CapturedLead`, RECORDS the consent (the form opt-in is the TCCPR/DPDP shield), mints the
journey at first touch, and hands off to the W2 orchestrator. Grow-native ingress — no
coupling to the shared auto_lead/caller.
| file | role |
|---|---|
| `acquisition.py` | parsers (Meta leadgen / Google lead-form / CTWA referral → CapturedLead), `verify_meta_signature` (HMAC, fail-closed) + `verify_meta_challenge`, `make_consent_recorder()` (binds voice_ops.compliance.ConsentLedger), `AcquisitionService` (parse → consent → on_lead_captured; meta webhook page→tenant map drops unmapped pages — no cross-tenant capture) |
| `loop.py` (+) | `GrowLoop.acquisition = AcquisitionService(self)` |
| `endpoints.py` (+) | `POST /grow/acquire/{meta,google,ctwa}` (write-gated, token-derived tenant) |
| `tests/test_acquisition.py` | 12 offline tests (3 parsers, signature/challenge verify, consent recording, page→tenant mapping, unmapped-page drop) |

**Acceptance (met):** 48 grow tests pass (11+13+12+12). The full core loop is now
end-to-end: **capture (L1) → orchestrate <60s (L3) → qualify call (L4, existing) → score
(L5) → CAPI feedback (L7, shadow)**. The live unauthenticated leadgen webhook (GET verify +
POST signature) is a thin founder-gated wrapper over the built `verify_meta_*` helpers +
`ingest_meta_webhook` (needs Meta app review + page→tenant map + `GROW_META_APP_SECRET`).

## W4 — L8 ROI funnel + semantic metrics layer  ✅ BACKEND GREEN (offline)
The deck's "100% analytics", ONE definition of every KPI (GROWTH-OS §8.5). Computed live
from the data the loop produces; ₹ metrics light up the moment spend is connected.
| file | role |
|---|---|
| `metrics.py` | `GrowMetrics`: `funnel` (captured→contacted→scored→qualified→signal-qualified→booked→won + drop-offs), `tier_distribution`, `by_source`, `sla` (capture→fire p50/p95 + <60s rate), `roi` (CPL, **CPqL north-star**, cost-per-booking/won — spend INJECTED), `summary` (all-in-one) |
| `loop.py` (+) | `GrowLoop.metrics = GrowMetrics(self)` |
| `endpoints.py` (+) | `GET /grow/funnel`, `GET /grow/roi?spend_minor=`, `GET /grow/summary?spend_minor=` |
| `tests/test_metrics.py` | 9 offline tests (funnel counts, drop-off ratios, tiers, by-source, SLA, CPqL math, empty-tenant no-divide-by-zero) |

**Acceptance (met):** 57 grow tests pass (11+13+12+12+9). spend is injected (query now; the
W5 ad-connector spend feed later) so the funnel + quality metrics are fully live today.

## W5 — L7 ad-optimization brain (Budget Governor + Draft/Trash/Promote)  ✅ BACKEND GREEN
The "yours" layer (the platforms do targeting+bidding; we decide what to risk/kill/scale
against the TRUTH signal — GROWTH-OS §12/§13). Live execute is connector-gated (founder Ads
OAuth); the brain runs live + dry-run today.
| file | role |
|---|---|
| `budget.py` | `BudgetGovernor` (INTEGER paise): `admit_spend` (daily/monthly caps + Governor stamp), `is_runaway`, `detect_anomaly` (Spend Sentinel: velocity/CPM/CTR/EMQ → yellow/red), `month_forecast` (graduated throttle), `kill_switch` (pause-all) |
| `optimizer.py` | `Optimizer` Draft/Trash/Promote: Gamma–Poisson posterior on qualified-rate per ₹ + `p_cpql_exceeds_target` (math.erf, no RNG), guardrails **G1–G6** (runaway/zero-q/set-fail/junk-trap/fatigue/policy), PROMOTE (scale +20%), HOLD — each with a plain-language `Explanation` (what/evidence/effect/confidence/reversible/undo); `allocate` (bounded posterior-mean split, min-explore/max-arm) |
| `loop.py` (+) | `GrowLoop.optimizer` |
| `endpoints.py` (+) | `GET /grow/ads/health`, `POST /grow/ads/optimize` (dry-run decisions + allocation), `POST /grow/ads/budget/check` |
| `tests/` | 23 offline tests (12 optimizer G1-G6/promote/hold/allocate/posterior + 11 budget caps/runaway/anomaly/forecast/kill) |

**Acceptance (met):** 80 grow tests pass total. The brain is live; only the Meta/Google
write-path (campaign create/pause/budget) is a founder-gated connector seam (Ads OAuth).

---

## ✅ FULL CORE SYSTEM BUILT (W1–W5) — branch `feat/haptica-grow` on origin
**L1** capture (Meta/Google leadgen + CTWA + consent) → **L3** orchestrate <60s (compliance
gate + WhatsApp + AI call, journey-threaded) → **L4** qualify (existing voice agent) →
**L5** score (hot/warm/investor/end-user/junk + why) → **L7** CAPI feedback (value=score,
shadow-safe) + ad-optimization brain (Budget Governor + Draft/Trash/Promote) → **L8** ROI
funnel + CPqL. 80 offline tests, FEATURE_GROW-gated, earner-safe, PII-min, FORCE-RLS.

## W6 — DEEP WIRING into the live voice/WhatsApp infrastructure  ✅ GREEN (offline)
The seams are now REAL connections — the loop fires actual WhatsApp + AI calls on capture.
| file | role |
|---|---|
| `adapters.py` | registration seams (`register_voice_caller`/`register_whatsapp_sender`) + late-binding `live_*` adapters + a **self-contained Meta Graph WhatsApp sender** (env-cred-gated, zero caller.py needed) + `set/get_main_loop` + `status` |
| `loop.py` (+) | GrowLoop default channel seams = the live adapters (explicit seam still overrides for tests) |
| `__init__.py` (+) | `acapture()` async helper (binds the loop + runs scoring off-thread), re-exports `register_*`/`set_main_loop` |
| `auto_lead/router.py` (+) | after a real ingested lead is accepted → `await grow.acapture(...)` (FEATURE_GROW-gated, best-effort — never breaks ingest). REAL webhook leads now drive the whole loop. |
| `caller.py` (+) | registers the live `<60s` **voice dial** into Grow: builds a 1-lead speed-to-lead JOB + schedules `run_job` on the FastAPI loop via `run_coroutine_threadsafe`. Honours the TRAI window. EARNER `agent.py` untouched. |
| `tests/test_adapters.py` | 10 tests (registration, dormant-without-creds, live override, dict/str/exception wrapping, GrowLoop default = live, loop bind) |

**Acceptance (met):** 90 grow tests pass (added 10). End-to-end: a real lead POSTed to the
auto-lead webhook → `acapture` → compliance gate → real Graph WhatsApp + a real `<60s`
outbound AI call → call finalizes → scored → CAPI signal — all journey-threaded via the
deterministic journey_id. Dormant-safe: no creds / no registration → records intent, fires
nothing. caller.py change committed via HEAD-safe plumbing (patched a clean extract — the
concurrently-edited working-tree caller.py was never touched).

### To activate the deep wiring
- WhatsApp: `META_WA_TOKEN` + `META_WA_PHONE_NUMBER_ID` + `GROW_WA_WELCOME_TEMPLATE` (approved).
- Voice: automatic once `FEATURE_GROW=1` (caller.py registers the dial at mount).
- A captured lead needs a `campaign_id` (from the ad/source) for the call to use the right brain.

## W7/W8 — Famit Growth: Realtime All-Ads-Platform analysis + advisor + chat  ✅ GREEN
The Figma "Famit Growth" system: ONE normalized view across every ad platform + cross-platform
insights + AI recommendation toward the goal + a chat over the data.
| file | role |
|---|---|
| `platforms.py` | normalized `PlatformMetrics` (spend/impr/clicks/conv + derived CTR/CPC/CPM/CPI/CVR + by_location/by_device/top_ads) for Google/Facebook/Instagram/YouTube/LinkedIn/Twitter-X/TikTok; `register_platform_fetcher` seam (real APIs founder-gated); deterministic **DEMO** mode (`GROW_PLATFORMS_DEMO=1`) so the dashboard renders now; `AdsAggregator` (totals, averages, cheapest/best platform, same-type-ad overlap) |
| `advisor.py` | `recommend(snapshot, goal)` — ranked plain-language recs toward min_cost/max_conversions/max_reach (reuses W5 `optimizer.allocate` across platforms-as-arms) + `chat(snapshot, question)` — deterministic NL Q&A over the data (LLM narrative is an optional seam) |
| `endpoints.py` (+) | `GET /grow/platforms`, `/grow/platforms/config`, `/grow/platforms/{p}`, `POST /grow/advisor/recommend`, `/grow/advisor/chat` (token-derived tenant) |
| `tests/test_platforms.py` | 15 tests (derived metrics, demo determinism, live fetcher, aggregator insights, recommend min_cost/max_conv/diversify, chat cheapest/spend/recommend/ctr/fallback) |

**Acceptance (met):** 105 grow tests pass. With `GROW_PLATFORMS_DEMO=1` the whole dashboard
renders realistic cross-platform metrics + insights + working chat immediately; real platforms
go live as each `register_platform_fetcher(<platform>, fn)` is wired (founder Ads OAuth).
Env: `GROW_PLATFORMS_DEMO=0|1`.

### Founder-gated to go LIVE (build done; needs creds/integration)
- **CAPI live:** `META_CAPI_PIXEL_ID`+`META_CAPI_TOKEN` + `GROW_SIGNALS_LIVE=1` (else shadow).
- **Leadgen webhook:** Meta app review + page→tenant map + `GROW_META_APP_SECRET` (wrap the built `verify_meta_*` + `ingest_meta_webhook`).
- **Channel adapters (L3):** inject `whatsapp_sender` (voice_ops.whatsapp) + `voice_caller` (caller dial) into `GrowLoop` — kept out of grow to avoid the shared caller.py.
- **Ad execute (L7):** Meta/Google Ads OAuth + a connector to apply optimizer decisions.
- **Postgres:** apply `db/ddl_grow.sql` + `GROW_USE_PG=1` (else InMemory).
- **W4** L8 ROI funnel dashboard + Signal Health UI (frontend control surface).
- **W5** L7 ad-optimization engine (Meta/Google connector + rules + Thompson bandit + Budget Governor) — founder-gated on Ads OAuth.

## Env reference (add to .env.example when wiring)
```
FEATURE_GROW=0                 # mount the /grow/* surface + finalize hook
GROW_PACK=real_estate
GROW_HOT_THRESHOLD=70  GROW_WARM_THRESHOLD=40  GROW_JUNK_THRESHOLD=25
GROW_HASH_SALT=<salt>          # at-rest PII-min (falls back to COMPLIANCE_HASH_SALT)
GROW_USE_PG=0                  # bind the FORCE-RLS Pg backends (needs db.engine + ddl_grow.sql applied)
# --- L7 CAPI (shadow until BOTH creds present AND GROW_SIGNALS_LIVE=1) ---
GROW_SIGNALS_LIVE=0
META_CAPI_PIXEL_ID=   META_CAPI_TOKEN=   META_CAPI_TEST_EVENT_CODE=   META_GRAPH_VERSION=v21.0
GOOGLE_ADS_CUSTOMER_ID=   GOOGLE_CONVERSION_ACTION=
```
