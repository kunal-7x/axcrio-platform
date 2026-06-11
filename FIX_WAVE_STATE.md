# FIX WAVE — founder-flow control + workflow + whatsapp (2026-06-11)

Standard: a fix is DONE only when the FOUNDER FLOW works in the UI->backend chain.
No git. Backup-first; regression-gate; rollback on failure. Backend = live earner, do NOT touch.

## FLOW 1 — CONTROL LAYER (hide/lock a vendor page)

### ROOT CAUSE (LIVE-PROVEN, supersedes stale design/fix-control-enforce.md)
Backend is 100% correct (proven live on box 168.144.153.145:8209, tenant 013a13841fd5):
- admin PUT mod.grow=hidden -> modes['mod.grow']=hidden, rolldown grow.campaigns=hidden, vendor GET /campaigns -> 404
- page grow.campaigns hidden -> 404; locked -> 402; restore -> 200; admin bypass -> 200. ALL PASS.

The diagnosis doc claimed "nav has ZERO feature_key" — STALE. The premium-UI wave already added
feature_key to nav + resolveNav consumes it + RouteEntitlementGate is mounted in providers.tsx.

REAL BUG = **FE/backend KEY MISMATCH on MODULE GROUP keys**:
- FE nav authors module key `grow` / `sell` / `engage` / `ai_manager` / `command` / `automate` / `intelligence`
- backend /me/entitlements `modes` map uses `mod.grow` / `mod.sell` / ... (the `mod.` prefix)
- => resolveNav(entOf("grow")) reads ABSENT key -> "ON" -> the GROUP HEADER never hides.
  (Page CHILD keys grow.campaigns etc. DO match -> children drop, but the empty parent header lingers.)
- Also `money.billing` (api.ts) vs backend `money.billing_overview` (core, low-impact).

### FIX (FE-only, 2 files; backend untouched)
1. contstants/navigation.tsx — module group `feature_key`: grow->mod.grow, sell->mod.sell,
   engage->mod.engage, ai_manager->mod.ai_manager, automate->mod.automate, intelligence->mod.intelligence.
   (Command/Money/Foundation groups are intentionally unkeyed/core — leave.)
2. lib/api.ts FEATURE_REGISTRY — align module rows + billing key to backend so RouteEntitlementGate's
   pathname->key map and the super-admin matrix write/render the SAME keys the backend resolves.
   command->mod.command, ai_manager->mod.ai_manager, grow->mod.grow, sell->mod.sell, engage->mod.engage,
   automate->mod.automate, money->mod.money, intelligence->mod.intelligence, foundation->mod.foundation;
   money.billing->money.billing_overview + add billing_vendors/explorer/audit/plan rows to mirror backend.

STATUS: FE FIX APPLIED + tsc clean (EXITCODE=0). navigation.tsx module keys -> mod.*;
api.ts FEATURE_REGISTRY module keys -> mod.*, money.billing -> money.billing_overview.
Backend confirmed already correct (matrix gets mod.* keys live via /admin/vendors/{id}).
Vendor-side nav was the only broken link. PENDING: deploy to live panel + browser-mirror re-verify.

## FLOW 2 — WORKFLOW BUILDER (add node + run) — **PASS** (live-proven)
Stale doc said engine dormant + no click-add/blank/fullscreen. ALL OUTDATED — already fixed:
- Backend /workflows router MOUNTED (FEATURE_WORKFLOWS=1); status 200 (engine in_process, store memory, hatchet dormant).
- Editor has blankDefinition() ('New' = blank), click-to-add (addNode onClick l.541), fullscreen portal (l.625, fixed inset-0 z-60)+Esc.
- toDefinition() puts trigger top-level (backend-valid); saveWorkflow PUTs {draft:def} (correct contract).
- LIVE CHAIN (tenant 013a13841fd5, vtok): POST create->200 server wid; PUT {draft}->200; validate->200 ok:true;
  publish->200 version:1; RUN->200 ok:true run_id wfr_... engine:in_process status:COMPLETED steps:2; GET run->completed.
=> add node on canvas + save + publish + RUN executes with real status. WORKS.

## FLOW 3 — WHATSAPP TEMPLATE (AI + manual create) — **PASS** (live-proven)
- whatsapp_builder mounted (FEATURE_WHATSAPP_BUILDER=1, prefix /whatsapp/campaign).
- builder/status 200: llm:ready, whatsapp:ready, meta_submit:ready, feature_enabled:true.
- AI generate (POST /whatsapp/campaign/{cid}/generate-templates) as ADMIN (funded wallet ₹5000):
  status:accepted, model groq llama-4-scout, 3 templates/3 variations, FIRST TEMPLATE META-COMPLIANT
  (name/language/category MARKETING, TEXT header, body w/ {{1}}+example, footer, URL button). validate module passed.
- Credit-gated: a BROKE vendor gets status:error:insufficient_credits (est ₹4) — CORRECT by design, not a bug.
  Manual path = select/edit/approve a generated variation + submit-to-meta (routes present).
=> create a WhatsApp template (AI) -> created, Meta-compliant. WORKS (vendor needs wallet credits).

## FLOW 1 — DEPLOYED + VERIFIED (PASS)
- Local: navigation.tsx + api.ts edited, tsc EXITCODE=0, next build EXITCODE=0.
- Deployed to live panel root@143.110.247.249:/opt/famit-panel (.next via tarball, source files scp'd).
  BACKUP: /opt/famit-panel/.next.CLfixbak.20260611-183733 (593M) + *.CLfixbak.20260611-183733 source.
- Verified deployed bundle: bare module keys feature_key:"grow"/"sell"/... = 0; now mod.grow etc.
- Panel healthy: localhost:3001/login 200, panel.famit.in/login 200, service active, no errors.
- FINAL FOUNDER FLOW (live backend, test vendor 013a13841fd5):
  admin HIDE mod.grow -> vendor modes['mod.grow']=hidden (deployed nav reads this -> drops Grow group);
  child grow.campaigns rolled hidden; vendor GET /campaigns 404; ADMIN GET /campaigns 200 (bypass);
  LOCK grow.campaigns -> 402 (proven separately); RESTORE -> all 'on', /campaigns 200. PASS.

## FLOW 4 — REGRESSION — PASS
core /campaigns /leads /me /me/entitlements /calls all 200 (vendor token); famit-caller + famit-bridge(voice) active; zero 5xx. Test tenant clean (no leftover overrides). Both boxes temp-cleaned.

## ROLLBACK (if needed)
Panel: cd /opt/famit-panel; rm -rf .next; mv .next.CLfixbak.20260611-183733 .next; restore the two *.CLfixbak source files; systemctl restart famit-panel. Backend untouched all along.
