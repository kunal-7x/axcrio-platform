# CUSTOMER (SALES) MODE — BUILD STATE (Queue #5)

Box: famit@168.144.153.145  key C:\Users\kunal\.ssh\do-blr-test\id_ed25519
Edit ONLY: /opt/famit-agent/aim_voice_agent.py  (+ NEW /opt/famit-agent/ai_manager/sales_flow.py)
REUSE READ-ONLY: agent.py (_load_campaign, AgentSession kwargs, _summarize), prompt.py (build_system_prompt),
  memory.py (load_memory/build_recap/save_memory), registry.lookup, calls.json/leads.json/campaigns/*.json.
NEVER edit: agent.py, trunks, firewall, SIP, earner.

## REGRESSION GATE (G) — run BEFORE and AFTER
- famit-agent is-active == active
- outbound place_call.py +917861019021 => INVITE emitted / Riya opener spoken (rings)
- agent.py md5 == 9150fabe4ff62b4b4470f9a87df346e5  (UNCHANGED)
- zero new 5xx in famit-agent log

## BASELINE (BEFORE) — CAPTURED 2026-06-12 07:31 UTC  [GREEN]
- famit-agent active; aim-voice-agent active
- agent.py md5 = 9150fabe4ff62b4b4470f9a87df346e5
- ring test: job AJ_4UiU3MSdmUx8 room famit-917861019021-9f5182 => opener spoken, STT connected, tts_ttfb 0.215s; 2nd attempt 486 Busy. EARNER RINGS.
- 5xx: 0

## CLASSIFY (decided)
- registry.lookup(caller_id) returns verified+active row with role in (admin, manager) => MANAGER => existing CommandMachine/PIN path (UNCHANGED).
- else => CUSTOMER SALES flow (new).
- Both founder numbers (+917861019021, 06375548830) ARE registered admins => correctly route to MANAGER. Non-registered numbers => CUSTOMER.

## SMOKE FIXTURES (non-PSTN LiveKit harness; AIM_SMOKE_CALLER_ID env injects caller-id)
- returning customer: 917987388671 (colin / Jabalpur Property cid=480e846dc8, has memory) -> sales greeting + recap
- returning customer: 916375538830 (kunal / Premium 2/3BHK cid=d81d1da4d6, has memory)
- new customer:       919900112233 (no memory, no calls) -> asks "kis project ke baare mein?"
- manager:            +917861019021 -> PIN greeting (unchanged)

## ACTIVE CAMPAIGNS = status=="ready" (7 of 8). >1 ready => ASK; ==1 => short-circuit.

## TASKS
- [DONE] read plans + box files + baseline gate BEFORE (green)
- [IN PROGRESS] write ai_manager/sales_flow.py (self-contained read-only helpers + sales AgentSession runner)
- [ ] wire classify + customer branch into aim_voice_agent.py (after caller-id read + greet)
- [ ] py_compile both; backup-first (*.CUSTbak.<ts>)
- [ ] restart ONLY aim-voice-agent
- [ ] SMOKE harness: returning -> recap greeting; new -> which-campaign; manager -> PIN
- [ ] gate AFTER (green) ; commit ; append MASTER_BUILD_STATE.md

## DESIGN NOTES
- DO NOT import caller.py into the worker (5500-line FastAPI module, heavy globals). Re-implement the 4 tiny
  read-only helpers in sales_flow.py against the SAME var/*.json file formats (norm, resolve_contact, list ready
  campaigns, lead upsert append). This is the SAME pattern aim_voice_agent already uses (it re-implements _canon/_match_forms).
- Sales AgentSession mirrors agent.py kwargs (already mirrored in aim_voice_agent._entrypoint_impl); reuse the worker's
  own _build_tts/_build_stt + the same low-latency kwargs. The ONE difference vs manager session: the Agent gets a
  campaign system prompt (build_system_prompt(fields)) + PICHHLI BAAT recap, and there is NO CommandMachine/PIN.
- Name capture: the sales prompt asks the name in-call; on hangup we parse turns for a name OR fall back to existing
  lead name; lead upserted to leads.json {id,tenant_id,name,phone,status,added_at, campaign_id, source:"inbound"}.
- On hangup: merge prior memory.history + this call's turns -> save_memory(key, merged, summary) so the thread grows.
- import caller.py is FORBIDDEN here; sales_flow.py reuses memory.py + agent._load_campaign + prompt.build_system_prompt
  ONLY (those are light, safe imports), and reads var json directly for contact/campaign/lead.
