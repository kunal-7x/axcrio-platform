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

## Units — ALL DONE (commit 4db497f)
- [x] U1 memory.py _path_for(phone,tenant_id) + tenant-checked legacy fallback + migrate-on-read + build_recap(agent_name). Self-test + on-box smoke PASS.
- [x] U2 caller.py WA path/read/write tenant-scoped + _unrouted (no ADMIN_ID) + recursive glob + admin _wa_thread_find_any + tenant-scoped _wa_memory_recap w/ campaign agent name. Self-test PASS.
- [x] U2b aim_voice_agent.py (inbound, restarted) load/save_memory tenant-scoped to resolved call tenant + recap label = configured agent voice.
- [x] U3 deployed box 168.144.153.145 (backups *.LEAKbak.20260614-052257), md5-gated, restarted famit-caller + aim-voice-agent ONLY. famit-agent PID 1477083 untouched.
- [x] U4 EARNER GATE before+after PASS: agent.py md5 9150fabe... UNCHANGED, PID 1477083 not restarted, /health 200, aim re-registered clean (worker 23:55:19), no 5xx. gitleaks 0.

## How the tenant-check prevents the leak
load_memory/_wa_thread_read prefer {tenant}/{phone}.json. On miss they read the legacy flat {phone}.json
but return it ONLY IF its stored tenant_id == this tenant OR is empty (unowned -> claim+migrate). A legacy
file whose tenant_id is a DIFFERENT tenant returns None/{} -> tenant A can never read tenant B. Unknown WA
number -> _unrouted bucket, never ADMIN_ID.

## How legacy/earner-written files still load for the same tenant
The un-restarted earner runs the OLD memory.py and writes legacy flat {phone}.json with tenant_id="" (or
absent). A new tenant-aware reader treats an empty/absent owner as "unclaimed" -> returns it AND migrates it
into {tenant}/{phone}.json. So returning leads keep their memory; only cross-tenant reads are blocked.
