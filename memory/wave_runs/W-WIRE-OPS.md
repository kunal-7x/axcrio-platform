# W-WIRE-OPS — wire the real-time ops backbone into caller.py (flag-gated)

Goal: the founder sees LIVE data (recordings/hot-leads/dashboard/CRM update in
seconds) by wiring the BUILT-but-unwired modules into the live FastAPI app
`caller.py` (service `famit-caller`, :8209). EARNER `agent.py`/`famit-agent`
NEVER touched. Each feature behind its own flag, default OFF.

## Ground truth (start of wave)
- Box: famit@168.144.153.145, /opt/famit-agent/caller.py
- Box golden caller.py md5 = `6d9f9e7d0631454c7603bda9b4c02643` (8177 lines)
- /health = 200 before.
- `voice_kernel/` IS on the box (incl. events + memory). `voice_ops/` is NOT yet
  on the box -> MUST ship voice_ops/ to /opt/famit-agent/ for W9/W14/W10.
- Python on box = 3.12.3.

## Real env-var flag names (authoritative — what the module configs read)
| Founder label (task) | REAL env var (config reads) | Module |
|---|---|---|
| EVENTS_ENABLED | `EVENTBUS_ENABLED` | voice_kernel.events |
| RECORDING_FINALIZE_POLL | `RECORDING_FINALIZE_ENABLED` | voice_ops.recording |
| REPORTING_ENABLED | `REPORTING_ENABLED` (read at caller singleton) | voice_ops.reporting |
| LEAD_LIFECYCLE_ENABLED | `LEAD_LIFECYCLE_ENABLED` (read at caller) | voice_kernel.memory |
| CALLBACK_CADENCE_ENABLED | `CALLBACK_CADENCE_ENABLED` (+ existing RETRY_SCHEDULER_ENABLED) | voice_ops.callback |

## Patches applied (LOCAL copy .wireops_work/caller.py.WIRED — NOT deployed yet)
- P0 singletons (after line 120): EventBus, recording cfg+providers, reporting svc,
  callback cfg/store, memory flag. All import-guarded (try/except -> None).
- W8: `_ev()` wrapper + emit-sites in `_finalize_call` + call_started in run_job.
- W9: detached StagedPipeline finalize task in `_finalize_call`; read self-heal in
  `_outbound_rec_item`.
- W14: 9 additive `GET /report*` routes + AI-Manager live `POST /ai-manager/report`.
- W7: `_w7_lifecycle_after_call` enrich (lifecycle + AI summary card) in `_finalize_call`.
- W10: cadence enqueue in `_finalize_call` + recon sweep + `fire_due` dial in
  scheduler_loop, all additive behind CALLBACK_CADENCE_ENABLED (legacy path skipped
  only when the flag is ON).

## STATUS — BUILD WAVE COMPLETE (no box mutation; deploy is a separate signed step)
- [DONE] pulled box golden, verified md5 `6d9f9e7d...`, read all 5 seam docs.
- [DONE] confirmed module env-var names + signatures (factories, fire_due,
  enqueue_smart, AIManagerLiveService, ReportingService all match call sites).
- [DONE] built `.wireops_work/caller.py.WIRED` — 485 lines added, +1 helper
  (`_w7_lifecycle_after_call`), 10 `/report*`+AIM routes, all flag-gated.
- [DONE] `py_compile caller.py.WIRED` clean.
- [DONE] smoke `voice_ops/tests/test_wire_ops_smoke.py` 5/5 PASS:
  STATIC seams present; W8 8 emits land; W14 report+isolation; W7 FSM; W10 anti-runaway.
- [DONE] full module suite `pytest voice_ops voice_kernel` = 900 passed.
- [DONE] W10 anti-runaway proven: 60-day time-advance + re-enqueue every no-answer
  -> exactly 1 dial then EXPIRED (old bug = 10-11x/night infinite).
- [DONE] wrote `design/W-WIRE-OPS-DEPLOY.md` (ship voice_ops -> deploy caller ->
  5-flag gated flip order, each with its smoke + revert).
- [BOX] `voice_kernel/` already on box (imports OK). `voice_ops/` NOT yet on box ->
  DEPLOY STEP A ships it. agent.py md5 `5c055a31...` UNCHANGED (earner untouched);
  box caller.py still golden (build wave did not mutate the box).

## FLAGS (real env-var names the configs read; founder labels in parens)
- `EVENTBUS_ENABLED`            (EVENTS_ENABLED)          — W8 event backbone
- `RECORDING_FINALIZE_ENABLED`  (RECORDING_FINALIZE_POLL) — W9 recording-in-seconds
- `REPORTING_ENABLED`           (REPORTING_ENABLED)       — W14 reporting + AIM live
- `LEAD_LIFECYCLE_ENABLED`      (LEAD_LIFECYCLE_ENABLED)  — W7 lifecycle + AI summary
- `CALLBACK_CADENCE_ENABLED`    (+RETRY_SCHEDULER_ENABLED)— W10 smart callbacks
All default OFF -> resting build byte-identical.

## FLIP ORDER (per W-WIRE-OPS-DEPLOY.md §4)
ship voice_ops -> deploy WIRED caller (flags OFF) -> earner-ring gate ->
1) EVENTBUS_ENABLED  2) RECORDING_FINALIZE_ENABLED  3) REPORTING_ENABLED
4) LEAD_LIFECYCLE_ENABLED  5) CALLBACK_CADENCE_ENABLED (then RETRY_SCHEDULER_ENABLED).
Each: smoke green + real call rings BEFORE the next. Revert = drop the drop-in line
(per-feature) or restore caller.py backup (full) + restart famit-caller.

## ARTIFACTS
- deployable: `.wireops_work/caller.py.WIRED` (from box golden + seam patches)
- box golden backup: `.wireops_work/caller.py.BOXGOLDEN` (md5 6d9f9e7d...)
- deploy runbook: `design/W-WIRE-OPS-DEPLOY.md`
- smoke test: `voice_ops/tests/test_wire_ops_smoke.py`
