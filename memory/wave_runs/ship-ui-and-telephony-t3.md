# Ship pending UI + Telephony T3 — wave run log

Spec: `design/TELEPHONY-INDEPENDENCE-PLAN.md` §5 (T3 row) + §3 red-team B1/D/E/F + the T2 log
`memory/wave_runs/telephony-foundation-t1-t2.md` (NEXT=T3 spec). Branch `fe/unify-run-wavec`.
Flag `TRUNK_REGISTRY_ENABLED` default OFF (resting byte-identical). caller.py edited FROM the
box golden (`ef9ae696`, the video-wave Video-API mount already present). agent.py (`9150fabe`)
NEVER imported/touched. Box `famit@168.144.153.145`, key `do-blr-test/id_ed25519`.

## T3 — additive trunk_registry mount in caller.py (flag OFF)

**Status:** IN PROGRESS.


### THE DELIVERABLE — trunk_registry/endpoints.py (NEW) + additive caller.py mount

**Status:** DONE + DEPLOYED (flag OFF, resting byte-identical). 2026-06-15.

**Endpoints (16 routes, one token-deriving `build_router`, prefix `/trunk-registry`):**
VENDOR/TENANT surface (resolve_tenant, RLS is_admin=False):
- `GET  /trunk-registry`                          — list trunks (own + `_global`, masked creds).
- `GET  /trunk-registry/health`                   — per-trunk circuit/quarantine/eligibility diag.
- `POST /trunk-registry/byo`                       — add a BYO-number SIP trunk (sip_provider only;
  SSRF-validated sip_host; SIP password scope='integration'; is_campaign_eligible stays DB-derived).
- `PUT  /trunk-registry/{id}`                      — update an owned trunk (re-SSRF on host change).
- `DELETE /trunk-registry/{id}` (default soft-disable; `?hard=1` refuses `_global`/undeletable/env-
  protected + requires PIN step-up) — RED-TEAM D.
- `POST /trunk-registry/{id}/credential`           — store/rotate the SIP password (integration).
- `POST /trunk-registry/{id}/reveal-init`          — mint 60s aud-bound single-use trunk.reveal token.
- `POST /trunk-registry/{id}/reveal`               — reveal plaintext SIP pw (PIN step-up; integration-
  only; replay→403) — firewall.consume_reveal_step_up.
- `POST /trunk-registry/{id}/test-call`            — RED-TEAM F: single founder-typed test ring, rate-
  limited ≤3/hr/trunk (in-proc), purpose='test' (skips B1 gate), NEVER auto-dials (intent-only at T3;
  single dial wires at T5).
- `POST /trunk-registry/{id}/quarantine-did`       — RED-TEAM E: per-DID kill switch (rest a number).
- `POST /trunk-registry/{id}/release-quarantine`   — release the rest.
SUPER-ADMIN surface (require_super_admin — excludes legacy `FamitCall2026`, control-security #1):
- `GET  /trunk-registry/admin/all`                 — all tenants + `_global`.
- `POST /trunk-registry/admin`                     — create any trunk (gsm/direct_sip/`_global`; SSRF).
- `PUT  /trunk-registry/admin/{id}`                — update any trunk (set DLT fields / soft-disable).
- `POST /trunk-registry/admin/{id}/reveal`         — reveal any SIP cred (PIN step-up; audited).
- `GET  /trunk-registry/admin/health`              — per-trunk state across all tenants.

**Mount file:lines (caller.py.LIVEBOX golden, box `/opt/famit-agent/caller.py`):**
- The additive mount block = `caller.py:7349-7393` (45 lines inserted right AFTER the provider-registry
  mount `:7327-7346`, BEFORE the video-studio mount). Import-guarded (`try: from trunk_registry.endpoints
  import build_router … except: None`), flag-guarded (`TRUNK_REGISTRY_ENABLED` via `cfg_get`, default OFF),
  wrapped `try/except` so a mount failure can NEVER crash startup. Injects the SAME helpers as the
  provider-registry twin: `resolve_tenant, can, need_auth, _forbidden, require_super_admin=require_super_admin,
  firewall=_firewall_mod, audit=_audit`.

**caller.py additive golden-diff (box golden `ef9ae696` → T3 `44b867ea`):** `7349a7350,7394` —
**0 deletions, 45 additions** (the single mount block). NOTHING else changed; no existing route/line
touched. New box caller.py md5 = `44b867eaa3a448792a82c9760db0d76b`.

**Deploy (FORTRESS recipe, famit-caller ONLY):**
- Edited FROM the box golden (`ef9ae696` == box; PLAYBOOK r16). Backup `caller.py.T3bak.20260615-004201`
  + `.env.T3flagbak` (used during the flag-on proof, then restored). No prior trunk_registry dir on box.
- tarball (13 py modules, no `__pycache__`) + caller scp→/tmp → md5-gate (caller staged == local
  `44b867ea`) → box-venv (`/opt/capsy-agent/.venv`, Py 3.12.3) py_compile package + caller = OK →
  import-smoke `trunk_registry __version__ 0.2.0-t2` + `build_router import OK` → atomic swap (package +
  caller) → chown famit:famit → dormancy import-smoke `config.is_enabled()=False`.
- Restarted **famit-caller ONLY** (PID 2774834 → 2797157 → [flag-proof] → 2797344, NRestarts=0).
  famit-agent (1477083), aim-voice-agent (2739156), famit-aiasset (2768818) ALL UNTOUCHED.
- `TRUNK_REGISTRY_ENABLED` NOT in `.env` (absent → default OFF → resting byte-identical end-state).

**Flag-OFF dormancy (LIVE):** `/trunk-registry`, `/trunk-registry/byo`, `/trunk-registry/health` all
= **404** (router not mounted). Legacy `/campaigns` = 401 (run-path intact). Resting byte-identical.

**Flag-ON proof (temp .env flip + restart, then REVERTED to dormant):** every route AUTH-GATED — list
401, health 401, byo POST 401, admin/all 401, test-call 401 (mounted, NOT 404; NOT 500). caller /health
200. **0 5xx, 0 mount failures** in the journal. Reverted: `.env` restored (flag absent), routes 404
again, /health 200.

**31/31 trunk_registry offline suites still PASS** (9 registry + 8 concurrency + 14 rotation/livekit) —
no regression from adding endpoints.py. NEW endpoints helper unit-checks PASS (rate-limit ≤3/hr +
window-prune + per-trunk isolation; privileged-type gate). gitleaks staged = 0.

### EARNER GATE — BEFORE + AFTER = ALL PASS
| Check | Before | After |
|---|---|---|
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` | `9150fabe…` UNCHANGED |
| famit-agent MainPID | 1477083 NRestarts=0 | 1477083 NOT restarted, active |
| famit-caller MainPID | 2774834 | 2797344 (restarted only this) NRestarts=0 |
| caller.py md5 | `ef9ae696` | `44b867ea` (T3) |
| caller /health (8209) | 200 | 200 |
| 5xx (caller, recent) | 0 | 0 (10 min) |
| trunk-registry routes | n/a | 404 (flag OFF dormant) |
| ring | none | NO ring (no calls) |
| aim-voice / aiasset | active | 2739156 / 2768818 UNTOUCHED |

ROLLBACK: leave `TRUNK_REGISTRY_ENABLED` absent/0 (instant — already the resting state). To remove the
code: restore `/opt/famit-agent/caller.py.T3bak.20260615-004201`, `rm -rf /opt/famit-agent/trunk_registry`,
restart famit-caller.

NEXT: T4 (Telephony FE — `app/telephony/page.tsx` Core_2 port: trunk cards + 3-step add-trunk wizard +
founder test-call + reputation panel + DID kill switch) → T0 (scheduler_loop retry-bug fix, HARD GATE) →
T5 (strangler `caller.py:2913` dial-loop cut + wire `place_test_call` seam, real founder ring before+after).

## Phase: VERIFY (2026-06-15) — PASS

### Panel edge (8/8 pages = 200 PASS)
/integrations=200, /super-admin/integrations=200, /creative/video=200, /run=200, /crm=200, /ai-manager=200, /workflows=200, /knowledge=200. BUILD_ID `u6yKGIuhALhhzdzQcywXQ`.

### Trunk-registry flag-OFF dormancy (PASS)
GET /trunk-registry=404, GET /trunk-registry/health=404, POST /trunk-registry/byo=404. Legacy GET /campaigns=401 intact. TRUNK_REGISTRY_ENABLED: ABSENT from .env (confirmed via grep = no output). caller /health=200.

### Trunk-registry flag-ON auth-gate (PASS)
All 5 sampled routes: GET /trunk-registry=401, GET /trunk-registry/health=401, POST /trunk-registry/byo=401, GET /trunk-registry/admin/all=401, POST /trunk-registry/admin=401. caller /health=200. 0 5xx in journal.
Note: systemctl restart did NOT re-exec the process (PID unchanged); required kill -9 + systemd Restart=always to get a fresh PID with the new env. Flag reverted (ABSENT) after proof — new PID confirmed dormant (404).

### Earner gate FINAL (PASS)
- agent.py md5: 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED
- famit-agent MainPID: 1477083, NRestarts: 0, NOT restarted
- caller.py md5: 44b867ea (T3)
- famit-caller /health: 200
- 0 5xx, NO ring

### Docs updated
- design/TELEPHONY-INDEPENDENCE-PLAN.md → T3 row DONE
- design/VIDEO-STUDIO-MASTER-PLAN.md → U6 DEPLOYED
- ORCHESTRATOR.md → wave block appended
- AGENT_LEARNINGS.md → lessons (t)–(x) appended
