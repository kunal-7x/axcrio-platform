# BRAIN — mounting modules into caller.py (the live spine). Learnings from ads-engine mount (2026-06-10).

## THE LIVE SPINE FACTS (reuse for EVERY future module mount)
- caller.py is a FastAPI app: `app = FastAPI()` (~line 171), routes are inline `@app.get/post`. NOT
  include_router-based historically — ads-engine is the FIRST `app.include_router` mount.
- Auth helpers a bare-OK module's router looks up via `import caller`:
  `resolve_tenant(request)->dict|None` (line 404), `need_auth()->Response 401` (436),
  `can(tenant, "write"|"read"|"manage_tenants")->bool` (641). org_id is ALWAYS `t["tenant_id"]` (token).
- Legacy admin auth for gates: header `X-Auth: <CALLER_PASS>`. CALLER_PASS in .env = `FamitCall2026`
  (code default `Famit@2026`; PW read at caller.py:138). `_extract_cred` accepts Basic/Bearer/X-Auth.
- Import-guard precedent (top of caller.py, ~lines 34-125): `try: import X as _mod / except: _mod=None`
  for wa_mod/_auth_mod/_audit_mod/_brain_mod/_kb_mod/_wallet_mod/_firewall_mod/_crm_mod/_rl_mod/_obs_mod.
  Boolean env convention: `(cfg_get("KEY","default") or "default").strip().lower() in ("1","true","yes","on")`.

## ⚠ THE VENV TRAP (advisor catch — would have wasted a cycle)
- The RUNNING service uses `/opt/capsy-agent/.venv/bin/python` — NOTE `capsy-agent`, NOT famit-agent.
  There IS a decoy `.venv` under /opt/famit-agent — do NOT smoke against it.
- systemd: `famit-caller.service` -> WorkingDirectory=/opt/famit-agent, EnvironmentFile=.env,
  PYTHONPATH=/opt/famit-agent, ExecStart=/opt/capsy-agent/.venv/bin/uvicorn caller:app --port 8209 --workers 1.
- So a top-level package (e.g. `ads_engine/`) must live at `/opt/famit-agent/<pkg>/` to import.

## THE WINNING MOUNT PATTERN (flag-OFF = byte-identical, crash-safe)
1. Append the mount block at the END of caller.py (app + helpers fully defined -> no circular import).
2. import-guard the router + FEATURE_<MOD> flag DEFAULT OFF + `if FLAG and router is not None: include_router`
   wrapped in try/except (a mount failure logs, never crashes the live spine). NO .env change at rest.
3. Spine instantiate-smoke = `import caller` in the REAL venv, BOTH flag states, BEFORE restart:
   flag OFF -> assert no `/ads` routes; FEATURE_ADS=1 (inline env on the subprocess) -> assert routes present.
   Proves mounted-vs-absent without ever toggling the live service. Catches syntax/circular/import errors.

## /run DISPATCH GATE WITHOUT A PAID CALL (the proven method — from P1 build log lines 575-577)
- PRE-SEED the test number into suppression FIRST (POST /suppression numbers=+910000000066), THEN POST /run
  campaign=<id> leads=+910000000066. Expect 200 + suppressed_count=1 -> the dial loop reads suppression and
  dials NOBODY. Confirm /calls newest record for the number = status=suppressed (NOT "calling").
- DO NOT just POST a junk number without pre-suppressing: if suppression hasn't propagated, /run DID dial a
  SIP attempt (carrier no-answer/voicemail) — that's the documented S-batch mistake. Pre-seed is the fix.
- A safe existing campaign id on the box: `c17e55e9f3`.
- ⚠ `/run` AND `/suppression` take **FORM fields, NOT JSON** (caller.py L2593: `/run` `campaign_id`+`leads`
  =`Form()`; L2834: `/suppression` `numbers`=`Form()`). A JSON body is SILENTLY IGNORED → empty leads →
  misleading `count=0,suppressed_count=0` (looks like it worked but tested nothing). Use
  `curl --data-urlencode "campaign_id=c17e55e9f3" --data-urlencode "leads=+9100000000XX"` and
  `--data-urlencode "numbers=+9100000000XX"`. The proven GREEN signal is `count=1, suppressed_count=1`
  + a /calls record `phone=<num> status=suppressed` traceable to the run — NOT count=0.

## ads-engine SPECIFICS
- Router is BARE-OK / token-derived (NOT a body-tenant module) -> plain include_router is safe, no
  build_router needed. (Booking/media-gen/funnels DO read tenant from body -> they need a token-deriving
  surface BEFORE mount — do NOT confuse them with ads.)
- Mounted flag-OFF on 2026-06-10. Box backup to roll back to: `caller.py.MNTbak.1781068286`
  (md5 6478885b... = unmodified original). Deployed caller md5 = 8c0ab9e31349a637f98051d667c7a22f.
- Go-live = set FEATURE_ADS=1 + restart; stays dormant/not_configured until Meta/Google creds + LLM_ROUTER_URL.
- DEFERRED (not in this mount): scheduler poll_and_enforce tick; multi-window wallet settle->re-reserve loop.

## media-gen SPECIFICS (mounted 2026-06-10 — the FIRST body-tenant / build_router mount)
- BODY-TENANT module -> mounted the TOKEN-DERIVING surface `build_router(resolve_tenant, can, need_auth,
  forbidden, firewall=None)` (NOT the bare module-level `media_gen.router.router` = `_bare_router()`, which
  reads tenant from body = cross-tenant hole; DO NOT MOUNT it). build_router already shipped in router.py
  (2026-06-10 security fix): overwrites body["tenant_id"]=token on video-submit + image-generate, enforces
  rec["tenant_id"]==token ownership on by-job_id routes. webhook stays unauth (provider-signed, fail-closed).
- HELPER MAPPING for build_router(...): pass caller.py's `resolve_tenant`, `can`, `need_auth`, **`_forbidden`**
  (caller's forbidden helper is `_forbidden(msg="...")`, not a bare `forbidden`; default arg => zero-arg call
  works), and **`_firewall_mod`** for firewall (forward-compat only — firewall is a reserved/unwired seam in
  build_router today, so None vs _firewall_mod is functionally identical; don't claim approve is step-up-gated).
- ⚠ THE ADVISOR CATCH that mattered here (NOT needed for ads): media_gen is NOT httpx-only like ads_engine.
  router.py has TRANSITIVE module-level imports (media_gen.video.*, .image/.threed re-export creative/*, .spaces
  pulls boto3). An import-guard would SILENTLY set the router to None on any missing transitive dep and you'd
  ship a hollow flag-on mount = false GREEN. MUST run a BARE UNGUARDED `import media_gen.router` in the BOX venv
  (py3.12, NOT local py3.14) before trusting the mount. Result: it resolved clean — creative/* absence + boto3
  absence degrade gracefully (image/threed try/except -> not_configured; boto3/httpx lazy inside calls).
- ROUTE COUNT GOTCHA: build_router has 12 route OBJECTS but **11 unique paths** (GET+POST share
  /media/video/jobs). Assert on route-object count (12) AND that GET+POST both exist on that path — not unique
  paths==12 (that false-fails).
- Mounted flag-OFF. Box rollback backup: `caller.py.MNTbak.1781071064` (md5 8c0ab9e3... = post-ads-mount
  original). Deployed caller md5 = `4a92b5145dbf7d856db444c423602cc3` (4070 LOC).
- Go-live = FEATURE_MEDIA=1 + restart; dormant/not_configured until SPACES_*/VIDEO_PROVIDER+VIDEO_API_KEY.
  creative/image_banner_studio + creative/threed_model are NOT on the box -> image/3D stay not-importable until
  deployed. DEFERRED: repoint creative/video_studio engine import; firewall step-up on approve; selfhost worker.
