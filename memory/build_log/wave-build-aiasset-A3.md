# wave-build-aiasset-A3 — wallet + audit + async jobs + API surface (U6 + U7 + U10)

> AI Asset Service (Creative Studio generation engine), UNIT A3. Builds on A1 (service live+dormant on the
> box) and A2 (openrouter provider + 2-stage campaign-aware pipeline). LOCAL build only (not yet deployed).
> NO caller.py edit, NO famit-caller/agent restart, AIASSET_ENABLED=0 default -> live byte-identical.
> Conforms to design/asset-service-backend.md §3/§5/§6/§8/§9 + the architecture doc (standalone service).

## What was built (5 new/extended files in droplet_work/ai_asset/)

### ai_asset/auth.py  (NEW — the standalone tenant-from-TOKEN seam)
- The service is STANDALONE (binds :8310; panel reaches via frontend-box nginx /api/assets/ -> :8310), so
  unlike the in-caller ai_manager mount it must derive the tenant itself. resolve_tenant(request):
  (1) lib mode -> monolith `auth.resolve_token(cred)` (the scoped JWT the AIM mint-scoped-token seam issues;
  sub=tenant) [auth.py:142]; (2) fallback `caller.resolve_tenant` (JWT+legacy+hmac) [caller.py:551];
  (3) offline -> None -> 401. NEVER reads the body. extract_cred = Bearer/X-Auth/Basic. can() reuses
  caller.can with a conservative fallback. service_token_ok() (AIASSET_SERVICE_TOKEN, dormant->False) for
  internal/provider/AIM callers. NEVER raises.

### ai_asset/billing.py  (NEW — U6 CostGuard; thin wrapper over wallet.py)
- estimate_minor(n, rate_card_minor) = ceil(rate * n * COST_SAFETY)  (never under-reserve; cost_safety 1.15).
- usd_to_inr_minor(usd) = ceil(usd * AIASSET_USD_INR(84) * 100) — OpenRouter reports USD; wallet is INR paise.
- reserve_hold -> (hold_id, backend) idem "reserve:job:<id>"; None=insufficient -> over_budget (clean, not 500).
- settle_actual(hold_id, actual, job_id, backend) idem "settle:job:<id>" -> charges actual, refunds remainder.
- release_hold idem "release:job:<id>" -> full reserved returned (fail/cancel).
- HOLD-BACKEND TAG ('wallet' real int id | 'json' shim) -> settle/release dispatch to the SAME backend (the
  media-gen silent-no-op lesson — a json `hold_<hex>` never hits wallet.settle(int)).
- _JsonHold degrade shim (NOT money) = identical reserve/settle/release semantics incl. no-double-settle, so
  the full pipeline + A3 smoke run OFFLINE at zero spend (local build box / PG down). wallet.py reused verbatim
  (reserve [wallet.py:214] / settle [277] / release [344]).

### ai_asset/store.py  (EXTENDED — U2 CRUD the jobs/API need)
- Added jobs/assets/versions/scores/usage/brand-kit/audit CRUD on top of A1's engine+ensure_schema layer.
  Every op = one RLS-scoped _exec txn (tenant_id=vendor_id GUC). public_dict() drops local_path (§9). JSONB via
  CAST(:p AS jsonb). create_job ON CONFLICT DO NOTHING + get_job_by_idem -> no double-submit. add_version =
  next version_no, ON CONFLICT (asset_id,version_no) DO NOTHING (immutable; edit/regen appends, never
  overwrites). NO hard DELETE (lifecycle = status flips). audit_log -> the immutable ai_asset_audit_logs mirror.

### ai_asset/jobs.py  (NEW — U7 async job state machine + inline/Hatchet runner)
- submit(): estimate -> reserve hold -> persist queued job (idem) -> enqueue. over_budget if hold None;
  releases the hold if the job-row persist fails (no stranded money). audit.record on submit.
- State machine: queued -> running -> streaming -> (succeeded|partial|failed|cancelled); phase reading_campaign
  -> building_prompts -> rendering -> scoring -> storing -> done (drives the premium liquid-wave loader).
- Runner _run(): IDEMPOTENT RE-ENTRY GUARD (a Hatchet retry / double inline call on a non-queued job is a
  no-op — proven exactly-once). Runs A2 pipeline.generate (stage1 prompts + stage2 render), persists each
  produced variant as asset+immutable version, streams progress, settles ACTUAL (remainder refunds; zero-cost
  fake -> settle 0 + full refund), audits the terminal state.
- _enqueue: Hatchet (AIASSET_HATCHET_HOST_PORT set -> workflow.enqueue) else INLINE daemon-thread fallback (§5,
  works without the cross-box gRPC cutover). cancel() releases the hold + marks cancelled (idempotent).
- stream_events() = SSE generator polling the row -> /jobs/{id}/stream. get()/listing() public_dict-scrubbed.
- audit() = the shared helper: audit.record -> PG events (channel="ai_asset") [audit.py:60] + the per-vendor
  immutable mirror. CRASH-SAFETY: a worker death leaves the hold OPEN -> wallet.sweep_expired_holds reclaims it.

### ai_asset/endpoints.py  (NEW — U10 token-deriving API router)
- build_router(resolve_tenant, can, prefix="") -> APIRouter. NOT a module-level router (the media-gen security
  lesson — auth is INJECTED so the isolation suite can mount a negative-control double). NO module-level
  `router` symbol (asserted by the smoke).
- Every route: tenant from TOKEN (body tenant_id IGNORED, §9 probe 3); writes behind can(.,'write'); whole
  surface behind AIASSET_ENABLED -> 503 EXCEPT GET /status (un-gated dormancy probe). by-id reads are
  RLS-scoped -> a cross-tenant id returns 404 no field leak (§9 probe 2). /assets/{id}/raw streams bytes but
  NEVER returns local_path in JSON.
- FROZEN API SURFACE (18 routes): GET /status, GET /providers, POST /generate, GET /jobs, GET /jobs/{id},
  GET /jobs/{id}/stream (SSE), POST /jobs/{id}/cancel, GET /assets, GET /assets/{id}, GET /assets/{id}/raw,
  POST /assets/{id}/edit, POST /assets/{id}/regenerate, POST /assets/{id}/approve, POST /assets/{id}/reject,
  POST /assets/{id}/attach, POST /assets/{id}/attach-whatsapp, POST /variation-from-upload, GET/POST /brand-kits.
  over_budget -> 402; not_approved attach -> 409; PG down -> 503. edit/regenerate = a NEW job seeded from the
  asset (original version immutable, never overwritten).
- Mounted additively in app/main.py (try/except — never breaks boot; /health + /status stay alive even if the
  mount fails). app version bumped 0.1.0-a1 -> 0.2.0-a3.

## Verify (offline, zero network, zero spend) — ALL GREEN
- `python -m ai_asset.tests.test_a3_smoke` -> 30/30 PASS:
  * ROUTER: all 18 frozen routes registered; no module-level router (auth injected).
  * WALLET: estimate ceils (1208); usd->paise ceils (328); settle charges actual+refunds remainder;
    DOUBLE settle charges once (idempotent); release returns full hold; actual>reserved CLAMPED (no over-charge).
  * ISOLATION: resolve_tenant returns A from the TOKEN with a malicious body tenant_id=B present (body ignored);
    no-cred -> None.
  * NEGATIVE CONTROL: a body-reading handler IS forged to B (proves the token-derived path is load-bearing).
- Full app boots with the router mounted (23 routes incl /health + /generate + /assets/{id}/attach-whatsapp).
- A2 dry-run test still PASS after the pipeline enrich (no-invent + angle diversity intact).
- JOB STATE MACHINE exercised inline offline (fake provider + json hold + MockLLM): submit -> queued ->
  running -> streaming -> succeeded; 2 variants -> 2 assets + 2 versions; settle 0 + full refund.
- EXACTLY-ONCE: a second run_inline on a non-queued job is a no-op (idempotent guard) when vendor is
  recoverable (the box path) -> exactly 2 assets, no duplicate render/charge.
- py_compile OK on all 7 modules.

## Reuse contracts pinned (don't re-derive)
- wallet.reserve(tenant_id, amount_minor, resource_type, resource_id, idem_key, ...) -> hold_id|None [wallet.py:214]
- wallet.settle(hold_id, actual_minor, idem_key, ...) -> dict(charged_minor, refunded_minor) idem [wallet.py:277]
- wallet.release(hold_id, idem_key, reason, ...) -> dict idem [wallet.py:344]
- audit.record(actor, action, ..., channel, tenant_id, meta) never-raises [audit.py:60]
- auth.resolve_token(cred) -> tenant dict|None (scoped JWT) [auth.py:142]
- pipeline.generate(context, spec, tenant_id, llm_fn, dry_run) -> {status, variants[...]} [pipeline.py:39]
- INTEGER PAISE; USD->INR ceil; TWO BALANCES (prepaid=billing.balance vs prepaid_wallet=wallet_accounts) NEVER summed.

## DEFERRED (not A3 / next units)
- U4 campaign.py loopback reader (fill CampaignContext from caller.py /campaigns) — endpoints currently seed a
  bare context from the explicit request fields (safe no-invent default until the reader lands).
- U8 score.py (rule-based creative scorer -> ai_creative_scores); jobs.phase already has the 'scoring' slot.
- workflow.py (the real Hatchet workflow) — jobs._enqueue_hatchet imports it; absent -> inline fallback (works).
- DEPLOY: scp auth.py/billing.py/jobs.py/endpoints.py + the store.py CRUD into /opt/famit-aiasset, restart
  famit-aiasset (NOT famit-caller/agent). Keep AIASSET_ENABLED=0 until the Wave-E isolation suite (U12) +
  the per-tenant flip. The router mounts dormant (503 on everything but /status) so deploy is byte-identical.
