# wa-llm-conversation — the LLM multi-step WhatsApp conversation brain (EXPLORE-2)

> READ-ONLY exploration. Maps the EXISTING inbound-reply chatbot, what context it loads, the
> conversation-state store, the 24h-vs-template decision, and the EXACT gap to make it a
> context-rich, multi-step WhatsApp sales/support brain grounded in the call + campaign + memory.
> Box: `famit@168.144.153.145` `/opt/famit-agent/`. No app code, no deploy. Append-only.

## VERDICT (one line)
**A working multi-turn LLM WhatsApp reply brain ALREADY EXISTS** (caller.py "WAVE A2") — inbound
webhook → thread state → ONE Groq call → reply, with opt-out/handoff/max-turn guards. The GAP is
**context depth, not existence**: the reply prompt is grounded only in *campaign fields + last 10
chat turns*; it does NOT load the per-call **summary / next_action / transcript**, and never touches
the per-person **memory.py** recap. ai_manager/workforce is a separate *operator command* brain, not
the customer-reply path.

## 12-LINE MAP
1. **Inbound webhook** — `caller.py:4361 GET /whatsapp/inbound` (hub verify, `META_WA_VERIFY_TOKEN`) + `:4415 POST` (verifies `X-Hub-Signature-256` via app secret, parses, returns fast 200). Already VERIFIED/subscribed per brain note.
2. **Parser** — `caller.py:4390 _parse_meta_inbound()` extracts `[{phone,text}]` from `entry[].changes[].value.messages[]`; handles text + interactive `button_reply`/`list_reply` titles.
3. **Core inbound handler** — `caller.py:1543 _wa_handle_inbound(phone,text)`: provider-agnostic; loads thread, appends user turn, applies guards, generates+sends reply, persists. ALWAYS the only target of the webhook (ai_manager is NOT wired here).
4. **The LLM reply brain** — `caller.py:1518 _wa_reply_text(thread, camp_fields, incoming)`: ONE `_groq_chat` call. System prompt = agent_name + company + product + `product_summary[:400]` (campaign brain) + "move to next step / offer human if unknown". History = **last 10 thread turns** as role-tagged messages. 1–3 sentence Hinglish. `""` on failure.
5. **Conversation-state store** — flat JSON file per phone: `var/memory/wa_threads/<digits>.json` (`WA_THREADS_DIR`, `caller.py:166`), written under `_STORE_LOCK`. Keys: `phone, tenant_id, name, campaign_id, campaign_name, status, turns[], created_at/updated_at`. Turns capped at 200. **NOT a DB table; no RLS, no `ai_manager_*`/`wa` schema row** — pure filesystem.
6. **Contact linking** — `caller.py:1466 _resolve_contact_by_phone()`: maps an inbound number → tenant/name/campaign by scanning the most-recent CALL to that number, then LEADS file, else `ADMIN_ID`. This is the only "what happened on the call" bridge — and it carries only campaign_id/name, **not the call summary**.
7. **Guards** — opt-out words → suppression + `lead.opted_out` webhook; handoff words ("talk to human", "call me") → `needs_human`; `WA_MAX_TURNS=12` human turns → `max_turns_handoff`. Else generate reply.
8. **Outbound seam (the template you asked about)** — post-call hook `caller.py:1872 _finalize_call` fires `:1927 _send_whatsapp` (legacy BSP template) **and** `:1931 _wa_ai_followup`. `_wa_ai_followup` (`:1600`) is the AI post-call follow-up: gated by campaign `wa_followup` flag + `outcome∈{interested,callback} or score≥70`, drafts via `:1492 _wa_draft_followup_text` (which DOES load `tr.summary`+`tr.next_action`+outcome+interest — the call context), sends free-form text in-window, then **seeds the thread** so inbound replies continue.
9. **24h window vs template** — `whatsapp.py` cleanly supports both: `send_whatsapp_text_async` (`:242`, type=`text`, valid only inside 24h CS window) and `send_whatsapp_async` (template). Reply brain prefers TEXT when `meta_configured()` (`:1581`). So replies ride the OPEN 24h session opened by the inbound message — correct. Cold/outside-24h re-engage = a template (the approved one), not free-form.
10. **The other "brain" (NOT this path)** — `ai_manager/` + `workforce/` is the OPERATOR command/action engine: an authenticated user says "send WhatsApp to X" / "enqueue calls" and a state-machine (`ai_manager/state_machine.py:446 whatsapp.send`) verifies→PIN→permission→delegate. `ai_manager/inbound_agent.py` is a **DEFERRED stub** (LiveKit VOICE inbound, raises NotImplementedError). Neither handles a customer's WhatsApp reply.
11. **Memory engine UNUSED here** — `memory.py` (`load_memory`, `build_recap`, `save_memory`, `var/memory/<phone>.json`) is the per-person history used by the VOICE agent (agent.py). caller.py **never imports memory.py** (grep = 0). The reply brain has no access to the lead's prior-call recap.
12. **Money/audit** — inbound replies are FREE-form sends through `whatsapp.py` and are NOT metered/credited or written to immutable audit (only `_wa_log` JSON). The builder's `wa_template_gen` meter is template-gen-only, unrelated to live replies.

## WHAT EXISTS vs WHAT IS MISSING
EXISTS (working today, flag-gated): inbound webhook (sig-verified) → parse → per-phone thread → multi-turn
Groq reply grounded in campaign + last-10-turns → 24h-window TEXT send → opt-out/handoff/max-turn → thread persist;
plus the AI post-call follow-up that seeds the thread WITH call context (`_wa_draft_followup_text` reads `tr.summary`/`next_action`).

MISSING (for "context-rich, multi-step, grounded in what happened on the call"):
- **Call context not in the REPLY** — `_wa_draft_followup_text` reads the call summary, but `_wa_reply_text` does NOT. The summary/next_action/outcome/interest are never stored on the thread nor reloaded at reply time, so the 2nd+ turn forgets the call.
- **memory.py recap not loaded** — no `load_memory(phone)` / `build_recap()` injection; prior-call history (the voice agent's memory) is invisible to WhatsApp.
- **Full transcript / lead history not fetched** — only campaign `product_summary[:400]`; no per-lead notes, no booking/CRM state.
- **State is flat JSON, not schema** — no `wa` / `ai_manager_*` table, no RLS, no tenant-isolation at the store layer (tenant lives only inside the file); not queryable/auditable like the rest of the platform.
- **No structured slot/goal tracking** — single free-text prompt; no booking-intent capture, no tool-calling (can't actually book/schedule, only "offer a callback").
- **No audit/metering** of live AI replies; no quality/learning writeback loop into the thread.

## THE EXACT GAP (single sentence)
The minimal change to make this "context-rich multi-step": **persist the call context on the thread at
follow-up/seed time and reload it (plus `memory.py.build_recap(phone)` + the lead's CRM/booking state)
into `_wa_reply_text`'s system prompt on every inbound turn** — i.e. enrich the prompt context in
`caller.py:1518 _wa_reply_text` (add `thread["call_summary"]/["next_action"]/["interest"]` written in
`_wa_ai_followup`'s seed block at `:1632`, and a `memory.build_recap(load_memory(phone))` line). The
multi-turn loop, 24h-window send, guards, and store already exist; only the **grounding context is thin**.
Optional hardening: move thread state into a FORCE-RLS `wa_conversation` table and meter/audit live replies.

## KEY FILE:LINE INDEX
- `caller.py:166` `WA_THREADS_DIR` (state store) · `:1351 _send_whatsapp` (legacy BSP) · `:1398 _wa_send` · `:1417 _wa_followup` (template) · `:1466 _resolve_contact_by_phone` · `:1492 _wa_draft_followup_text` (loads call context) · `:1518 _wa_reply_text` (THE reply brain — thin context) · `:1543 _wa_handle_inbound` · `:1600 _wa_ai_followup` (seeds thread, `:1632` seed block) · `:1872 _finalize_call` (post-call hook) · `:1927/:1931` (template + AI followup fire) · `:4361/:4415 /whatsapp/inbound` GET+POST · `:4390 _parse_meta_inbound`.
- `whatsapp.py:233/242 send_whatsapp_text(_async)` (24h text) · `:248/291 send_whatsapp(_async)` (template) · `:101 meta_configured` · `:120 _meta_to`.
- `memory.py:53 load_memory` · `:67 build_recap` · `:96 save_memory` (UNUSED by caller.py — the integration seam).
- `ai_manager/state_machine.py:446 whatsapp.send` (operator command, not customer reply) · `ai_manager/inbound_agent.py` (DEFERRED voice stub).
