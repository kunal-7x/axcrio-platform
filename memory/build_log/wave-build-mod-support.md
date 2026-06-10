# wave-build-mod-support — AI Customer Support (omnichannel ticketing + KB-grounded AI replies)

Date: 2026-06-10 · Agent: PLATFORM-ENG · Status: BUILT + offline-smoke green (47/47) · NOT deployed, NO git.

## What this is
The `support` module: AI Customer Support — omnichannel ticketing (WhatsApp/voice/email/web) + AI replies
drafted from the F2 Knowledge Base (RAG) + escalation/human-handover + sentiment. Built the ticket model
(schema + core logic) AND the support role agent. All NEW files under `droplet_work/support/`. Provider/
channel-agnostic, DORMANT-UNTIL-CREDS. Router DEFINED-NOT-MOUNTED. No caller.py/agent.py edit, no restart,
no deploy, no git (orchestrator commits).

## Files created (all under droplet_work/support/)
- `schema.sql` — `support_tickets` + `support_messages`. FORCE-RLS admin-GUC policy BYTE-COPIED from
  crm/payments (`is_admin='1' OR org_id=current_setting('app.tenant_id',true)`, WITH CHECK). Idempotent
  (CREATE TABLE/INDEX IF NOT EXISTS, DROP POLICY IF EXISTS). NOT an Alembic rev (F2/F4/crm/payments
  precedent — kept off the P1 keystone chain). Deterministic PKs (tk_/sm_).
- `core.py` — the domain logic: thread-identity grouping, idempotent inbound append, KB-grounded draft
  (grounded-or-escalate), escalation/handover with §8 AI-summary, claim/resolve/human-reply, RLS reads.
  Composes kb.retrieve + workforce.llm.driver + workforce support RoleSpec + audit + crm. Lazy/defensive
  resolvers (try-import -> None) so it imports clean with kb/workforce/crm/db ABSENT.
- `sentiment.py` — DETERMINISTIC lexicon sentiment + escalation-intent flags (refund/legal/angry/human).
  NO LLM, NO network (crm-NBA/langdetect discipline). English + Hinglish/Devanagari markers.
- `agent.py` — `SupportAgent`: the support role agent as a standalone reply-SERVICE that composes the
  workforce primitives. Does NOT re-implement the runner loop, does NOT call AgentRunner.run (no ticket
  tools / no loopback offline). `triage()` = the PG-free escalation decision (the offline discriminator).
- `router.py` — FastAPI `APIRouter`, DEFINED-NOT-MOUNTED, `wire(resolve_tenant,can,need_auth,forbidden,
  firewall)` injection (payments pattern). 10 routes. import-safe (router=None if FastAPI absent).
- `__init__.py` — facade re-exporting core + SupportAgent + sentiment.
- `tests/_smoke_support.py` + `tests/__init__.py` — offline smoke (47/47, ZERO keys/network/PG).

## What it COMPOSES (foundation, never re-implemented)
- **F2 Knowledge Base** (`kb.retrieve`, hybrid FTS+dense, RLS-scoped) — the AI reply is DRAFTED from KB
  chunks. Empty corpus / confidence < floor -> ESCALATE, never hallucinate. (grounded-or-escalate.)
- **workforce `support` RoleSpec** — system_prompt + `handover_on=(refund_request,legal,angry)` are SOURCED
  from `workforce.roles.get("support")` (local fallback if workforce absent). NOT re-declared.
- **shared dormant LLM driver** (`workforce.llm.driver`) — when configured, drafts from-context-only;
  TODAY dormant (driver has no generic completion method yet — `is_configured()` False) so the
  deterministic extractive KB draft fires. The LLM seam tries `answer/complete/generate` so the activation
  unit's method is picked up with no edit here.
- **immutable audit** — every open/draft/handover/resolve -> `workforce.audit_bridge.record` (channel='ai',
  aiwf.* — falls back to bare `audit.record(channel='support')`). NEVER a new JSONL.
- **crm** (best-effort) — `_crm_stitch` ensures the person spine knows the human (`crm.upsert_contact`, a
  REAL crm API) + links `contact_id` onto the ticket. A crm outage NEVER breaks support.

## Router endpoints (for the later mount; prefix `/support`)
- `GET  /support/health` — core.status() (pg/kb/llm dormancy).
- `POST /support/inbound` — the omnichannel turn (write): ingest -> sentiment -> escalate-or-draft. Idempotent
  on redelivery (provider_msg_id / body hash).
- `GET  /support/tickets` — list (status/channel/assigned_to/limit), RLS-scoped.
- `GET  /support/tickets/{ticket_id}` — ticket + messages.
- `POST /support/tickets/{ticket_id}/draft` — (re)draft a KB-grounded AI reply (write).
- `POST /support/tickets/{ticket_id}/reply` — a human posts a reply (write).
- `POST /support/tickets/{ticket_id}/escalate` — force-escalate (write).
- `POST /support/tickets/{ticket_id}/claim` — a human claims (write).
- `POST /support/tickets/{ticket_id}/resolve` — resolve/close. STEP-UP-gated (`support_override`; pass-
  through when FIREWALL_ENABLED off / no PIN). The ONLY step-up route (support is NOT a money path).
- `POST /support/webhooks/{channel}` — omnichannel inbound webhook (machine call, NOT tenant-auth'd).
  Dormant no-op ({status:not_configured}) — channel adapter + tenant binding + signature verify DEFERRED.

## Creds / prerequisites awaited (dormant-until-set)
- **Knowledge Base content** (F2) — replies are KB-grounded; an empty corpus -> every question escalates.
  Needs tenant KB docs ingested (kb.ingest). Optional embedder key activates the dense RAG leg (FTS works
  keyless today).
- **LLM key** (`ANTHROPIC_API_KEY` / `GROQ_API_KEY`, via `AIWF_LLM_PROVIDER`) — activates LLM-authored
  answers; until then the deterministic extractive KB draft is used. The shared driver also needs its
  generic-completion method (activation unit).
- **Channel creds** (Meta WhatsApp BSP / email) — to actually SEND drafted replies + verify inbound webhook
  signatures. Today: DRAFT-only (reply_state=pending_send), sending is dormant.
- **Postgres** — the box `famit` DB (support_tickets/support_messages applied via ensure_schema).

## Post-build review fixes (advisor, applied + re-verified)
- **jsonb CAST** — both `support_messages` INSERTs now `CAST(:data AS jsonb)` (crm precedent). A bare
  json.dumps string into a `jsonb` column raises on the box (text→jsonb has no implicit assignment cast).
  The offline smoke can't see this (executes zero SQL); it was a real first-real-use defect, now fixed.
- **low-confidence escalation branch made REACHABLE** — the old confidence formula floored a single hit at
  40 > CONFIDENCE_FLOOR(35), so low-confidence-escalate only ever fired on an EMPTY corpus. Removed the
  inflating floor; confidence is now monotonic in retrieval strength (score_pts cap 70 + corroboration), so
  a WEAK/tangential single FTS match falls below the floor → escalate. New test t8 asserts both a strong hit
  (auto-draft) AND a weak match (escalate). "Never answer from a too-weak retrieval" now actually holds.
- **msg_count no double-count** — draft_reply now bumps the counter only when the ON-CONFLICT INSERT
  actually inserted (RETURNING guard), matching ingest's `if appended:`.
- **redelivered dup can't reopen** — the inbound dedupe-append now precedes the reopen/sentiment-refresh
  UPDATE, so a redelivered old message (dropped as a dup) cannot reopen a resolved ticket / overwrite sentiment.

## Verification (HONEST)
- Offline smoke **48/48** (laptop, ZERO keys/network/PG): import+dormancy; router 10-routes-defined-not-
  mounted; deterministic sentiment (angry/refund/legal/human/positive/Hinglish); triage escalation decision
  (handover_on-sourced); escalation_reason severity order; thread-identity (threaded-by-thread-id vs contact
  fallback, deterministic ticket id = redelivery-safe, distinct threads -> distinct tickets); idempotent
  message id (same provider_msg_id -> same id = the ON-CONFLICT dedupe key that stops a double AI reply);
  grounded-or-escalate (empty KB -> grounded False); PG-touching entry points degrade to 'unavailable' /
  [] / None with NO db, never raise.
- ⚠ **NOT proven locally (box-only, like payments' 19/19 roundtrip):** the real PG DDL apply, RLS tenant
  isolation, the ON-CONFLICT idempotency *executing in the DB*, and the live ingest->draft->escalate
  persistence. The laptop smoke proves IMPORT/DEGRADE/LOGIC only — a green local run is NOT "RLS works".
  These are box-verifiable later (scp support/ into /opt/famit-agent, ensure_schema, throwaway-tenant
  round-trip, rm) — out of scope for this local-only build wave.

## Deferred (named, for the orchestrator's later sequential steps)
1. **Mount:** caller.py `support.router.wire(...)` + `include_router(prefix="/support")` + `support.init()`.
2. **Runner integration:** `tickets.read/write` + `kb.read` tool-catalog entries in
   `workforce/tools/catalog.py` + `/tickets` loopback endpoints in caller.py, so `AgentRunner.run("support",
   ...)` can ACTION tickets over the loopback (this wave's agent.py becomes the body of those tool fns).
3. **Channel send + inbound webhook signature verify** (WhatsApp BSP / email adapters) — flips DRAFT-only
   to actually-sent; lands with the Omnichannel Inbox + Meta-creds unit.
4. **crm 'support' TIMELINE row** — crm timeline is a rebuilt projection; add support as a stitched source
   (the crm schema already declares kind='support'). Today the stitch ensures the contact + links contact_id.
5. SLA timers / breach + CSAT survey + canned-response macros + ticket merge/split (schema notes them).

## Reversible
Fully — all NEW files under `droplet_work/support/`; nothing in the run path imports them; 2 tables
DROP-able. `rm -rf droplet_work/support` discards everything. No caller.py/agent.py edit, no .env change,
no deploy/restart/calls.
