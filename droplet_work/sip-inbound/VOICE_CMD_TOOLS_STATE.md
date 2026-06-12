# Voice Command Tools — attach real manager tools to inbound aim-voice-agent (queue #4-voice)

GOAL: after PIN, the inbound `manager` voice agent can run REAL work by voice via @function_tools
that call the SAME backend the chat Test Console uses. run_campaign -> the PROVEN `POST /run` dial path.

## BASELINE (regression gate)
- earner agent.py md5 = 9150fabe4ff62b4b4470f9a87df346e5 (MUST stay unchanged)
- services active: famit-agent, aim-voice-agent, famit-caller
- caller.py on port 8209; loopback auth = `X-Auth: FamitCall2026` (admin tenant) -> 200
- real data confirmed over loopback: /leads (5, 5 hot), /stats (134 total/8 camp), /wallet (₹4942.34), /campaigns (8; Codename Joy 3.0 = c17e55e9f3)

## DESIGN
- NEW helper `ai_manager/voice_tools.py` — thin loopback HTTP client (httpx) to caller.py:8209 with
  admin X-Auth. Functions: list_campaigns, resolve_campaign(name)->id, lead_counts(cid),
  recent_calls, analytics, wallet_status, run_campaign(cid, segment, count) [the /run dial path].
  segment map: all->source_mode=all ; hot/warm/cold-> read /leads, filter by score, take first N,
  pass explicit lead_ids to /run (preview==dials, count honored).
- EDIT `aim_voice_agent.py` ManagerAgent: add @function_tools:
  - check_leads / lead_counts (safe read, no extra PIN)
  - recent_calls, analytics, wallet_status (safe reads)
  - run_campaign(campaign, segment, count) — RISKY: requires self._verified (verify_pin gate) +
    spoken read-back confirm before dialing. Calls voice_tools.run_campaign -> /run.
  - (defer send_whatsapp/create_campaign unless time)
- ISOLATION: edit aim_voice_agent.py + add voice_tools.py ONLY. Reuse caller routes READ-ONLY over HTTP.
  NEVER touch agent.py / outbound earner / trunks / firewall / SIP. Restart ONLY aim-voice-agent.

## STEPS
1. [DONE] explore: routes/auth/data confirmed
2. [DONE] write voice_tools.py + edit aim_voice_agent.py (local mirror) — py_compile OK
3. [DONE] backup-first (aim_voice_agent.py.CMDbak.20260612-134700) + deployed both files + restarted aim-voice-agent ONLY
4. [DONE] VERIFY: 7 tools registered on ManagerAgent (verify_pin, manager_status, check_leads, recent_calls,
   analytics, wallet_status, run_campaign); worker re-registered clean (AW_74Jcb6yUmKBF agent_name=manager);
   read tools return REAL data (leads 5/5hot, wallet ₹4942.34, analytics 134/42/75, resolve Codename Joy->c17e55e9f3);
   run_campaign->/run dispatch PROVED RINGS (job bc282a53c8 -> room famit-917861019021-3c63a8, capsy connected,
   Codename Joy opener spoken, tts_ttfb 0.237s).
5. [DONE] REGRESSION-GATE BEFORE+AFTER: real outbound to +917861019021 RANG both (before room -4b3138 ttfb 0.213s;
   after room -7ec966 ttfb 0.212s); agent.py md5 9150fabe... UNCHANGED; all 4 services active; 0 5xx.
6. [IN PROGRESS] commit + append MASTER_BUILD_STATE.md

## RESULT = DONE. Box backup: /opt/famit-agent/aim_voice_agent.py.CMDbak.20260612-134700.
## ROLLBACK: restore that .CMDbak + rm /opt/famit-agent/ai_manager/voice_tools.py + restart aim-voice-agent.
