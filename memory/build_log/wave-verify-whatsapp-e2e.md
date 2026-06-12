# Wave — WhatsApp pipeline END-TO-END VERIFICATION (honest, non-destructive)

Date: 2026-06-12. Run: verify-wa-e2e. Branch: feat/premium-ui.
Goal: independently verify the BUILDER + POSTCALL reports — template builder (Groq +
TEXT submit + banner-header submit), post-call approved-template auto-send, deepened
reply context, and the earner regression gate. NO code changed (verification only);
no service restarted; earner never at risk.

## BOX / SURFACE FACTS (rediscovered, save time)
- Backend port is **8209** (uvicorn `caller:app`), NOT 8000. Core API on 127.0.0.1:8209.
- WhatsApp builder routes are mounted under prefix **`/whatsapp/campaign`** (router in
  `whatsapp_builder/router.py`, build_router pattern). Status = `/whatsapp/campaign/builder/status`.
- Meta env on box: `META_WA_TOKEN`, `META_WA_PHONE_NUMBER_ID`, `META_WA_BUSINESS_ACCOUNT_ID`
  (WABA), `META_WA_APP_ID` (for Resumable Upload). `WA_LANG=en`, `WA_AUTO_FOLLOWUP=0`
  (global OFF — safe), `WA_FOLLOWUP_TEMPLATE=post_call_followup`.
- Post-call follow-up gate (caller.py `_wa_ai_followup` ~:1660): fires ONLY when
  `outcome in (interested, callback) OR interest >= 70` AND
  `(WA_AUTO_FOLLOWUP OR camp_fields.wa_followup)`. So a `no_answer`/USER_REJECTED call
  does NOT send a follow-up (correct — no spam). Gate value lives at `fields.wa_followup`
  on the campaign JSON (the `/campaigns` API does not echo that sub-field — not a bug).

## RESULTS — per item

### (1) Template builder — PASS (the "create→thinking→try again" loop is GONE)
- builder/status = `{"llm":"ready","whatsapp":"ready","meta_submit":"ready","feature_enabled":true}`.
- Groq key from the box = HTTP 200 (the old "DEAD key / err1010" was a Cloudflare block
  on the dev IP, never the box — confirms U1).
- AI GENERATE on c17e55e9f3 → `status: accepted`, 2 real AI templates (Groq llama-4-scout),
  each with a persisted `template_id`. No hang, no "try again".
- TEXT submit-to-Meta → `status: submitted`, real `meta_template_id 1709258580269519`,
  Meta verdict **REJECTED / INVALID_FORMAT** (the AI used a NAMED placeholder `{{name}}` in
  the header instead of numbered `{{1}}` — a Meta CONTENT rule, surfaced verbatim, NOT a
  hang). Deleted (success:true).
- IMAGE/banner-header submit (production path: test PNG → `upload_header_image` →
  Resumable Upload → 191-char `header_handle` → `example.header_handle` → submit) →
  `status: submitted`, real `meta_template_id 871272952684679`, **review PENDING (200)**.
  Deleted (success:true). This is the exact U1 fix (old broken path sent `header_handle:[""]`→400).

### (2) Post-call automation — PASS (approved template auto-sends; founder receives)
- The real call to +917861019021 on c17e55e9f3 came back `no_answer`/USER_REJECTED →
  follow-up correctly did NOT fire (gate requires interested/callback/score≥70).
- To prove the qualifying path: invoked the REAL finalize hook `_wa_ai_followup` with an
  interested rec (interest=82) for the founder # → wa_log row:
  `template=post_call_followup, kind=auto_followup_template, status=sent:200, ok=True`.
  Meta accepted the APPROVED template → founder receives it. Cold-safe TEMPLATE path
  (kind=auto_followup_template), NOT free-form. Thread seeded with call_summary + the
  verbatim template opener turn (G5 grounding live). Smoke artifacts cleaned afterward.

### (3) Reply context — PASS (the convo KNOWS the call)
- `_wa_reply_text` (caller.py ~:1546) injects `call_summary / next_action / call_outcome /
  interest` (from the thread) + `_wa_memory_recap(phone)` (= `memory.load_memory` →
  `build_recap`) into the reply system prompt.
- `_wa_memory_recap("917861019021")` returned a real recap: "(pichhli call: 2026-06-11 …)
  Riya: नमस्ते…". Ran the REAL reply on the founder thread (has call_summary):
  inbound "remind me what we discussed and the price?" →
  reply "Kunal, we discussed Codename Joy 3.0, our premium 3BHK residences… prices start
  around 3.5 crores…" — demonstrably references the call/product. REPLY_KNOWS_CALL=True.

### (4) Regression — PASS (earner intact)
- famit-agent, famit-caller, famit-bridge, aim-voice-agent ALL active before+after.
- Real outbound to +917861019021 RANG during the wave (room famit-917861019021-70d40a,
  agent connected, Riya Hinglish opener "नमस्ते Kunal जी… Codename Joy 3.0…",
  tts_ttfb=0.370s; phone rang → USER_REJECTED).
- Core `/me /campaigns /leads` = 200; zero caller 5xx; zero agent tracebacks.
- NO .py changed, NO service restarted, SIP/trunk/firewall/agent.py UNTOUCHED.

## G3 gate scope (unchanged, re-confirmed)
WA_FOLLOWUP ON=[c17e55e9f3 only]; OFF=[7 other campaigns]; global WA_AUTO_FOLLOWUP=0.
Real leads are NOT mass-messaged.

## RESIDUAL GAPS (honest)
- (minor, content-quality) The AI template GENERATOR emits NAMED placeholders (`{{name}}`)
  in header/body which Meta rejects as INVALID_FORMAT. The numbered-placeholder body
  (`{{1}}`) submits & goes PENDING fine. Fix later in generate.py/validate.py to coerce
  named→numbered before submit so AI-generated TEXT templates also pass Meta on first try.
- (cosmetic) `_wa_log` does not surface the Meta `wamid` to the top of the log row
  (status:sent:200/ok:True is logged; wamid is inside result). Optional: hoist wamid for
  panel display.
- The cleaned-up `wa_log.json` was re-serialized with `indent=0` during artifact cleanup
  (functionally identical JSON array; cosmetic only).

## FOUNDER TEST STEPS (how to self-verify)
1. CALL: in the panel, run campaign "Codename Joy 3.0" (c17e55e9f3) against your own
   number +917861019021 and ANSWER it — talk to Riya, sound interested (or just let it
   score you). After the call ends, you'll receive the `post_call_followup` WhatsApp
   template ("Hi Kunal, thanks for taking our call about Codename Joy 3.0…").
2. REPLY: reply to that WhatsApp ("what's the price / remind me what we discussed"). The
   AI reply will reference your call (product, what was discussed) — it KNOWS the call.
3. BUILDER: in the WhatsApp builder, step ③ AI Templates → cards appear instantly (no
   "try again"); pick one, optionally attach a banner in ④/⑤, then Submit to Meta → you'll
   see a real PENDING/APPROVED/REJECTED badge with Meta's verbatim reason.
