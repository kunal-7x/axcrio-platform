# PLAN — COMPLETE FEATURE INVENTORY for a world-class AI inbound voice sales+support brain (SMB)

> **Status:** READ-ONLY research + deep-reasoning inventory. No code, no deploy, no git. Extends
> `INBOUND-PIPELINE-MASTER-PLAN.md` and the companion explores (`plan-existing-inbound.md`,
> `plan-lead-history.md`, `plan-campaign-context.md`, `plan-aim-brain.md`, `plan-inbound-research.md`,
> `plan-rag-context.md`, `plan-handoff-hotlead.md`, `plan-vendor-modules.md`).
>
> **Purpose:** the founder *knows* he is forgetting features. This is the FULL feature inventory of a
> world-class AI inbound voice brain — each item with **what it is · why it matters · state on THIS box
> (EXISTS / PARTIAL / MISSING) with file:line evidence · the additive reuse seam**. It surfaces what is
> **not yet in the plan** so the build never silently drops a capability.
>
> **Box (read-only):** `famit@168.144.153.145` (key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`).
>
> ## 🟥 #1 RULE (unchanged) — NEVER BREAK THE OUTBOUND EARNER
> Every feature below is **ADDITIVE + ISOLATED** and **NEVER touches** `agent.py` / `famit-agent` /
> the outbound trunks `ST_fmtVmNJmpzKa`+`ST_LH8ighJJtHSi`. The earner was just restored after an infra
> mistake. The outbound regression gate `G` (famit-agent active + one real test call) runs before+after
> every wiring step. **The single best news from this audit: the box is FAR more built than the founder
> remembers — ~70% of a world-class inbound brain already exists as flag-gated, import-safe, tenant-scoped
> modules. Most of the "missing" work is WIRING the inbound voice path to modules that are already live.**

---

## 0. HEADLINE — the box is a near-complete modular monolith already

Deep audit of `/opt/famit-agent/` found **18+ purpose-built modules**, most flag-gated + dormant-safe:
`booking/` (appointments + Google-Calendar sync + reminders + no-show), `payments/` (links + invoice +
dunning, Razorpay/Stripe-dormant), `crm/` (contact spine + timeline + next-best-action), `kb/`+`brain/`
(hybrid RAG), `forms-surveys/`, `eval/` (call-quality scorers + LLM judge), `workflow/` (event/cron
triggers + DSL), `whatsapp.py`+`whatsapp_builder/`, `langdetect.py` (per-turn language mirror),
`ratelimit.py`, `firewall.py`, `support/` (grounded-or-escalate), plus the live `scheduler_loop`
(retry/callback dispatch + opt-out sweep, `caller.py:4813`). **So the feature inventory is mostly about
CONNECTING the inbound voice worker to engines that already exist — not building from zero.**

---

## 1. THE FEATURE INVENTORY (every capability · state · why it matters · the seam)

Legend: ✅ EXISTS (live/reusable) · 🟡 PARTIAL (built but dormant/un-wired/outbound-only) · ❌ MISSING.

### A. Conversation & understanding
| # | Feature | State | Evidence (file:line) | Why it matters / the seam |
|---|---|---|---|---|
| A1 | **Human-like greeting** ("Hey, this is Riya from <company>…") not robotic "I am an AI" | 🟡 PARTIAL | OUTBOUND prompt is already warm + human (`prompt.py:228` "नमस्ते/good morning" + name + company; natural per-campaign disclosure `prompt.py:274-284`). INBOUND Mode-B greeting is robotic by design (`aim_voice_agent.py:540` "Hello, this is your Famit AI Manager. Please say or enter your PIN"). Mode-A **sales-in** greeting doesn't exist yet. | The founder's ask (#4). FIX = the new `sales-in` worker reuses `prompt.py`'s warm opener verbatim ("Hey, main Riya from {company}…") + the SHORT natural disclosure clause; keep the legal AI line but phrase it like a human. Tiny edit, big trust win. The eval guard `claim_human` (`eval/scorers.py`) already prevents the agent from *denying* it's AI when asked. |
| A2 | **Multi-turn slot-filling** (hold partial intent, ask the one missing detail) | ❌ MISSING (Mode B) / 🟡 (Mode A sub-tasks) | Master-Plan §4 + Phase 2; `state_machine.py:212` `clarify` is a dead-end that discards intent+slots. | Without it, "Run a campaign" / "book a site visit" can't ask "which one? when?". Master-Plan Phase 2 covers Mode B; Mode A needs the same shared slot-fill helper for booking/callback sub-tasks. |
| A3 | **Multi-language detection + code-mix mirror** | ✅ EXISTS | `langdetect.py` per-turn (hindi/english/hinglish/gujarati), confidence floor + hysteresis, sets reply lang + TTS lang; Sarvam `language="unknown"` Hinglish STT. | Inherited by the inbound worker for free — verify after wiring, don't re-derive. |
| A4 | **Barge-in / interruption + low latency (~1.1s/turn)** | ✅ EXISTS (outbound) → reuse | Outbound tuned `AgentSession` kwargs (preemptive_generation, semantic turn-detect, endpointing, ElevenLabs flash) `agent.py:597-651`. | Inbound `sales-in` worker copies the kwargs verbatim (Master-Plan §5.7). The moat; verify post-wire. |
| A5 | **Sentiment + emotion read (in-call + post-call)** | 🟡 PARTIAL | Post-call interest score 0-100 (`agent.py:155 _summarize_transcript`); Support scores message sentiment (`support/core.py:316`). **No live/mid-call sentiment signal** on voice. | Drives the "lead getting frustrated → escalate to human" path + analytics. Add a cheap mid-call sentiment tick (reuse the hot-signal mechanism, GAP-B1 in `plan-handoff-hotlead.md`). |

### B. Routing, transfer & escalation
| # | Feature | State | Evidence | Why / seam |
|---|---|---|---|---|
| B1 | **Live human warm-transfer** (lead hot OR "talk to a human") | 🟡 PARTIAL (primitive present, un-wired) | `transfer_sip_participant` in venv (`sip_service.py:804`) + `lk sip participant transfer`. **Designed in full** in `plan-handoff-hotlead.md` (dial-into-room conference shape recommended). | Founder ask #1. Build = `transfer_to_human` tool + per-vendor handoff list. **Verify Vobiz SIP-REFER support (GAP-A1).** |
| B2 | **Hot-lead → WhatsApp team notify** (phone + summary to handoff numbers) | 🟡 PARTIAL (all blocks exist) | `whatsapp.py:248 send_whatsapp` (cold template); hot flag `caller.py:1297 hot=score>=70`; post-call WA hooks `caller.py:1417/1600`. Designed in `plan-handoff-hotlead.md`. | Founder ask #2. **Blocker = register Meta `hot_lead_alert` template (founder/Meta step).** |
| B3 | **Callback queue + speed-to-lead** (≤5min = 100× connect) | 🟡 PARTIAL | `scheduler_loop` dispatches `callback_at` retries (`caller.py:4813/4876`); outbound only. | Inbound miss/after-hours must enqueue a callback the same loop drains — never a dead drop. Reuse the scheduler; no new infra. |
| B4 | **IVR / DTMF menu navigation** (press 1 for sales…) | 🟡 PARTIAL (DTMF for PIN only) | DTMF capture wired for PIN (`aim_voice_agent.py:21`); no menu/branch tree. | Mostly obviated by NL routing (the AI *is* the IVR). A thin DTMF fallback ("press 1 to repeat / 9 for human") is a small additive nicety, low priority. |
| B5 | **Voicemail / answering-machine detection (AMD) + voicemail drop** | 🟡 PARTIAL (hint only) | `amd_hint="no_user_audio"` (`agent.py:464`); classified `caller.py:1253`. **No true AMD signal, no voicemail-drop**. Inbound rarely needs AMD (caller is live); matters for the callback-out leg. | Add a proper AMD + pre-recorded voicemail-drop on the callback/transfer-out leg so a machine doesn't burn an agent. |
| B6 | **Supervisor whisper / barge / live monitor** for the human team | ❌ MISSING | No live-listen/whisper path. | Lets a human manager listen to a live AI call + whisper guidance + barge in. Higher-tier feature; LiveKit supports a hidden participant + selective audio — additive, post-MVP. |

### C. Actions the agent can DO in-call (the revenue moves)
| # | Feature | State | Evidence | Why / seam |
|---|---|---|---|---|
| C1 | **In-call appointment / site-visit BOOKING + calendar** | 🟡 PARTIAL (full engine, un-wired to voice) | `booking/core.py` = availability + **atomic no-double-book** slot claim + reschedule/cancel + reminders + no-show; `booking/calendar_sync.py` = Google Calendar two-way (dormant-until-OAuth). Mounted `caller.py:5012`. **Voice never calls it.** | HUGE existing asset. Build = a `book_appointment` voice tool (slot-fill date/time/property → `booking.book`). Founder forgot this engine exists. |
| C2 | **Payment / deposit capture in-call** (send pay-link, confirm) | 🟡 PARTIAL (full engine, un-wired) | `payments/core.py` = pay-link + invoice + idempotent intent + dunning; Razorpay/Stripe dormant-until-keys; → CRM purchase row. | Voice tool `send_payment_link` (book site-visit fee, token amount). Blocker = gateway keys (founder). |
| C3 | **Automated follow-up scheduling + reminders** (WhatsApp/voice) | 🟡 PARTIAL | `scheduler_loop` (retries/callbacks LIVE); booking reminder `tick()` + payment `drain_followups()` are **built but the actuation enqueue is DEFERRED/un-mounted** (`caller.py:5072`). | Mount the booking-reminder + dunning ticks into the gated dial/WA path → automatic "your site visit is tomorrow" nudges. Reuse, don't rebuild. |
| C4 | **Capture brand-new caller as a lead** | 🟡 PARTIAL (designed) | Master-Plan §5.2 / Phase 4. `_update_lead_after_call` is the writer. | A banner caller with no CRM row must be created in-call (name + caller-ID + campaign) else the sale is invisible. Already in the plan; flagged here as a revenue action. |
| C5 | **CRM contact-360 + timeline + next-best-action** | ✅ EXISTS | `crm/core.py` (contact spine, stitched timeline from calls+wa+transcripts+events, derived stage, NBA). | The inbound call should write into this so contact-360 stays whole. Already mounted; the inbound write-path just needs to land here (Master-Plan Phase 5). |

### D. Knowledge & quality
| # | Feature | State | Evidence | Why / seam |
|---|---|---|---|---|
| D1 | **RAG / pgvector grounded knowledge** (product, FAQ, objection, history) | 🟡 PARTIAL (built, empty, un-wired to voice) | `kb/core.py` hybrid FTS+pgvector RRF; `kb/schema.sql` FORCE-RLS; `vendors/embeddings.py` dormant. **Corpus = 0 rows; voice never imports kb/brain.** Full design in `plan-rag-context.md`. | Founder ask #3 — CONFIRMED REAL. Tier-1 precompute + Tier-2 mid-call tool. Blockers = populate corpus + configure embedder (FTS works keyless now). |
| D2 | **Objection / FAQ learning loop** (capture → improve) | 🟡 PARTIAL | `eval/` harness replays + judges objection-handling quality offline; `kb` can store objection docs. No closed loop that *feeds* new objections back from live calls into KB. | Mine post-call transcripts for unhandled objections → draft KB chunks for review → re-ingest. Reuses `eval/` + `kb.ingest`. Medium-term. |
| D3 | **Knowledge-gap detection** ("I don't know" → flag) | 🟡 PARTIAL | Support already escalates below a KB confidence floor (`support/core.py:50` "grounded-or-escalate, never hallucinate from empty corpus"). Voice has no equivalent gap-logger. | Voice should log "caller asked X, no KB hit" → a knowledge-gap queue the vendor fills. Reuse the Support confidence-floor pattern. |
| D4 | **Call-quality scoring / QA** (every call rated) | 🟡 PARTIAL (offline gate, not per-call live) | `eval/scorers.py` (deterministic: latency, monologue, language-match, guard violations) + `eval/judge.py` (pinned LLM judge). It's a **release gate**, not a per-call production QA score. | Run a slimmed scorer per production call → a QA score + flags on the call record (panel). Reuse `eval/scorers.score_reply`. High-value, low-cost. |
| D5 | **A/B test of greetings / scripts** | 🟡 PARTIAL (outbound only) | Campaign `variants` weighted round-robin assignment for OUTBOUND (`caller.py:1954-1979`). | Extend the same variant mechanism to inbound greetings/openers; tie outcome (interest, booking) back to the variant for a real lift read. Reuse, don't rebuild. |

### E. Compliance, safety & abuse (India-specific — load-bearing)
| # | Feature | State | Evidence / research | Why / seam |
|---|---|---|---|---|
| E1 | **AI self-disclosure at call start (TRAI mandate)** | ✅ EXISTS (configurable) | `prompt.py:274-284` per-campaign natural disclosure; default `"Famit की एक AI assistant"` (`prompt.py:417`). | TRAI's synthetic-voice consultation → **mandatory AI disclosure at the start of every commercial call**. Make it non-optional for inbound sales (keep it natural per A1). |
| E2 | **Opt-out / DND / STOP suppression** | ✅ EXISTS | `suppression.json` DND store; STOP-keyword auto-suppress (`caller.py:1561/1900`); scheduler opt-out sweep. | Inbound-created callbacks must respect this list; an opted-out caller is still answered (consent-by-inbound-action) but not re-engaged outbound. |
| E3 | **Recording + consent + retention (90-day, Indian infra)** | 🟡 PARTIAL | Recorder is a `_NullRecorder` no-op (Master-Plan §3.4); no Egress, no Spaces, no recording_url. Research: TRAI **90-day min retention on Indian infrastructure**; consent must be informed+specific+revocable. | Phase 5 wires Egress→Spaces→recording_url. **Add: voice consent line + 90-day retention policy + Indian-region storage.** PIN/secret spans paused in the recording (already designed). |
| E4 | **DPDP data-handling for transcript / analytics / CRM** | ❌ MISSING (policy) | Research: DPDP governs what you may DO with the call's data (transcript, recording, sentiment, CRM, analytics) — distinct from TRAI's permission-to-call. | Needs a data-handling posture: purpose-limit, deletion-on-request, tenant data isolation (RLS already gives isolation). Mostly policy + a delete-my-data path; flag for the founder. |
| E5 | **Spam / abuse / robocaller rate-limit** | 🟡 PARTIAL | `ratelimit.py` exists; abuse rate-limit for inbound is designed (Master-Plan §5.12) but not wired to the inbound number. | Repeat abusive/robocaller numbers throttled; suppression applies inbound too. Reuse `ratelimit.py`. |
| E6 | **DLT / number-series + caller-ID attestation** | ❌ MISSING (carrier/founder) | Research: DLT Principal-Entity + header/template registration; 140-series (promo) vs 160-series (service); STIR/SHAKEN attestation. | Carrier/founder onboarding step (not code). Record so go-live isn't blocked by a surprise. Inbound DIDs should be the right series. |
| E7 | **Business-hours / after-hours / compliance window** | 🟡 PARTIAL | `brain` has `call_window_*` + `escalation_rules`; handoff design carries `hours` + `after_hours:"wa_only"` (`plan-vendor-modules.md`). | Inbound is answered anytime, but in-call-scheduled callbacks + transfers must respect the window. Reuse Brain config. |

### F. Ops, integrations & growth
| # | Feature | State | Evidence | Why / seam |
|---|---|---|---|---|
| F1 | **Post-call automations** (tag / route / trigger workflow) | 🟡 PARTIAL | `workflow/` DSL emits `lead.qualified` / `call.completed` + event/cron triggers (`workflow/__init__.py:118-153`). Inbound calls don't emit into it yet. | Hang automations (tag hot, assign owner, start a drip) off the inbound `call.completed` event. Reuse the workflow engine. |
| F2 | **External CRM sync** (Salesforce/HubSpot/Zoho) | 🟡 PARTIAL (generic webhook only) | HMAC-signed outbound webhooks + delivery log (`caller.py:1652-1685`); native connectors absent. | The webhook is the universal seam — a thin per-CRM adapter (or Zapier/n8n) covers most SMBs. Native connectors are later. |
| F3 | **Inbound analytics / reporting dashboard** | ❌ MISSING (business) | Only Prometheus infra `/metrics` (`caller.py:130/268`); no inbound business analytics (volume, containment, booking rate, transfer rate, sentiment trend). | Research: "built-in analytics — call volume, containment, sentiment, resolution — without a separate tool." Build an inbound dashboard off the call records. High-value panel page. |
| F4 | **Per-campaign / per-vendor number provisioning** | 🟡 PARTIAL (design) | `var/inbound_dids.json` DID→campaign map (Master-Plan §5.1/§5.6); registry `aim_numbers.jsonl`. Procuring DIDs = Vobiz/founder step. | Banner prints its own number → zero-ask routing. Code-side designed; DID procurement is a founder/carrier blocker. |
| F5 | **Per-vendor handoff-number list (multiple numbers)** | 🟡 PARTIAL (designed) | `plan-vendor-modules.md` §2 — `handoff{numbers[],rules,wa_template}` on the Business Brain + Settings card. | Founder ask #1 storage. A vendor adds many numbers (label/hours/roles/priority/wa-optin). Reuse `PUT /brain`. |
| F6 | **Modular + scalable codebase (add/upgrade features forever)** | ✅ MOSTLY (modular monolith) | `plan-vendor-modules.md` §3-4: clean flag-gated modules + tangled seams (`caller.py` 258KB god-router; `agent.py` sales-brain inlined). | Founder ask #5. Target seams: per-mode workers, extract a `voice_brain` lib, a `handoff/` module, wire RAG into the prompt assembler, consolidate config→PG+RLS. |

---

## 2. THINGS THE FOUNDER STILL HASN'T NAMED (net-new, beyond Master-Plan §5)

These are NOT in the master plan's "forgot" list and are NOT obvious — surfaced by research + reasoning:

1. **Per-call production QA score (D4).** The `eval/` harness exists as a *release gate* but nothing rates
   *production* calls. A slim per-call score + flags (monologue, language-mismatch, guard-violation,
   objection-quality) on every call record is a cheap, huge trust/coaching win. **Reuse `eval/scorers`.**
2. **Knowledge-gap learning loop (D2/D3).** Voice has no "I didn't know that" capture. Mine unhandled
   asks/objections → draft KB chunks for vendor review → re-ingest. Closes the loop `eval/` + `kb/` enable.
3. **Inbound business analytics dashboard (F3).** Containment rate, booking rate, transfer rate, hot-lead
   rate, sentiment trend, language mix — the founder has Prometheus infra metrics but **no business view**.
4. **DPDP data-handling posture + delete-my-data (E4).** Distinct from TRAI. Transcript/recording/sentiment
   are personal data; need purpose-limit + deletion path. Mostly policy; one delete endpoint.
5. **90-day recording retention on Indian infra + consent line (E3).** Not just "record" — record *legally*:
   consent at start, Indian-region storage, 90-day min retention. Folds into Phase 5.
6. **Supervisor whisper/barge live-monitor (B6).** A human manager listening + whispering on a live AI call —
   the single biggest "we trust the AI" enabler for a nervous vendor. Post-MVP but strategically important.
7. **True AMD + voicemail-drop on the callback/transfer-out leg (B5).** Inbound is live so AMD matters only
   on the *outbound* legs the inbound flow spawns (callback, human-dial); a machine shouldn't burn a human.
8. **A/B greetings for INBOUND + outcome attribution (D5).** Variant infra exists for outbound; extend to
   inbound openers and attribute booking/interest lift to the variant.
9. **Workflow automations on the inbound `call.completed` event (F1).** The engine exists; inbound just needs
   to emit into it (tag, assign, drip).

---

## 3. PRIORITIZED TOP-16 MISSING FEATURES (the return value)

Ordered by **(impact on the founder's core goal — full-automation revenue) × (low cost, because the engine
already exists) × (safety to the earner)**. Each line: feature — state — the one-line reason.

1. **Human-like inbound greeting** ("Hey, this is Riya from {company}…") — 🟡 reuse `prompt.py` warm opener — founder ask #4, trivial edit, instant trust.
2. **Live human warm-transfer** (hot OR "talk to a human") — 🟡 primitive present, un-wired — founder ask #1; build `transfer_to_human` + handoff list (verify Vobiz REFER).
3. **Hot-lead → WhatsApp team notify** (phone + summary) — 🟡 all blocks exist — founder ask #2; needs Meta `hot_lead_alert` template (founder step).
4. **Wire RAG into the inbound prompt** (product/FAQ/objection/history) — 🟡 built, empty, un-wired — founder ask #3; Tier-1 precompute first; populate corpus + embedder key.
5. **In-call appointment / site-visit BOOKING** — 🟡 full engine un-wired — `book_appointment` voice tool over `booking.book`; founder forgot this engine exists.
6. **Capture brand-new caller as a lead** — 🟡 designed — else the inbound sale is invisible to the panel.
7. **Callback queue + speed-to-lead on miss/after-hours** — 🟡 scheduler live — never a dead drop; reuse `scheduler_loop`.
8. **Mid-call sentiment + hot signal** (enables live transfer) — 🟡 post-call only — GAP-B1; cheap LLM tick so "gets hot → transfer NOW" can fire.
9. **Per-call production QA score on every call** — 🟡 offline gate only — reuse `eval/scorers`; coaching + trust, near-zero cost.
10. **Automated follow-up / reminder ticks** (booking + dunning) — 🟡 built, DEFERRED mount — mount the reminder/dunning ticks into the gated WA/dial path.
11. **In-call payment / deposit capture** — 🟡 full engine un-wired — `send_payment_link` tool; blocker = gateway keys (founder).
12. **Inbound business analytics dashboard** — ❌ missing — containment/booking/transfer/sentiment; founder has infra metrics, no business view.
13. **Compliant recording: consent + Egress→Indian-region + 90-day retention** — 🟡 `_NullRecorder` no-op — Phase 5 + India legal posture.
14. **Knowledge-gap + objection learning loop** — 🟡 pieces exist — capture unhandled asks → draft KB → re-ingest; closes `eval/`+`kb/`.
15. **Per-vendor handoff-number list UI + abuse rate-limit** — 🟡 designed — Brain `handoff` block + Settings card; wire `ratelimit.py` to inbound.
16. **DPDP data-handling + delete-my-data; DLT number-series/disclosure** — ❌/carrier — policy + one delete path + correct DID series; record so go-live isn't surprised.

---

## 4. SAFETY NOTE (unchanged)
Every item above is additive to the inbound workers / modules / panel; **no edit** to `agent.py`,
`build_system_prompt` (concatenate, don't modify), the outbound trunks, or the dispatch. Modules degrade
import-safe (a KB/booking/payment/WA outage cannot break a live call). Regression gate `G` before+after
every wiring step. Tenant isolation via FORCE-RLS on all new PG tables.

## 5. EVIDENCE INDEX (file:line, live box `168.144.153.145`, all read-only)
- **Greeting/disclosure:** `prompt.py:228` warm opener, `:274-284` natural disclosure, `:417` default line; inbound `aim_voice_agent.py:540` robotic Mode-B greet.
- **Booking:** `booking/core.py` (atomic no-double-book, reminders, no-show), `booking/calendar_sync.py` (Google two-way, dormant), mounted `caller.py:5012`.
- **Payments:** `payments/core.py` (links/invoice/dunning, gateway-dormant, →CRM purchase).
- **CRM:** `crm/core.py` (contact spine, stitched timeline, derived stage, next-best-action).
- **RAG:** `kb/core.py` (hybrid FTS+pgvector RRF), `kb/schema.sql` (FORCE-RLS), `vendors/embeddings.py` (dormant); corpus 0 rows; voice doesn't import. Full design `plan-rag-context.md`.
- **Eval/QA:** `eval/scorers.py` (deterministic metrics), `eval/judge.py` (pinned LLM judge) — offline gate.
- **Scheduler/follow-up:** `caller.py:4813 scheduler_loop` (retry/callback + opt-out sweep); booking `tick()` + payments `drain_followups()` DEFERRED (`caller.py:5072`).
- **Suppression/DND/opt-out:** `caller.py:1218-1234`, STOP `:1561/1900`; `ratelimit.py`.
- **Language:** `langdetect.py` (per-turn mirror); **A/B variants:** `caller.py:1954-1979` (outbound).
- **Webhooks (CRM-sync seam):** `caller.py:1652-1685` (HMAC-signed + delivery log).
- **Workflow:** `workflow/__init__.py:118-153` (event/cron triggers, DSL); emits `lead.qualified`/`call.completed`.
- **Transfer primitive:** `livekit/api/sip_service.py:804 transfer_sip_participant`; design `plan-handoff-hotlead.md`.
- **Disclosure mandate / compliance research (2026):** TRAI synthetic-voice AI-disclosure-at-start + 90-day Indian-infra recording retention; DPDP governs transcript/recording/analytics data use; DLT 140 (promo) /160 (service) number series.
