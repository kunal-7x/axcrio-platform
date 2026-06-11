# WAVE — fix the 3 "still broken in the browser" founder flows (2026-06-11)

Standard this wave: a fix is DONE only when the FOUNDER UI->backend chain works (not an API bypass).
No git. Backup-first, regression-gated, rollback-ready. Backend (live earner) left untouched.

## VERDICT (per flow, user-level, live-proven)

### FLOW 1 — CONTROL LAYER (hide/lock a vendor page) — **FIXED + DEPLOYED + PASS**
The prior diagnosis (`design/fix-control-enforce.md`) was STALE. It claimed "nav has ZERO feature_key"
+ "EntitlementGuard wraps no page". Both already fixed by the premium-UI wave: nav carries feature_key,
`Sidebar/resolveNav` consumes it, and `RouteEntitlementGate` is mounted in `app/providers.tsx` (HIDE->
redirect "/", LOCK->LockOverlay).

**REAL root cause (newly found, live-proven): FE<->backend KEY MISMATCH on MODULE GROUP keys.**
The backend `/me/entitlements` `modes` map (source = `var/control/registry.json`) keys every MODULE as
`mod.grow` / `mod.sell` / `mod.engage` / `mod.ai_manager` / `mod.command` / `mod.automate` /
`mod.intelligence` (and billing as `money.billing_overview`). The premium-UI nav authored the BARE keys
`grow` / `sell` / ... which are ABSENT from the backend map -> `modeToEnt(undefined)`="ON" -> a module
HIDE never dropped the sidebar group header. (PAGE child keys `grow.campaigns`/`sell.leads`/... already
matched, so a page HIDE worked; a MODULE hide left an orphaned/empty group header = the founder's bug.)
The deployed live bundle was confirmed to contain `feature_key:"grow"` (10x) — i.e. the bug was live.

Backend is 100% correct (live-proven, tenant 013a13841fd5, port 8209, form-encoded admin write = the UI path):
- admin PUT mod.grow=hidden -> modes['mod.grow']=hidden, rolldown grow.campaigns=hidden, vendor GET /campaigns 404
- page grow.campaigns: hidden->404, locked->402, restore->200; admin bypass->200. ALL PASS.

**FIX (FE-only, 2 files):**
- `contstants/navigation.tsx`: module group feature_key grow->mod.grow, sell->mod.sell, engage->mod.engage,
  ai_manager->mod.ai_manager, automate->mod.automate, intelligence->mod.intelligence. (Command/Money/Foundation
  groups stay unkeyed/core.)
- `lib/api.ts FEATURE_REGISTRY`: module rows -> mod.*; money.billing -> money.billing_overview; parent_key
  refs updated; dropped stale integration.*/money.billing.pay rows; foundation.settings -> core.settings.
  (This feeds RouteEntitlementGate's pathname->key map + the CONTROL_ENABLED=0 fallback. With control LIVE the
  super-admin matrix already pulls the backend's own keys via /admin/vendors/{id}, so the WRITE path was always right.)

tsc EXITCODE=0, next build EXITCODE=0. Deployed to live panel (root@143.110.247.249:/opt/famit-panel) via
tarball of .next + scp of the 2 source files. Backup `.next.CLfixbak.20260611-183733` (+source *.CLfixbak.<ts>).
Deployed bundle verified: bare module keys = 0; `mod.grow` etc present. Panel localhost:3001/login 200,
panel.famit.in/login 200, service active.

FINAL FOUNDER FLOW (live): admin HIDE mod.grow -> vendor modes['mod.grow']=hidden (the deployed nav group key
reads exactly this -> resolveNav DROPS the Grow section) + child grow.campaigns rolled hidden + GET /campaigns 404;
ADMIN still 200; LOCK->402; RESTORE->all on/200. **PASS — the vendor genuinely no longer sees the section.**

### FLOW 2 — WORKFLOW BUILDER (add node + run) — **PASS** (already built; live-proven)
`design/fix-workflow-builder.md` was outdated: it said engine dormant (R1) + no blank/click-add/fullscreen.
ALL fixed in current code:
- Backend `/workflows` router MOUNTED (FEATURE_WORKFLOWS=1); GET /workflows/status 200 (engine in_process,
  store memory, hatchet dormant-until-creds).
- `_editor.tsx`: blankDefinition() (New=blank), click-to-add (`onClick addNode`), fullscreen portal
  (`fixed inset-0 z-[60]`) + Esc; `toDefinition()` emits trigger at top level (backend-valid); `saveWorkflow`
  PUTs `{draft:def}` (correct contract).
- LIVE CHAIN (vendor token): POST create->200 server wid; PUT {draft}->200; validate->200 ok:true
  reachable[n_trigger,n_delay]; publish->200 version:1 hash; **RUN->200 ok:true run_id wfr_... engine:in_process
  status:COMPLETED steps:2**; GET run->completed. Add node + save + publish + RUN executes with real status. PASS.

### FLOW 3 — WHATSAPP TEMPLATE (AI + manual) — **PASS** (live-proven)
- whatsapp_builder MOUNTED (FEATURE_WHATSAPP_BUILDER=1, prefix `/whatsapp/campaign`). builder/status 200:
  llm:ready, whatsapp:ready, meta_submit:ready, feature_enabled:true.
- AI generate (POST /whatsapp/campaign/{cid}/generate-templates) as ADMIN (funded wallet ₹5000):
  status:accepted, model groq llama-4-scout, **3 templates / 3 variations**, first template META-COMPLIANT
  (name/language/category MARKETING, TEXT header, body w/ {{1}}+example, footer, URL button) — the `validate`
  authority passed it. Manual path = select/edit/approve a variation + submit-to-meta (routes present).
- Credit-gated: a BROKE vendor (013a13841fd5, available ₹0) correctly returns status:error:insufficient_credits
  (est ₹4). That is by design (reserve()->insufficient_credits), NOT a defect — vendor just needs wallet credits.

### FLOW 4 — REGRESSION — **PASS**
Core /campaigns /leads /me /me/entitlements /calls all 200 (vendor token). famit-caller + famit-bridge (voice)
active. Zero 5xx/tracebacks. Test tenant left clean (overrides cleared). Temp test scripts removed from both boxes.

## ROLLBACK
Panel only (backend never touched): `cd /opt/famit-panel; rm -rf .next; mv .next.CLfixbak.20260611-183733 .next;`
restore the two `*.CLfixbak.20260611-183733` source files; `systemctl restart famit-panel`.

## Ledger: `caps/FIX_WAVE_STATE.md`.
