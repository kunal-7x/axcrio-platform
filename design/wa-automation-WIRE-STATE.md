# WhatsApp Automation — WIRE/FINISH STATE (build ledger)

> Box `famit@168.144.153.145:/opt/famit-agent/`. Build = wire the post-call template auto-send
> + enrich inbound LLM reply with call-context + memory. Backup-first, flag-OFF default, restart
> ONLY famit-caller. Crash-safe per-unit.

## DECISIONS (locked)
- **Global flag** `WA_AUTO_FOLLOWUP` (default `0` = OFF/safe). Gate = `WA_AUTO_FOLLOWUP=1` OR per-campaign `wa_followup=True`.
- **Template** name from env `WA_FOLLOWUP_TEMPLATE` (default `post_call_followup`). Lang already `WA_LANG=en` (GAP-G4 satisfied).
- **Cold post-call → TEMPLATE** (not free-form). Params `[name, product_or_enquiry]`. `{{2}}` = product_name else "your enquiry".
- **Idempotent:** stamp `rec["wa_followup_sent"]` (call id) — never double-send for the same call.
- **Consent:** skip if phone in `_suppressed_set(tenant_id)`.
- **In-window free-form preserved:** if a thread already open/active (24h window via prior inbound) keep AI free-form draft; cold path uses template.
- **LLM enrich:** persist `call_summary/next_action/interest/outcome/product` on thread at seed; reload into `_wa_reply_text` system prompt + `memory.build_recap(load_memory(phone))`.
- **memory.py** imported safely (try/except) into caller.py; never crash if absent.

## UNITS — ALL DONE 2026-06-12
- U1 [DONE] explore + decisions.
- U2 [DONE] backup caller.py+.env (*.WAbak.20260612-041348), env reads + safe `import memory as _mem_mod`.
- U3 [DONE] rewrote `_wa_ai_followup`: cold→TEMPLATE send, idempotency (rec["wa_followup_sent"]), suppression skip, window-open detection (free-form only if open), thread seed w/ call_summary/next_action/outcome/interest/product.
- U4 [DONE] enriched `_wa_reply_text`: injects call grounding + `_wa_memory_recap()` (memory.py build_recap). Added `_wa_followup_product` helper.
- U5 [DONE] env appended (WA_AUTO_FOLLOWUP=0 OFF, WA_FOLLOWUP_TEMPLATE=post_call_followup, WA_FOLLOWUP_ENQUIRY_FALLBACK). py_compile OK (local+box venv). Isolated import/memory/template-body smoke OK.
- U6 [DONE] restarted famit-caller ONLY. REGRESSION GREEN: 3 services active, core health/me/campaigns/leads=200, ZERO 5xx/traceback, REAL outbound call to +917861019021 fired+connected+conversed (room famit-917861019021-bdcfa6, memory turns 1→5) post-swap.
- U7 [DONE] live template send proof status:sent:200 accepted wamid HBgMOTE..RDU1NTY3...; build_log written.

## RESULT
- Live caller.py md5 = 107b4793b7b107d6452b4f37f8637e45. Flag default OFF (no live behavior change).
- ROLLBACK: `cp /opt/famit-agent/caller.py.WAbak.20260612-041348 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller` (+ restore .env.WAbak if needed).
- ENABLE: set WA_AUTO_FOLLOWUP=1 in /opt/famit-agent/.env (global) OR set a campaign's fields.wa_followup=true, then restart famit-caller.

## FILE:LINE TOUCH POINTS (verified on box 2026-06-12)
- caller.py:1600 `_wa_ai_followup` (rewrite cold→template + seed call-context)
- caller.py:1518 `_wa_reply_text` (enrich prompt)
- caller.py:1543 `_wa_handle_inbound` (pass call-context + memory)
- caller.py:1872 `_finalize_call` (no change to ordering; followup already called :1937)
- env: WA_LANG=en already; add WA_AUTO_FOLLOWUP=0, WA_FOLLOWUP_TEMPLATE=post_call_followup
- whatsapp.py: NO CHANGE (send_whatsapp_async already templates w/ lang from WA_LANG=en)

## E2E VERIFY 2026-06-12 (live, 4/4 PASS, nothing broken) — port 8209
- Template APPROVED (Graph API): post_call_followup en BODY+BUTTONS, 2 placeholders.
- S1 auto-send PASS: cold send_whatsapp_async(...,"post_call_followup",[name,product]) → sent:200,
  wamid wamid.HBgMOTE3…NDc4N0MyRTcz…
- S2 inbound→LLM PASS: real _wa_handle_inbound → action:replied, call-aware reply (knew name+next step),
  thread persisted w/ call_summary.
- S3 manual PASS: POST /whatsapp/send (auth) → ok:true sent:200 configured:true.
- S4 regression PASS: 3 services active, /health/me/campaigns/leads=200, webhook GET=200, real /run call
  rang (room RM_NE2NiYWtNEr3, opener TTS tts_ttfb=0.215s), ZERO 5xx/traceback.
- Flag still OFF (WA_AUTO_FOLLOWUP=0). Synthetic test thread cleaned. NEEDS-FOUNDER: a real typed inbound
  from his own handset (webhook receive path wired+GET-verified; I invoked the handler directly).
- Founder test steps written in build_log/wave-build-wa-automation.md.
