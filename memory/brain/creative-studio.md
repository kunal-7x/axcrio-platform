# 🎨 Creative Studio + AI Asset Service — build brain

> Durable learnings for the Creative Studio (panel UI) + the AI Asset Service (dedicated generation engine).
> Append-only. Companion design docs in `design/`; the build plan is `CREATIVE_STUDIO_EXECUTION_PLAN.md`.

## What it is
- **AI Asset Service** = a DEDICATED coarse service (own process `/opt/famit-aiasset/`, own venv, port
  `127.0.0.1:8310`, own PG schema `ai_asset_*` FORCE-RLS, Hatchet async jobs, DO Spaces storage [interim=box fs]).
  Model-AGNOSTIC: a `Provider` ABC; **OpenRouter = the FIRST impl, not the architecture**.
- **Creative Studio** = the panel UI (route group `app/creative/`), stays in `famit-panel`.
- Reuses `wallet.py` (credit holds) / `audit.py` / `firewall.py` / `db.engine` RLS / Hatchet (F3). Co-located now
  (droplet 3/3), extractable to a GPU droplet later by changing 3 env URLs (`_mode=lib|http` seam).

## Key verified facts (don't re-derive)
- **OpenRouter CAN generate images:** same `POST /api/v1/chat/completions` + top-level `"modalities":["image","text"]`;
  image returns SYNCHRONOUSLY as a base64 data-URL at `choices[0].message.images[0].image_url.url`; decode→PNG.
  Default model `google/gemini-2.5-flash-image` (~$0.039/img). Edit/variation = same call + `image_config.strength`.
- **⚠ Env var is the founder typo `OPNEROUTER_API_KEY`** ("OPNE"). Adapter reads `OPNEROUTER_API_KEY or
  OPENROUTER_API_KEY`. Value is in `caps/.env.local`, NOT on the box `.env`.
- **⚠ Pricing:** read live `usage`, settle ACTUAL — never hard-code per-image cost.
- **The image engine already EXISTS but is UNDEPLOYED:** `droplet_work/creative/image_banner_studio/` has the full
  Provider ABC (`providers/base.py`) + 6 adapters (fake/ideogram/recraft/gpt_image/flux_hosted/flux_selfhost) + router/
  safety/batch/types. The box's `media_gen/image/` is a STUB that degrades to `engine:absent` because `creative/` was
  never deployed. **Phase-1 = DEPLOY this engine + ADD `providers/openrouter.py` (the one missing impl) + 1 registry
  line + the stage-1 prompt-builder. NOT a from-scratch build, NOT a new abstraction.**
- `media_gen/spaces.py` (S3/Spaces writer, dormant-until-`SPACES_*`), `media_gen/video/{schema.JobStatus,cost,
  audit_hook,safety,approval,client}` are directly reusable. `media_gen` stays unmounted (FEATURE_MEDIA off →
  live byte-identical) and is retired in a later caller.py cleanup.

## Architecture verdict (whole platform)
AI Asset Service = service · AI Manager = service · Workflow = Hatchet (already) · Voice = separate runtime (already) ·
Integrations + Analytics + Adbot = monolith-for-now · Control Layer = core INLINE boundary (never a service) ·
Wallet/Audit/Firewall = core shared libs. → a few coarse services around a service-extractable modular monolith.

## The build plan (CREATIVE_STUDIO_EXECUTION_PLAN.md) — 5 waves
- **A** AI Asset Service backend (12 units U1–U12; START NOW, backend lane, non-colliding with caller.py/frontend).
- **B** Creative Studio frontend (12 screens + the ONE new component `CreativeSkeleton` liquid loader; MUST run AFTER
  the in-flight UI-overhaul + Control-Layer frontend waves clear the `famit-panel` lane — design ON TOP of their look).
- **C** WhatsApp page upgrade + asset-attach (W1; after B's asset-browser/Library; same frontend lane).
- **D** AI-Manager `creative.*` + Adbot + Workflow wiring (6 seams; parallel to B/C, backend lane).
- **E** live real-banner test via founder OpenRouter key (interim box-fs) + security gate (flip `AIASSET_ENABLED`).

## Parallelization rule (the load-bearing decision)
Exactly TWO write-lanes: **backend lane** (new service dir + monolith adapters; NEVER edits caller.py/agent.py
run-path) and **frontend lane** (`famit-panel`). A ∥ (B/C) ∥ D — different lanes, zero shared files; the only cross-lane
seam is A's FROZEN route contract (publish it at U10 before B starts). SERIALIZE: UI-overhaul+Control→B; B's browser→C;
A's contract→D; A+isolation-suite→E. One agent per file; commit per verified unit; dormant-first.

## Contract reconciliation (the trap)
Docs use two prefixes for the SAME service: architecture/integrations use `/api/assets/*` (nginx) + `creative.*`
(tools); the UI doc used `/creatives/*`. **Architecture doc WINS on transport** → public base = `/api/assets/*`
(frontend-box nginx `location /api/assets/ → :8310`); tool names = `creative.*`. UI `/creatives/*` calls map 1:1
(`creative-studio-ui.md` §17). U10 freezes the route table as the artifact B/C/D build against.

## Non-negotiable gates (every wave)
- `AIASSET_ENABLED=0` default → live platform byte-identical until Wave E's per-tenant flip.
- Tenant from TOKEN never body; FORCE-RLS `ai_asset_*`; 9-probe isolation suite WITH a body-override negative control
  (proves teeth) gates activation.
- One money-path (`wallet.py`, idempotent, INR paise, no-double-spend proven via the asset path); ceil-never-under-
  reserve; tag the hold backend; prepaid vs prepaid_wallet branch NEVER summed.
- §20 NO-INVENT validator: strip any price/discount/RERA/phone/claim not verbatim in `CampaignContext` (LLM is input,
  never the authority on facts) — negative-control tested.
- Versions not overwrites (edit/regen = new `ai_asset_versions`, original kept); approve = the content-policy firewall
  before anything spends money downstream; only `approved` assets leave the studio.
- The ONE new frontend component is `CreativeSkeleton` (the liquid/wave loader — token-built, CSS-only, reduced-motion
  safe, morphs in-place like ChatGPT image gen); everything else PORTS `core-2-dashboard-builder-react` verbatim.

## Founder blockers (in need.md)
OpenRouter key (`OPNEROUTER_API_KEY`, provided in `.env.local`, paste server-side) · DO Spaces (interim=box fs) ·
Hatchet cross-box gRPC (interim=inline runner) · `AIASSET_SERVICE_TOKEN` · stage-1 LLM key (interim=MockLLM) ·
droplet limit 3/3 (co-located) · Meta WhatsApp for live publish. Only the OpenRouter key (+ optionally the LLM key) is
needed for the real-banner proof; the pipeline runs offline at ₹0 via `fake`/`MockLLM`.

## ⭐ A1 SHIPPED (2026-06-11) — service LIVE + DORMANT on the box. Build log `build_log/wave-build-aiasset.md`.
- Service running at `/opt/famit-aiasset/` (own venv py3.12, `127.0.0.1:8310`, localhost-only). systemd
  `famit-aiasset` enabled+active; `famit-aiasset-worker` installed but DISABLED (U7 module pending). Local
  source = `droplet_work/ai_asset/` (mirrors the ai_manager service layout). `AIASSET_STATE.md` = the ledger.
- Schema applied: 9 `ai_asset_*` tables (8 spec + `ai_asset_audit_logs` immutable mirror), ALL FORCE-RLS by
  `vendor_id` (RLS verbatim the ai_manager/crm/wallet admin-GUC policy). `ensure_schema()` idempotent x2.
  PROVEN: RLS teeth (A sees 1 / B sees 0 / admin 1), audit UPDATE denied at DB. `/status` = `enabled:false`.
- The reused engine `creative/image_banner_studio/` is DEPLOYED into the service (added `creative/__init__.py`
  — repo dir was a namespace dir). `providers.all_status()` → fake=configured, rest dormant. openrouter adapter
  = U3 (NOT yet built).
- ⚠ BOX FACTS (don't re-derive): `apt install python3.12-venv` was required (ensurepip). `db.engine` reads
  **`PG_DSN`/`PG_DSN_ASYNC`** (NOT DATABASE_URL) and a STANDALONE service MUST call `engine.init()` in-process
  (caller.py does it for the monolith; we replicate in `store._engine()`). `.env` carries PG_DSN copied from
  the monolith env at deploy. `asyncpg` absent = non-fatal (sync psycopg2 only). A bare python CLI doesn't
  source the systemd EnvironmentFile → `set -a; . .env; set +a` first. Live monolith routes = `/campaigns` +
  `/health` (NO `/api/*` on the backend box; that proxy is on the FRONTEND box). Probe live earner via `/campaigns`.
- ⚠ CONCURRENCY: a co-running session (the Control-Layer build, `PWD=/opt/famit-agent`) DID `sudo systemctl
  restart famit-caller famit-agent` mid-deploy — NOT us. Our deploy has ZERO caller/agent systemctl. When
  verifying "live untouched", grep the journal for the sudo COMMAND to attribute restarts correctly.

## ⭐ A2 BUILT (2026-06-11) — OpenRouter provider + campaign-aware 2-stage prompt pipeline. LOCAL only (not yet on box).
- The MISSING image provider is now built: `creative/image_banner_studio/providers/openrouter.py` (the ONLY adapter
  that was absent). Clones the b64-parse from `gpt_image.py` but for the CHAT endpoint: `POST {base}/api/v1/chat/
  completions` body `modalities:["image","text"]` -> image at `choices[0].message.images[0].image_url.url` (a
  base64 data-URL) -> decode to PNG bytes -> storage (data-URL NEVER stored). +1 registry line + router fallback head.
  COST = prefers LIVE `usage.cost` (send `body["usage"]={"include":True}`) -> settle ACTUAL (estimated=False); rate
  card (`AIASSET_IMAGE_RATE_USD` default 0.039) is the PRE-flight estimate only. Key: OPNEROUTER_API_KEY -> OPENROUTER_
  API_KEY -> per-tenant `..._API_KEY__<tenant_id>`. Dormant w/o key, never raises.
- STAGE-1 = `ai_asset/prompt_builder.py` (the intelligence core): `CampaignContext`(sec-6 provenance-tagged facts) +
  `GenerateSpec` + `VariantBrief`. `build_variants` -> N DIFFERENT angles (sec 8-9; dup angles rolled), each w/
  headline(3-8w)/subhead/goal-matched-CTA(sec-10 table)/visual/style/size/hypothesis/render_prompt. **sec-20 NO-INVENT
  validator** = fail-closed regex scrub (price/%/phone/RERA + guarantee/award/no.1/cure denylist); a claim survives
  ONLY if verbatim in `ctx.fact_blob()`, else stripped + `missing_field` note; fully-blanked headline falls back to
  business name. Stage-1 LLM = gemini-2.5-flash via OpenRouter, INJECTED callable (`set_llm_fn`) -> MockLLM in tests,
  zero network dormant; bad JSON -> deterministic `DEFAULT_ANGLES` fallback (never stalls).
- WIRING = `ai_asset/pipeline.py` two-stage: campaign -> build_variants -> router.select -> provider.generate ->
  storage.save_job -> variants. `generate()` GATED behind `config.enabled()` (not_enabled when OFF); `dry_run=True` =
  stage-1 only, no render/spend.
- PROVEN OFFLINE (zero spend): dry-run PASS — adversarial MockLLM injecting "₹58L/50% OFF/RERA Approved/phone" into a
  no-facts context -> ALL stripped; verbatim ₹58L in context KEPT (positive control); 4 distinct angles + full DNA +
  goal CTA. openrouter mocked-HTTP -> data-URL decoded to PNG + actual cost from usage.cost. full pipeline (fake
  provider) 3/3 rendered+stored. Test: `ai_asset/tests/test_a2_dry_run.py` (run PYTHONUTF8=1). Build log:
  `build_log/wave-build-aiasset-A2.md`.
- ⚠ LOCAL `creative/` is a NAMESPACE pkg (no `__init__.py`) — py3 implicit-namespace import works from `droplet_work/`;
  on the BOX A1 added `creative/__init__.py`. DEPLOY A2 = scp the 4 files into /opt/famit-aiasset + add OPNEROUTER_API_
  KEY to the service .env (value in `.env.local`). NOT done yet (kept dormant per task). NEXT: U4 campaign.py loopback
  reader fills CampaignContext from caller.py /campaigns (ads_engine `spine_link.py` pattern, X-Auth header).

## ⭐ A3 BUILT (2026-06-11) — wallet + audit + async JOBS + the AUTHED API SURFACE (U6+U7+U10). LOCAL only (not on box).
- 5 files in `ai_asset/`: **auth.py** (standalone tenant-from-TOKEN seam — `auth.resolve_token` scoped-JWT in lib
  mode, `caller.resolve_tenant` fallback; body tenant_id ALWAYS ignored; can()/service_token_ok()); **billing.py**
  (U6 CostGuard, thin wrapper over `wallet.py` — estimate ceil*COST_SAFETY, USD->INR-paise CEIL @AIASSET_USD_INR=84,
  reserve/settle/release idem `*:job:<id>`, **HOLD-BACKEND TAG** wallet|json so a json `hold_<hex>` never hits
  wallet.settle(int); `_JsonHold` degrade shim = same no-double-settle semantics offline); **jobs.py** (U7 state
  machine queued->running->streaming->succeeded|partial|failed|cancelled + phase; submit=estimate->reserve->persist
  ->enqueue; runner runs A2 pipeline, persists asset+immutable version per variant, settles ACTUAL+refund;
  **IDEMPOTENT RE-ENTRY GUARD** = Hatchet-retry/double-run no-op (exactly-once proven); `_enqueue`= Hatchet when
  `AIASSET_HATCHET_HOST_PORT` else INLINE daemon-thread fallback; SSE `stream_events`; `audit()`=audit.record PG
  events ch="ai_asset" + per-vendor immutable mirror); **endpoints.py** (U10 `build_router(resolve_tenant,can)` —
  NOT a module-level router, the media-gen lesson; 18 frozen routes; whole surface 503-gated by AIASSET_ENABLED
  except GET /status; by-id RLS-scoped->404; over_budget 402; not_approved-attach 409; raw streams bytes never
  exposes local_path). **store.py EXTENDED** with the jobs/assets/versions/scores/usage/brand-kit/audit CRUD (each =
  one RLS `_exec` txn; `public_dict()` drops local_path; create_job ON CONFLICT->no double-submit; add_version
  immutable append). app/main.py mounts the router additively (try/except, version 0.2.0-a3).
- FROZEN API (base `/api/assets/*` via frontend nginx): /status /providers /generate /jobs /jobs/{id}
  /jobs/{id}/stream(SSE) /jobs/{id}/cancel /assets /assets/{id} /assets/{id}/raw /assets/{id}/edit
  /assets/{id}/regenerate /assets/{id}/approve /assets/{id}/reject /assets/{id}/attach /assets/{id}/attach-whatsapp
  /variation-from-upload GET+POST /brand-kits. (This is the U10 contract B/C/D build against.)
- PROVEN OFFLINE (zero spend): `ai_asset/tests/test_a3_smoke.py` 30/30 — 18 routes registered + no module-level
  router; wallet estimate(1208)/usd->paise(328)/settle-actual+refund/double-settle-once/release-full/clamp-no-over-
  charge; isolation token-derived (malicious body tenant_id=B ignored) + NEGATIVE CONTROL (body-reading handler
  forgeable -> proves teeth). Full app boots w/ router (23 routes). Job machine inline: submit->...->succeeded, 2
  variants->2 assets+2 versions, settle 0+full refund. EXACTLY-ONCE: 2nd run = no-op when vendor recoverable (box
  path). A2 dry-run still PASS. py_compile OK x7. Build log `build_log/wave-build-aiasset-A3.md`, ledger
  `ai_asset/AIASSET_A3_STATE.md`.
- DEPLOY (kept dormant): scp the 4 new files + store.py into /opt/famit-aiasset, restart **famit-aiasset ONLY**
  (never caller/agent); router mounts DORMANT (503 except /status) -> byte-identical to live. NEXT: U4 campaign.py
  reader (endpoints seed a bare context from explicit fields until then — safe no-invent default), U8 score.py (the
  'scoring' phase slot already exists), workflow.py (real Hatchet; absent -> inline fallback works).

## ⭐ A4 PASSED (2026-06-11) — LIVE REAL-BANNER PROOF. A2+A3 DEPLOYED + service ON for the admin tenant.
- A2+A3 are now ON THE BOX (were local-only). Service `:8310` LIVE; `AIASSET_ENABLED=1` for the `admin` tenant.
  Report `build_log/wave-build-aiasset-A4.md`; ledger `ai_asset/AIASSET_A4_STATE.md`; handoff updated.
- PROVEN: OpenRouter `google/gemini-2.5-flash-image` made 3 REAL banners (1024² 1.3-1.9MB) from real campaign
  "Codename Joy 3.0" (Shapoorji Pallonji). 3 distinct angles, verbatim facts (no-invent held). Wallet settled
  ACTUAL **Rs10.14** from live `usage.cost`, NO double-charge (balance 10000->8986, lifetime_spend 1014, held 0).
  Immutable `ai_asset_audit_logs` written. Isolation PASS (forge B->404; admin token+body tenant_id=B -> vendor
  =admin; unauth->401). Live platform UNTOUCHED (caller/agent never restarted; /campaigns 200 throughout).
- ⚠ 4 BOX BUGS found+fixed in A4 (don't re-derive — all deployed): (1) box **router.py was OLD, missing
  `openrouter` in the fallback ladder** -> rendered via `fake` (3.6KB). router.py MUST be redeployed alongside the
  providers. (2) jobs.submit reserved with literal `"pending"` -> idem `reserve:job:pending` SHARED -> wallet
  returned the SAME hold -> 2nd+ job charged 0. FIX: pre-gen job_id, reserve+create_job with it. (3) standalone
  venv lacks `google.protobuf` (caller.py unimportable) AND jwt -> token auth dead. FIX: `pip install PyJWT==2.13.0`
  into the service venv; `auth.resolve_tenant` lazy-inits the monolith auth secret from `/opt/famit-agent/var/secret`
  + resolves tenant from verified `access_claims`. Legacy `X-Auth FamitCall2026` does NOT work on the service (no
  caller.py) — mint a scoped Bearer JWT. (4) admin pseudo-tenant wallet reserve needs the admin GUC -> thread the
  token's `is_admin` endpoints->jobs->billing->wallet. `wallet.available()` False until `store.available()` runs
  `engine.init()` in-process; admin prepaid_wallet was empty -> `wallet.topup("admin",N,is_admin=True)` for the test.
- GAPS (need.md): box-fs storage (DO Spaces creds VALID -> set `SPACES_*` to switch); per-tenant OpenRouter keys
  (`OPNEROUTER_API_KEY__<tid>`) optional; per-tenant ON/OFF gating (flag is global env today, OK while localhost-only,
  needed before the `/api/assets/` nginx route opens to all vendors); `version.local_path` unset so `/assets/{id}/raw`
  can't stream (PNG on disk; one-line map fix); cross-module PG `events` leg not written from the standalone process
  (per-vendor `ai_asset_audit_logs` IS). ROLLBACK = `AIASSET_ENABLED=0` + restart famit-aiasset. Backup
  `/opt/famit-aiasset/.a4bak.20260610-203503`.

## ⭐ FRONTEND BUILD PLAN SYNTHESIZED (2026-06-11) — `CREATIVE_STUDIO_FRONTEND_PLAN.md`. READ-ONLY design wave.
- Synthesized the 4 design docs (`design/cs-{loading-component,workspace-final,asset-library,out-of-box-features}.md`)
  into ONE page/component build plan = Wave B of `CREATIVE_STUDIO_EXECUTION_PLAN.md`, expanded into parallelizable
  groups G0–G9. **Runs AFTER the UI-overhaul build clears the `famit-panel` frontend lane** (+ Control-Layer FE wave).
- ⚠ LOAD-BEARING RECONCILIATION: the exec plan named only `CreativeSkeleton` as new; the loader spec (authored later)
  adds a SECOND new component **`GenerationLoader`**. So **TWO hand-built components, not one** — everything else PORTS
  Core_2. They COMPOSE: GenerationLoader (batch dot-matrix "engine thinking" charcoal hero) collapses inward → grid of
  `CreativeSkeleton` cards streams in → each morphs into a real `GridProduct` variant card as SSE lands. Build loader
  FIRST (reusable platform-wide: image/banner/ad/brochure/video-thumbnail).
- BUILD ORDER (16 units): (1) `app/creative/` scaffold+nav+`/status` dormant guard → (2) **GenerationLoader**
  (`field.ts` canvas + `gl-*` globals.css, 60fps mobile, no fake %, reduced-motion CSS fallback) → (3) **CreativeSkeleton**
  → (4) S2 Create panel (`NewProductPage` port, `/generate`) → (5) S3 Campaign Context (provenance dots) → (6) S4 SSE
  queue (`useGenerationJob` hook, `/jobs/{id}/stream`) → (7) S5 Variant grid (`DraftsPage/Grid`+`GridProduct`) → (8) S6
  Asset Detail+NL edit (`Modal isSlidePanel`, `/edit`=new version) → (9) S1 flagship assembly (`HomePage` 2-col) → (10)
  S9/L1–L4 Library (gallery+filter rail+card+bulk bar; `GET /assets` 8 facets) → (11) L5/L6 detail drawer+version
  timeline → (12) L7–L9/S11 reuse (one `attach` verb + embedded `selectMode="pick"` picker) → (13) S7 Brand Kit
  (`SettingsPage`)+S8 Performance → (14) S10 upload-reference → (15) W1 WhatsApp builder (exec-plan Wave C) → (16)
  acceptance pass.
- PARALLELIZATION (one agent per group, zero shared files): G0 scaffold → then **G1 loaders ∥ G2 create ∥ G3 library**
  (3 disjoint file sets) → **G4 generate** (S4/S5/S6/S1 assembly; needs G1+G2+G3-card; opus) → **G5 reuse ∥ G6
  brand/perf ∥ G7 upload** → **G8 WhatsApp** last (needs G5 picker) → G9 acceptance. Opus on G1/G2/G4 (loader +
  orchestration), sonnet on the ports. Share state via the FROZEN `/api/assets/*` contract only.
- TOP-5 FEATURES plug into existing units, **zero new tables/columns, only F1 adds 1 endpoint**: F1 Brand-Kit
  Auto-Extraction (G6, additive `POST /brand-kits/extract`) · F2 Make-All-Sizes (G4/G5, `BatchSpec` cross-product) ·
  F3 In-UI A/B test (G4+G6, reuses `attach`→`ads_engine`→`metrics`, reports-only) · F4 Model-Comparison 2-up (G2 Advanced)
  · F5 Version Timeline (G3+G4, pure VIEW of `ai_asset_versions`). Riders: F11 credit estimator (G2), F12 "From this →"
  remix (G3/G7).
- ACCEPTANCE BAR: Inter Display single-line headings/no subtitle/one `<Layout title>`/no `PageHeader`; ZERO raw hex
  (tokens only); dark-mode; reference-port-only except the 2 new components; real loading/empty/error/dormant states +
  NEVER a fabricated % (hairline only with real `progress.total`); `/status` dormant guard every screen (byte-identical
  when `AIASSET_ENABLED=0`); provenance dots make no-invent visible; approved-only attach + visible wallet estimate
  before spend; 60fps loader on throttled mobile. Wire to `/api/assets/*` (NOT `/creatives/*`).

## ⭐ B3 WIRED (2026-06-11) — AI MANAGER `creative.*` -> LIVE Asset Service (voice/chat -> real banner). LIVE on the box.
- The `creative.*` workforce adapters (`/opt/famit-agent/workforce/tools/catalog.py`) now hit the LIVE Asset
  Service `:8310` `POST /generate` (was the dead `/media/*`). AI-Manager Test Console command -> real
  OpenRouter banner, asset-svc-owned credit settle, no double-charge, audited, isolation intact, 0
  regression. Build log `build_log/wave-build-aim-creative-wiring-B3.md`. THIS is the D-wave "AI-Manager
  creative.* wiring" seam from the exec plan, done.
- AUTH SEAM CLOSES: the workforce mints the per-run Famit access JWT (`transport.mint_run_token` ->
  `auth.issue_pair`) signed by the SHARED monolith secret -> `ai_asset.auth.resolve_tenant` verifies it via
  `access_claims` (same secret). One Bearer authenticates the AIM->asset dispatch AS the run's tenant; body
  tenant_id ignored. New `workforce.config.asset_service_base()` (`AIASSET_LOOPBACK_BASE`, default :8310) +
  `transport.call_service(base=...)`.
- DON'T RE-DERIVE: the workforce LLM planner is a DORMANT stub (`llm/driver.propose` returns None always),
  so the deterministic **StubPlanner drives and reads `task['plan']`** — the AIM delegate had to add `plan`
  (mirroring `actions`) AND mint+thread `run_token`. See mod-ai-manager.md B3.
- A4 wallet now shows 5 admin jobs / lifetime_spend 2028 paise (A4's 3 + B3's banner gj_87f260…676 + one
  more). DO Spaces is NOW the storage backend (storage=spaces in result.json; box-fs gap from A4 closed for
  new jobs). Per-tenant AIASSET_ENABLED gating still global (founder/eng follow-up before opening to all
  vendors).

## ⭐ C3 VERIFIED (2026-06-11) — END-TO-END DEMO PROOF via the panel-equivalent path. Report `build_log/wave-build-C3-e2e-verify.md`.
- FULL e2e GREEN over the VPC (the byte-identical request FE nginx forwards): `POST /generate` (n=2) -> job
  `gj_9792a293b4974ac6` -> SSE `/jobs/{id}/stream` real phases (streaming/rendering done 0/2 -> succeeded/done
  2/2, real `progress.total`, NO fake %) -> 2 openrouter banners in DO Spaces (`creative/admin/banner/
  20260611-043239-w26y7a-{0,1}/0.png`, 1.38MB+901KB, valid 1024² PNG) -> **presigned URL GET 200 image/png**
  (the panel's real image-fetch path) -> wallet settled ACTUAL 676 paise (reserved 755, refund 79), avail
  7172->6496, held 0, spend 2828->3504, NO double-charge. Isolation PASS (forge B->404/0; admin token + body
  tenant_id=B -> owner=admin body IGNORED; B/unauth->401).
- ⚠ BOX FACTS (don't re-derive): (1) service now binds **10.122.0.4:8310** (VPC IP, NOT just 127.0.0.1); the
  caps-prompt's "bound 127.0.0.1 ONLY / 504" is STALE — backend ufw ALLOWS `8310/tcp from 10.122.0.2`. (2)
  Live earner caller.py is on port **8209** (NOT 8000). (3) Auth: mint admin Bearer JWT in the service venv:
  `jwt.encode({sub:admin,role:admin,is_admin:True,type:access,iat,exp:+900,jti}, open("/opt/famit-agent/var/
  secret").read().strip(), "HS256")`. Legacy X-Auth FAILS on the service. (4) PG_DSN is a SQLAlchemy URL
  (`postgresql+psycopg2://…`) — strip `+psycopg2` for raw psycopg2; wallet/store RLS GUC is NOT plain
  `app.is_admin` for the ai_asset_* tables (use the service's own `store`/`wallet.balance(tid,is_admin=True)`).
- ⚠ **THE ONE BLOCKER to a clickable browser demo:** public `panel.famit.in/api/assets/*` TIMES OUT (000)
  while sibling `/api/campaigns`,`/api/me` (-> caller 8209) reach the backend (401). famit-aiasset journal
  shows NO request on 8310 during a panel hit; direct VPC hit IS logged + 200. => **FE-box nginx `location
  /api/assets/` proxy_pass is stale** (not repointed at `10.122.0.4:8310` after the bind move). Fix = one line
  on `root@143.110.247.249` + `nginx -s reload`. No SSH to FE box this session (do-blr-test key is famit@,
  FE is root@). Cosmetic: version DB row `storage='local'` though bytes ARE in Spaces + presigned-fetchable.
