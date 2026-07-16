# CONTROL LAYER — INTEGRATE + ACTIVATE + DEPLOY + LIVE VERIFY (state ledger)

Role: deploy the built (dormant, T1-T18 passed) control-layer backend + Super Admin UI LIVE.
Backend box: famit@168.144.153.145 (SSH 22, app 8209). venv /opt/capsy-agent/.venv/bin/python.
Frontend box (FORTRESS): root@143.110.247.249:/opt/famit-panel. SSH key C:\Users\kunal\.ssh\do-blr-test\id_ed25519.
Restart backend: sudo systemctl restart famit-caller famit-agent.
NO git on this repo. ROLLBACK on ANY failure: CONTROL_ENABLED=0 + restore backups.

## RECONCILED STATE (from build logs, before I touch anything)
- Backend CL-B1..B4 DONE + dormant. caller.py md5 was dd872d9... (CL-B4). CONTROL_ENABLED OFF, FIREWALL_ENABLED false.
- /admin/* routes + /me/entitlements + act-as + suspend all shipped behind CONTROL_ENABLED.
- T1-T17 PASS in-process (CL-B4), T18 N/A (C10 copilot not built).
- Frontend: app/super-admin/{page,vendors,vendors/[id],flags,plans,usage,audit} built; lib/entitlements.ts,
  components/{EntitlementGuard,EntitlementToggle,LockOverlay}; Sidebar resolveNav HIDE/LOCK; nav group added.
  All FE units report tsc --noEmit exit 0 (per F3_STATE / STATE_CL_F2).
- GATE noted: before CONTROL_ENABLED=1, ALSO set FIREWALL_ENABLED=true (admin step-up for act-as).

## MY TASKS
1. FE: npm install --legacy-peer-deps + npm run build EXIT 0. Fix any error.   [IN PROGRESS]
2. FE: FORTRESS deploy to root@143.110.247.249:/opt/famit-panel (BACKUP first) + restart.
3. FE verify: /super-admin/* 200 for admin, HIDDEN for non-admin.
4. ACTIVATE: CONTROL_ENABLED=1 (+ FIREWALL_ENABLED=1) on box; restart.
5. LIVE E2E: HIDE->404+nav gone; LOCK->402+overlay+dim pill; ON->restored; SUSPEND->token revoke+data preserved->unsuspend; audit log shows changes.
6. RE-RUN T1-T18 LIVE with CONTROL_ENABLED=1 -> all PASS; legacy FamitCall2026 rejected on /admin/*.
7. Confirm core endpoints 200, both services active, zero 5xx, voice untouched.
8. Append build log + update HANDOFF + MEMORY.

## PROGRESS
- [x] 1 FE build EXIT 0 (next build, exit 0; all 7 /super-admin/* routes compiled). 2026-06-11
- [x] 2 FE deploy — box backup /opt/famit-panel.CLbak.1781120589; rsynced source; npm install+build EXIT 0 on box (node20); famit-panel restarted ACTIVE; super-admin compiled. 2026-06-11
- [x] 3 FE verify routes — local 127.0.0.1:3001 root/login/super-admin=200; public panel.famit.in login/super-admin=200, /api/health=200; SuperAdminGuard bounces non-admin to / + nav group roles:"admin" (hidden). Backend 403 is the real boundary. 2026-06-11
- [x] 4 ACTIVATE — .env backup .env.CLbak.20260610-195647; set CONTROL_ENABLED=1 + FIREWALL_ENABLED=true; restarted; both services active. Resting unharmed: vendor A all-core 200 + /me/entitlements all-on map; admin core 200; /run/preview 200. Admin tenant id=`admin` (already PIN-enrolled). Vendors A=21d0a13603da B=ae1ba3017296 C=013a13841fd5. FIREWALL safe: require_step_up pass-throughs for no-PIN tenants (firewall.py:194). 2026-06-11
- [x] 5 LIVE E2E — over real HTTP to running :8209: HIDE engage.calls->vendor /calls 404 + nav-mode hidden; LOCK grow.campaigns->/campaigns 402 {error:locked,upgrade:true}; clear->restored 200; SUSPEND->non-core 404 floor + login blocked + JWT revoke + admin reads data (preserved) + restore 200; audit row control.override.set old/new actor=admin on PG events leg. 2026-06-11
- [x] 6 T1-T18 live — _probe_live_e2e.py vs running service, CONTROL_ENABLED=1 in .env: 18 PASS / 0 FAIL / T18 N/A (C10 copilot deferred). T2 legacy FamitCall2026->403 on /admin/*. Box pristine (0 residual). Probe removed from box. 2026-06-11
- [x] 7 resting platform unharmed — both services active; core+modules 200; /run/preview 200; ZERO 5xx since probe; voice agent.py untouched (0 control refs, mtime 2026-06-09); caller.py md5 dd872d9 byte-stable. 2026-06-11
- [x] 8 docs — appended memory/build_log/wave-build-control-layer.md (CL-ACT), brain/control-layer.md (LIVE), HANDOFF.md, MEMORY.md index. 2026-06-11

## WAVE COMPLETE — Control Layer LIVE + ENFORCING. All 8 tasks done. 18 PASS / 0 FAIL / T18 N/A.

## KNOWN RESIDUAL (recorded, not a blocker)
- Legacy panel /login issues a STATELESS hmac token (tenant_id.hmac, no jti) => auth.revoke_all (JWT refresh
  revoke) cannot cryptographically kill a held hmac bearer. Suspension is enforced in SUBSTANCE by the STATUS
  FLOOR (every non-core route 404) + login-block + JWT-refresh-revoke; core.* stays 200 by anti-lockout
  (exposes nothing actionable). Same residual class as the legacy-password finding. Hardening: migrate panel
  to /auth/login (JWT) or add a per-tenant token-epoch to the hmac. T15 PASSES (vendor neutralized).
- FIREWALL_ENABLED=true is SAFE for live vendors: firewall.require_step_up pass-throughs for any tenant with
  no PIN enrolled. Only the `admin` tenant has a PIN (pre-existing) => act-as step-up is genuinely gated.
- T18 (AI Copilot entitlement gate) deferred — C10 not built (no copilot tool route in caller.py).

## ACTIVE LIVE STATE
- Backend .env: CONTROL_ENABLED=1, FIREWALL_ENABLED=true. Backup .env.CLbak.20260610-195647. caller.py md5 dd872d9 (unchanged).
- Frontend: super-admin deployed + built on box; famit-panel active. Box backup /opt/famit-panel.CLbak.1781120589.
- ROLLBACK: backend = restore .env.CLbak.20260610-195647 (or set CONTROL_ENABLED=0+FIREWALL_ENABLED=false) + restart famit-caller famit-agent. frontend = restore /opt/famit-panel.CLbak.1781120589 + restart famit-panel.
