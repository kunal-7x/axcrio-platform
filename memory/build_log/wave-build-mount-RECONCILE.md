# WAVE BUILD — MOUNT RECONCILE (crash recovery, sequential spine) — PLATFORM-ENG

Date: 2026-06-10. Trigger: laptop switched off mid-mount (session believed it was "at support ~unit 5-6").
Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/` (venv `/opt/capsy-agent/.venv`, py3.12).
NO git. THE LIVE EARNER — stabilize-first, reconcile, then finish.

## STEP 0 — BOX HEALTH FOUND (no rollback needed; live system was STABLE)
- `famit-caller` **active** (NOT crash-looping). Clean restart at 07:36:13 (`Application startup complete`,
  `Uvicorn running on 0.0.0.0:8209`). `famit-agent` also active. famit-livekit unit inactive (expected).
- `curl -H 'X-Auth: FamitCall2026' localhost:8209/campaigns` → **200**. /me,/leads,/contacts,/billing/overview
  all 200 in the logs.
- caller.py AST parses; FULL `import caller` in the box venv succeeds → **79 routes** (all flags OFF) → the
  resting deployed state is byte-clean. ZERO 5xx/traceback. The only log errors are a benign elevenlabs
  analytics "interval_too_small" quirk (unrelated to mounting). The `/forms`,`/forms/status` 404s at 07:36:28
  were the interrupted session's own smoke probes (flag-OFF → correctly absent), NOT a fault.
- Gotcha noted: the SERVICE python is `/opt/capsy-agent/.venv/bin/python` (NOT `/opt/famit-agent/.venv`,
  whose `python` is a broken relative symlink). WorkingDirectory=/opt/famit-agent, EnvironmentFile=.env.
- VERDICT: live backend HEALTHY. No half-finished mount left it broken. No restore performed.

## STEP 1 — RECONCILE (what was already done)
caller.py HEAD md5 = `943bff85fc4cd2f79f1fe43ba0000869` (4324 LOC). Newest backup
`caller.py.MNTbak.1781097663` md5 `68218dfa...` = the post-forms-surveys state = rollback target BEFORE the
workflow mount. So the workflow-studio block is the LAST edit — complete + deployed, just never separately
backed up or build-logged (the crash hit between deploy and logging).

MOUNTED + GATE-GREEN (flag default OFF, byte-identical at rest), confirmed in caller.py tail + flag-on smoke:
| # | Module | Flag | Mount line | Status |
|---|--------|------|-----------|--------|
| 1 | ads-engine | FEATURE_ADS | L4030 include_router(_ads_router) | GREEN (logged) |
| 2 | media-gen | FEATURE_MEDIA | L4067 build_router→include | GREEN (logged) |
| 3 | booking | FEATURE_BOOKING | L4108 build_router→include | GREEN (logged) |
| 4 | payments | FEATURE_PAYMENTS | L4153 wire→include /payments | GREEN (logged) |
| 5 | support | FEATURE_SUPPORT | L4201 wire→include /support | GREEN (logged) |
| 6 | forms-surveys | FEATURE_FORMS | L4269 build_router→include | GREEN (logged) |
| 7 | workflow-studio | FEATURE_WORKFLOWS | L4319 build_router→include + L4321 attach_event_bridge | GREEN (UNLOGGED — verified this pass: FEATURE_WORKFLOWS=1 → 18 /workflows routes, total 97, import clean; flag OFF → 79, byte-identical) |

`workflow/` package present on box. `ai_manager/` and `funnels/` packages NOT on box → genuinely unmounted.

REMAINING (2):
- **ai-manager** — clean bare-OK mount (token-derived via lazy caller.resolve_tenant; NOT body). prefix /ai-manager.
- **funnels** — ⚠ BLOCKED: ships endpoints.py that reads tenant_id FROM BODY; the shipped funnel_wiring.diff
  mounts it BARE = cross-tenant hole. MUST build a token-deriving build_router first; DO NOT apply the diff.
  Requires `import workflow` (now resolvable — workflow pkg on box). Mount AFTER workflow.

## STEP 2 — FINISH (this pass) — progress below (one at a time, build_log after each)
- [x] ai-manager  — DONE/GREEN. bare-OK include_router(_ai_manager_router) @ caller.py tail. FEATURE_AI_MANAGER
      default OFF. box md5 5cc2d6b4..., backup MNTbak2.1781081110 (943bff85...). flag-OFF 79 routes byte-identical;
      flag-ON 7 paths/88. Regression GREEN (core 200, /ai-manager 404, /run suppressed no-paid-call, 0 5xx).
      Build log: wave-build-mount-ai-manager.md.
- [x] funnels     — DONE/GREEN. NOT actually blocked: the token-deriving build_router ALREADY EXISTS in
      funnels/endpoints.py L132 (2026-06-10 security fix). Mounted build_router (NOT bare body-tenant router;
      did NOT apply funnel_wiring.diff). FEATURE_FUNNELS default OFF. box md5 bb87bd18..., backup
      MNTbak2.1781081810 (5cc2d6b4...). flag-OFF 79 routes byte-identical; flag-ON 10 paths/90. Regression
      GREEN (core 200, /funnels 404, /run suppressed no-paid-call, 0 5xx). Build log: wave-build-mount-funnels.md.

---

## FINAL STATE — MOUNT WAVE COMPLETE (9/9)
- **Box HEALTHY throughout.** No rollback was ever needed; the live system was never broken by the crash.
- All 9 FEATURE flags present in caller.py (ADS, MEDIA, BOOKING, PAYMENTS, SUPPORT, FORMS, WORKFLOWS,
  AI_MANAGER, FUNNELS), ALL default OFF. Resting `import caller` = **79 routes** = byte-identical to the
  pre-mount original. Both famit-caller + famit-agent active. ZERO paid calls placed (suppression-gated /run).
- caller.py box HEAD md5 = `bb87bd18b49c9dea152728fb7e92af60` (4404 LOC). Newest rollback backups (chain):
  MNTbak2.1781081810 (5cc2d6b4 post-ai-manager) → MNTbak2.1781081110 (943bff85 post-workflow) →
  MNTbak.1781097663 (68218dfa post-forms).
- 7 modules were already mounted before this pass (ads/media/booking/payments/support/forms logged;
  workflow mounted-but-unlogged → verified+logged in RECONCILE). This pass finished the last 2: ai-manager
  + funnels. NOTHING deferred. Each module: dormant-by-flag, lazy schema (no live PG touch), token-derived
  tenant isolation, additive-only.
- TO GO LIVE: set the relevant FEATURE_*=1 in /opt/famit-agent/.env + restart famit-caller (per-module creds
  in REMAINING_MODULES_BUILD_STATE.md §D). funnels needs FEATURE_WORKFLOWS=1 to be useful.
