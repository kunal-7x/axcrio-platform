# RealtimeVoiceKernel v2 — OBSERVABILITY Blind-Spot Sweep

> READ-ONLY design artifact. Dimension: **OBSERVABILITY** — per-call trace (provider
> selected vs used, tokens, retrieval hits, tool calls, events), no-silent-failure,
> debuggability. Maps each gap to the owning wave (W1..W17) or flags NET-NEW.
> Grounded in: the 18-wave plan, request1/2, deep-research (7)/(8), the live
> `droplet_work/agent.py` + `aim_voice_agent.py`, and `design/obs-sec-cost.md` +
> `design/eval-harness.md`. Web-researched current voice-agent observability practice
> (LiveKit OTel, OTel GenAI semantic conventions, Hamming/Pipecat silent-failure modes).

---

## 0. GROUND TRUTH (what observability actually exists today — file:line verified)

**Outbound earner `agent.py` (the heart of the product):**
- Per-stage latency is **logged to journald only** — `LATENCY eou_delay=…`, `llm_ttft=…`,
  `tts_ttfb=…` (`agent.py:767/769/778`). These are **ephemeral text lines**, not a queryable
  per-call record. journald rotates; once gone, a call is undebuggable.
- Token usage is accumulated into an in-memory `usage` dict (`groq_in_tokens`/`groq_out_tokens`,
  `agent.py:773-774`) → flushed to `usage_events_raw/<room>.json` for **billing**, not as a trace.
- A thin transcript is saved (`var/transcripts/<room>.json`: turns + summary + outcome +
  interest, `agent.py:548`).
- **There is NO trace/correlation ID** anywhere in `droplet_work` (grep `trace_id|request_id|
  correlation|span` = 0 hits). A call cannot be followed across agent → caller → CRM → WhatsApp.
- **There is NO record of which provider was selected vs actually used** (grep `tts_provider`,
  `provider selected`, `fallback` for the OUTBOUND path = effectively absent). When a fallback
  key/provider fires, nothing durable says so.
- **There is NO retrieval-hit log** — when RAG is wired (W4), there is currently no field that
  records "query → which store → top-k doc ids → scores → was it injected → did the answer use it."
- **There is NO tool-call log on the outbound path** — outbound has no tools yet, but the plan
  adds `book_site_visit` / transfer / callback (W10/W11); none of them have an observability seam.

**Inbound `aim_voice_agent.py` is AHEAD of outbound** — it already writes "a per-call session row
+ transcript turns + executed commands + outcome" (`aim_voice_agent.py:191`). This is the closest
thing to a per-call trace in the codebase, and it is **inbound-only**. The earner has nothing
equivalent.

**Fleet-level obs already designed (`obs-sec-cost.md`):** Prometheus + Grafana on the panel box,
voice latency histograms (`famit_voice_stage_latency_seconds{stage}`), call-outcome counter,
per-vendor cost gauge, SLO alerts. **This is AGGREGATE telemetry, not per-call trace** — it tells
you "p95 TTS TTFB is high across the fleet," never "show me everything that happened on call X."
You cannot debug a single bad call from a histogram.

**Eval harness (`eval-harness.md`):** offline replay/gate. Not live observability; doesn't help
when a real call fails in production.

**Net:** the 18-wave plan treats observability as ~1.5 bullets inside **W17** ("per-call trace
(TTFA, TTFT, …, retrieval-hit, booking/handoff success) + latency/cost dashboards"). That single
line **massively underweights** the dimension. The plan is adding three-speed routing, hard
provider routing, four RAG stores, an event bus, brain packs, callback cadence, transfer, booking
— a huge surface of NEW decision points — with **no first-class, queryable, per-call trace spine
to prove any of them did what they claim on a real call.** This is the central blind spot.

---

## 1. THE CORE FRAMING THE FOUNDER + PLAN MISS

The founder's whole complaint history is an **observability failure in disguise**:
- "vendor script not working" — he has no per-call trace showing *whether the script was loaded,
  injected, and which turn deviated*. He's debugging by ear, one PSTN call at a time.
- "it still says I am an AI assistant" — fixed "three times," still fires. **There is no
  regression-visible signal** that the offending line was emitted on call N. A per-turn guard-event
  ("agent claimed-AI at turn 4") would have caught it once, forever.
- "campaign brief is compressed, loses context" — no trace shows *what context bytes were actually
  in the model's prompt on that call*, so nobody can see the loss happen.
- "Sarvam selected but silent" — the single sharpest example: **provider-selected ≠
  provider-used**, and **no telemetry recorded the divergence**. Silent for the whole call.
- "recording takes 20–60 min / never appears" — a fire-and-forget egress with **no completion
  event and no failure event** = a silent failure by construction.

Every one of these is the SAME root disease: **the system makes a decision (provider, context,
retrieval, tool, recording) and emits nothing durable and queryable about it, and fails silently
when the decision goes wrong.** The fix is not 17 separate patches; it is ONE per-call trace spine
+ a no-silent-failure contract that every wave plugs into. The plan has no such spine.

---

## 2. CONCRETE GAPS (severity · owning wave · fix)

### G1 — No per-call trace record exists; W17 reinvents it manually instead of adopting LiveKit's built-in OpenTelemetry  [CRITICAL · W17 (pull EARLY, before W1) + W1]
The plan's W17 lists per-call trace *fields* (TTFA, retrieval-hit, …) as if they'll be hand-rolled
into ad-hoc JSON. But the stack is **LiveKit Agents, which ships native OpenTelemetry** — spans for
session / job / STT / LLM / TTS / function-tools / turns, exportable via
`from livekit.agents.telemetry import set_tracer_provider` to any OTLP backend. The plan never
mentions adopting it; it risks rebuilding a worse, partial tracer by hand.
**Fix:** Make the per-call trace a **W1-core foundation, not a W17 afterthought.** Adopt LiveKit's
OTel: one `set_tracer_provider` in the agent entrypoint exporting OTLP to a self-hosted collector
(SigNoz / Langfuse / Grafana Tempo — Langfuse is the cheapest GenAI-native option and self-hostable
on the panel box next to Prometheus). Every LLM/TTS/STT/tool span then carries
`gen_ai.usage.input_tokens` / `output_tokens`, model id, latency **automatically**, per OTel GenAI
semantic conventions. W17 then *consumes* that trace for the eval/SLO dashboards instead of inventing
the capture. **This is the single highest-leverage observability decision in the whole program.**

### G2 — "provider selected vs provider USED" is never recorded — the exact Sarvam-silence class of bug stays invisible  [CRITICAL · W5 + W13]
The founder's marquee bug: select Sarvam TTS → total silence (ElevenLabs path actually ran, or
nothing ran). Today there is **zero durable record of (a) what provider the plan/entitlement
selected, (b) what provider the adapter actually instantiated, (c) whether it produced audio.**
W5 (provider router) and W13 (provider config) add MORE routing/fallback/key-rotation — i.e. more
ways for selected≠used to diverge — but neither wave makes the divergence observable.
**Fix:** Every call's trace MUST carry an explicit `provider_decision` event per modality:
`{modality: tts, requested: "sarvam_bulbul_v3", resolved: "sarvam_bulbul_v3", reason:
"plan=growth", fallback_chain: [], first_audio_ms: 187, produced_audio: true}`. A
**`requested != resolved` or `produced_audio == false` is a loud, alertable event, never a silent
log line.** Add a fleet counter `famit_provider_mismatch_total{modality,requested,resolved}` and an
SLO alert. This one record would have turned a multi-week "Sarvam is silent" mystery into a
one-glance diagnosis.

### G3 — No "no-audio / dead-air" detector → silent TTS failure looks like a successful call  [CRITICAL · W5 + NEW cross-cutting "no-silent-failure" contract]
Documented production failure mode (Pipecat #4263, LiveKit #3043, Hamming): STT works, LLM
generates text, TTS *transcript* is produced, **but no audio frames reach the caller** (codec/sample
-rate/transport drop). The call "completes," a transcript saves, billing meters it — and the lead
heard dead air. Nothing in the plan detects this. The agent doesn't assert that audio was actually
emitted per turn.
**Fix:** Per turn, assert `tts produced ≥1 audio frame` (LiveKit exposes this) and that
`audio_duration_s > 0`. If a turn generated text but emitted no audio → emit a
`silent_turn` trace event + increment `famit_silent_turn_total` + flag the call `degraded` in its
record. A call with ≥1 silent turn must surface in the dashboard as **degraded, not success**.
Pair with an empty-STT detector (empty transcript on a turn the caller clearly spoke = STT/VAD
drop). This is the heart of the founder's "no-silent-failure" intent and the plan has no owner for it.

### G4 — Recording is fire-and-forget with no completion/failure event — silent failure by design  [HIGH · W9]
The plan (W9) already targets "egress-finalize polling," good. But the OBSERVABILITY gap is sharper
than "poll it": today there is **no recording lifecycle trace** — no event for egress-started,
egress-finalized, upload-started, upload-done, presigned-url-ready, OR egress-failed. So a recording
that never lands is indistinguishable from one that's "still processing." That's exactly the
founder's "20–60 min / never appears, can't tell why."
**Fix (assign to W9):** model recording as a **state machine with an emitted event at every
transition**, written to the call's trace and the call record: `recording_state ∈
{requested, egress_running, egress_done, uploading, available, FAILED}` + `recording_latency_s` +
`failure_reason`. A FAILED or >N-minute-stuck recording is an alert, not a shrug. The CRM/call-detail
UI shows the live state, never a spinner-forever.

### G5 — No retrieval-hit trace → "is RAG even working?" is unanswerable (the founder's literal question)  [HIGH · W4]
The founder: "I really don't know if the RAG system is actually working or not." W4 wires retrieval
into the call path but the plan's trace mentions only a "retrieval-hit" boolean. That is far too
thin to debug retrieval quality or to prove the PDF he uploaded was used.
**Fix (W4 must emit, per retrieval call):** a `retrieval` trace event:
`{stage: "objection", query: "...", store: "campaign_facts", top_k: 5, hits: [{doc_id, chunk_id,
score}], reranked: true, injected: true, injected_chars: 380, latency_ms: 22, used_in_answer:
<heuristic/judge>}`. Surface a per-call "knowledge used" panel in the call-detail UI (the founder can
SEE "your PDF page 3 answered this question"). Without `injected` + `used_in_answer`, a retrieval that
fired but was ignored looks identical to one that helped — undebuggable.

### G6 — No tool-call / action trace on the OUTBOUND path (booking, transfer, callback all land here)  [HIGH · W10/W11 + W1]
Inbound (`aim_voice_agent.py`) already logs "executed commands." Outbound has no tool seam, and
W10 (callback scheduling), W11 (`book_site_visit`, warm transfer) will add the **most
business-critical, most-failed actions** ("I booked a site visit, nothing happened" / "transfer
doesn't ring") with **no per-call record that the tool fired, what args, what result, success/fail.**
**Fix:** Define a single `tool_call` trace event the outbound agent emits for every action:
`{tool: "book_site_visit", args: {...}, started_ms, ended_ms, ok: false, error:
"calendar_oauth_expired", side_effect_id: "booking#123"}`. The same event powers the firewall/audit
already in the codebase. Transfer especially: emit `transfer_state ∈ {requested, music_started,
sip_dialing, human_answered, bridged, FAILED}` — the founder's "it's not even ringing" becomes a
single failed-state read instead of a mystery.

### G7 — No correlation/trace ID stitching agent → caller → CRM → WhatsApp → booking  [HIGH · W8 + W1]
The whole product is "ONE lifecycle" (call ↔ memory ↔ WhatsApp ↔ booking ↔ CRM). But with **zero
trace/correlation ID** today, when a lead's journey breaks (call happened, CRM didn't update,
recording missing, WhatsApp didn't send) **nobody can follow the thread across services.** W8 (event
bus) is the natural owner but the plan frames it as "emit events for live dashboards," not as
"every event carries a `call_id`/`trace_id` so the full lifecycle is reconstructable."
**Fix:** Mint ONE `call_id` (already exists as room) AND a `trace_id` at dial; **propagate it as a
field on every event, every DB write, every WhatsApp send, every booking row, every log line.** W8's
Redis-Streams events MUST carry it. Then "show me everything that touched lead X's call" is one
query. This is the difference between a debuggable platform and the current archaeology.

### G8 — "Calls but nothing updated in real time" is an observability gap: no event-delivery / write-confirmation telemetry  [HIGH · W8]
The founder repeatedly: "call happened but CRM/recording/dashboard didn't update." The plan (W8)
adds an event bus to fix the *propagation*, but adds **no telemetry on the propagation itself** — no
"event emitted but no consumer acked," no "CRM write attempted → failed → silently dropped." So the
same class of "nothing updated" bug can recur silently behind the new bus.
**Fix (W8):** instrument the event bus — per stream, emit `events_published_total`,
`events_consumed_total`, `consumer_lag`, `dead_letter_total`. A consumer that falls behind or a write
that fails goes to a **dead-letter stream with an alert**, never a silent drop. The CRM/dashboard
"freshness" (seconds since last successful write for this tenant) is itself a displayed SLI.

### G9 — Multi-tenant: traces/metrics not guaranteed tenant-labeled → can't debug ONE customer, and a cross-tenant trace leak is a security hole  [HIGH · W17 + W8 + W18-security]
`obs-sec-cost.md`'s call counter has a `tenant` label, but the *per-call trace* spine (G1) has no
stated tenant-scoping rule, and traces contain transcripts (PII). Two failures: (a) you can't filter
"show me tenant Godrej's failing calls"; (b) if the trace UI isn't tenant-isolated, support staff /
a tenant could see another tenant's call content — a DPDP/privacy breach.
**Fix:** every span/event/trace record carries `tenant_id` as a first-class indexed attribute;
the trace-viewer UI is RLS/tenant-scoped exactly like the rest of the panel; PII in traces obeys the
same retention/redaction policy as transcripts. Make tenant-labeling a **lint check** in W17's
acceptance (a span without `tenant_id` fails CI).

### G10 — No cost-per-call / cost-per-outcome in the per-call trace → cost is only fleet-aggregate  [MEDIUM · W17 + W5]
`obs-sec-cost.md` gives per-vendor fleet cost gauges. But the founder's stated metric is **"cost per
appointment, not per turn"** (plan W17) — which requires cost attributed *per call and per outcome*,
which requires the per-call trace to sum its own LLM+STT+TTS+telephony spend. Today cost lives only
in the billing ledger, not joined to the call's quality/outcome.
**Fix:** the per-call trace record carries `cost_breakdown {llm, stt, tts, telephony, total_inr}`
(LiveKit's OTel spans already carry token counts → cost is a multiply). Then "cost per booked
appointment by campaign/provider" is a join, and the W17 dashboard can answer "is Sarvam actually
cheaper per *appointment* (not per minute) given its quality?" — the real economic question.

### G11 — Token-bloat (the "10k tokens every turn") is invisible per-call → can't prove the W1 context-packet fix worked on real calls  [MEDIUM · W1 + W17]
The founder's #1 cost complaint is ~10k input tokens/turn. The plan's W1 fix (context packets) needs
**per-turn prompt-token telemetry to prove it landed** — but today tokens are only summed for billing,
not exposed per-turn with the prompt-cache hit/miss. You can't see "turn 3 sent 9,800 prompt tokens,
cache miss."
**Fix:** the LLM span (from G1's OTel adoption) already carries `prompt_tokens` per turn; ADD a
`prompt_cache_hit` boolean + `prompt_layer_bytes {identity, campaign_card, lead_memory,
retrieved}` breakdown so the trace shows *which layer* is bloating the prompt. A regression guard in
W17: if median prompt_tokens/turn > target, fail. This makes the W1 win measurable and prevents silent
regression back to 10k.

### G12 — No "agent went silent / stuck turn" liveness signal during a live call  [MEDIUM · W1 + W5]
Distinct from G3 (no audio): the agent can hang mid-turn (LLM stall, provider 5xx, deadlock) and the
caller hears nothing while the call clock runs. No heartbeat/watchdog detects an in-flight turn that
never completes. The founder won't even know which calls died this way.
**Fix:** per-turn watchdog — if `turn_started` has no `agent_spoke` within N seconds, emit a
`turn_timeout` event + (optionally) a graceful filler/recovery. Counter
`famit_turn_timeout_total`. Surfaces stalls that a post-hoc transcript can't reveal.

### G13 — Language-mirror failures (Gujarati/English mis-mirror, casual-Hindi violations) have no per-turn observable signal in production  [MEDIUM · W2/W5 + W17]
The eval harness checks language-mirror **offline**. But in PRODUCTION there's no per-turn event when
the agent replies in the wrong language or emits a TTS-unspeakable script (a real past incident). The
founder catches these only by listening to calls himself.
**Fix:** run the deterministic language-classifier (already exists, `langdetect.py`) **live, per
agent turn**, and emit a `language_mismatch` / `unspeakable_script` trace event when the reply
language ≠ caller's last-turn language. Fleet counter + sample-capture for review. Cheap (the
classifier is pure-Python, zero network) and turns "he speaks too much Hindi" into a measured,
trending, alertable number.

### G14 — No durable error taxonomy / "what failed and why" — failures are bare-except-swallowed  [HIGH · NEW cross-cutting + W1]
The codebase pattern is `try/except: pass` / `logger.warning(...)` everywhere (correct for not
breaking the call, but it means **failures vanish**). There is no structured error event, no error
code taxonomy, no "this call had 3 swallowed exceptions." A call can be quietly degraded by 5 caught
errors and still report `outcome=interested`.
**Fix (NEW small cross-cutting unit, consumed by every wave):** a single `emit_call_error(code,
stage, detail, fatal: bool)` helper that every swallowed exception ALSO calls (keep the `except:
pass` for call-safety, but record it). Define a closed error-code enum (`STT_DROP`, `TTS_NO_AUDIO`,
`LLM_TIMEOUT`, `PROVIDER_FALLBACK`, `RAG_TIMEOUT`, `TOOL_FAIL`, `RECORDING_FAIL`, …). A call's record
gains `error_count` + `errors[]`; any call with `fatal` errors or `error_count>0` shows as **degraded**
in the dashboard. This is the literal implementation of "no silent failure."

### G15 — No call-detail "debug view" for the founder — debuggability is an engineer-only privilege today  [HIGH · W15 + W17]
Every gap above produces data; none of it reaches the **non-technical founder's screen**. He debugs
by placing a real PSTN call and listening. The plan's W15 (UI) lists a CallLogs page but not a
**single-call timeline view** that renders the trace: turn-by-turn transcript + per-turn latency +
provider used + retrieval hits + tool calls + errors + recording state, all on one screen.
**Fix (assign to W15, fed by W17/G1):** a per-call "Call Inspector" page — the LiveKit "Agent
insights" timeline equivalent, self-hosted: each turn shows what the caller said, what the agent
said, which provider/model, ttft/ttfb, any retrieval, any tool call, any error, plus the recording
player. This is what makes the platform debuggable by the founder himself (his standing rule:
"every backend capability ships with a frontend control/test UI"). Without it, all the trace data is
invisible to the one person who needs it.

### G16 — No data-retention / cost ceiling on traces themselves → observability becomes a cost/PII liability  [LOW · W17 + W13]
Full per-call traces with transcripts + audio refs are PII-heavy and grow unbounded. The plan has no
retention/redaction/sampling policy for the trace store itself. At 500-telecaller scale this is both a
storage-cost leak and a DPDP exposure.
**Fix:** tiered retention (hot 7–14d full-fidelity in the trace backend, then summarize + drop
raw spans to cold object storage; redact PII fields per policy); head-based sampling for
high-volume healthy calls, **always-keep for degraded/failed/flagged calls** (never sample away a
failure). Wire to the same retention dashboard W13 already plans.

### G17 — No synthetic canary / heartbeat call to detect a fully-down pipeline before the founder/customer does  [MEDIUM · NEW + W17]
All telemetry above is reactive — it tells you a call failed *after* a real lead got a broken call.
There's no proactive "is the whole voice pipeline alive right now?" probe. If LiveKit/SIP/Groq/TTS is
down, the first signal is an angry customer.
**Fix:** a scheduled **synthetic held-canary** (the plan already forbids unsolicited PSTN burns — so
use a held/loopback synthetic session, NOT a real outbound dial): every N minutes spin a synthetic
session that exercises STT→LLM→TTS→tool→recording end-to-end and emits `canary_ok/fail` +
stage latencies. A failing canary pages before real traffic is harmed. (Distinct from the W17
benchmark harness, which is for provider A/B, not liveness.)

---

## 3. NET-NEW WAVE THE PLAN IS MISSING

**NEW WAVE — "W-OBS: Per-Call Trace Spine + No-Silent-Failure Contract" (foundation, pull to Wave A
alongside W1).** The plan buries observability in W17 (quality/eval) as if it's a final-QA concern.
It is not — it is **foundational instrumentation that every other wave must emit into.** Stand up
FIRST: (1) adopt LiveKit OTel + a self-hosted GenAI trace backend (G1); (2) define the canonical
per-call trace schema with the events all waves emit — `provider_decision`, `retrieval`, `tool_call`,
`recording_state`, `transfer_state`, `silent_turn`, `language_mismatch`, `call_error` (G2–G6, G13,
G14); (3) the no-silent-failure contract (every silent failure becomes a loud event + a `degraded`
call flag); (4) `trace_id`/`tenant_id` propagation across services (G7, G9). Then W1–W16 each plug in
their events, and W17 *consumes* the spine for eval/SLO/dashboards instead of inventing capture.
**Rationale:** building the kernel, providers, RAG, booking, transfer, callback FIRST and bolting
observability on LAST guarantees a repeat of the founder's whole grievance list — decisions made,
nothing recorded, failures silent. Instrument first; you cannot debug what you didn't trace.

---

## 4. PRIORITIZED SUMMARY

| # | Gap | Sev | Wave |
|---|---|---|---|
| G1 | No per-call trace; adopt LiveKit OTel instead of hand-rolling | CRITICAL | W17→W1 (NET-NEW W-OBS) |
| G2 | provider selected vs USED never recorded (Sarvam-silence class) | CRITICAL | W5 + W13 |
| G3 | No no-audio/dead-air detector → silent TTS fail looks like success | CRITICAL | W5 + NET-NEW contract |
| G4 | Recording fire-and-forget, no lifecycle event | HIGH | W9 |
| G5 | No retrieval-hit trace ("is RAG even working?") | HIGH | W4 |
| G6 | No tool-call trace on outbound (booking/transfer/callback) | HIGH | W10/W11 + W1 |
| G7 | No trace_id stitching across agent→caller→CRM→WhatsApp→booking | HIGH | W8 + W1 |
| G8 | Event bus has no delivery/write-confirmation telemetry | HIGH | W8 |
| G9 | Traces not tenant-labeled → can't debug one customer + leak risk | HIGH | W17 + W8 |
| G14 | Failures bare-except-swallowed; no error taxonomy | HIGH | NET-NEW + W1 |
| G15 | No founder-facing per-call "Call Inspector" debug view | HIGH | W15 + W17 |
| G10 | No cost-per-call/per-outcome in trace | MEDIUM | W17 + W5 |
| G11 | Token-bloat invisible per-turn; can't prove context-packet fix | MEDIUM | W1 + W17 |
| G12 | No stuck-turn/agent-silent liveness watchdog | MEDIUM | W1 + W5 |
| G13 | Language-mismatch has no live per-turn signal | MEDIUM | W2/W5 + W17 |
| G17 | No synthetic canary/heartbeat for full-pipeline liveness | MEDIUM | NET-NEW + W17 |
| G16 | No retention/redaction/sampling on the trace store itself | LOW | W17 + W13 |

**Bottom line:** the founder's entire bug list (Sarvam silent, "is RAG working?", recording never
appears, transfer doesn't ring, still says AI-assistant, nothing updates in real time) is one
disease — **decisions made with no durable per-call record and failures that vanish silently.** The
plan's 18 waves add enormous new decision surface (routing, RAG, providers, tools, events) but treat
observability as a W17 footnote. The fix is to promote it to a foundational NET-NEW wave: ONE
per-call OpenTelemetry trace spine + a no-silent-failure contract that every wave emits into, plus a
founder-facing Call Inspector so the one person who needs to debug can actually see it.
