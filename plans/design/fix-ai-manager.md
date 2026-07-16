# Fix — AI Manager "execute no-ops + shows raw JSON"

READ-ONLY diagnosis. Founder symptom: a command asks for PIN, he enters it, it
says "done" but NOTHING actually happens; and the reply shows raw JSON, not
human language. Two independent defects — one in EXECUTION (backend), one in
RENDERING (frontend). Both are real; fixing one without the other still looks broken.

Live wiring confirmed (`AIM_INTEGRATE_STATE.md` U3/U4): on the box `AIM_ENABLED=1`,
`AIM_LLM_PROVIDER=groq`, `WORKFORCE_ENABLED=1`, `AIWF_SERVICE_TOKEN` set,
`AIWF_LOOPBACK_BASE=127.0.0.1:8209`, test PIN `4827` enrolled. So `make_registry()`
returns the LIVE loopback catalog (not StubTools), and the runner DID return
`status="done"` for the budget command — yet no side effect occurred.

---

## A. WHY EXECUTE IS A NO-OP (backend)

Path: `endpoints.py /commands/{id}/execute` -> `_transition_command(action="execute")`
-> PIN check (`firewall_bridge.check_pin`, ok for 4827) -> `mint_step_up`
-> `delegate.execute()` -> `workforce.run_agent()` -> `AgentRunner.run()` ->
loopback tool -> caller.py route.

Three distinct breaks compound, in order of severity:

### A1 (the killer) — the loopback run_token is NEVER minted -> every live tool call is unauthenticated -> 401
- `workforce/tools/transport.py:25` defines `mint_run_token(tenant_of_run)` (calls
  `auth.issue_pair`) — but **grep proves it is never called anywhere in the runner.**
- `runner.AgentRunner.run()` builds `_tool_ctx(ctx)` (runner.py:383) from
  `ctx.run_token`, and `run_agent()` (`workforce/__init__.py:58`) defaults
  `run_token=""`. `delegate.execute()` (delegate.py:128) calls `run(...)` WITHOUT a
  run_token.
- So the live catalog's `_tok(ctx)` returns `""`, and `transport.call()` sends
  `Authorization: Bearer ` (empty) to `127.0.0.1:8209`. caller.py rejects it 401 ->
  tool returns `{ok:False}`. **Even with every FEATURE_* flag ON, no write would ever land.**
- FIX: in `runner.run()` (or in `run_agent` before constructing `RunContext`), when
  `transport.available()` and no `run_token` was passed, mint one:
  `ctx.run_token = transport.mint_run_token(ctx.tenant_dict or {"tenant_id": ctx.org_id, ...})`.
  The tenant_dict must carry enough for `auth.issue_pair` to mint a token whose
  `resolve_tenant` lands on `ctx.org_id` (RT-3: org from the authenticated trigger,
  never a model field). delegate.execute already forwards `tenant_dict=t`.

### A2 — target-module routes are 404 (their FEATURE_* flags are OFF) -> tool "parks", run still reports done
- U4 noted it directly: budget command -> `/ads/*` 404 (FEATURE_ADS off) -> no Meta
  reach -> wallet spend 0. The live catalog `_parked()` maps 404 to
  `{ok:False, reason:"not_configured"}`. That is CORRECT graceful degrade, but the
  runner's loop only `continue`s past a failed/parked tool and still finalizes
  `status="done"` (runner.py:248). `delegate._normalize_result` sees `status=="done"`
  -> `_transition_command` writes `execution_result={status:done, executed:true}`.
  So the UI says "Executed" for an action that did nothing.
- FIX (truth-in-reporting): the runner should reflect per-tool outcome in the run
  result (e.g. surface `tool_results`/`parked`/`not_configured` so a run where the
  only action returned `not_configured` is NOT reported as a clean `done`). At
  minimum, `delegate._normalize_result` + `_transition_command` must read the tool
  result detail and set the command status to `failed`/`needs_review` (with the
  reason) when no tool actually succeeded — so the UI never claims success on a no-op.
- Operational note: to make these commands ACTUALLY execute, the relevant module
  flags (FEATURE_ADS / FEATURE_WHATSAPP / dialer) must be ON for the tenant. That is
  a separate activation step, NOT a code bug — but A1 must be fixed first or they
  still 401.

### A3 — `_nlu_to_match` silently downgrades most commands to "clarify" (so they never become executable)
- `_run_test_command` (endpoints.py:108-148) routes the rich NLU parse through
  `intent/driver.py:_nlu_to_match`, which maps the NLU's wide `action_type` set down
  to the voice state-machine's TINY `_NLU_ACTION_TO_INTENT` table (driver.py:221).
  Only 8 action_types are routed; everything else -> `kind:"clarify"`
  (`reason:"unrouted_action:<x>"`). e.g. `analytics.send_report`,
  `whatsapp.send_brochure`, `leads.update`, `bookings.write`, `calls.control`,
  `workflow.*`, `creative.generate` all collapse to clarify -> never an executable
  command row. The founder's "Aaj ka report WhatsApp kar do" is one of these.
- Compounding: `delegate.py`'s `_INTENT_ROLE` table (delegate.py:32) keys on STILL
  ANOTHER vocabulary (`analytics.read`, `leads.enqueue_calls`, `ads.set_budget`) —
  so any intent it doesn't know falls to `_DEFAULT_ROLE="ops"`, a role whose scopes
  may not cover the tool -> runner `blocked:scope`/`unknown_tool`.
- FIX: drive the command row + delegation directly off the NLU `action_type` (which
  already equals the workforce tool-scope vocabulary — `identity.py` and
  `delegate._INTENT_ROLE` use that vocabulary), and EXPAND `_INTENT_ROLE` to cover
  every `INTENT_TO_ACTION` value in `nlu.py` (analytics.send_report, leads.update,
  calls.control, bookings.write, whatsapp.send_brochure/_followup, workflow.*, etc.).
  Stop funnelling through the lossy `_nlu_to_match`/driver enum for the dashboard
  execute path — that adapter exists for the (deferred) voice state machine, not for
  the HTTP test console.

### A4 (verify) — read commands (analytics/billing) return synthetic, not real data
- A "Wallet balance?" / "Aaj ka report" read routes to `analytics.read` /
  `wallet.read`. With A1 fixed + the read route live (`/analytics`, `/billing/overview`
  are GETs that don't need a FEATURE flag), the live catalog returns REAL data. Until
  A1 is fixed the read either 401s or (in stub mode) returns the hardcoded
  `{calls:83, conversions:4}` placeholder (`stub_tools.py:44`). Confirm the read path
  returns live figures after A1.

---

## B. WHY THE UI SHOWS RAW JSON, NOT HUMAN LANGUAGE (frontend + backend contract)

The FE is mostly RIGHT — `_tryit.tsx` `AiBubble` renders `p.user_facing_summary` as
the human line (line 555-557), risk as a plain-language Badge, entities as chips. The
JSON only appears in TWO places, and the EXECUTED case is the one the founder hits:

### B1 — the "Executed" block prints `execution_result` as raw JSON
- `_tryit.tsx:596-602`: after execute it renders
  `JSON.stringify(p.execution_result, null, 2)` in a `<pre>`. The backend's
  `execution_result` is `{status, executed, run_id}` (endpoints.py:301) — a machine
  blob, not a sentence. THIS is the "raw JSON" the founder sees post-PIN.
- ROOT of it on the backend: the command ROW returned by confirm/execute has NO
  human field. `_run_test_command` returns `user_facing_summary` on the FIRST parse,
  but `_transition_command` returns `_store.get_command()` whose SELECT
  (store.py:441) has `execution_result, error_message` and **no `user_facing_summary`
  column at all.** So the post-execute payload carries only the JSON blob.

### B2 — the fix (both ends)
- BACKEND (preferred, fixes voice + chat together): have `_transition_command`
  produce a human `user_facing_summary` for the executed/failed/cancelled outcome and
  return it on the response dict (it doesn't need a DB column — just add the key to
  the returned dict, e.g. build it from status + run result:
  "Done — today's report is on its way on WhatsApp." / "I couldn't do that yet —
  the Ads module isn't switched on for your account." / "Cancelled, nothing ran.").
  `delegate._normalize_result` already has `detail`/`reason`/`parked` to phrase from.
- FRONTEND: in the `executed` branch, render a human success line first and DROP the
  raw `<pre>` (or hide it behind the existing "JSON trace" toggle, which already
  exists at `_tryit.tsx:672` for power users). Specifically: show
  `p.user_facing_summary` (now populated post-execute by the backend fix) as the
  success sentence; keep `action_run_id` as a tiny mono caption; remove the
  `JSON.stringify(execution_result)` `<pre>` from the chat view. The "JSON trace" tab
  already gives the full object for debugging — the chat bubble must stay human.
- The human-summary field the backend ALREADY produces = `user_facing_summary`
  (nlu.py SCHEMA + `_run_test_command` return). The gap is purely that the
  confirm/execute hops don't re-emit it. Re-emit it (B2 backend) and render it
  (B2 frontend) and the chat is human end-to-end.

---

## ORDER TO FIX
1. A1 mint the run_token in the runner (without it, nothing executes — top priority).
2. A3 route execute off the NLU action_type + expand `_INTENT_ROLE` (so commands
   stop collapsing to clarify / mis-routing to `ops`).
3. A2 make the run result honest (don't report `done` when the only tool parked /
   `not_configured`), and turn on the target module FEATURE_* flags to actually act.
4. B2 emit + render `user_facing_summary` on execute; drop raw JSON from the chat bubble.
5. Re-run the U4 §23 samples on the box: a read returns real figures; a write on an
   ENABLED module truly lands (audit + action_run succeeded); a write on a disabled
   module says, in plain language, that the module is off — never a false "Executed".
