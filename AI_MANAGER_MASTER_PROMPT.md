# AI MANAGER — MASTER SPEC (Axcrio / Famit AI Business OS)

> Canonical, founder-authored spec for the **AI Manager** — the voice-controlled
> business execution brain. Build coded files in the repo; reuse existing UI
> components + backend primitives. NOT a chatbot, NOT a mockup. Production-grade.
> ARCHITECTURE DECISION (orchestrator): AI Manager is a **dedicated coarse SERVICE**
> (own process, own Postgres schema `ai_manager_*` with FORCED RLS, own deploy/scale
> unit, own port) that calls the monolith `/api` over the network to execute actions.
> Co-located on an existing box now (DO droplet limit 3/3 full); extractable to its
> own droplet when the founder raises the limit. Reuse the monolith primitives:
> Logto auth, **firewall.py** (PIN/step-up), **wallet.py** (CostGuard holds/settle),
> **audit.py** (immutable events), RLS tenant isolation, the voice stack (LiveKit +
> VoBiz/SIP, Sarvam STT, Groq LLM, Sarvam TTS), workflow-studio, creative/media-gen.

## 1. PRODUCT CONTEXT
Autonomous business OS for vendors. Modules: AI voice calling, WhatsApp automation,
CRM/leads, campaigns, ad automation, Creative Studio (image/video/banner/brochure),
workflow automation (n8n-style, React Flow), billing/credit/wallet, analytics,
booking/site-visits/callbacks, support automation, vertical packs (real-estate, salon,
clinic, cafe, coaching, ecommerce, agency). The **AI Manager** is the main command brain:
the vendor calls a dedicated phone number from their registered phone and tells it what
to do ("Stop today's campaign", "Set budget ₹500 for Urban Nest", "Send today's analytics
on WhatsApp", "Call all hot leads after 5 PM", "Create 5 ad videos", "Create workflow: if
lead hot, send brochure, wait 2h, call again"). It understands → verifies vendor → checks
permissions → asks confirmation/PIN when needed → executes → logs everything.

## 2. CORE CONCEPT — 4 responsibilities
A. **Understand** vendor instruction (phone/voice/WhatsApp/dashboard chat → structured command).
B. **Verify authority** (caller phone, vendor account, role, permission, risk level, PIN/OTP/confirmation).
C. **Execute** platform actions (campaigns, ads, leads, WhatsApp, voice calls, Creative Studio, workflows, analytics, billing, CRM, booking).
D. **Log everything** (transcript, intent, action payload, risk, auth result, confirmation, execution result, error, audit, cost/credit entry).

## 3. BUILD RULES (strict)
1 reuse existing FE components · 2 don't redesign the app · 3 wire UI to REAL APIs (no fake) ·
4 production-grade backend · 5 multi-tenant from day one · 6 every action vendor-scoped ·
7 never execute risky actions without auth · 8 never store raw PIN · 9 hashed PIN only (Argon2/bcrypt) ·
10 audit log every command · 11 idempotency keys on execution · 12 queue/background jobs for long-running ·
13 provider-agnostic · 14 missing provider keys → clean interface + mock/dev adapter (NOT hardcoded fake logic) ·
15 build in phases, leave system clean + expandable.

## 4. MAIN USER FLOWS
**Flow 1 — Vendor calls AI Manager number:** inbound call webhook → identify vendor by caller phone →
known number continue / unknown = cannot identify, offer registered-phone/email/OTP → voice session
(streaming STT) → vendor speaks command → STT → NLU extracts intent+payload → permission+risk check →
L0 read-only execute directly / L2 verbal confirm / L3 ask PIN → verify hashed PIN → execute (or deny+log
on wrong PIN) → short spoken result summary → save full session.
**Flow 2 — Analytics:** "Send today's report to WhatsApp" → identify → classify read → fetch leads/calls/
connected/hot/site-visits/ad-spend/revenue/WA-sent/credits → short summary → send to vendor WhatsApp → log.
(No PIN unless export to an external person/email.)
**Flow 3 — Ad budget:** "Increase Meta budget to ₹1000 today" → extract campaign/platform/budget/date →
check credit → check permission → risk=high (money) → ask PIN → verify → execute via ad adapter → save → confirm.
**Flow 4 — Stop campaigns:** "Stop all losing campaigns" → find losers (high CPL/low CTR/no leads/high spend
no conv) → summarize "found 3, pause?" → confirm → PIN if high spend/bulk → pause → log each.
**Flow 5 — Creative assets:** "Create 5 video ads for 2BHK, test tomorrow" → extract campaign → use existing
brief → create creative job (hooks/scripts/image+video prompts/VO/ad copy) → Creative Studio → on ready attach
to campaign → launch=separate high-risk PIN before spend → save.
**Flow 6 — Workflow by voice:** "When lead hot → brochure → wait 2h → call again" → extract trigger+actions →
create workflow DRAFT in workflow-studio (React Flow nodes) → do NOT auto-activate → activation = confirm/PIN by risk.
**Flow 7 — Operational:** "Call all hot leads today" → count hot → check calling-time + DND/STOP/consent +
credits → estimate cost → confirm "found 42, est ₹X, start?" → PIN if bulk/billable → queue calls → log job.

## 5. CHANNELS (channel-agnostic engine, ONE engine for all)
1 phone voice call (primary) · 2 WhatsApp message/voice-note (arch-ready) · 3 dashboard chat (available) ·
4 future proactive outbound (arch-ready, inbound first). Do NOT hardcode phone-only.

## 6. RISK LEVELS
- **L0 safe read-only** (today summary, lead count, hot leads, balance, running campaigns, own analytics) — registered phone/session, usually no PIN.
- **L1 low-risk write** (draft campaign/creative/workflow, add note, schedule reminder, report draft) — logged-in/registered caller, sometimes verbal confirm.
- **L2 medium execution** (WA to selected leads, schedule limited calls, activate low-impact workflow, edit copy, assign stage, create booking) — confirm required, PIN by tenant policy.
- **L3 high execution** (launch ads, change budget, pause all, bulk call, bulk WA, billing settings, team perms, export customer data, activate high-impact workflow, delete) — PIN mandatory, sometimes OTP, strict audit.
- **L4 blocked / human admin** (delete vendor account, reveal secrets/keys/PIN, bypass compliance, spam, message STOP/DND, spend over limit, transfer ownership, disable audit, remove security) — REFUSE.

## 7. SECURITY
**Vendor identification:** match inbound caller phone to registered vendor/admin/team phone; normalize Indian + intl numbers; multiple authorized users per vendor; unknown caller executes nothing.
**PIN:** 4 or 6 digit; store ONLY Argon2/bcrypt hash; never log/return raw; rate-limit; lock after repeated wrong; log failures; reset only via secure dashboard or OTP.
**Action authorization:** check vendor_id, user_id, role, permission, action type, risk, spend limit, credit balance, compliance.
**Confirmation:** M/H risk → AI summarizes intended action → "Should I continue?" → high risk → PIN after confirm.
**Spend controls:** before paid action check wallet/credit, estimate cost, daily/monthly + campaign budget, vendor policy; reject if insufficient.
**Compliance (calls/WA):** allowed calling hours, DND, STOP keyword, consent ledger; never contact blocked leads; log the compliance decision.
**Audit log fields:** vendor_id, user_id?, caller_phone, channel, transcript, intent, action_payload, risk_level, permission_result, pin_required, pin_success/fail (never raw), confirmation_result, execution_status, provider_response_summary, created/updated resource IDs, cost_estimate, actual_cost?, timestamp, IP/webhook metadata.

## 8. DATABASE MODELS (schema `ai_manager_*`, FORCED RLS by vendor/tenant_id; reuse the P1 Postgres + RLS pattern; idempotency table)
- **ai_manager_profiles**: id, vendor_id, enabled, ai_manager_phone_number, language_preference, default_voice_provider, require_pin_for_level, daily_spend_limit, monthly_spend_limit, max_bulk_leads_without_pin, allowed_call_start_time, allowed_call_end_time, timezone, created_at, updated_at.
- **ai_manager_authorized_users**: id, vendor_id, user_id?, name, phone_number, normalized_phone_number, role, permissions(json), is_active, pin_hash?, pin_set_at, failed_pin_attempts, locked_until, created_at, updated_at.
- **ai_manager_sessions**: id, vendor_id, user_id?, channel(phone/whatsapp/dashboard), provider_call_id?, caller_phone, status(active/completed/failed/blocked), started_at, ended_at, transcript_text, stt_provider, tts_provider, llm_provider, metadata(json).
- **ai_manager_commands**: id, session_id, vendor_id, user_id?, raw_text, normalized_text, detected_intent, action_type, action_payload(json), risk_level, status(pending/needs_confirmation/needs_pin/executing/succeeded/failed/denied/cancelled), confirmation_required, confirmation_status, pin_required, pin_verified, permission_result(json), cost_estimate(json), execution_result(json), error_message, idempotency_key, created_at, updated_at.
- **ai_manager_audit_logs** (immutable): id, vendor_id, user_id?, session_id?, command_id?, event_type, severity, message, metadata(json), created_at.
- **ai_manager_action_runs** (async runs): id, command_id, vendor_id, action_type, target_module, status(queued/running/succeeded/failed/retried/cancelled), job_id?, input(json), output(json), error(json), started_at, completed_at, created_at.

## 9. BACKEND ARCHITECTURE (services inside the dedicated AI Manager service)
- **AIManagerCommandEngine** (orchestrator): receive input+context → classify intent → extract payload → detect missing → classify risk → check permissions → decide confirm/PIN → dispatch → create command record → audit.
- **AIManagerNLU**: input raw text + vendor context (active campaigns, recent leads, available modules) → strict JSON (schema in §22). Provider-agnostic; reuse existing Groq/LLM abstraction.
- **AIManagerPolicyEngine**: role permissions, vendor policies, risk rules, spend limits, compliance, PIN requirement, blocked actions.
- **AIManagerAuthService**: caller identification, phone normalization, PIN verify, lockout, authorization.
- **AIManagerExecutionRouter**: route to module adapters (campaigns, ads, creative, leads, calls, WhatsApp, workflows, analytics, billing, bookings, support) — each adapter calls the monolith /api with a service token + vendor scope.
- **AIManagerVoiceSessionService**: inbound webhook, session create, streaming audio events, STT, TTS response, barge-in if supported, final transcript save. Reuse LiveKit/VoBiz/SIP patterns; generic provider interface.
- **AIManagerAuditService**: immutable logs (reuse audit.py / events).
- **AIManagerCostGuard**: estimate cost → reserve credits (wallet hold) → settle after → release on fail → write ledger events (reuse wallet.py).

## 10. API ENDPOINTS (existing backend convention; admin/vendor auth; signature-verify webhooks)
Config: GET/PUT /api/ai-manager/profile · GET/POST /api/ai-manager/authorized-users · PATCH/DELETE /api/ai-manager/authorized-users/:id.
PIN (never expose raw): POST /pin/set · /pin/verify · /pin/reset/request · /pin/reset/confirm.
Sessions/Commands: GET /sessions · /sessions/:id · /commands · /commands/:id · POST /commands/test (dashboard chat → same engine).
Execution: POST /commands/:id/confirm · /cancel · /execute.
Telephony webhooks: POST /voice/inbound · /voice/events · /voice/status · /voice/recording.
WhatsApp: POST /whatsapp/inbound · /whatsapp/status.
Dashboard: GET /dashboard/summary · /audit-logs · /action-runs.

## 11. INTENT TAXONOMY
analytics.{today_summary,campaign_summary,lead_summary,cost_summary,send_report,compare_periods} ·
campaign.{list,create_draft,pause,resume,update_budget,update_copy,launch,kill_losers,scale_winners} ·
creative.{generate_banner,generate_video,generate_brochure,generate_ad_copy,generate_hooks,create_asset_pack} ·
lead.{list_hot,call_hot,update_status,add_note,assign,export,schedule_followup} ·
call.{start_bulk,call_single_lead,stop_queue,retry_failed,send_summary,get_recording} ·
whatsapp.{send_brochure,send_followup,send_bulk,stop_sequence,template_status} ·
workflow.{create_draft,activate,pause,update,run_now,show_runs} ·
billing.{balance,usage_today,usage_month,cost_breakdown,low_balance_alert} ·
booking.{today,tomorrow,create,reschedule,cancel,send_reminder}.

## 12. ACTION EXECUTION LIFECYCLE (no action bypasses)
receive → parse intent → create ai_manager_commands row → check permissions → estimate risk →
estimate cost if billable → confirm if needed → PIN if needed → create action_run → execute via adapter →
save result → audit log → speak final response.

## 13. RESPONSE STYLE
Real business assistant, not robotic. Short responses, confirm key details, no long phone paragraphs,
Hinglish when preferred, natural Indian business tone, summarize risky actions before executing, never reveal
sensitive on wrong PIN, on unsupported command say what it CAN do, ask only the minimum missing detail.
Examples: "Aaj 38 leads aaye. 9 hot, 17 warm, 12 low. Full report WhatsApp bhej du?" / "Ye paid action hai,
apna AI Manager PIN boliye." / "PIN match nahi hua, ye action execute nahi kar sakta." / "42 hot leads, est ₹X, calling start karu?"

## 14. DASHBOARD UI (reuse Core_2 components; add AI Manager sidebar section)
Pages: **Overview** (status, phone number, today/successful/failed-denied commands, pending approvals, credit
impact, recent sessions, recent risky actions, quick test input) · **Setup** (enable, phone, language, voice,
confirm policy, require-PIN-from-level, daily/monthly spend limit, calling hours, timezone) · **Authorized Users**
(table: name/phone/role/permission/PIN-status/active/last-used/failed-attempts/lock; add/edit/disable/reset-PIN/set-perms)
· **Command History** (date, user/caller, channel, command text, intent, risk, status, result, cost, details; filters:
status/channel/risk/date/user/module) · **Session Detail** (full transcript, command chain, recording link, execution
timeline, audit logs, provider metadata, errors) · **Pending Approvals** (commands needing approval/PIN/review) ·
**Test Console** (dashboard chat → same command engine). FOUNDER ADD-ON: make the AI Manager UI rich — multiple
pages, more features/functions, "crazy" polished — all by porting Core_2 templates.

## 15. WORKFLOW INTEGRATION
Voice → generate React-Flow-compatible workflow DRAFT (trigger node + action/delay/condition nodes + edges + notify).
Never auto-activate; draft first; activation = confirm/PIN by risk. Compatible with the workflow-studio (React Flow) builder.

## 16. CREATIVE STUDIO INTEGRATION
Trigger Creative Studio jobs (banners, WA banners, ad videos, VO script, brochure, hooks, ad copy, full pack).
Async; track job; respond "started generating, will save + notify". Launch ads after = separate high-risk PIN before spend.

## 17. AD AUTOMATION INTEGRATION
Actions: create draft, launch, pause, resume, update_budget, kill losers, scale winners, get performance, test variants,
set budget limit. High-risk: launch, budget, scale, bulk pause/resume, spend>limit. Before spend: wallet+budget+policy → confirm → PIN.

## 18. LEAD + CALLING INTEGRATION
Actions: show hot/warm/cold, call one, call all hot, schedule callbacks, retry missed, stop queue, follow-up,
update stage, add notes, book visit. Before bulk: time + DND + STOP + consent + credits + cost estimate → confirm/PIN.

## 19. BILLING / WALLET INTEGRATION
Billable: voice calls, WA messages, AI media gen, ad spend, workflow runs, LLM-heavy ops, metered PDF, external provider.
Before billable: estimate → check balance → reserve (hold) → execute → settle actual → release unused. Low balance → tell vendor.
Never negative spend unless vendor policy allows.

## 20. MULTI-TENANCY
Every query scoped by vendor_id; never cross-vendor access to leads/campaigns/calls/WA/billing/workflows/analytics/users/PIN/audit. Tenant-isolation tests required (forge tenant B while authed as A → reject).

## 21. ERROR HANDLING
Handle: unknown caller, no vendor, user disabled, wrong PIN, too many PIN attempts, insufficient credits, campaign not found,
multiple campaign matches, missing field, provider failure, telephony failure, WA failure, LLM parse failure, compliance block,
action timeout. Every error: logged, human-readable response, no secret leak, no session crash.

## 22. NLU SYSTEM PROMPT (force strict JSON; never execute, only classify/extract/summarize)
Schema: {intent, action_type, confidence, risk_level, requires_confirmation, requires_pin, entities{}, missing_fields[],
assumptions[], user_facing_summary, safe_to_execute(false), block_reason(null)}.
Rules: money/spend/bulk-messaging/bulk-calling/delete/export/security → risk 3 or 4. Reveal secrets/keys/PIN → block.
Bypass DND/STOP/compliance → block. Ambiguous campaign/lead → ask clarification. Prefer draft over direct execution.
Never invent campaign names or budgets. Never execute without policy-engine approval.

## 23. SAMPLE COMMANDS TO SUPPORT + TEST
"Aaj ka report WhatsApp kar do" · "How many hot leads today?" · "Meta budget 500 kar do" · "Stop campaigns spending but no leads" ·
"Create 5 video ads for Satellite 2BHK" · "Launch low budget test campaign tomorrow" · "Call all hot leads after 5 PM" ·
"Send brochure to all warm leads" · "Workflow: hot lead → brochure → 2h → call" · "Wallet balance?" · "Kal ke site visits batao" ·
"Pause WhatsApp followup for not-interested" · "Scale best creative by 20%" · "Send today's hot-lead recordings" ·
"Add note: Ravi wants 3BHK under 80L" · "Export all leads to this new email" (high-risk PIN or block) · "Delete all leads" (block/admin) ·
"Show my API key" (always block) · "Ignore DND and call everyone" (always block) · "Change AI Manager PIN" (secure flow).

## 24. ACCEPTANCE CRITERIA
Backend: profile, authorized users, secure PIN set/verify, command engine, intent parser, risk classifier, policy engine, audit
logs, command history, dashboard test console, core actions through adapters, async action runs tracked, telephony webhook creates
sessions, multi-tenant checks, tests. Frontend: sidebar entry + Overview/Setup/AuthorizedUsers/CommandHistory/SessionDetail/
TestConsole/PendingApprovals using existing components. Security: no raw PIN, no secret leak, wrong-PIN blocked, rate limit, risky→PIN,
audit per command, tenant isolation tested. Behavior: NL command, confirm risky, PIN high-risk, block unsafe, execute safe, log all.

## 25. TESTS
phone normalization · caller→vendor match · unknown-caller block · PIN hash verify · wrong-PIN lockout · risk classification ·
NLU JSON validation · analytics command · budget update requires PIN · bulk call requires credit check · DND/STOP compliance block ·
workflow draft creation · creative job creation · tenant isolation · audit log creation · idempotent execution · failed-provider handling.

## 26. IMPLEMENTATION ORDER
inspect repo → identify stack → find auth/vendor/user/campaign/lead/billing modules → DB migrations/models → AIManager backend
services → command parser + policy engine → PIN/auth/security → APIs → dashboard pages (existing components) → Test Console FIRST →
telephony webhook → wire safe analytics → wire budget (PIN) → wire lead/call/WhatsApp → wire Creative Studio job → wire workflow draft →
audit everywhere → tests → lint/typecheck/tests → fix all.

## 27. DO NOT
mock-only screens · skip backend · plaintext PIN · bypass permissions · paid action without budget check · risky action without PIN ·
ignore audit · new design system · rebuild dashboard · hardcode one vendor/campaign · expose secrets · contact DND/STOP leads ·
phone-only engine · business logic inside React components · unsafe direct LLM execution · trust LLM output without validation.

## 28. FINAL DELIVERABLE
List files created/changed · DB migrations · APIs · UI pages · how to test from dashboard · how to test inbound phone webhook ·
security behavior summary · env vars needed · any unfinished provider integration clearly marked.

---
### BLOCKERS (founder-side, for need.md)
- A **dedicated AI Manager phone number / DID** (inbound) on the telephony provider (VoBiz/SIP) — required for Flow 1.
- **Raise DigitalOcean droplet limit** (3/3 used) so the AI Manager service can get its own box (until then it co-locates).
- WhatsApp Cloud API creds (for the WhatsApp channel + send-report actions) — already in need.md.
- (Optional) paid Groq/Cerebras for NLU/voice latency — already in need.md.
