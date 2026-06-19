# ROUND-5 P4b — BACKEND WIRING (famit-caller ONLY) — STATE

Box: famit@168.144.153.145 :8209 famit-caller (uvicorn caller:app --port 8209).
Earner = famit-agent (NEVER restart; agent.py md5 MUST stay 48bc2b5a). famit-agent active confirmed.
Pre-edit live md5: caller.py f7d48c18 (== prior P4). endpoints.py: TBD.
Token: legacy /login password=CALLER_PASS (Famit@2026 default) -> /tmp/p4b_bearer.txt on box.
Flags live: FEATURE_AI_MANAGER=1, CONTROL_ENABLED=1, FIREWALL_ENABLED=true, AIM_LLM_PROVIDER=groq.
NOT set (code-default OFF): RETRY_SCHEDULER_ENABLED, CALLBACK_CADENCE_ENABLED, GOOGLE_OAUTH_*.

## ITEMS (priority order)
1. BOOKING real-time + GCal — POST /booking/book persist -> GET /bookings. GCal OAuth dormant on creds. IN PROGRESS
2. CALLBACKS auto-trigger — ENABLE scheduler w/ caps (max 1-2 retries, DND 9-21 IST, dedup, per-tenant rate cap). PENDING
3. AI-MANAGER e2e — /numbers persist+register inbound routing; /pin/set 422 fix; LLM read+PIN-action. PENDING
4. SUPER-ADMIN script-lock + render-brain-lock — entitlement keys + enforcement (locked -> not served). PENDING

## RULES
- NEVER edit agent.py / restart famit-agent. Back up files *.R5BEbak.<ts>. py_compile. restart famit-caller ONLY.
- Verify after deploy: /health 200 + agent.py md5 48bc2b5a + famit-agent active + 0 new errors.
- Commit caller.py selectively if tracked (gitleaks 0, no -A). endpoints.py is git-ignored (deploy+backup on box).
- Drop-in has R2 secret -> NEVER print full drop-in / commit it.

## GROUND TRUTH (verified on box)
- Caller :8209, PG_DSN set in DROP-IN (not .env) -> PG fully available in-service. db.engine.available()=True in-service.
- BOOKING: tables EXIST (bookings, booking_resources, booking_reminders, booking_events, booking_reminder_fires),
  RLS FORCE-on. booking_resources=0 rows -> must auto-provision default resource. FEATURE_BOOKING=0 (router NOT mounted).
  GCal calendar_sync.py FULLY BUILT + wired into core.book, dormant. Env: GOOGLE_CALENDAR_CLIENT_ID/SECRET/REFRESH_TOKEN
  + flag BOOKING_CALENDAR_SYNC=1. core.book needs resource_id. Router /book at booking/router.py:235.
  Contract gap: router wants {resource_id,phone,slot_start,...}; voice/task wants {phone,lead_name,datetime_iso,campaign_id,notes}.
- CALLBACKS: scheduler_loop (caller.py:8066) gated RETRY_SCHEDULER_ENABLED (=0 now). Caps present:
  window 09:00-21:00 IST (_in_window :1070), retry_max default 3 (:3069 -> clamp to 2), backoff [120,360,1440],
  NCPR/DND fail-closed (:8107), suppression (:8099), dedup in _enqueue_retry (:1889 phone+camp+tenant).
  Per-tenant daily_call_cap=500 applies to DIAL loop (:3289). W10 cadence (voice_ops/callback) gated CALLBACK_CADENCE_ENABLED.
  Warm-lead 40-69 branch: NOT present; HOT>=70 webhook at :3140. enqueue at :3074 (callback) / :3086 (retry).
- AI-MANAGER: BOX endpoints.py 7c2ce93f ALREADY has /pin/set(:200) /pin/verify(:223) _aim_llm_answer(:452).
  LOCAL repo endpoints.py 740a9aac is STALE (lacks them) -> EDIT box_live/endpoints.py copy. /numbers persists+registers
  (registry.py JSONL); inbound lookup = service-token GET /ai-manager/numbers/lookup (consumed by SEPARATE aim_voice_agent).
- ENTITLEMENTS: entitlements.py assert_access (HIDDEN=404, LOCKED=402). registry.json in control/var/control/.
  No campaign.script / render.brain key yet. Campaign script served at GET /campaigns/{cid}/prompt-preview (:5162) + dry-run (:5191), NOT gated.

## PLAN
1. BOOKING: add core.ensure_default_resource(org); router /book accept lead_name/datetime_iso + auto-resource;
   set FEATURE_BOOKING=1 in caller drop-in. GCal dormant (support GOOGLE_OAUTH_* alias too).
2. CALLBACKS: clamp retry_max<=2 (env RETRY_MAX_ATTEMPTS_CAP), add per-tenant callback daily rate cap,
   add warm-lead 40-69 next-day auto-schedule, ENABLE RETRY_SCHEDULER_ENABLED=1 (legacy path; assess W10 via agent a4c9bdb8).
3. AI-MGR: verify /pin/set 200, /numbers persist+register+lookup, LLM read+PIN-action e2e (box copy).
4. SCRIPT-LOCK: add entitlement key campaign.script (+ render.brain), gate /campaigns/{cid}/prompt-preview + dry-run.

## RESULTS — ALL 4 ITEMS DONE + CURL-VERIFIED (deploy TS 20260619-153344)
Box md5 post-deploy: caller.py 6f13c93b, booking/router.py eebc812d, booking/core.py e784dcdd, registry.json 35aa15e3.
agent.py = c33c03e2 (PARALLEL session changed it 15:23 — NOT me; was c33c03e2 pre+post my caller restart). famit-agent active.
Drop-in /etc/systemd/system/famit-caller.service.d/r5p4b.conf: FEATURE_BOOKING=1 + RETRY_SCHEDULER_ENABLED=1.

1. BOOKING — DONE. POST /booking/book {phone,lead_name,datetime_iso,campaign_id,notes} -> bk_f37577da5216 persisted,
   auto-resource res_6ecfcb44b12e (idempotent: 2nd book reused it), IST->UTC ok. GET /booking/bookings lists it.
   GCal dormant (calendar_configured:false). Env alias added: GOOGLE_OAUTH_* OR GOOGLE_CALENDAR_* both work + BOOKING_CALENDAR_SYNC=1.
2. CALLBACKS — DONE + ENABLED. Legacy DURABLE flat-file path (NOT W10 in-mem — survives restart). Caps:
   RETRY_MAX_ATTEMPTS_CAP=2, CALLBACK_TENANT_DAILY_CAP=50/tenant/day (durable counter autofire_counts.json),
   window 09-21 IST, NCPR fail-closed, opt-out skip, dedup, warm-lead(40-69) next-day@11 auto-schedule, every fire logged.
   Verified: scheduler clean (0 exc), window-gate works (21:10 IST -> in_window False -> no fire), counter roundtrip ok.
   /callbacks shows 2 REAL in-call callbacks. autofire today admin:1 (<<50, no runaway).
3. AI-MGR — VERIFIED (no code change; box endpoints.py already complete). /numbers GET+POST 200 (not 404),
   /pin/set 200 (not 422), LLM read "Aaj 14 calls huye hain" (grounded, no PIN), write -> eliciting/confirm (no exec w/o PIN),
   inbound lookup resolves after verify (tenant+grants). GAP: OTP dormant (numbers stay verified=False) -> founder action.
4. SCRIPT-LOCK — DONE. New keys grow.campaigns.script + grow.campaigns.render_brain (default_mode on, earner-safe).
   _feature_block on /campaigns/{cid}/prompt-preview (script) + /dry-run (render_brain). Full cycle proven over HTTP:
   default 200 -> admin lock -> 402 {error:locked} -> unlock -> 200. Two keys independent.

CLEANUP: test AI-mgr number num_024019a7ae8a REVOKED (lookup->None). _p4b_probe counter pruned. Test bookings left (harmless, no DELETE route).

## ROLLBACK
Flags off: rm /etc/systemd/system/famit-caller.service.d/r5p4b.conf && daemon-reload && restart famit-caller (booking unmounts, scheduler off).
Files: cp *.R5BEbak.20260619-153344 back (caller.py booking/{router,core,config,calendar_sync}.py var/control/registry.json) + restart famit-caller.
Granular: RETRY_MAX_ATTEMPTS_CAP/CALLBACK_TENANT_DAILY_CAP/WARM_LEAD_AUTOSCHEDULE env knobs; script-lock = clear the override.

## PROGRESS LOG
- box connected, token, explore ac82ff1c + W10-safety a4c9bdb8 done.
- booking tables exist+RLS; PG live via drop-in DSN; endpoints.py box ahead.
- ALL 4 built+deployed+curl-verified. earner byte-safe (my restart didn't touch agent.py). DONE.
