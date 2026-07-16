# BUILD QUEUE #5 — Customer (sales) mode + test_call_me

Box: famit@168.144.153.145 (key C:/Users/kunal/.ssh/do-blr-test/id_ed25519)
Edit ONLY: /opt/famit-agent/aim_voice_agent.py  + new helper ai_manager/customer_brain.py + small additions to ai_manager/voice_tools.py
READ-ONLY: agent.py / prompt.py / memory.py / caller.py / registry / firewall / trunks / SIP
Regression-gate (G): famit-agent active + real outbound dial to +917861019021 RINGS + agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED + core 200 + 0 5xx, BEFORE+AFTER.
Restart ONLY aim-voice-agent.

## Reuse seams (verified)
- classify: ai_manager.identity.resolve(caller_id) -> registry row (manager) | None (customer). Already wired aim_voice_agent.py:664.
- prompt.build_system_prompt(fields:dict) -> full sales brain. fields = campaign json "fields".
- memory.load_memory(digits)/build_recap(mem)/save_memory(digits,history,summary). digits = re.sub non-digit.
- voice_tools: list_campaigns()/resolve_campaign()/_camp_name()/campaign_details() reads /campaigns/{id} (has fields)/run_campaign()/_get()/_post_form().
- caller HTTP: GET /campaigns (no fields), GET /campaigns/{id} ({campaign:{...fields}}), GET /calls, GET /leads, POST /leads (Form leads="name,phone"), POST /run (Form leads="name,phone" OR campaign_id+lead_ids).
- /run dials an ad-hoc phone via leads="name,phone" + campaign_id + force=1.

## Plan (additive, isolated)
1. [G-BEFORE] regression gate. -- IN PROGRESS
2. ai_manager/voice_tools.py: add resolve_contact_by_phone(phone), campaign_fields(spoken|id), active_campaigns(), create_lead(name,phone,campaign_id), test_call(name,phone,campaign_id).
3. aim_voice_agent.py: add CustomerSalesAgent (build instructions from build_system_prompt(fields)+recap; returning vs new; one-active short-circuit; on-end create/update lead+save_memory). classify branch in _entrypoint_impl -> CustomerSalesAgent for non-managers.
4. aim_voice_agent.py ManagerAgent: add test_call_me @function_tool -> voice_tools.test_call(manager caller-id).
5. py_compile, backup *.CUST2bak.<ts>, restart aim-voice-agent.
6. SMOKE: non-manager caller -> sales greeting (no PIN); manager caller -> ManagerAgent PIN; test_call_me -> /run dispatch.
7. [G-AFTER] regression gate. Commit. Append MASTER_BUILD_STATE.md.

## Progress log
- (init) all seams read; baseline md5 9150fabe4ff62b4b4470f9a87df346e5; both services active.
- [G-BEFORE] DONE GREEN: /run job a6f171c526 -> capsy worker connected room famit-917861019021-* lead=calling (founder RINGS). core 200, famit-agent active, md5 unchanged.
- Step2 DONE: voice_tools.py += resolve_contact_by_phone/campaign_fields/active_campaigns/create_lead/test_call. Backups *.CUST2bak.20260612-093259. py_compile OK, import OK, live smoke OK (resolve +917861019021 -> Codename Joy returning lead; active_campaigns real; campaign_fields full).
- Step3/4 DONE: aim_voice_agent.py += import prompt/memory (READ-ONLY); CustomerSalesAgent (build_sales_instructions reuses prompt.build_system_prompt(fields)+PICHHLI recap; pick_campaign/remember_name/capture_interest tools); entrypoint customer-branch (returning lead -> recap+continue; one-active short-circuit; else disambiguate); customer greeting (returning/new/disambig); on-disconnect persist (save_memory merge + create_lead); DTMF guarded to managers; ManagerAgent += test_call_me tool (-> voice_tools.test_call manager caller-id via /run). py_compile OK, full module import OK (15275-char reused brain w/ PICHHLI).
- DEPLOY DONE: in-place + restart aim-voice-agent via sudo -n. registered worker agent_name=manager, NRestarts=0, no errors. agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED.
- SMOKE DONE: manager +917861019021 -> ManagerAgent (PIN); non-manager +919876500111 -> CustomerSalesAgent -> "Aap kis project ke baare mein jaanna chahte hain?" (NO PIN); returning resolve -> Codename Joy recap; test_call_me -> /run job ae7643e866 -> capsy room famit-917861019021-5ddc84 RINGS founder.
- [G-AFTER] DONE GREEN: md5 unchanged, famit-agent+aim-voice-agent active, /stats+/campaigns 200, zero 5xx, earner RINGS (a6f171c526 + ae7643e866). agent.py only IMPORTED-never-edited (imported prompt+memory; agent.py NOT imported nor edited). COMPLETE.
