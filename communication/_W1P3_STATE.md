# W1-P3 STATE — founder_alert + post_call + caller.py _finalize_call hook

Branch `fe/unify-run-wavec`. Earner-safe; create_task never await; snapshot sync; per-channel timeout (engine wait_for).

## Plan / progress
- [ ] consent.py — append-only comm_consent_log writer (service-implicit post-call artifact) IN PROGRESS
- [ ] founder_alert.py — hot-lead alert to founder Telegram (URL buttons only)
- [ ] post_call.py — _comm_snapshot (pure sync) + _comm_post_call (alert + auto-summary, owns timeouts)
- [ ] caller.py _finalize_call insertions (CALLER_EDIT_LOCK, anchor-string, additive) — 1 snapshot + create_task
- [ ] py_compile + offline tests + gitleaks 0
- [ ] deploy comm pkg + caller.py (lock) ; flip FEATURE_TELEGRAM_FOUNDER_ALERT / FEATURE_TELEGRAM_FOLLOWUP ON for admin tenant
- [ ] earner gate before+after under induced telegram outage
- [ ] append _BUILD-LOG.md ; WORKFLOW_LEDGER + README

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
