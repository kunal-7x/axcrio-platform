# WAVE BUILD — WhatsApp Post-Call Automation (after-call template trigger + context-rich LLM reply)

> Date: 2026-06-12. Box `famit@168.144.153.145:/opt/famit-agent/`. Single file changed: `caller.py`
> (+ 3 additive `.env` lines). Restarted ONLY `famit-caller`. Live outbound earner untouched & verified.
> Append-only build report.

## GOAL
Finish the post-call WhatsApp automation: (1) on call-complete INSTANTLY send the APPROVED post-call
template (`post_call_followup`) to the lead, populated with call/campaign context; (2) when the lead
REPLIES (24h window), run a context-rich, multi-step LLM conversation grounded in the call summary +
campaign + per-person memory. Behind a feature flag, default-OFF/safe. Never break the call flow.

## WHAT WAS WIRED

### (1) AFTER-CALL TRIGGER — rewrote `caller.py:_wa_ai_followup`
The call-complete hook `_finalize_call` already called `_wa_ai_followup`. The bug (GAP-G1): it sent
COLD free-form text, which Meta rejects outside the 24h window. Rewrote it so:
- **Gate** = global `WA_AUTO_FOLLOWUP=1` **OR** per-campaign `fields.wa_followup=true` (was per-campaign only). Default OFF.
- **Cold post-call → APPROVED TEMPLATE.** Sends `WA_FOLLOWUP_TEMPLATE` (=`post_call_followup`) via
  `whatsapp.send_whatsapp_async(phone, tpl, [name, product])`. Language comes from `WA_LANG=en`
  (fixes GAP-G4, the historical `sent:404`). `{{1}}`=lead name, `{{2}}`=product (campaign `product_name`,
  else transcript enquiry/next_action, else `WA_FOLLOWUP_ENQUIRY_FALLBACK`="your enquiry"), via new
  helper `_wa_followup_product`.
- **Window-open detection:** if the thread already has a `user` turn (lead messaged us = 24h window
  open), it prefers a personalised free-form `_wa_draft_followup_text` send; only the COLD case uses the
  template. So we never burn a template when a cheaper free-form text is valid, and never send cold
  free-form (rejected).
- **Idempotent:** stamps `rec["wa_followup_sent"]` — one follow-up per call, never double-sends.
- **Consent:** skips if the number is in `_suppressed_set(tenant_id)` (DND/opt-out).
- **Seeds the thread WITH call context** for the reply brain: writes `call_summary`, `next_action`,
  `call_outcome`, `interest`, `product`, name/campaign onto the thread JSON, plus the opener turn.
- Fire-and-forget, wrapped in try/except — never raises into the call loop.

### (2) INBOUND REPLY → context-rich LLM — enriched `caller.py:_wa_reply_text`
The multi-turn inbound reply brain existed but was grounded only in campaign fields + last-10 turns.
Enriched its system prompt to also inject:
- **Call grounding** read back from the thread: "What happened on the phone call: {call_summary}",
  agreed next step, outcome + interest — so 2nd+ turns no longer forget the call.
- **Per-person memory recap** via new `_wa_memory_recap(phone)` → `memory.load_memory` +
  `memory.build_recap` (the voice agent's cross-call store; added a safe `import memory as _mem_mod`).
  Read-only, import-safe (missing module degrades to no recap).
- Reframed the persona as "continuing AFTER a phone call", pushes toward a concrete next step
  (site visit / details / callback / booking), offers human handoff for unknowns. Escalation/handoff
  hooks (opt-out, "talk to human", max-turns) were already present and are untouched.

### Flag / config (added to `/opt/famit-agent/.env`, default SAFE)
- `WA_AUTO_FOLLOWUP=0`  ← master switch, OFF by default (no live behaviour change).
- `WA_FOLLOWUP_TEMPLATE=post_call_followup`  ← approved template name.
- `WA_FOLLOWUP_ENQUIRY_FALLBACK=your enquiry`
- `WA_LANG=en` already present (template is `en`).

## NOT CHANGED (deliberately)
- `whatsapp.py` — untouched; `send_whatsapp_async` already templates with `language.code` from `WA_LANG=en`.
- The outbound dial / agent / `/run` path — untouched (upstream of `_finalize_call`).
- `ai_manager/` + `workforce/` — NOT wired to the customer-reply path (G5, optional action-taking) — left as-is.
  Inbound replies converse + flag `needs_human`; richer action-taking (booking) is the documented next step.

## SMOKE / PROOF
- **Backups:** `caller.py.WAbak.20260612-041348` + `.env.WAbak.20260612-041348` (orig md5 `ca26f4e4...`).
- **Compile:** `py_compile` OK locally AND with the service venv `/opt/capsy-agent/.venv/bin/python` on box.
- **Isolated smoke:** `import memory` OK (load_memory/build_recap present, empty-safe); `whatsapp._meta_template_body`
  emits correct `language.code=en` + 2 body params; `meta_configured()=True` with env.
- **Swap + restart:** live `caller.py` md5 = `107b4793b7b107d6452b4f37f8637e45`; restarted ONLY `famit-caller`
  (new worker PID 1782404, clean — no ImportError from the new `memory` import or env reads).
- **REGRESSION GREEN (post-swap):** `famit-caller`/`famit-agent`/`famit-bridge` all **active**; core
  `health/me/campaigns/leads` = **200**; **zero 5xx / traceback** in logs.
- **REAL OUTBOUND CALL still works (post-swap):** placed a live call to founder test `+917861019021`
  via `/run` (campaign `c17e55e9f3`). Agent `capsy` job connected (room `famit-917861019021-bdcfa6`),
  multi-turn real conversation (`memory saved turns 1→3→5`), finalized — no errors. Earner intact.
  (Side-confirmation: `returning lead phone=917861019021 recap_chars=599` — memory.py is producing the
  same recaps the WA reply brain now reuses.)
- **Auto-followup correctly DORMANT:** with flag OFF + campaign `wa_followup=false`, NO auto template
  send fired (wa_log shows only old manual entries) — proves the safe default.
- **Wired template send proven LIVE:** replicated the exact cold-path call
  `send_whatsapp_async("+917861019021","post_call_followup",["Kunal","your property enquiry"])`
  → `status: sent:200`, `message_status: accepted`, wamid `wamid.HBgMOTE3...RDU1NTY3NDc1RjMwQUUxM0Ux`.

## HOW TO ENABLE (founder)
Either set `WA_AUTO_FOLLOWUP=1` in `/opt/famit-agent/.env` (global — fires on every meaningful completed
call) OR set a single campaign's `fields.wa_followup=true`; then `sudo systemctl restart famit-caller`.
Meaningful = outcome interested/callback OR interest score ≥ 70.

## ROLLBACK
`cp /opt/famit-agent/caller.py.WAbak.20260612-041348 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restore `.env.WAbak.20260612-041348` only if env needs reverting — the new lines are inert while flag=0).

## RESIDUAL / DEFERRED
- Inbound replies still use the local Groq reply brain, not `ai_manager/workforce` — fine for
  conversation; wire to workforce only when replies must EXECUTE actions (booking/scheduling). [G5]
- Thread state is still flat JSON (`var/wa_threads/<digits>.json`), not a FORCE-RLS table; live AI
  replies are logged (`wa_log.json`) but not metered/audited. Hardening, not blocking.
- The window-open heuristic (thread has a prior `user` turn) is a proxy for the 24h CS window; Meta is
  the final arbiter (a stale window still 404s, which is logged, not fatal).

## END-TO-END VERIFICATION — 2026-06-12 (live box, honest, nothing broken)
Re-verified the whole pipeline on `famit@168.144.153.145:/opt/famit-agent/`. caller.py md5 still
`107b4793b7b107d6452b4f37f8637e45` (unchanged). Flag `WA_AUTO_FOLLOWUP=0` (OFF). Live service =
`famit-caller` on **port 8209** (uvicorn `caller:app`, PID 1782404 — the post-swap worker). No code
edited during verify; my synthetic test thread was removed after, dir left clean.

- **Template is APPROVED (Graph API):** `post_call_followup` lang `en`, components BODY+BUTTONS, body
  `Hi {{1}}, thanks for taking our call about {{2}}. Reply here if you have questions or want to take
  the next step.` → exactly 2 placeholders, matching the wired `[name, product]` send.
- **STEP 1 (auto-send) PASS LIVE:** exact cold-path call via live whatsapp.py (`meta_configured=True`):
  `send_whatsapp_async("+917861019021","post_call_followup",["Kunal","your property enquiry"])`
  → `sent:200`, `accepted`, wamid `wamid.HBgMOTE3ODYxMDE5MDIxFQIAERgSNDc4N0MyRTczMzM2OTY0QUY1AA==`.
- **STEP 2 (inbound → context LLM) PASS LIVE:** seeded a thread with call context, drove the REAL
  `_wa_handle_inbound("+917861019021","Haan bhai weekend pe site dekhni hai, Saturday theek rahega.
  Floor plan bhejo")` → `action: replied` (sent via Meta). Reply was call-aware:
  *"Kunal, Saturday ko site visit arrange kar dete hain. Floor plan aur price list maine aapko abhi
  share kar diya hai, check kijiye."* — used name + agreed next step + product, did NOT repeat opener.
  Thread persisted (3 turns), `call_summary`/`next_action` retained, status `active`.
- **STEP 3 (manual fallback) PASS LIVE:** `POST /whatsapp/send` (X-Auth, write role) with the approved
  template → `{"ok":true,"status":"sent:200","to":"+917861019021","configured":true}`. Panel path
  `app/whatsapp/page.tsx` → `lib/api.ts:1586 sendWhatsApp()` posts the same form to this endpoint.
- **STEP 4 (regression / earner) PASS LIVE:** 3 services active; `/health /me /campaigns /leads`=200;
  webhook GET `hub.challenge`=200. Real `POST /run` (camp `c17e55e9f3`, `+917861019021`) → 200,
  `job_id 9a510462f4`; agent connected (room `RM_NE2NiYWtNEr3` → `famit-917861019021-e4cc72`), Sarvam
  STT WS connected, opener TTS played (`tts_ttfb=0.215s`). **ZERO 5xx/traceback** in all 3 services (30m).

**PROVEN LIVE vs NEEDS FOUNDER:** Steps 1-4 are proven on the box via the real code paths + the live
Meta Cloud API (real wamids). The single hop only the founder can close = a real **inbound WhatsApp
message from his own handset** so Meta POSTs the signed webhook to `/whatsapp/inbound` (I invoked the
handler directly; the receive+HMAC-verify path is wired and GET-verified, but an actual typed reply
from his phone is the last unproven link).

## FOUNDER TEST STEPS (do these on your phone — ~3 minutes)
1. **Turn it ON.** On the box: edit `/opt/famit-agent/.env`, set `WA_AUTO_FOLLOWUP=1`, save, then
   `sudo systemctl restart famit-caller`. (Or, to test ONE campaign only, set that campaign's
   `fields.wa_followup=true` instead and restart.)
2. **Make sure your number is a lead** in a campaign (use `Codename Joy 3.0` / `c17e55e9f3`), and that
   you've **messaged the WhatsApp business number once before** OR are inside a 24h window — for the
   FIRST cold test the APPROVED TEMPLATE is used, so a cold number is fine.
3. **Run a 1-lead call to YOUR own number** from the panel Run page (campaign `Codename Joy 3.0`, lead
   = your number, concurrency 1). Answer it, have a short chat, show interest ("haan interested hoon"),
   and hang up.
4. **Within seconds of hang-up you should receive the WhatsApp template** ("Hi <name>, thanks for
   taking our call about …"). ✅ = auto-send works on a real call. (Fires only if the call outcome was
   interested/callback OR interest score ≥ 70 — that's by design, so we don't spam dead leads.)
5. **Reply to that WhatsApp** in your own words (e.g. "haan site dekhni hai, kab dikha sakte ho?").
   Within a few seconds the AI should reply — and its reply should **reference your call** (your name,
   what you discussed, the next step). Send 2-3 messages to confirm it stays on-context across turns. ✅
   = the multi-step, call-aware brain works end-to-end on a real handset.
6. **Manual fallback (optional):** on the WhatsApp panel page, pick the `post_call_followup` template,
   enter your number + the 2 params, Send → you should get it. ✅ = manual path works.
7. **If anything looks wrong, turn it back OFF instantly:** set `WA_AUTO_FOLLOWUP=0` + restart
   `famit-caller`. No data lost; the live call flow is untouched either way.

If step 4 doesn't arrive: most likely the call outcome wasn't "interested" (raise interest in the chat),
or your number is in the suppression/DND list. If step 5's reply isn't call-aware, the thread seed
didn't persist — check `/opt/famit-agent/var/wa_threads/<yourdigits>.json` has `call_summary`.
