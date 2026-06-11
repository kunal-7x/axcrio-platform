# FIX-B — AI Manager EXECUTE truth + HUMAN summary + Campaign API (2026-06-11, LIVE on box 168.144.153.145)

Founder symptom: a command asks for PIN, he enters it, it says "done" but NOTHING happens;
and the reply shows raw JSON not human language. Diagnosis: `design/fix-ai-manager.md`.

## STARTING REALITY (source-of-truth = THE BOX, not droplet_work/)
By the time this ran, A1 (run_token mint) and A3 (route off NLU action_type + expanded
`_INTENT_ROLE`) were ALREADY DONE on the box from the prior B3 creative-wiring session:
- `ai_manager/delegate.execute` already mints `transport.mint_run_token(tenant_dict)` and threads it.
- `_INTENT_ROLE` already covers all INTENT_TO_ACTION values (workflow/booking/creative/etc.).
- `endpoints._aim_parse_card` (NOT the old lossy `_nlu_to_match`) already drives off `parse_intent`
  + `map_intent_to_action` and emits `user_facing_summary` at every parse state.
So the REMAINING real defects were: A2 (false "executed" on a parked no-op), A4 (reads returned
no real data), and B2-polish (generic/English summary; raw JSON `<pre>` on the FE — FE not touched here).

## WHAT THIS WAVE CHANGED (3 code files + 1 env line)
Backups on box: `*.FIXBbak.1781167858` (runner.py, delegate.py, endpoints.py) + `.env.FIXBbak.*`.

### 1. `workforce/runner.py` — TRUTH-IN-REPORTING (A2) + return read DATA (A4)
The runner finalized `status="done"` even when its only tool returned `{ok:False, reason:"not_configured"}`
(a parked module, e.g. FEATURE_ADS off). The PG `list_steps` strips the tool `result` body, so the
run-level result must carry the truth itself. Added (all ADDITIVE — existing callers ignore unknown keys):
- counters `tools_ok / tools_failed / last_tool_reason` in the loop (classify each tool by `result.get("ok")`;
  unknown_tool + exec_error count as failed).
- `last_tool_data = _redact(result)` on the last SUCCESSFUL tool — so a safe read's body returns to the caller.
- finalize `result={outcome, tools_ok, tools_failed, last_reason, data}` where
  `outcome = "effective" (a tool landed) | "noop" (all parked/failed) | "empty"`. STATUS stays "done"
  for back-compat; truth rides in `result`.

### 2. `ai_manager/delegate.py` `_normalize_result` — hoist the truth
Reads `detail.outcome/last_reason/data` and computes `effective = (status=="done" AND outcome=="effective")`.
Returns `{..., outcome, last_reason, effective, data}`. A parked (awaiting_approval) or done-but-noop run
is NOT effective.

### 3. `ai_manager/endpoints.py` — honest status + Hinglish summary + execute reads inline
- `commands_execute`: `executed = result.effective` (NOT bare `status=="done"`). Audit n_actions only when
  effective. `user_facing_summary = _aim_human_outcome(tool, effective, reason)`.
- NEW helpers `_TOOL_LABEL` / `_REASON_HUMAN` / `_aim_human_outcome` / `_scrub_read_data`: Hinglish
  business-tone success/failure lines. reason normalized (`transport_error:Conn...`->`transport_error`).
- `_aim_parse_card` QUERY branch now EXECUTES the read inline (reads are safe: no PIN/spend/idempotent)
  via `delegate.execute`, returns REAL `data` + a human summary + `status:"executed"`. (Was: a "ready"
  card with no data.)

### 4. `.env` — `AIASSET_LOOPBACK_BASE=http://10.122.0.4:8310`
ROOT CAUSE of the creative no-op: the AI Asset Service binds to the VPC IP `10.122.0.4:8310`, but
`workforce/config.asset_service_base()` defaults to `127.0.0.1:8310` and the var was absent -> every
creative.* call got `transport_error:ConnectionError` -> honest noop. Setting the VPC base restored the
live banner path (the B3 note's E2E success — the var had been lost). ENV-only, no code.

## PROVEN LIVE (X-Auth admin, PIN 2468 enrolled this session)
- READ "aaj ka report": `executed:True`, summary "Ho gaya — aaj ka performance report ready hai..."
  + REAL data `{dialed:99,connected:85,interested:20,funnel:[...]}`.
- READ "wallet balance": REAL `{available:57.59, held:0.0, lifetime_spend:42.41, plan:postpaid}`.
- COMMAND creative banner + PIN 2468: `outcome:effective`, `executed:True`, "Done! ad banner successfully
  ho gaya.", run_id; asset svc logged `POST /generate -> 200` (real side effect).
- COMMAND ads budget + PIN 2468 (FEATURE_ADS off / spend gate): `awaiting_approval`, `executed:False`,
  HONEST "Abhi ad budget update nahi ho paaya — is spend ke liye extra approval pending hai." (NO false success).
- BLOCKED "show my api key": risk 4, blocked, never executes.
- WRONG PIN: denied, "That PIN was incorrect. Cancelling that action.", never executes.

## CAMPAIGN API (founder ask #3) — backend already serves both shapes cleanly, NO backend change
- LIST `GET /campaigns` -> `{campaigns:[{id,name,company,product,status,created_at,tenant_id,voice_id}]}` (8 live, clean).
- DETAIL `GET /campaigns/{id}` -> `{campaign:{id,name,company,product,status,created_at,system_prompt,
  fields:{company_name,product_name,product_summary,goal,location,price_offer,usps,value_prop,language,
  agent_name,wa_template_*,...}}}` — RICH, real, the right source for the generator.
- ⚠ CORRECTION to `design/fix-campaign-dropdown.md`: `GET /assets/campaign-context` does NOT exist on the
  box (asset svc :8310 has only /generate + regenerate; returns 404). The FE `getCampaignContext()` always
  404->falls back to client `contextFromCampaign`. The REAL per-campaign detail endpoint is `/campaigns/{id}`
  (with the rich `fields`). FE CampaignSelect should fetch `/campaigns/{id}` for detail, not campaign-context.

## REGRESSION (GREEN)
core `/me /campaigns /leads` 200, `POST /run/preview` 200; both services active (famit-caller + famit-bridge);
agent.py + caller.py byte-untouched. ONLY 5xx in window = `/funnels/{id}/run` (a real user on funnels UI;
pre-existing, unrelated to ai_manager/workforce/campaigns). FIX-B paths: zero 5xx.

## DEFERRED / NOTES
- A spend command (ads.set_budget amount>0) is RE-PARKED by the runner's own gate (awaiting_approval) even
  with a valid AIM step-up token, because the runner requires a matched APPROVAL ROW, not just a task
  step_up_token. This is defense-in-depth and now reported HONESTLY (not a false "executed"). Wiring the
  AIM step-up -> a runner approval row (resume path) is a separate, deferred unit. Reads + creative (no
  reserve) execute fully today.
- FE (`_tryit.tsx`): backend now guarantees a human `user_facing_summary` + structured `data` on every
  execute/read response, so the FE can drop the raw `JSON.stringify(execution_result)` `<pre>` and render
  `user_facing_summary` + (for reads) `data`. FE not edited in this backend wave.
