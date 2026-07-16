# FIX — WhatsApp template create (cannot create a template)

**Status:** ROOT CAUSE FOUND — live UI->backend chain reproduced (no API bypass).
**Date:** 2026-06-11. **Verdict:** Backend route is LIVE and works. **The DEPLOYED
frontend calls a DEAD route → always 404 → silent "Coming Soon".** FE-only fix +
redeploy. Backend untouched.

---

## TL;DR (the one broken link)

The deployed WhatsApp builder's "Generate templates" action fires
`POST /api/whatsapp/templates/generate` — a route that was **NEVER mounted** on the
backend (returns **404**). `safePost` swallows the 404 as `{configured:false}`, so
the Templates step renders the premium **ComingSoon** card and no template is ever
generated. The founder sees "can't create a template."

The CORRECT, LIVE route is campaign-scoped:
`POST /api/whatsapp/campaign/{id}/generate-templates` → **200** with real AI
templates. A FIXED `waapi.ts` that calls this route **exists locally but is
UNTRACKED and was never committed/deployed**. The live box still serves the old
build.

---

## What the live reproduction proved (curl = exact browser chain, X-Auth = token)

Live `https://panel.famit.in/api`, admin token `FamitCall2026`:

| Call (what the UI does) | Result |
|---|---|
| `GET /campaigns` (CampaignSelect dropdown source) | **200**, 3+ campaigns → dropdown POPULATES |
| `GET /me/entitlements` → `engage.whatsapp` | `on` (vendor not blocked from the module) |
| `POST /whatsapp/templates/generate` (n,campaign_id as multipart) — **DEPLOYED UI calls THIS** | **404 `{"detail":"Not Found"}`** ← the break |
| `POST /whatsapp/campaign/test123/generate-templates` (JSON {n}) — **the route that actually exists** | **200** with `templates:[…]` (real Meta-shape: name/header/body/buttons) |

Deployed-box proof (`root@143.110.247.249:/opt/famit-panel`):
- `.next/static` bundle contains **only** the string `whatsapp/templates/generate`
  (the dead route). It contains **no** `whatsapp/campaign/.../generate-templates`.
- `app/whatsapp/_lib/waapi.ts:152` on the box = `safePost("/whatsapp/templates/generate", …)`.
- So the shipped JS the founder runs in the browser calls the 404 route, every time.

Net effect: dropdown works, campaign context shows, user clicks **Generate
templates** → 404 → dormant → **"Coming Soon" card**. No template. The only thing
that "works" is the dormant card's **"Write one manually"** fallback → the Preview
step (free-text body/CTA/footer/language), which is the manual path but is buried
behind a coming-soon wall that shouldn't be there.

---

## ROOT CAUSE (12 lines)

1. The WhatsApp builder has two template-gen route names in history.
2. OLD (committed + DEPLOYED): `POST /whatsapp/templates/generate` (multipart).
3. That route was **never mounted** on the backend → **404** on every call.
4. NEW/correct (LIVE on backend): `POST /whatsapp/campaign/{id}/generate-templates` (JSON).
5. A fixed `waapi.ts` calling the NEW route exists **only locally and UNTRACKED**
   (`git status` = `?? app/whatsapp/_lib/`), so it was never committed or deployed.
6. The live box still serves the OLD `.next` build → UI hits the dead route.
7. `safePost` treats 404 as a dormant feature (`DORMANT_STATUS` includes 404) and
   returns `{configured:false}` instead of surfacing an error.
8. `TemplatesStep` maps `!configured` → the **ComingSoon** card, so the failure is
   invisible; it looks like an unfinished feature, not a broken call.
9. The campaign **dropdown is NOT the problem** — `GET /api/campaigns` = 200 and
   `CampaignSelect` populates correctly.
10. Entitlements are NOT the problem here — `engage.whatsapp` = `on`; the call 404s
    on the route name, not on control enforcement.
11. There is **no separate "manual create-a-template" object**; the only manual path
    is PreviewStep (per-send free-text draft), currently reachable only via the
    dormant fallback.
12. Fix = ship the campaign-scoped route from the FE (commit + redeploy), handle the
    empty/insufficient-credits 200, and expose the manual path without the
    coming-soon wall.

---

## THE FIX (frontend only — backend already correct; redeploy required)

### Fix A — call the route that exists (the load-bearing change)
The local untracked `app/whatsapp/_lib/waapi.ts` already has the right
implementation — **commit it and redeploy**. The function must POST JSON to the
campaign-scoped route and require a `campaign_id`:

```ts
// generateTemplates(): require campaign_id, POST JSON to the LIVE route
if (!input.campaign_id) return { configured: false, reason: "no_campaign" };
const body = { n: input.n ?? 4, objective, audience, language }; // omit empties
return safePost(
  `/whatsapp/campaign/${encodeURIComponent(input.campaign_id)}/generate-templates`,
  body,                       // JSON, not FormData
  (data) => ({ suggestions: (data.templates ?? data.suggestions ?? []).map(asSuggestion),
               rationale: data.rationale })
);
```
The local `asSuggestion` already reads the Meta shape (`body.text`, `buttons[0].text`).
**This single change makes AI template generation work end-to-end.**

### Fix B — surface the real failures instead of a false "Coming Soon"
The live route can return **200 with `status:"error:insufficient_credits"`,
`templates:[]`** (wallet low) — and the current code treats that as `configured:true`
with zero cards (silent blank). Patch `generateTemplates` + `TemplatesStep`:
- If the 200 body has `error`/`status:"error:*"` or `templates:[]`, return a typed
  result the step can show as a real message (e.g. "Add credits to generate" with a
  retry / Top-up link) — **not** the dormant card, and **not** a blank grid.
- Keep `{configured:false}` → ComingSoon ONLY for genuine 404/503 (route truly
  absent on a given box), with the **"Write one manually"** fallback intact.

### Fix C — make the MANUAL create path first-class (founder may want it directly)
Today the only "create a template by hand" path is PreviewStep, reachable solely
through the dormant card. Add an always-present **"Write one manually"** button on
the Templates step (next to / under "Generate"), so the founder can author a
template (body / CTA / CTA-URL / footer / language, with live PhonePreview) WITHOUT
needing AI. No backend needed — PreviewStep already renders + advances to approval.

### Do NOT change
- `GET /api/campaigns`, `CampaignSelect`, `getCampaignContext` — dropdown is fine.
- The backend. `POST /whatsapp/campaign/{id}/generate-templates` is LIVE and correct.
- The dormant-degrade machinery for the genuinely-unbuilt steps (Creative, Banner,
  Approval-of-asset, Analytics) — those legitimately stay ComingSoon.

---

## DEPLOY + VERIFY (founder flow, in the browser — not API)
1. Commit the untracked `app/whatsapp/_lib/`, `_steps/`, `_components/`, and the
   modified `page.tsx`. `npm install --legacy-peer-deps` → `npm run build`.
2. Deploy via FORTRESS recipe to `root@143.110.247.249:/opt/famit-panel` (BACKUP
   first: `cp -a /opt/famit-panel /opt/famit-panel.bak.$(date +%s)`), restart
   `famit-panel.service`. Regression-gate: `/campaigns /leads /me` 200, no 5xx.
3. In the browser: WhatsApp → **Campaign** step → pick a campaign from the dropdown
   (it populates) → **Generate templates**.
   - EXPECT: 3–5 AI template cards (today: "Coming Soon").
   - If wallet low: a clear "add credits" message + working **Write one manually**
     button (today: silent blank / coming-soon).
4. "Write one manually" → Preview → edit body/CTA → **send for approval** works
   without AI.

## One-line summary
The deployed UI posts to the un-mounted `/whatsapp/templates/generate` (404→silent
ComingSoon); the working route is `/whatsapp/campaign/{id}/generate-templates`
(200). Commit the already-fixed local `waapi.ts`, handle the empty/insufficient-
credits 200, expose the manual "Write one manually" path, and redeploy. FE-only;
never touch the backend.
