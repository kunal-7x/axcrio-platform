# wave-build-fix-broken-2 — BACKEND fixes (control / workflow / whatsapp)

Date: 2026-06-11. Box: famit@168.144.153.145 /opt/famit-agent (svc `famit-caller`, port 8209,
venv /opt/capsy-agent/.venv). Standard: founder-flow, live-reproduced (no API bypass).

## Scope verdict (what actually needs BACKEND change)
- CONTROL  -> NO backend change. Live-reproduced: WRITE persists + version bumps, /me/entitlements
  flips, path->feature_key middleware 404s the vendor route. Backend correct. (frontend-only fix)
- WHATSAPP -> NO backend change. `POST /whatsapp/campaign/{id}/generate-templates` is LIVE + 200.
  (frontend-only fix: deployed UI calls the dead `/whatsapp/templates/generate`)
- WORKFLOW -> BACKEND CHANGE REQUIRED (run never drains). Real root cause found below.

## WORKFLOW real root cause (corrected vs the diagnosis doc fix-workflow-2.md B3)
The diagnosis blamed `get_version`/`version_not_found`. The LIVE cause is different and proven:

`POST /workflows/{id}/run` over HTTP -> 500 internally -> falls through entitlement middleware
fail-closed `except` -> returns `{"error":"not_found"}` (caller.py:419) -> run row stuck `queued steps:0`.

Exception = `RuntimeError: asyncio.run() cannot be called from a running event loop`, raised at
`workflow/__init__.py:174` — the sync `run()` calls `asyncio.run(engine.run_in_process(...))` from
INSIDE FastAPI's async route (`endpoints._run_ep2` is `async def`). A fresh Python process has no
running loop so in-process tests PASS, masking it; the live async route ALWAYS hits it.
Same anti-pattern in `run_definition` (L181) and `resume()` (L205) -> `/hook` and
`/runs/{id}/approve` would 500 the same way.

PROOF: in fresh process W.run(...) -> `awaiting_approval steps:2` (drains). Inside `asyncio.run(main())`
the SAME call raises `RuntimeError(asyncio.run() cannot be called from a running event loop)`.

## FIX (backend, additive, minimal)
`workflow/__init__.py`: add `_run_coro(coro)` — if a loop is already running, offload the coroutine
to a fresh loop on a 1-worker ThreadPoolExecutor; else `asyncio.run`. Replace the 3 `asyncio.run(...)`
call sites (run L174, run_definition L181, resume L205) with `_run_coro(...)`. Sync public API + tests
unchanged; the live async routes now drain. NO endpoints.py / caller.py change.
Verified the thread-offload helper drains a run to `awaiting_approval steps:2` inside a running loop.

BE-4 (PG persistence, WORKFLOW_STORE=pg + schema) = IMPORTANT but SEPARATE durability concern, not
the run-drain break. Staged after the run fix is proven; in-memory store keeps the founder demo flow
working end-to-end now.

## Backups: /opt/famit-agent/workflow/__init__.py.FIX2bak.20260611-113249

## SMOKE PROOF (live HTTP through the router, port 8209, post-restart)
- BEFORE: POST /workflows/{id}/run -> {"error":"not_found"} (HTTP 404), run row queued steps:0.
- AFTER (gated template): RUN -> {"ok":true,"engine":"in_process","status":"awaiting_approval","steps":2};
  run row awaiting_approval steps=2 (parks at budget node, no wallet funds = correct fail-closed).
- AFTER (minimal no-gate wf: trigger->leads.read): RUN -> {"ok":true,"status":"completed","steps":2}.
- Run now DRAINS to a terminal/parked status instead of crashing the route.

## REGRESSION GATE (GREEN)
- /me 200, /campaigns 200, /leads 200.
- WhatsApp /whatsapp/campaign/test123/generate-templates -> 200 (backend correct, FE-only fix).
- /me/entitlements 200 (control backend correct, FE-only fix).
- famit-caller / famit-bridge (voice) / famit-agent -> all active.
- Zero 5xx in caller journal since restart.

## STATUS: DONE (backend run-drain fix shipped + verified). BE-4 (PG persistence) deferred/separate.
