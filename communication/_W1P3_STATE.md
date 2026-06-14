# W1-P3 STATE — founder_alert + post_call + caller.py _finalize_call hook

Branch `fe/unify-run-wavec`. Earner-safe; create_task never await; snapshot sync; per-channel timeout (engine wait_for).

## Plan / progress — ALL DONE + LIVE (2026-06-15)
- [x] consent.py — append-only comm_consent_log writer (service-implicit post-call artifact)
- [x] founder_alert.py — hot-lead alert to founder Telegram (URL buttons only, PII-min default)
- [x] post_call.py — snapshot (pure sync, no live ref) + run (alert + auto-summary, engine owns timeouts)
- [x] sessions.py — set/get_founder_chat_id (STRICT sentinel; survives getUpdates aging)
- [x] engine.py — derive_founder_chat_id prefers persisted → getUpdates → auto-persist
- [x] caller.py _finalize_call hook (CALLER_EDIT_LOCK, anchor-string, +28/-0) — snapshot + create_task
- [x] py_compile + 5 offline suites (test_post_call_offline 22/22) + gitleaks 0 + agent-import grep 0
- [x] deploy comm pkg + caller.py (md5-gated) ; flags FEATURE_TELEGRAM_FOUNDER_ALERT/FOLLOWUP ON (admin)
- [x] EARNER GATE under induced telegram black-hole: snapshot 0.047ms + create_task 0.015ms + detached 0.10s ; agent.py 9150fabe UNCHANGED ; famit-agent 2808658 NOT restarted ; /health 200 ; 0 5xx
- [x] append _BUILD-LOG.md ; WORKFLOW_LEDGER + README ; lock RELEASED (golden ccf9715b)

## OPEN (founder action — see _HUMAN_TASKS.md)
- Founder taps @mr_kunal_bot ONCE → live chat_id seeds + auto-persists → real-reach hot-lead alert.
  Until then the alert no-ops cleanly (no_founder_chat_id), never blocks the call loop.

## Key facts (verified on disk)
- Hot path: `_finalize_call` awaited at caller.py.LIVEBOX.py:2845 inside run_job dial loop. Insert at END of _finalize_call (after :2794).
- Hot-lead = (outcome != opt_out) and interest score >= 70 (mirror existing _score>=70 + notify_handoff_team branch).
- Fields to SNAPSHOT (duplicate the reads, do NOT refactor _wa_draft_followup_text):
  rec: name, phone, id(call_id), outcome, interest, duration_s, campaign_name, room
  tr: summary, next_action, interest
  camp_fields: company_name, product_name, agent_name
- engine.send is the seam (owns asyncio.wait_for per-channel timeout). slug="telegram-founder".
- founder chat_id: engine.derive_founder_chat_id(tenant) (cached; '' if not started).
- Flags: FEATURE_TELEGRAM_FOUNDER_ALERT (alert), FEATURE_TELEGRAM_FOLLOWUP (auto-summary). Both gated under COMM_ENABLED+COMM_TELEGRAM_ENABLED.
- consent: post-call summary = service-implicit (defensible lane) -> write a consent artifact BEFORE the contact send.
- caller.py golden = caller.py.LIVEBOX.py (box live md5 73d7be4f). cfg_get exists. Mount block at 7832.
- DDL comm_consent_log cols: consent_id,tenant_id,contact_ref,channel,purpose,action,consent_basis,lead_source,wording,captured_by,call_id,captured_at.
