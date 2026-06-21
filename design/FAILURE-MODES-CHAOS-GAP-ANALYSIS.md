# FAILURE MODES / CHAOS — Blind-Spot Gap Analysis (RealtimeVoiceKernel v2)

**Status:** READ-ONLY research + diagnosis. Zero box mutation, zero code edit, zero deploy. Doc-only.
**Date:** 2026-06-18
**Dimension:** FAILURE MODES / CHAOS — provider outage mid-call, STT garbage, caller hangs up mid-tool,
calendar/WhatsApp down, partial deploys, what DEGRADES vs what BREAKS.
**Scope:** Find what the founder AND the 18-wave plan miss on chaos/resilience. Map each gap to its
owning wave (W1..W17) or flag NET-NEW. Grounded in the live earner code (`_inbound_ref/agent.REFERENCE.py`
= mirror of box `agent.py` md5 `9150fabe`), `droplet_work/caller.py`, the deep-research reports (7)/(8),
and current web best practice.

> **Framing — and the dividing line from the latency doc.** The companion `LATENCY-TAILS-GAP-ANALYSIS.md`
> owns *how slow* the tail gets (p95 TTFA, failover latency, cold-start). THIS doc owns the *binary*
> question the founder keeps hitting: **when a thing fails, does the call DEGRADE gracefully or does it
> silently BREAK and the lead is lost / data is corrupted / money is mischarged?** The plan is written as
> a happy-path build ("wire RAG", "add booking tool", "re-enable scheduler") and almost nowhere specifies
> the failure branch. Voice is uniquely unforgiving: there is **no retry button for a human on a phone
> call** — a 5s silence or a confidently-wrong "booked!" is permanent. The founder already lived three of
> these (Sarvam silence, dead handoff, no recording) and read them as "feature broken." They are
> **failure-handling gaps**, and the plan re-adds the same shape of gap to every new subsystem.

---

## 0. The structural truth the plan never states: durable state is fire-and-forget to LOCAL DISK in a shutdown hook

This is the master failure mode that every CRITICAL below inherits.

- **Ground truth (live earner, verified):** the entire durable record of a call — transcript, AI summary,
  lead memory, AND the billing/usage events — is written **only inside `_persist_memory()`, an
  `add_shutdown_callback`** (`agent.REFERENCE.py:423/479`), to **local box files** (`TRANSCRIPT_DIR /
  f"{room}.json"`, `mem.save_memory`). The plan's research anchor claims "**Postgres as the source of
  truth**" — but the live call path does NOT write call truth to Postgres synchronously. It writes JSON to
  one box's filesystem at teardown.
- **Worse:** `_persist_memory` → `_summarize(turns)` makes a **blocking `httpx.post` to Groq
  `/chat/completions`** (`agent.REFERENCE.py:170,244`) **inside the shutdown callback**. A network LLM call
  in a hard-timeout teardown path is the textbook way to lose data: if the worker is SIGKILLed, OOM-killed,
  crashes, or the shutdown timer fires before the Groq call returns, **the whole call's transcript +
  summary + memory + billing event are lost with zero trace.** The founder's "call happened but I got no
  recording / no hot-lead update / no CRM change" is partly THIS: the call worked, the persistence at the
  end didn't, and nothing detected the loss.
- **`caller.py` state is also JSON-files-on-one-box** (`leads`, `calls`, `suppression`, `retry_queue.json`)
  guarded by a file-lock (`_file_lock`, `caller.py:788`). There is one good atomic-write primitive
  (`_atomic_write_json`, `:794` — temp+fsync+`os.replace`) but it is NOT used everywhere (many sites do a
  bare `path.write_text(json.dumps(...))` — `:781,:906,:1499,:4574` — non-atomic, corruptible on crash).

**This is the #1 chaos blind spot: the system has no durable, crash-safe, transactional record of a call.**
Everything is best-effort, end-of-call, single-box, local-disk, partly non-atomic, with a network call in
the teardown. Every "X didn't update after my call" the founder reports is a symptom of this one root.
The plan's W8 (event bus) and W9 (recording) *touch* this but never make **"a call's outcome is durably
recorded the instant it is known, transactionally, surviving a worker kill"** a hard invariant.

---

## 1. Provider outage MID-CALL — the plan has fallback chains but no "what the lead HEARS while we fail over"

### Gap 1A — TTS websocket dies mid-utterance → agent goes SILENT for the rest of the call, no recovery (CRITICAL)
Confirmed in the live code AND in upstream bug reports. `agent.REFERENCE.py:574-578` documents the exact
trap: sending an unsupported language code to ElevenLabs flash → `unsupported_language(1008)` → **"TTS
websocket dies → the agent goes SILENT for the rest of the call (update_options is sticky)."** Web research
confirms this is a *general* failure, not just the language case: LiveKit agents issues **#4676 / #4609 /
#306 / #3235** — the ElevenLabs TTS/STT WS "closes unexpectedly (status_code=-1)" and the stream **raises
`retryable=True` but does NOT reconnect**; the plugin has no framework-level stream recreation. Sarvam has
the analogous silent-drop (see latency doc 2A). So today: **one WS hiccup at any point = the lead hears
nothing for the rest of the call, the agent has no idea, and there is no watchdog to detect or recover.**
The current code only clamps the *known* language trigger (`safe_tts_language_code`) — it does nothing for
a generic mid-call WS death.

**Fix (W5 + W1):** (1) a **TTS-output watchdog**: if the synthesizer produces no audio frame for ~1.2s
while the agent believes it is speaking, **tear down the dead WS and recreate a FRESH one** (do NOT retry
the same dead socket — research: retry-same-WS fails with the same error) and re-synthesize the remaining
text; (2) if recreation fails twice, **fail over to the other provider mid-utterance** (warm standby WS,
latency doc 2B); (3) a "silence guard" at the kernel: the agent must NEVER be in a state where it believes
it is speaking but no audio has flowed for >1.5s without firing recovery. Eval (W17): kill the TTS WS
mid-utterance, assert audio resumes within budget and the call completes.

### Gap 1B — STT garbage / mis-transcription is acted on as if it were truth; no confidence gate, no "I didn't catch that" (HIGH)
The plan treats STT as reliable. Reality: Sarvam (or any STT) under load / on a noisy India line returns
**garbage or empty transcripts**, and the LLM will **confidently act on garbage** — answer the wrong
question, extract a wrong phone number / wrong callback time / wrong name, or trigger a wrong tool. There is
NO confidence threshold, NO "low-confidence → re-prompt", and NO guard before a *consequential* action
(booking, transfer, opt-out, callback scheduling) that the transcript it is acting on is even coherent. The
founder's "speaks half a sentence / asks weird things" is partly the LLM reacting to mangled STT input.

**Fix (W5 + W6):** (1) gate consequential tool calls behind a **transcript-coherence / confidence check**
— if STT confidence is low or the text is degenerate, the agent **re-prompts** ("sorry sir, line thodi
unclear thi — aap phir se bata sakte hain?") instead of acting; (2) **always read back** safety-critical
extracted values (phone for callback, date/time for booking, name) before committing — a human telecaller
does this reflexively; (3) an STT-stall watchdog (latency doc 2D) for the *empty* case. Eval (W17): feed
garbled/empty STT, assert the agent re-prompts and never books/transfers/opts-out on noise.

### Gap 1C — One bad provider/key takes down ALL concurrent calls — no circuit breaker, no bulkhead (HIGH)
`agent.REFERENCE.py:506` round-robins Groq keys per call, which spreads *load* — but it is NOT a circuit
breaker. If a key is rate-limited/revoked, or if Groq/Sarvam/ElevenLabs has a regional incident, **every
in-flight and new call keeps hammering the dead dependency**, each eating its own full timeout, and the
"failover" (if any) is per-call sequential. At the 500-concurrent scale the product targets, this is a
**cascading failure**: one degraded provider serializes/stalls the whole fleet. Web best practice
(circuit-breaker + bulkhead) is absent from the plan: there is no shared health state that says "Sarvam is
open-circuit right now, skip it for the next 30s and go straight to ElevenLabs."

**Fix (W5 + W13):** a **provider health registry** (shared across the worker pool, e.g. in Redis) with a
**circuit breaker** per provider/key (closed→open→half-open): N failures in a window → open → all calls
fast-skip to the fallback for a cooldown → half-open probe to re-close. Add **bulkheads**: a stuck call /
provider can't consume the whole connection pool (cap concurrent waits per provider). This is the single
biggest resilience gap for the 500-team goal. Eval (W17): hard-fail one provider, assert calls fail over
fleet-wide within one breaker window, not call-by-call.

### Gap 1D — No graceful-degradation ladder: when failover ALSO fails, the agent dead-airs or drops (HIGH)
Every fallback can itself fail (both TTS providers down, both Groq keys 429, network partition to all of
US). The plan defines fallback *chains* but no **terminal behavior**. A real telecaller, when truly stuck,
says "sir line bahut slow hai, main aapko 2 minute mein call back karti hoon" and **schedules a callback +
exits gracefully** — it does NOT sit in silence. The kernel has no such ladder.

**Fix (W1 + W6):** explicit **degradation ladder** as kernel behavior: filler → retry-fresh-connection →
swap provider → **cached canned audio line** (pre-synthesized "ek second sir") → **graceful exit that
auto-enqueues a callback** so the lead is recovered, not burned. Never dead-air > budget; never silently
drop. Eval (W17): inject total-provider-failure, assert graceful exit + callback enqueued, not silence.

---

## 2. Caller hangs up MID-TOOL — the orphaned-side-effect / partial-state class (the founder's booking pain, generalized)

### Gap 2A — Tool side effects are not transactional: a hangup mid-booking leaves a half-written record OR a "confirmed" that never persisted (CRITICAL)
This is the deepest correctness gap and it is exactly the founder's "I booked on the call, nothing updated"
**plus its mirror image**. When `book_site_visit` runs (W11, to-be-built) it will: validate → write PG row
→ create Google Calendar event → confirm to caller → emit event → WhatsApp. If the **caller hangs up**, or
the **worker is killed**, or the **calendar API 503s** at any point in that chain, you get one of two
silent failures: (a) the agent already SAID "ho gaya, booking confirm" but the PG/calendar write never
happened → **ghost booking the vendor never sees**; or (b) the PG row was written but the calendar event
and WhatsApp were not → **partial booking, no calendar, no confirmation**. Web research names this exactly:
"the booking API returns a 503 and the agent says 'Your appointment is confirmed.'" The plan's W11 is a
happy-path build ("AI book_site_visit tool → persist → calendar") with **no failure branch and no
atomicity.**

**Fix (W11 + W1, the architecture, not a patch):**
1. **Write-before-speak**: the agent must persist the booking to PG (the source of truth) and get a
   committed ack **BEFORE** it utters "confirmed". If the write fails, it says "ek second sir, main confirm
   kar ke aapko WhatsApp pe bhej deti hoon" — never a false confirm.
2. **Outbox pattern** for downstream side effects: PG write + an `outbox` row in ONE transaction; a
   separate durable worker drains the outbox → Calendar + WhatsApp with **idempotency keys** (Gap 2C). The
   live call NEVER blocks on calendar/WhatsApp and a hangup can't orphan them.
3. **Validate-and-store-in-session-early** (web best practice): downstream tool reads booking fields from
   validated session state, not from re-parsing the model's args — so a hangup mid-flow has a complete,
   validated intent to replay.
Eval (W17): hang up the caller (and separately SIGKILL the worker) at each step of booking; assert the
final state is either fully-booked-and-confirmed or cleanly-not-booked — **never a ghost confirm, never a
half-record.**

### Gap 2B — Calendar / WhatsApp / CRM DOWN is unhandled: the call blocks, dead-airs, or silently no-ops (HIGH)
The plan assumes Google Calendar OAuth (W11), WhatsApp (W14/W16), and CRM push (W7/W8) are *up*. They will
be down (token expired, Meta API rate-limit, Google 5xx, quota). Today there is no spec for: token-expiry
re-auth, API-down queueing, or what the lead hears if the agent tries a calendar check live. If a
slot-availability check is on the hot path and Calendar is slow/down, the lead **dead-airs** (latency doc)
or the agent **hallucinates a slot**. If WhatsApp is down, the daily report / hot-lead notify just
**silently vanishes** (the founder's "I didn't get the WhatsApp").

**Fix (W11 + W14 + W16):** (1) **never put a 3rd-party API on the hot path synchronously** — pre-load
slot availability into the warm-path cache at dial-time; if booking needs a live check and the API is down,
offer a tentative hold + async-confirm, don't dead-air; (2) **every external integration goes through the
outbox/queue with retry + dead-letter** (Gap 2C) so an API outage = delayed delivery, not lost delivery;
(3) **OAuth token-refresh + expiry alerting** as an explicit W11/W13 feature (a silently-expired Google
token = every booking silently fails to sync — the founder would never know until a customer no-shows a
slot that was never on the calendar). (4) Surface integration health in the UI (W13/W15) so "Calendar
disconnected" is visible, not invisible.

### Gap 2C — Side effects are NOT idempotent → retries double-book, double-WhatsApp, double-charge the wallet (HIGH)
Once you add an outbox/retry (Gap 2A/2B) or re-enable the callback scheduler (W10) with at-least-once
semantics, **every retry without an idempotency key duplicates the side effect** (web best practice
confirms: "retries without idempotency means duplicates"). Concretely: a retried booking → **two calendar
events**; a retried hot-lead notify → **two WhatsApp blasts to the lead** (spam + TRAI risk); a retried
wallet charge → **double-debit** (the wallet already has an idempotency table per the F4 memory note, but
the *call→charge* path and the new side effects must actually USE it). The dialer itself: a crash between
"dialed" and "marked-dialed" → **the same lead gets called twice** (the founder explicitly fears
re-dialing/spam — that's what killed the old scheduler).

**Fix (W10 + W11 + W14 + W8):** a **deterministic idempotency key per logical action** (e.g.
`booking:{lead_id}:{slot}`, `wa_notify:{lead_id}:{campaign}:{date}`, `dial:{lead_id}:{attempt}`), stored
and checked before every side effect; the dialer marks intent-to-dial **before** dialing (claim/lease) so a
crash can't double-dial; calendar/WhatsApp use the provider's own idempotency/dedup where available. Eval
(W17): replay every side effect 3× under simulated retry, assert exactly-once visible effect.

### Gap 2D — Mid-tool hangup leaves the lead's lifecycle state ambiguous (was it a booking or not?) (MEDIUM)
If the caller hangs up *during* a discovery/booking/transfer, the post-call classifier (`_summarize`)
runs on a truncated transcript and may mis-bucket the lead (mark "not interested" a lead who was actively
booking when the line dropped, or vice-versa). There's no "interrupted/incomplete" outcome state — it's
forced into hot/warm/cold/dead, losing the signal that this lead was mid-action and should be **re-dialed
with continuity** ("sir hum baat kar rahe the, line cut gayi").

**Fix (W7 + W10):** add an explicit **`incomplete` / `dropped-mid-action` lead state** carrying *what
stage* was interrupted; the scheduler prioritizes a fast continuity callback for dropped-mid-booking leads
and the brain resumes from the interrupted stage. Eval: drop mid-booking, assert lead = incomplete +
continuity callback enqueued, not mis-classified.

---

## 3. PARTIAL DEPLOYS / operational chaos — the multi-service single box has no safe-deploy or drain story

### Gap 3A — A deploy/restart drops or freezes live calls — no connection draining, env captured at import (CRITICAL)
The voice box runs multiple services (`famit-agent`=earner, `aim-voice-agent`=inbound, `famit-caller`) and
the deploy recipe is "scp + `systemctl restart`". Web research + LiveKit docs are explicit: a worker
SIGTERM on restart either **drops the in-flight call** (if forced) or **blocks the deploy up to the 30-min
`drain_timeout`** — and the live `WorkerOptions` (`agent.REFERENCE.py:758`) sets **no `drain_timeout`, no
`shutdown` hook config, no `num_idle_processes`/warm-pool, no `load_threshold`** (all defaults). Worse, the
**WARM-TRANSFER outage was caused by exactly this class of bug**: `_OUTBOUND_TRUNK` is captured at module
import (`aim_voice_agent.py:172`), so a `.env` change + `famit-caller`-only restart left the voice agent
running the **old dead trunk in memory** → every handoff dialed a spam-blocked trunk for ~20h
(`WARM-TRANSFER-DIAGNOSIS.md`). **Config-captured-at-import + partial-service-restart = silent split-brain
across the box.** The plan adds 18 waves of new flags and services to this same fragile deploy model with
no deploy-safety wave.

**Fix (NET-NEW deploy-safety concern → W0 infra + W13):**
1. **Graceful drain on deploy**: configure `drain_timeout` sanely (calls are minutes not hours — set ~5
   min, not 30), stop accepting new jobs, let in-flight calls finish, THEN swap. Use blue/green or a warm
   replacement worker so new calls route to the new build while old calls drain on the old one.
2. **Kill config-at-import**: read failover-critical config (trunk IDs, provider endpoints, flags) **at
   call start**, not module import, OR add a SIGHUP/`/reload` that re-reads `.env` without a full restart,
   so a config change can't leave a service split-brained.
3. **Deploy must restart the RIGHT set of services together** (a checklist/automation), and **assert the
   new code is actually loaded** (the RECOVERY-STATE md5 discipline) — a partial restart that reloads
   `caller.py` but not the agent is the exact bug that bit warm-transfer.

### Gap 3B — Flags default-ON-when-absent and are read inconsistently → "I deployed the fix but it didn't take" (HIGH)
`RECOVERY-STATE.md:66-67` already shows the hazard: `CTX_CACHE` and `INBOUND_PROV_LOCK` were "committed to
flip to 1" but are **absent from the live `.env`**, so the *code default* silently governs — nobody is sure
if the feature is on. With 18 waves each adding flags (RAG_INJECT, WALLET_ENABLED, RETRY_SCHEDULER_ENABLED,
provider locks…), the failure mode is **a fix that's deployed but inert because a flag's absent-default is
wrong**, or **a kill-switch that doesn't kill because it's read at import**. The founder's recurring "you
said you fixed it but on the call it still does the old thing" is partly this.

**Fix (W0 + W17):** (1) a **single config module** that resolves every flag with an explicit default and
**logs the effective value at startup** (one line: "RAG_INJECT=1 CTX_CACHE=0 …") so the live state is
never a mystery; (2) **fail-safe defaults** (a missing kill-switch must default to SAFE/off for risky
behavior, not on); (3) a startup **config-assertion** that warns if a flag the wave expects is absent; (4)
a tiny `/config` health endpoint that dumps effective flags so "is it actually on?" is one curl, not an
`/proc/environ` autopsy.

### Gap 3C — Schema/data migrations vs. running old code = split-brain on the shared DB (MEDIUM)
The plan adds many new PG tables (booking lifecycle, lead lifecycle, event store, number pool). With
multiple services + a strangler "dual store" (`STORE_MODES=dual`, RECOVERY-STATE:64), a migration that
runs while old code is still live can **read/write a half-migrated schema** (old code writes the JSON leg,
new code expects the PG leg, they diverge). There's no expand/contract migration discipline named.

**Fix (W0 + W8):** **expand/contract migrations only** (add columns/tables backward-compatibly → deploy
code that writes both → backfill → switch reads → contract later); every migration reversible; never a
destructive migration against a running old binary. Document in the deploy checklist.

### Gap 3D — No health/readiness probe that reflects real call-serving ability; a "running" worker can be dead (HIGH)
`curl /health 200` is the only gate. Web + LiveKit issue #3841: **workers can die silently after prewarm**
yet the process still answers `/health`. A worker whose provider connections are all dead, or whose Redis/PG
is unreachable, or that's wedged on a drained Groq stream (latency doc 2C) will pass `/health 200` and **the
dispatcher will route fresh leads straight into a dead worker** = the freshest leads get cold silence.

**Fix (W0 + W17):** a **deep readiness probe** that actually checks the dependencies the call path needs
(can reach Redis, PG, at least one TTS + one LLM provider; VAD/turn model loaded) and **deregisters a
worker from dispatch when unhealthy**; an external **synthetic canary** call on a schedule that exercises
the real stack and alerts on failure (the only thing that catches "all green per component, product dead" —
the founder's #1 standing complaint).

---

## 4. Cross-cutting chaos the plan misses entirely

### Gap 4A — No "what does the lead HEAR" spec for any failure — silence is the default failure output (CRITICAL)
Tying §1–§3 together: across the plan there is **no single owner of the audible failure contract.** Every
failure mode above currently degrades to the same thing the founder hates most: **dead air**, or a
**confident lie** ("booked!"), or an **abrupt drop**. A human telecaller NEVER goes silent — they fill,
acknowledge, recover, or gracefully exit. The kernel needs a **first-class "audible failure" policy** so
that *no matter which subsystem fails*, the lead always hears a human-plausible response, never silence and
never a lie.

**Fix (W1, kernel invariant):** "**the lead never hears silence > 1.5s and never hears a confirmation of
something that didn't durably happen**" is a HARD kernel invariant, enforced by the silence-guard (1A),
write-before-speak (2A), and degradation ladder (1D). This is the chaos counterpart to the latency SLO and
should be in the acceptance criteria.

### Gap 4B — No chaos / fault-injection testing; everything is validated on ONE happy-path call (HIGH)
The plan's verification is all single happy-path ("a booked visit is a real record", "warm transfer rings").
**Nothing injects faults.** None of the failure branches above will ever be exercised before a real lead
hits them — which is precisely how the founder discovered Sarvam-silence, dead-handoff, and lost-recording
**in production, on real leads.** Web best practice for production voice agents is explicit fault injection.

**Fix (W17, NET-NEW test class):** a **chaos harness** that, against shadow/synthetic sessions (never a
real PSTN burn), injects: TTS WS kill mid-utterance, STT garbage/empty, provider 429/timeout/total-outage,
worker SIGKILL mid-call, calendar/WhatsApp 503, Redis/PG unreachable, mid-tool hangup, partial-deploy/old-
trunk. Each asserts a **graceful** outcome (no silence > budget, no ghost booking, no data loss, no
double-side-effect). **This harness is the only proof the 500-team claim survives contact with reality.**

### Gap 4C — Recording finalize is fire-and-forget → silent permanent loss of the call audio (HIGH)
Already a known symptom ("recording takes 20-60 min / never appears") but the plan (W9) frames it as a
*latency* fix ("egress-finalize polling"). The deeper chaos issue: **egress can FAIL** (storage creds
expired, R2/B2 5xx, segment upload dropped) and there is **no detection, no retry, no alert** — the call
audio is **permanently lost** and nobody knows. For a product whose value is "listen to your calls", a
silently-lost recording is a trust-killer.

**Fix (W9):** treat egress as a durable job with **completion confirmation, bounded retry, dead-letter,
and an alert on permanent failure**; mark the call row "recording: pending/ready/FAILED" so a failure is
*visible* in the UI, not invisible. Reconcile: a call with no recording after N minutes auto-flags for
investigation.

### Gap 4D — Redis as event bus (W8) is at-least-once / can lose un-acked messages → events silently dropped (MEDIUM)
The plan makes Redis Streams the real-time backbone (W8) so dashboards/CRM/bookings "react live". Redis
Streams + consumer groups are **at-least-once** (need explicit ACK + claim of pending) and a Redis restart
without AOF can **lose recent un-persisted entries**. If an event (lead→hot, booking-created) is dropped,
the dashboard silently never updates — the founder's "nothing updates in real time" returns, now
intermittently and un-debuggably.

**Fix (W8):** consumers use **consumer groups with explicit ACK + a pending-entry reclaim loop**; Redis
runs with **AOF** for the event stream; **PG remains the source of truth** and the stream is a *notifier*,
not the record — every UI view can fall back to reading PG so a dropped event self-heals on next read/poll.
Never make a dropped Redis message = permanently-wrong UI.

### Gap 4E — No per-tenant blast-radius isolation: one tenant's runaway campaign / bad data starves everyone (MEDIUM)
Multi-tenant + 500-concurrent: one tenant firing a huge campaign, or one tenant with a malformed
campaign/brain JSON that throws on every call, can **consume the shared worker pool / provider quota / Redis
/ PG connections** and degrade *all* tenants (noisy-neighbor). The plan has tenant *data* isolation (RLS)
but no tenant *resource* isolation under chaos.

**Fix (W12 + W13):** **per-tenant concurrency caps + provider-quota bulkheads** (a tenant can't exceed its
plan's concurrent-call ceiling); a malformed-campaign guard (one tenant's bad JSON fails *that* call
gracefully, never crashes the worker for others); fair-share scheduling so a 5000-lead campaign doesn't
starve a 50-lead one.

### Gap 4F — Outbound dial AMD/no-answer/voicemail chaos: agent talks to a voicemail / dead air as if it's a human (MEDIUM)
On the *outbound* earner, the call connects to **voicemail, IVR, wrong number, or dead silence** constantly.
The code has a weak `amd_hint="no_user_audio"` (`agent.REFERENCE.py:466`) computed only at the END. There's
no live "is a human actually there?" gate, so the agent may **deliver its whole opener to a voicemail beep**
(wasting cost + leaving a creepy half-pitch on someone's VM) or sit waiting on dead air. The plan (W12)
mentions "no abandoned calls" for compliance but not the **inbound-of-outbound** AMD handling as a failure
mode.

**Fix (W12 + W1):** real **answering-machine detection** + a "are you there?" probe before committing the
pitch; if voicemail → leave a short compliant message or drop per policy + reschedule; if dead air →
re-greet once then end + reschedule. Eval: connect to a VM/silence, assert no full-pitch-to-voicemail and a
clean reschedule.

---

## 5. Summary — owning-wave map

| # | Gap | Sev | Owner |
|---|---|---|---|
| 0 | Durable call record is fire-and-forget to local disk in a shutdown hook (w/ a network call) → call truth lost on any worker kill | CRITICAL | NEW / W8+W9 (+W1) |
| 1A | TTS WS dies mid-utterance → silent rest of call, no detect/recover | CRITICAL | W5/W1 |
| 1B | STT garbage acted on as truth; no confidence gate / read-back | HIGH | W5/W6 |
| 1C | One bad provider/key cascades to all calls — no circuit breaker / bulkhead | HIGH | W5/W13 |
| 1D | No graceful-degradation ladder when failover itself fails | HIGH | W1/W6 |
| 2A | Tool side effects non-transactional → ghost "confirmed" / half-booking on hangup or API fail | CRITICAL | W11/W1 |
| 2B | Calendar/WhatsApp/CRM DOWN unhandled → block, dead-air, or silent no-op; no token-refresh | HIGH | W11/W14/W16 |
| 2C | Side effects not idempotent → double-book / double-WhatsApp / double-dial / double-charge on retry | HIGH | W10/W11/W14/W8 |
| 2D | Mid-tool hangup → ambiguous lead state, mis-classified, no continuity | MEDIUM | W7/W10 |
| 3A | Deploy/restart drops or freezes live calls; config-at-import → split-brain (the warm-transfer bug) | CRITICAL | NEW / W0+W13 |
| 3B | Flags default-wrong-when-absent, read inconsistently → "deployed but inert" | HIGH | W0/W17 |
| 3C | Migrations vs running old code → shared-DB split-brain | MEDIUM | W0/W8 |
| 3D | `/health 200` doesn't reflect real serving ability; dead worker gets fresh leads | HIGH | W0/W17 |
| 4A | No "what the lead HEARS on failure" contract — silence/lie is the default | CRITICAL | W1 |
| 4B | No chaos/fault-injection testing; all verification is single happy-path | HIGH | W17 |
| 4C | Recording egress fire-and-forget → silent permanent audio loss, no alert | HIGH | W9 |
| 4D | Redis event bus at-least-once / can drop events → UI silently stale | MEDIUM | W8 |
| 4E | No per-tenant resource isolation → noisy neighbor starves all under load | MEDIUM | W12/W13 |
| 4F | Outbound AMD/voicemail/dead-air chaos → full pitch to voicemail, sit on silence | MEDIUM | W12/W1 |

**The five CRITICALs the plan most needs to absorb:** (0) make a call's outcome **durably + transactionally
recorded the instant it's known**, surviving a worker kill — not a best-effort local-disk shutdown hook;
(1A) a **silence-guard + TTS recreate/failover** so a WS death never mutes the rest of the call; (2A)
**write-before-speak + outbox** so the agent never confirms a booking that didn't durably happen and a
hangup never orphans a side effect; (3A) **graceful drain + kill config-at-import** so a deploy never drops
a live call or split-brains the box; (4A) a kernel invariant that **the lead never hears silence or a lie
on any failure.** Three of these (0, 3A, 4A) plus the chaos harness (4B) are **NET-NEW** — no wave in the
18-wave plan currently owns the failure branch at all.

---

## Sources
- Live earner code (read-only mirror): `_inbound_ref/agent.REFERENCE.py` (shutdown-hook persistence
  `:423/:479`, `_summarize` blocking Groq httpx `:170/:244`, sticky-WS-death-on-bad-lang `:574-578`,
  `WorkerOptions` defaults `:758`, amd_hint `:466`); `droplet_work/caller.py` (JSON-file state + file-lock
  `:788`, atomic-write primitive `:794` used inconsistently, retry queue `:264`).
- Existing design: `design/RECOVERY-STATE.md` (flag-absent hazard, md5 deploy discipline, RAG ungated),
  `design/WARM-TRANSFER-DIAGNOSIS.md` (config-at-import split-brain root cause), `CALLBACK_SCHEDULER_REBUILD_STATE.md`
  (scheduler spam from non-idempotent re-enqueue), `design/LATENCY-TAILS-GAP-ANALYSIS.md` (companion — owns
  the *slow* tail; this doc owns the *break* tail).
- Deep-research reports (7)/(8): streaming-cascade resilience, Postgres-as-source-of-truth (which the live
  path violates), object-storage egress, Groq Flex 498 / no-stream-cancel.
- Web (2026): LiveKit graceful-shutdown/drain (livekit issues #3413/#4447, agents-js #275, Server Options
  drain_timeout 30-min default, community #647 user-stuck-after-drain); ElevenLabs WS dies mid-stream no
  reconnect (livekit/agents #4676/#4609/#306/#3235, EL 20s idle-close); voice-agent prod failure guides
  (Bluejay, SIMBA, SignalWire, Webfuse, CallSphere — booking-503-says-confirmed, validate-store-in-session,
  one stuck WS backs up 50 calls); idempotency/at-least-once (AWS Durable Execution, Hooksbase, BackendBytes);
  circuit-breaker + bulkhead for cascading-failure isolation (Azure Architecture Center, Cordum AI-agent
  circuit breaker, system-design.space).
