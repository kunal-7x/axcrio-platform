# ROUND-5 P4 — BACKEND WIRING (caller.py + ai_manager/endpoints.py) — STATE

Box: famit@168.144.153.145 :8209 famit-caller. Earner = famit-agent (NEVER restart; agent.py md5 48bc2b5a).
Backups (TS=20260619-144346): caller.py.R5P4bak.20260619-144346, ai_manager/endpoints.py.R5P4bak.20260619-144346
Live md5 pre-edit: caller.py 8f6bb1d0 ; endpoints.py 740a9aac

## ITEMS
1. /report add hot_leads + temperature_distribution + totals.{hot,warm,cold,dead}+by_status — IN PROGRESS
   - caller.py /report route (6034). Merge _REPSVC.hot_leads() + compute temp dist from totals. ADDITIVE.
   - FE wants: temperature_distribution:[{tier,count,pct,delta}], hot_leads:[{call_id,name,phone_masked,...}], totals{hot,warm,cold,dead}, by_status{hot,warm,cold,dead}
2. _finalize_call CRM upsert (2971) — wire crm.upsert_contact(tenant,phone,name=) — PENDING
3. sort_by+order on /calls (5700) /contacts (4047) /leads (5296) — PENDING
   - calls sort_by: name|campaign_name|status|started_at|duration_s|interest ; order asc|desc
   - contacts sort_by: name|temperature|stage|campaign|score|last_outcome|last_activity_at ; translate to crm sort
   - leads: FE sends `sort` (legacy, works). Add sort_by+order additive.
4. AI-Manager endpoints.py:
   - POST /numbers EXISTS (135) works. GET /ai-manager/numbers=401 (mounted, OK).
   - POST /ai-manager/pin/set MISSING (404) -> ADD {user_id,pin,admin}. Reuse firewall. PENDING
   - /commands/test (531) LLM-driven natural reply (no jargon). AIM_LLM_PROVIDER=groq already live.
     Make user_facing_summary always natural + grounded in caller._AIM_LIVE live data. PENDING
5. callbacks VISIBLE — ALREADY WORKS (legacy path: callback_at -> RETRY_FILE reason=callback -> /callbacks).
   CALLBACK_CADENCE_ENABLED unset (OFF), RETRY_SCHEDULER_ENABLED=0. 1 callback row live. VERIFY-ONLY.

## EDIT STATUS (all coded + py_compile OK local)
1. /report enrich — DONE (caller.py: _enrich_report_temperature helper + route merge)
2. _finalize_call CRM upsert — DONE (caller.py: crm.upsert_contact after _update_lead_after_call)
3. sort_by+order — DONE (caller.py: /calls + /contacts + /leads)
4a. POST /ai-manager/pin/set + /pin/verify — DONE (endpoints.py, firewall.set_pin, accepts user_id/admin)
4b. /commands/test LLM-driven — DONE (endpoints.py: _aim_llm_answer grounded in caller._AIM_LIVE,
    gated AIM_TRYIT_LLM=1 default, runs for query/clarify; write-cmds keep deterministic flow;
    removed jargon from query fallback + intent field)
5. callbacks — VERIFY-ONLY (already works via legacy RETRY_FILE path)

## DEPLOY
py_compile both -> scp to box -> sudo systemctl restart famit-caller ONLY -> /health 200 + agent.py md5 unchanged + famit-agent active + 0 errors.
ROLLBACK: cp *.R5P4bak.20260619-144346 back + restart famit-caller.
