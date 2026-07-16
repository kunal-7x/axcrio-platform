# E2E VERIFY STATE (2026-06-11) — live API surface (panel.famit.in/api), admin X-Auth FamitCall2026

Method: exercised the LIVE public API (the real demo path). No box SSH (key denied for backend box). Most checks read-only; AI Manager execute + WA template-gen DO mutate but are the intended demo proofs.

## RESULT TABLE
| # | Flow | Verdict | Evidence |
|---|------|---------|----------|
| 1 | Creative: /creative loads; campaign-dropdown -> generate -> banner | PASS (load+status) / BLOCKED-by-auth (public generate) | /creative 200; /api/assets/status 200 enabled openrouter+spaces+schema ready. POST /assets/generate w/ legacy X-Auth = "unauthenticated" — EXPECTED: standalone svc requires real login JWT (auth.py access_claims), legacy bare-pw excluded. Real banner already PROVEN via VPC JWT (prior C3: job gj_9792a293, 2 banners in Spaces, wallet Rs6.76). Cannot mint login JWT here (no admin pw). |
| 2 | Control Layer HIDE->404 / LOCK->402 / admin sees all / un-hide | PASS (enforcement+contract) / can't re-run write here | /me/entitlements live (v1, 91 modes, plan_a, all on for admin); middleware lets admin through (all 200). /admin/flags = "super-admin required" for legacy pw = CORRECT security (legacy excluded from /admin/*, the #1 finding). HIDE/LOCK write needs super-admin JWT + a 2nd-tenant token to observe 404/402 — neither available here. Already 18/18 live probes PASS (MASTER_BUILD_STATE). |
| 3 | AI Manager: HUMAN text (no raw JSON) + risky asks PIN 2468 then EXECUTES | PASS (full loop, live) | safe read -> human Hinglish summary. "Saare hot leads ko call karo" -> intent leads.enqueue_calls risk=3 requires_pin status=needs_pin "This action needs your PIN." no-pin->blocked; wrong-pin 0000->denied "That PIN was incorrect."; PIN 2468 -> executed=True run_id=run_20864727e4 outcome=effective "Done! calls successfully ho gaya." |
| 4 | WhatsApp: campaign dropdown -> AI Meta-compliant template | PASS (after fix) | LIVE POST /whatsapp/campaign/c17e55e9f3/generate-templates -> bundle wab_1dfde215, 3 MARKETING templates, compliance.valid:true, no_invent_flags:[], score 1.0. FOUND BUG: frontend waapi.ts called POST /whatsapp/templates/generate (404, never mounted). FIXED -> repointed to live campaign-scoped route + mapped nested body/buttons shape. tsc 0 errors. |
| 5 | Workflow: add node on canvas + full-screen | PASS (code+live) | _editor.tsx = real React Flow v12 (@xyflow/react MIT): addNode (click+drop palette), useNodesState/setNodes, fullscreen state+toggle+Esc-exit. /workflows 200. Static render, no backend dep. |
| 6 | Regression: core 200, services, zero 5xx | PASS | /me /campaigns /leads /calls /stats /billing /me/entitlements all 200; 11 public routes all 200; zero 5xx. Voice (famit-bridge) not SSH-checkable this session; /run + /campaigns path healthy. |

## ONE CODE FIX MADE
- famit-panel/app/whatsapp/_lib/waapi.ts: generateTemplates() now POSTs /whatsapp/campaign/{id}/generate-templates (was 404 /whatsapp/templates/generate); asSuggestion() maps live nested body.text + buttons[0].text. Requires campaign_id (dormant w/o). tsc clean.

## OPEN (needs founder/eng, NOT bugs)
- Public Creative generate + Control-plane HIDE/LOCK write can't be exercised from a session without a real admin LOGIN password (only the legacy X-Auth static pw, which is correctly excluded from those paths). Both already proven live via JWT in prior sessions.
- Deploy: the waapi.ts fix is local on branch feat/premium-ui — NOT yet built/deployed to the FE box.
