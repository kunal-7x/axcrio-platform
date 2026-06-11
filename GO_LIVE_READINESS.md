# GO-LIVE READINESS AUDIT
Date: 2026-06-10 | Branch: feat/premium-ui

---

## 1. BUILD RESULT

**BUILD: GREEN — exit 0**

```
✓ Compiled successfully
✓ Generating static pages (33/33)
```

**34 total routes** (33 app routes + /icon.png static):

| Route | Type |
|---|---|
| / (Dashboard) | Dynamic |
| /ads | Dynamic |
| /ai-manager | Dynamic |
| /analytics | Dynamic |
| /billing (+ /audit /explorer /overview /plan /vendors /vendors/[id]) | Dynamic |
| /booking | Dynamic |
| /callbacks | Dynamic |
| /calls | Dynamic |
| /campaigns | Dynamic |
| /crm + /crm/[id] | Dynamic |
| /forms + /forms/[id] | Dynamic |
| /funnels | Dynamic |
| /leads | Dynamic |
| /login | Dynamic |
| /payments | Dynamic |
| /run | Dynamic |
| /settings | Dynamic |
| /support | Dynamic |
| /suppression | Dynamic |
| /vendors | Dynamic |
| /webhooks | Dynamic |
| /whatsapp | Dynamic |
| /workflows | Dynamic |
| /_not-found | Dynamic |
| /icon.png | Static |

No TypeScript errors. No compilation warnings. Zero failing routes.

---

## 2. DORMANT-SAFE AUDIT — Per Module Page

### Method
For each of the 9 new module pages, the colocated `_lib.ts` / `api.ts` / `client.ts` / `_api.ts` fetch helper was audited for: (a) how it calls the backend, (b) what it does on HTTP 404 (router not mounted), and (c) whether the page component handles that result without crashing.

---

### ads — `app/ads/page.tsx` + `app/ads/_lib.ts`
**VERDICT: GREEN**

- Fetch helper: `app/ads/_lib.ts` — `apiGet` / `apiPost`
- On 404/501/503: returns `{ kind: "dormant", reason: "http_404" }` — never throws
- On network error: catch block returns `{ kind: "dormant", reason: "unreachable" }`
- Page renders a premium "not configured / coming soon" state when `kind === "dormant"`
- Comment in `_lib.ts`: *"404 (router not mounted) or 501/503 (feature off) => dormant, render coming-soon"*

---

### ai-manager — `app/ai-manager/page.tsx` + `app/ai-manager/_lib.ts`
**VERDICT: GREEN**

- Fetch helper: `app/ai-manager/_lib.ts` — `apiGet` / `apiPost`
- On 404/501/503: returns `{ kind: "dormant", reason: "http_N" }` — never throws
- On network error: catch → `{ kind: "dormant", reason: "unreachable" }`
- Page renders premium dormant/coming-soon state on any dormant result

---

### booking — `app/booking/page.tsx` + `app/booking/api.ts`
**VERDICT: GREEN**

- Fetch helper: `app/booking/api.ts` — defines `DORMANT` sentinel `{ status: "not_configured" }`
- On 404/network: helper resolves to the `DORMANT` sentinel — never throws
- `app/booking/api.ts:173`: *"Core GET helper that NEVER throws for dormant/unmounted backends. A 404 (router not mounted) or a network error resolves to a dormant sentinel"*
- Page sets `dormant = true` and renders activation panel + KPI cards showing "—"
- Mutations on dormant show a toast "Booking engine not available" — no crash

---

### crm — `app/crm/page.tsx` + `app/crm/client.ts`
**VERDICT: GREEN**

- Fetch helper: `app/crm/client.ts` — discriminates: 501/503/network → `CrmDormantError`; genuine 404 (known-mounted route) → `NotFoundError`
- Comment: *"crm routes ARE mounted in caller.py, so a 404 on a detail/timeline/nba call means 'this contact doesn't exist', NOT dormant"*
- Page: `app/crm/page.tsx:72` — `catch (e) { if (e instanceof CrmDormantError) { setDormant(true) } }`
- When `dormant=true`, page renders a "Dormant" tab state showing 0 contacts — no crash
- **Note:** CRM routes (F2) ARE already mounted — dormant state here means PG down, not router off. Not one of the 9 FEATURE_* gated modules.

---

### forms — `app/forms/page.tsx` + `app/forms/client.ts`
**VERDICT: GREEN**

- Fetch helper: `app/forms/client.ts` — 404/501/503/network → throws `FormsDormantError`
- Page: `app/forms/page.tsx:75-79` — `catch (e) { if (e instanceof FormsDormantError) { setDormant(true) } }`
- When `dormant=true`, renders premium "coming soon" panel — no crash
- Mutations blocked by `writable && !dormant` guard

---

### funnels — `app/funnels/page.tsx` + `app/funnels/_lib.ts`
**VERDICT: GREEN**

- Fetch helper: `app/funnels/_lib.ts` — `apiGet`: 404/501/503 → `{ kind: "dormant", reason: "http_N" }`; network error → `{ kind: "dormant", reason: "unreachable" }`
- Page: `moduleDormant = status?.kind === "dormant" && (funnels?.kind === "dormant" || funnels === null)`
- Renders `<ComingSoon />` component when dormant — no crash
- Static stage pipeline + starter templates rendered from local data (no fetch needed)

---

### payments — `app/payments/page.tsx` + `app/payments/_api.ts`
**VERDICT: GREEN**

- Fetch helper: `app/payments/_api.ts` — on 404 throws `PaymentsUnavailable` (a typed class, not generic Error)
- Page: `app/payments/page.tsx:83-97` — `Promise.allSettled` + filter: *"treat as dormant (same calm UX as not_configured)"*
  - Any `PaymentsUnavailable` rejection → `connected = false` (dormant state)
  - Only genuine non-dormant errors surfaced as error banner
- Renders dormant graceful state when `!connected` — no crash

---

### support — `app/support/page.tsx` + `app/support/api.ts`
**VERDICT: GREEN**

- Fetch helper: `app/support/api.ts` — `fetchHealth()` returns `null` on ANY failure (404/network/error)
- Page: `dormant = healthChecked && health === null` → renders `<ComingSoon />` — no crash
- List/detail calls tolerate 404/network without throwing (return empty arrays / null)
- `app/support/api.ts:16`: *"every call therefore tolerates a 404 / network failure WITHOUT throwing"*

---

### workflows — `app/workflows/page.tsx` + `app/workflows/_lib.ts`
**VERDICT: GREEN**

- Fetch helper: `app/workflows/_lib.ts` — `apiGet`: 404/501/503 → `{ kind: "dormant" }`; network → `{ kind: "dormant" }`
- Page: `moduleDormant = status?.kind === "dormant" && workflows?.kind === "dormant" && runs?.kind === "dormant"`
- Renders premium dormant/configuration board when dormant — no crash
- Canvas renders a local sample workflow definition (no fetch required)

---

### Summary Table

| Module Page | Dormant-Safe | Fetch file | On 404 |
|---|---|---|---|
| /ads | **GREEN** | `app/ads/_lib.ts` | returns `{kind:"dormant"}`, page shows coming-soon |
| /ai-manager | **GREEN** | `app/ai-manager/_lib.ts` | returns `{kind:"dormant"}`, page shows coming-soon |
| /booking | **GREEN** | `app/booking/api.ts:185` | resolves to `DORMANT` sentinel, page sets `dormant=true` |
| /crm | **GREEN** | `app/crm/client.ts:57` | throws `CrmDormantError`, page catches at line 72 |
| /forms | **GREEN** | `app/forms/client.ts:74` | throws `FormsDormantError`, page catches at line 75 |
| /funnels | **GREEN** | `app/funnels/_lib.ts:268` | returns `{kind:"dormant"}`, page shows ComingSoon |
| /payments | **GREEN** | `app/payments/_api.ts:50` | throws `PaymentsUnavailable`, page catches via allSettled:83 |
| /support | **GREEN** | `app/support/api.ts:156` | returns `null`, page dormant=true at line 781 |
| /workflows | **GREEN** | `app/workflows/_lib.ts` | returns `{kind:"dormant"}`, page shows config board |

**All 9 pages: GREEN. Zero RED. Safe to deploy while backends are flag-OFF.**

---

## 3. GO-LIVE MATRIX

Source: `REMAINING_MODULES_BUILD_STATE.md §D` + backend mount-safety analysis.

| Module | Frontend Dormant-Safe | Backend Creds to ACTIVATE | Cred Source | Backend Mount-Ready? | Cred-Free Activatable? |
|---|---|---|---|---|---|
| **ai-manager** | GREEN | `AIM_SERVICE_TOKEN` (dashboard service auth); voice: `AIM_VOICE_DID`, `AIM_VOICE_SIP_TRUNK_ID`, `AIM_VOICE_AGENT_NAME`; `AIM_OTP_PROVIDER`, `AIM_LLM_PROVIDER` | Generate `AIM_SERVICE_TOKEN` (random token, no 3rd party) — founder action; LLM reuses `GROQ_API_KEY*` already on box | Bare-OK mount | **YES** — generate one token; runs on existing Groq |
| **workflow-studio** | GREEN | `HATCHET_CLIENT_TOKEN`, `HATCHET_CLIENT_HOST_PORT` = `10.122.0.3:7077` (for durable engine; in-process interpreter works WITHOUT these) | Token on hatchet box; VPC address known — see `brain/orchestration-hatchet.md` | `build_router(...)` + `attach_event_bridge(app)` | **YES** — in-process interpreter needs NO creds; Hatchet token retrievable from box |
| **forms-surveys** | GREEN | `FORMS_CAPTCHA_PROVIDER`, `FORMS_CAPTCHA_SECRET` (optional — captcha off by default); `FORMS_NOTIFY_ENABLE` | All optional/env-only, no 3rd-party sign-up required to run core | `build_router(resolve_tenant, can, need_auth, forbidden)` | **YES** — captcha is optional; core form CRUD + submit works cred-free |
| **support** | GREEN | `GROQ_API_KEY*` already on box; channel tokens `SUPPORT_VOICE_INGEST_TOKEN`, `SUPPORT_WEB_WIDGET_SECRET` (optional) | Groq keys on live voice box already; channel tokens = generate random strings | `support.router.wire(...)` + include | **YES** — Groq already on box; extractive KB draft works without LLM key |
| **booking** | GREEN | `BOOKING_REMINDERS_ENABLE` (optional); Google Calendar creds (optional, reminders only) | Calendar = OAuth flow (founder-blocked); reminder flag = env var only | `include_router` + **must override `get_ctx`** with token-derived ctx (mount-time security fix) | **YES** (core booking engine) — calendar sync optional; no 3rd-party creds for core |
| **funnels** | GREEN | None to run (compiles to workflow engine); optional `FUNNELS_LANDING_API_KEY`, `FUNNELS_REVIEW_API_KEY` | Optional env-only | **BLOCKED — mount-time security fix required**: needs a token-deriving `build_router` (tenant from body = cross-tenant hole); do NOT mount shipped `funnel_wiring.diff` as-is | **NO** — backend mount blocker must be fixed first (build a `build_router` like workflow-studio) |
| **ads** | GREEN | Meta: `META_ADS_ACCESS_TOKEN`, `META_ADS_ACCOUNT_ID`, `META_ADS_APP_ID`, `META_ADS_APP_SECRET`; Google Ads: 6 vars; `LLM_ROUTER_URL` | Meta → Business Manager (founder-blocked); Google Ads → Google account (founder-blocked); noop provider runs without creds | Bare-OK mount | **NO** — noop provider until real ad platform creds; founder must authorize Meta/Google |
| **payments** | GREEN | `PAYMENTS_DEFAULT_PROVIDER`; Razorpay: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`; OR Stripe: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Razorpay/Stripe dashboard (founder-blocked — requires merchant account) | `payments.router.wire(...)` + include | **NO** — founder must create Razorpay/Stripe account and get API keys |
| **media-gen** | N/A (no frontend page in the 9) | DO Spaces + video provider creds | DO Spaces (founder-blocked); video provider API key (founder-blocked) | **BLOCKED — auth seam missing** (routes read `tenant_id` from body); refactor `build_router` to inject `resolve_tenant/need_auth/can` before mounting | **NO** — both mount blocker + founder creds required |

---

### Cred-Free Activatable Modules (flip `FEATURE_X=1`, no new 3rd-party sign-ups needed)

1. **forms-surveys** — core runs with zero creds (captcha optional)
2. **support** — Groq already on box; extractive KB works even without LLM key
3. **booking** (core) — no 3rd-party creds; just fix `get_ctx` override at mount + set `FEATURE_BOOKING=1`
4. **workflow-studio** — in-process interpreter needs NO creds; Hatchet durable engine optional (token already on hatchet box if needed)
5. **ai-manager** — generate `AIM_SERVICE_TOKEN` (a random string, no external service); reuses Groq already present

### Founder-Blocked (requires 3rd-party account / OAuth flow)

- **ads** — Meta Business Manager + Google Ads account authorization
- **payments** — Razorpay or Stripe merchant account + webhook endpoint registration
- **media-gen** — DO Spaces bucket setup + video provider API key

### Backend Mount-Blockers (security fix required before serving tenant traffic)

- **funnels** — needs `build_router(resolve_tenant, can, need_auth, forbidden)` built (tenant from body = cross-tenant hole); do NOT apply `funnel_wiring.diff` as-is
- **booking** — override default `get_ctx` with token-derived resolver via `dependency_overrides`
- **media-gen** — add auth seam to `build_router()` or gate admin-only

---

## FINAL VERDICT

| Dimension | Result |
|---|---|
| `npm run build` | **GREEN — exit 0** |
| Routes compiled | **34** (33 app + 1 static) |
| Module pages crashing on dormant backend | **0 of 9** |
| All 9 pages dormant-safe | **YES** |
| Cred-free activatable now | **5: forms, support, booking-core, workflow-studio, ai-manager** |
| Founder-blocked | **3: ads (Meta/Google), payments (Razorpay/Stripe), media-gen (Spaces+provider)** |
| Backend mount-blocker (security fix first) | **3: funnels (build token-router), booking (get_ctx override), media-gen (auth seam)** |

The committed tree is **safe to deploy as-is**. All 9 new module pages render clean dormant/coming-soon premium states while their backends are flag-OFF. No page will crash, error-wall, or expose a broken UI to users.
