# AIM #6 — ACCESS + PIN CHANGE (founder-requested) — BUILD STATE

Branch: backend/handoff-name-clean-line
Box: famit@168.144.153.145  /opt/famit-agent/  (caller.py, firewall.py)
caller listen: 127.0.0.1:8209 (uvicorn). Restart famit-caller ONLY.

## EARNER GATE BASELINE (must stay unchanged)
- agent.py md5 = 9150fabe4ff62b4b4470f9a87df346e5  (UNCHANGED)
- famit-agent MainPID = 1477083, NRestarts=0, ActiveEnter Wed 2026-06-10 19:58:18 UTC (NOT restarted)
- caller /health = 200, 0 5xx
- DID resting — NO ring (founder's job)

## BASELINE md5 (pre-change)
- box firewall.py = 1ac4f69917de05d074e3c10a983663d3  (== local mirror)
- box caller.py   = 1185562eabf1a06ed3e75fd94314b144  (== local mirror)

## PART 2 — AIM numbers CRUD mount — DONE/CONFIRMED (no work)
- AIM router mounted at caller.py:7376-7385 behind FEATURE_AI_MANAGER (=1 LIVE).
- Token-derived (caller.resolve_tenant(request) -> t["tenant_id"], NEVER body). Verified.
- Routes: GET /ai-manager/numbers (list, can=read), POST /ai-manager/numbers (add, can=write),
  POST /ai-manager/numbers/{id}/revoke (remove/lock, can=manage_tenants + firewall step-up),
  POST /ai-manager/numbers/{id}/grants. (No DELETE verb; removal = revoke.)
- LIVE smoke: GET /ai-manager/numbers unauth = 401 (mounted+gated). PASS.

## PART 1 — POST /firewall/pin/change — IN PROGRESS
Plan (ADDITIVE only; existing check_pin/set_pin/mint/verify/require_step_up stay BYTE-IDENTICAL):
- [ ] firewall.py: add lockout store (var/pin_lockout.json) + change_pin() orchestrator
      (uses EXISTING check_pin to verify old, EXISTING set_pin for new). NEW funcs only.
- [ ] caller.py: add @app.post("/firewall/pin/change") after /firewall/pin.
      body {old_pin, new_pin}; verify old via check_pin; lockout after 5 fails (time-boxed);
      audit firewall.pin.change (+ firewall.pin.change.fail / .locked). Tenant/role scoped.
- [ ] PROVE existing PIN verify byte-identical: diff the check_pin/set_pin/mint/verify/require_step_up
      bytes before vs after (unchanged region hash).
- [ ] py_compile both. Deploy box (backup firewall.py.bak + caller.py.bak). Restart famit-caller ONLY.
- [ ] EARNER GATE after. Commit.

## ROLLBACK
restore /opt/famit-agent/firewall.py.bak + caller.py.bak ; systemctl restart famit-caller
