# WAVE BUILD — AI Asset Service (Creative Studio generation engine)

Append-only per-unit build report. Conforms to `design/asset-service-architecture.md` +
`design/asset-service-backend.md` + `CREATIVE_STUDIO_MASTER_PROMPT.md`. Local source =
`droplet_work/ai_asset/`; deployed to `/opt/famit-aiasset/` on the backend box `famit@168.144.153.145`.
NO git. Lane = backend (NEVER edits caller.py / restarts famit-caller/agent / deploys the panel).

---

## U/A1 — SCAFFOLD + DEPLOY ENGINE + SCHEMA (DONE 2026-06-11)

**Deliverable:** standalone FastAPI service, the reused image engine deployed, the `ai_asset_*` schema
applied, all DORMANT behind `AIASSET_ENABLED=0`.

### What was scaffolded (local `droplet_work/ai_asset/`, deployed to `/opt/famit-aiasset/`)
- `app/main.py` — FastAPI factory `app`; sys.path bootstrap (adds the pkg parent for `creative.*` +
  `/opt/famit-agent` for the shared libs db/wallet/audit/vendors, mode=lib); `ensure_schema()` on startup
  (lazy, no-op w/o PG); routes `GET /health` (liveness, un-gated 200) and `GET /status` (readiness/dormancy
  probe: config posture + schema_report + provider readiness; never leaks the key value).
- `config.py` — env reader, dormant-until-creds, never raises. `AIASSET_ENABLED` master gate (default OFF),
  `AIASSET_MODE=lib|http` extraction seam, `openrouter_key()` reads BOTH spellings (founder typo
  `OPNEROUTER_API_KEY` first, then `OPENROUTER_API_KEY`), default image model `google/gemini-2.5-flash-image`,
  stage-1 LLM `google/gemini-2.5-flash`, service-token/monolith-URL/Hatchet/Spaces/cost-safety/caps.
- `store.py` — engine/availability/`ensure_schema()` copied from `ai_manager/store.py` (lazy, `exec_driver_sql`,
  never-raises). ADAPTED: a STANDALONE service must call `engine.init()` itself (the monolith does it in
  caller.py startup; we don't get that) — `_engine()` lazily calls `db.engine.init()` once. Plus
  `schema_report()` (admin-GUC introspection: tables_present + forced_rls) for /status and the verify smoke.
- `schema.sql` — 8 spec tables + a 9th immutable audit mirror (`ai_asset_audit_logs`): providers, brand_kits,
  generation_jobs, assets, versions, creative_scores, usage, idempotency. RLS verbatim the ai_manager/crm/
  wallet admin-GUC policy (`is_admin='1' OR vendor_id = app.tenant_id`), `ENABLE`+`FORCE` on every table.
  ZERO percent signs (exec_driver_sql-safe). `ai_asset_providers` is tenant-agnostic (read-to-all,
  admin-write). `ai_asset_audit_logs` INSERT/SELECT-only (UPDATE/DELETE REVOKEd) = tamper-evident.
  Money never stored as float (INTEGER paise mirror only); binaries never in PG (URL+metadata only).
- `requirements.txt` — isolated venv deps (fastapi/uvicorn/httpx/sqlalchemy/psycopg2-binary/pydantic);
  boto3/Pillow/hatchet-sdk deferred to their units.
- `systemd/famit-aiasset.service` (uvicorn `ai_asset.app.main:app` 127.0.0.1:8310, EnvironmentFile, light
  hardening) + `systemd/famit-aiasset-worker.service` (Hatchet worker, installed DISABLED — module = U7).
- `deploy_a1.sh` — idempotent deploy: dirs, isolated venv, code rsync, dormant `.env`, systemd install
  (API enabled, worker disabled), start, smoke. ZERO `famit-caller`/`famit-agent` systemctl.

### Engine REUSE (deployed verbatim, NOT rebuilt)
`creative/image_banner_studio/` copied to `/opt/famit-aiasset/creative/` (added a `creative/__init__.py` —
the repo dir was a namespace dir). Provider ABC (`providers/base.py`) + 6 adapters (fake/ideogram/recraft/
gpt_image/flux_hosted/flux_selfhost) + router/storage/types/_common — all import clean (no hard external
deps; httpx + `vendors` are guarded). `providers.all_status()` → fake=configured, rest=not_configured
(dormant, correct). The ONE missing adapter `providers/openrouter.py` is U3, not A1.

### VERIFY (all green on the live box)
- `GET :8310/health` = **200** `{"ok":true,...}`. `GET :8310/status` = 200, `enabled:false` (dormant).
- Schema: **9 tables present, 9 FORCE-RLS**; `ensure_schema()` idempotent **x2 = True/True**.
- **RLS_TEETH_PASS**: write as tenant A → A reads 1, tenant B reads 0 (cross-tenant blocked), admin GUC reads 1.
- **IMMUTABILITY_PASS**: `UPDATE ai_asset_audit_logs` → `permission denied` at the DB layer.
- Port 8310 bound **127.0.0.1 only** (never world-exposed). Worker unit installed but **disabled/inactive**.
- **LIVE EARNER UNTOUCHED by this deploy**: deploy script has zero caller/agent systemctl. famit-caller +
  famit-agent both **active**, `/campaigns` + `/health` = 200. (A caller/agent restart DID occur at 19:56 but
  was issued by ANOTHER session — `sudo systemctl restart famit-caller famit-agent` from `PWD=/opt/famit-agent`
  = the Control-Layer build's lane — not by this deploy; both recovered to active.)

### Box learnings (durable)
- Needed `apt install python3.12-venv` (ensurepip missing) before `python3 -m venv` worked.
- `db.engine` reads **`PG_DSN` / `PG_DSN_ASYNC`** (NOT `DATABASE_URL`), and a STANDALONE service MUST call
  `engine.init()` in-process (caller.py does it for the monolith; we replicate). The service `.env` carries
  PG_DSN/PG_DSN_ASYNC copied from the monolith env at deploy.
- `asyncpg` absent on box = **non-fatal** (sync psycopg2 engine is the authoritative availability signal;
  only the dead-path async write-mirror is skipped). We use only the sync session.
- A bare `python` invocation does NOT source the systemd `EnvironmentFile` — the proof/CLI path must
  `set -a; . /opt/famit-aiasset/.env; set +a` to get PG_DSN.
- The live monolith routes are `/campaigns` + `/health` (200); there is **no `/api/*` prefix on the backend
  box** (the `/api` proxy lives on the FRONTEND box). Probe the live earner via `/campaigns`.

### Open / next
- U2: `store.py` vendor-scoped CRUD + `public_dict()` (drops `local_path`) + the 9-probe isolation suite.
- U3: `providers/openrouter.py` (b64 data-URL parse modeled on `gpt_image.py`) + 1 registry line +
  seed `ai_asset_providers`.
- Activation (later, founder): paste `OPNEROUTER_API_KEY` + `AIASSET_SERVICE_TOKEN`, flip `AIASSET_ENABLED=1`,
  add frontend-box nginx `location /api/assets/ → :8310`. Until then: byte-identical live platform.
