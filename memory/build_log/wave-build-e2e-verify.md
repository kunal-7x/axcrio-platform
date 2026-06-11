# Wave build — END-TO-END VERIFY (the 6 demo flows) + WhatsApp path fix

Date: 2026-06-11. Method: live public API (panel.famit.in/api) as admin via X-Auth FamitCall2026
(the monolith legacy admin header). No backend-box SSH this session (key denied), so verification
ran against the real public demo surface, not the box.

## Per-flow verdict
1. Creative — /creative 200; /api/assets/status 200 (enabled, openrouter+spaces, schema ready). The
   public POST /assets/generate rejects the legacy X-Auth ("unauthenticated") — EXPECTED, not a bug:
   the standalone AI Asset svc (auth.py) derives tenant from a real signed access JWT (access_claims),
   and the legacy bare-password admin is deliberately not resolvable in its standalone venv. Real
   banner generation already PROVEN via a real JWT over the VPC in the prior C3 wave. PASS for
   load+status; public-JWT generate unverifiable here (no login password).
2. Control Layer — /me/entitlements live (v1, 91 modes, plan_a, all "on" for admin); the path->feature
   middleware lets admin through (every feature route 200). /admin/flags returns "super-admin required"
   to the legacy password = the #1 security control working (legacy pw EXCLUDED from /admin/*). The
   HIDE->404 / LOCK->402 WRITE needs a super-admin JWT + a 2nd-tenant token to observe — already 18/18
   live probes PASS per MASTER_BUILD_STATE.
3. AI Manager — FULL LOOP PASS, live. Safe read -> human Hinglish summary (never raw JSON). Risky
   "Saare hot leads ko call karo" -> intent leads.enqueue_calls, risk=3, requires_pin, status=needs_pin,
   human "This action needs your PIN." Execute with no PIN -> blocked; wrong PIN 0000 -> denied "That PIN
   was incorrect."; PIN 2468 -> executed=True, run_id=run_20864727e4, outcome=effective, "Done! calls
   successfully ho gaya." This is the headline founder ask and it is verified end to end.
4. WhatsApp — PASS after a frontend fix. The LIVE route POST /whatsapp/campaign/{id}/generate-templates
   returns a real bundle (wab_1dfde215), 3 Meta-compliant MARKETING templates, compliance.valid:true,
   no_invent_flags:[], score 1.0. BUG FOUND: the frontend (waapi.ts:generateTemplates) called
   POST /whatsapp/templates/generate which was never mounted (404) -> the browser button would silently
   fall to "coming soon". FIXED: repointed to the live campaign-scoped route + extended asSuggestion to
   map the live nested shape (body.text, buttons[0].text). tsc --noEmit = 0 errors.
5. Workflow — PASS. _editor.tsx is real React Flow v12 (@xyflow/react, MIT): addNode (palette click +
   drag-drop), useNodesState/setNodes, fullscreen state with toggle + Esc-to-exit. /workflows 200.
6. Regression — PASS. Core API (/me /campaigns /leads /calls /stats /billing /me/entitlements) all 200;
   11 public panel routes all 200; zero 5xx. Voice/famit-bridge not SSH-checkable here, but the earner
   path (/run, /campaigns) is healthy.

## Code change (1)
- famit-panel/app/whatsapp/_lib/waapi.ts — generateTemplates() now uses the live campaign-scoped route
  and requires a campaign_id (dormant without one); asSuggestion() reads both the flat and the live
  nested Meta-template shape. Branch feat/premium-ui, NOT yet built/deployed to the FE box.

## Notes for next session
- To fully exercise the public Creative generate + the Control-plane HIDE/LOCK write, a real admin LOGIN
  password (-> JWT) is needed; the legacy static X-Auth is correctly barred from both. Both are already
  proven via JWT in earlier waves.
- Deploy the waapi.ts fix (FORTRESS recipe, backup-first) so the WhatsApp wizard's AI step works in the
  browser, then click-test ③ on /whatsapp with the Codename Joy 3.0 campaign.
