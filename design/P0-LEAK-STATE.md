# P0-LEAK — cross-tenant memory leak hotfix (inbound + WhatsApp, no earner restart)

Wave spec: `design/VOICE-BRAIN-MASTER-PLAN.md` §7 (P0-LEAK), red-team break #1/#5/#6.
Box: famit@168.144.153.145, source /opt/famit-agent/ (memory.py, caller.py).
EARNER GATE pre-wave PASS: agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED, PID 1477083 not restarted, /health 200.

## The leak
Phone memory (`memory.py:_path_for`) + WA threads (`caller.py:_wa_thread_path`) live at unprefixed `{phone}.json`
shared across tenants -> tenant A reads tenant B. Unknown inbound WA number -> ADMIN_ID default poisons admin thread.
Hardcoded agent name "Riya".

## Fix (ADDITIVE — un-restarted earner uses OLD memory.py and writes legacy paths; new readers must still
## find legacy files for the SAME tenant)
- memory.py `_path_for(phone, tenant_id=None)` -> `{tenant_id}/{phone}.json` when tenant given, else legacy `{phone}.json`.
- load_memory(phone, tenant_id=None): try tenant path; if absent, read legacy file ONLY IF its stored tenant_id
  matches OR is empty (claim+migrate). A legacy file owned by a DIFFERENT tenant is NOT returned. Migrate-on-read.
- save_memory(phone, history, summary, tenant_id=None): stamps tenant_id in record; writes tenant path when given.
- caller.py `_wa_thread_path(phone, tenant_id=None)` + same tenant-checked legacy fallback in `_wa_thread_read`.
- unknown WA number -> `_unrouted` (NEVER ADMIN_ID).
- `whatsapp_threads` glob -> recursive (**/*.json) for tenant subdirs.
- replace hardcoded "Riya" in WA brain with tenant/campaign agent name.

## Units
- [ ] U1 memory.py edit + py_compile + backup
- [ ] U2 caller.py WA path/recap/unrouted/Riya edits + py_compile + backup
- [ ] U3 deploy box (backup-first *.LEAKbak.<ts>), restart famit-caller + aim-voice-agent ONLY
- [ ] U4 earner gate after + verify
