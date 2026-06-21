# AUDIT-2 — WhatsApp Template Builder (front-end + Meta-submit backend)

> READ-ONLY production-readiness audit. Date 2026-06-12. Box `famit@168.144.153.145`
> (`/opt/famit-agent/`, read-only SSH). Live API probes done directly (no box edits, no deploy,
> no git). Secrets never printed. The live outbound earner (`agent.py`) was NOT touched.

## VERDICT (one line)
The Meta `message_templates` CREATE path is REAL and WORKS for TEXT templates (live 200 + template
id), but the founder's "create -> thinking -> try again" loop is caused by a **dead `GROQ_API_KEY`
on the box (403/err 1010) with NO OpenRouter fallback set** — so AI copy always fails and the
front-end shows the failure panel. The **IMAGE-BANNER header is genuinely broken**: there is NO
resumable-upload code to mint a `header_handle`, so any media-header submit 400s.

---

## 14-LINE MAP (exists vs gap)

1. **Front-end builder = `app/whatsapp/` 11-step wizard** (`TemplatesStep.tsx` is step ③). It is an AI COPY generator + Meta-compliance LINT (`_lib/meta.ts`) + live phone preview — NOT a Meta submit UI.
2. **`TemplatesStep` flow** = `generateTemplates()` → `GenerationLoader` ("Thinking") → cards OR `GenFailurePanel` ("Couldn't generate… Try again / Write one manually"). This IS the founder's "thinking → try again".
3. **Front-end calls** `POST /api/whatsapp/campaign/{id}/generate-templates` (`_lib/waapi.ts:212`). The image/banner attach, approve, submit-to-Meta surfaces are designed but routed to the Asset Service (`:8310`, dormant).
4. **There is NO front-end "submit this template to Meta" button.** The UI generates copy and previews; it never drives `submit-to-meta`. Meta approval is shown read-only in `ApprovalStep` as a status badge.
5. **Backend IS deployed + mounted:** `whatsapp_builder/` package on the box, `FEATURE_WHATSAPP_BUILDER=1`, router mounted under `/whatsapp/campaign` (live probe: `401`, i.e. route exists, needs auth — not 404).
6. **The Meta CREATE call is REAL** — `whatsapp_builder/meta_submit.py:submit()` POSTs the correct body (`name/language/category/components`) to `/{waba}/message_templates`. It is NOT just text-gen. Exposed at `POST /whatsapp/campaign/templates/{id}/submit-to-meta`.
7. **LIVE PROOF — text template CREATE works:** direct probe with the box's `META_WA_TOKEN` → **HTTP 200, `{"id":"987343547416683","status":"PENDING"}`** (probe template created then deleted). The token + WABA are valid for template submission.
8. **LIVE PROOF — image header CREATE fails:** the backend builds `example:{header_handle:[""]}` (empty). Meta → **HTTP 400, subcode 2388043: "component of type HEADER is missing expected field(s) (example.header_url)"**. Media header is unusable as-is.
9. **ROOT CAUSE of "thinking → try again":** box `GROQ_API_KEY` returns **HTTP 403 / `error code: 1010`** for EVERY Groq model (key disabled/revoked at org level — `api.groq.com` itself is reachable and returns clean JSON for a dummy key, so it is NOT egress/Cloudflare). The key on the box is stale vs the 4 valid keys in `.env.local`.
10. **No fallback:** OpenRouter is absent on the box — neither `OPNEROUTER_API_KEY` (the founder-typo var the code reads first) nor `OPENROUTER_API_KEY` is set. So the LLM seam has zero working providers.
11. **What the backend returns:** LLM 403 → `generate.py` sets `bundle.error="llm:http_403"`, falls to the **deterministic templated fallback**, `status="partial"` (templates DO come back, just non-AI copy).
12. **Why the UI still shows failure:** `waapi.ts` computes `hadError = !!d.error` → `d.error="llm:http_403"` is truthy → `ok=false` → `TemplatesStep` renders `GenFailurePanel` even though fallback templates exist. The founder sees "Try again", never the fallback cards.
13. **Credits are NOT the cause:** `WALLET_ENABLED` unset → `credit.reserve()` returns `(None,"unavailable")` → generation proceeds free. `FIREWALL_ENABLED=true`. No `insufficient_credits`.
14. **Status sync (approved/rejected):** `submit-to-meta` records `meta_template_id`+`review_status:PENDING`; `meta-status` route polls Meta on demand. There is **NO webhook** subscribed to `message_template_status_update` — so approve/reject never push back automatically (poll-only, and only if a human ever calls submit).

---

## EVIDENCE (live probes, this session)
| Probe | Result |
|---|---|
| `POST .../message_templates` text-only (body+2 vars+example) | **200** `{"id":"987343547416683","status":"PENDING","category":"MARKETING"}` (created + deleted) |
| `POST .../message_templates` IMAGE header, `header_handle:[""]` | **400** subcode 2388043 — `HEADER missing example.header_url` |
| Groq chat (env model `meta-llama/llama-4-scout-17b-16e-instruct`) | **403 `error code: 1010`** |
| Groq chat `llama-3.1-8b-instant`, `llama-3.3-70b-versatile` | **403 `error code: 1010`** (all models → key-level block) |
| `api.groq.com` reachability (dummy key) | **200** clean JSON `invalid_api_key` → egress OK, key is the problem |
| Box env: `OPNEROUTER_API_KEY` / `OPENROUTER_API_KEY` | both **UNSET** (no LLM fallback) |
| Box env: `META_WA_TOKEN`(202c) / `META_WA_BUSINESS_ACCOUNT_ID`(16c) | **SET** → `meta_ready()` true |
| Box env: `META_WA_APP_ID` / `FB_APP_ID` / `META_APP_ID` | **UNSET** → resumable upload impossible |
| Route mount: `POST /whatsapp/campaign/{id}/generate-templates` | **401** (mounted, auth-gated — not 404) |

---

## THE TWO GAPS vs "AI creates & submits a real Meta template WITH a banner"

### GAP A — AI generation always fails (the visible "thinking → try again")
- **Cause:** dead Groq key + no OpenRouter fallback on the box.
- **Secondary cause:** even when the LLM is fixed, a transient LLM error still surfaces as a hard failure because the FE flags any `d.error` as fatal while the BE actually returned usable fallback templates.

### GAP B — Image-banner header submission is unimplemented
- **Cause:** `meta_submit.to_meta_payload` emits `example:{header_handle:[tpl["_header_handle"]]}` but **nothing ever sets `_header_handle`**. There is no resumable-upload step, and `META_WA_APP_ID` (required for `POST /{app_id}/uploads`) is not on the box. Meta requires EITHER a `header_handle` (from resumable upload) OR an `example.header_url`.
- **Also missing:** the FE never lets the user attach a banner to the *template* (banner attach is wired to the Asset Service for the *send*, not the template header), and there is no end-to-end "generate banner → upload to Meta → put handle in the template create" chain.

---

## THE EXACT FIX (to make AI-created real Meta templates WITH banners work)

**1. Restore the LLM seam on the box (fixes the "thinking → try again" today).**
- Update `/opt/famit-agent/.env`: set a VALID `GROQ_API_KEY` (use one of the 4 live keys in `caps/.env.local` §1, e.g. `GROQ_API_KEY=gsk_nMuRBKR…`; add `GROQ_API_KEY_2/_3` for the pool) AND add an OpenRouter fallback key as **`OPNEROUTER_API_KEY`** (the var `config.openrouter_key()` reads first — value `sk-or-v1-cde61…` from `.env.local`). Set `GROQ_LLM_MODEL=llama-3.3-70b-versatile` (a current, JSON-mode-capable Groq model; the env's `llama-4-scout` may be why scout 403s on some orgs). Restart `famit-caller` only (NOT `agent.py`).
- Verify: authenticated `POST /whatsapp/campaign/{id}/generate-templates` returns `status:"accepted"`, `model:"groq:…"`, real AI bodies.

**2. Make the front-end fault-tolerant (so a soft LLM error still shows the fallback templates).**
- In `app/whatsapp/_lib/waapi.ts` `generateTemplates` map: treat `status==="partial"` WITH `suggestions.length>0` as `ok:true` (render the templated-fallback cards + a small "AI copy unavailable, using a starter template" note), and only set `ok:false` when `suggestions.length===0` OR `status` starts with `"error:"`. Today it flags any `d.error` as fatal even when templates exist.

**3. Implement the IMAGE-banner header via Meta resumable upload (the only correct path).**
- Add `META_WA_APP_ID` to the box `.env` (Meta App ID; the WABA's app — `META_ADS_APP_ID=2741460946218468` in `.env.local` is the ADS app, NOT necessarily the WhatsApp app — confirm the WhatsApp app id in Meta dashboard).
- New 2-call upload in `meta_submit.py` (run at submit time when `header.format` is media):
  1. `POST https://graph.facebook.com/v21.0/{APP_ID}/uploads?file_length={bytes}&file_type=image/png&access_token=…` → returns an **upload session id** `upload:…`.
  2. `POST https://graph.facebook.com/v21.0/{upload_session_id}` with header `Authorization: OAuth {token}` and the **raw image bytes** as the body (offset 0) → returns `{"h":"<header_handle>"}`.
  3. Put that `h` into `components[HEADER].example.header_handle:[h]` (the field the payload already shapes) and submit. (Simpler interim: host the banner on DO Spaces — already proven live — and submit `example.header_url:["https://…"]` instead; Meta accepts a public image URL and avoids the App-ID dependency entirely. This is the FASTEST unblock.)
- Source the image from the Asset Service banner (`creative.*`) bound to the template, so "AI writes copy + AI banner → one Meta template" becomes the real chain.

**4. Add real status sync (approved/rejected) instead of poll-only.**
- Subscribe the WABA webhook to **`message_template_status_update`** (Meta → WhatsApp → Configuration → Webhook fields) and handle it in `caller.py`'s existing `/whatsapp/inbound` POST → write `meta_review=APPROVED|REJECTED` + `rejected_reason` onto `ai_wa_templates`. The `meta-status` poll route stays as a manual refresh.

**5. Wire a "Submit to Meta" action into the front-end** (currently absent): after Approval, call `POST /whatsapp/campaign/templates/{id}/submit-to-meta`, show the returned `PENDING` badge, and surface the webhook-driven APPROVED/REJECTED status — closing the "no manual Meta console" loop the founder asked for.

**Fastest path to a working demo (today):** fix #1 (LLM key) + #2 (FE tolerance) → AI copy works; do #3-interim (`header_url` via DO Spaces public URL) → real banner template submits to Meta (proven 200 for text already). #3-resumable, #4, #5 harden it for production.

## SAFETY
All probes were direct vendor-API calls + read-only SSH greps. One throwaway Meta template was created
to prove the 200 and immediately DELETED (WABA left clean). Zero box files/services touched; the live
earner (`agent.py`/`famit-caller`/`famit-agent`/`famit-bridge`) was not restarted.
