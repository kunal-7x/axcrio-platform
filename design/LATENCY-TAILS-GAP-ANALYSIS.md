# LATENCY TAILS — Blind-Spot Gap Analysis (RealtimeVoiceKernel v2)

**Status:** READ-ONLY research + diagnosis (no box mutation, no deploy). Doc-only.
**Date:** 2026-06-18
**Dimension:** LATENCY TAILS — TTFA p95, provider-failover latency, RAG-on-hot-path, cold-start,
region pinning, the warm-path "think-while-speaking".
**Scope:** Find what the founder AND the 18-wave plan miss on tail latency. Map each gap to its
owning wave (W1..W17) or flag NET-NEW.

> **Framing.** The plan optimizes the *median* turn (kill 10k prompt, context packets, preemptive
> generation, VAD endpointing, Groq prompt-cache). The median is mostly handled. **What the plan does
> NOT systematically own is the TAIL** — the p95/p99 turn where a provider stalls, a websocket drops,
> a cache misses, a worker cold-starts, or a packet crosses an ocean. A telecaller that is great at p50
> and goes silent for 5–7s at p95 *feels broken* to the lead, who hangs up. **Tails kill conversion,
> not averages.** This doc is the tail map.

---

## 0. The structural floor the plan never states: the box is in India, the brain is in the US

- **Ground truth:** all DO boxes are `blr1` (Bangalore) — `CLAUDE.md:36`. The hot-path LLM is **Groq**,
  whose datacenters are **US/Canada/Saudi/Finland/Australia — NO India POP** (Groq community FAQ +
  DCD 2026: India is *planned*, not live). ElevenLabs has an **India region**, but the live code calls
  the **default (US) endpoint** (`agent.py:563` — no `environment`/region kwarg). Only Sarvam is
  India-native.
- **Consequence:** every hot-path LLM round trip is **India→US→India ≈ 200–250 ms RTT of pure network
  before a single token**, on TOP of Groq's 85–110 ms TTFT. ElevenLabs adds another transcontinental
  hop. The plan's headline "TTFA p50 < 1s" is plausible at p50 but the **network RTT is a hard floor
  that no prompt-caching or context-packet work removes** — and it is exactly what blows the p95 when a
  single TCP retransmit or transcontinental jitter event lands.
- **The plan's research anchor even admits this** ("OpenRouter = fallback router only — adds latency on
  failover") but never turns it into a **region/RTT budget line item**. There is no wave that measures
  or pins region, no wave that even *names* the US round-trip as the dominant fixed cost.

**This is the #1 blind spot: nobody owns the network/region budget.** Everything below compounds on it.

---

## 1. TTFA p95 — the metric the plan optimizes for p50 only

### Gap 1A — No p95/p99 TTFA SLO, no per-turn tail dashboard, no alerting (CRITICAL)
The plan (W17) lists "per-call trace (TTFA, TTFT, TTS-first-byte…)" and "latency/cost dashboards", and
the existing `agent.py:760-784` logs `eou_delay`, `llm_ttft`, `tts_ttfb` **per turn to text logs**. But:
- There is **no aggregation to percentiles** (p50/p95/p99) — text-log lines are not a dashboard.
- There is **no SLO and no alert** — nothing fires when p95 TTFA crosses a threshold on a live call.
- TTFA is logged in **three separate stage metrics that are never summed into one end-to-end "caller
  stopped → caller hears first audio" number** — the only number the lead actually experiences.
- **The tail is invisible.** You cannot fix what you cannot see; a once-per-20-calls 6s stall never
  shows up in a p50 view, but it is the call that loses the deal.

**Fix:** W17 must define **hard SLOs** (proposal: TTFA p50 ≤ 1.2s, **p95 ≤ 2.5s, p99 ≤ 4s**; dead-air
budget: no silence > 1.5s ever) and ship a **real percentile pipeline** (emit per-turn stage timings to
the W8 event bus → roll into a tail dashboard) with **alerting** when p95 breaches. Add a single
synthesized **`ttfa_end_to_end`** span (EOU→first TTS frame) per turn. Without percentiles + alerts the
whole "latency improves" acceptance criterion is unfalsifiable.

### Gap 1B — TTFA is measured per-stage but never budgeted end-to-end; no "speak a filler before the slow await" rule in the OUTBOUND path (HIGH)
The inbound `LATENCY-ARCHITECTURE.md` design *does* prescribe "filler before any await > 700ms" — but
that is the **inbound AI-Manager** doc and is **not in the outbound earner** (`agent.py` has no
pre-await filler). On the outbound brain, the moment a tool (booking, RAG, calendar, transfer) or a slow
LLM turn runs, the lead hears **dead air** with no thinking-sound. Humans say "let me check that for
you…" — the agent must too, universally, on **every** path that can exceed the dead-air budget.

**Fix:** W1 (kernel) must make "**reflexive filler before any await > ~600ms**" a first-class kernel
primitive (not a per-feature afterthought), wired into the warm-path tool calls of W4/W11. One shared
mechanism, every slow seam covered.

---

## 2. Provider-failover latency — the plan has fallback CHAINS but not fallback *within the dead-air budget*

### Gap 2A — Sarvam TTS has a documented 5–7s TTFB spike under load that goes SILENT with no error (CRITICAL)
Web research (Pipecat field report on Sarvam): **Sarvam TTS TTFB is 0.5–0.9s under light load but
spikes to 5–7s under load**, and because the default TTS timeout is short, **the response drops
silently — no error, no exception, no log.** This is exactly the founder's "Sarvam = complete silence"
symptom (`request1.md:136`), and the plan currently treats Sarvam-silence as a *wiring* bug
(`INBOUND_PROV_LOCK`), **not** as a **tail-latency / timeout / silent-failure** bug. W5 plans to "fix
Sarvam silence" by enabling it — but enabling it on the Lean plan **exposes every Lean-plan lead to the
5–7s silent stall under load.**

**Fix (W5, must be in the failover spec, not just "turn it on"):**
- Set Sarvam TTS timeout generously (≥10s) **but** with a **mid-utterance watchdog**: if first audio
  byte hasn't arrived in ~**1.2s**, **fail over to ElevenLabs for that utterance** (don't wait the full
  10s — that *is* the dead air). The 10s timeout only prevents a hard error; the 1.2s watchdog prevents
  the dead-air.
- Treat **silent drop as a first-class failure mode** in eval (W17): a golden test that drives Sarvam
  under synthetic load and asserts the agent never goes silent > 1.5s.

### Gap 2B — Provider failover is mid-call but the failover *itself* costs 1–3s of dead air; no hedging / pre-warmed standby (HIGH)
The plan's provider router (W5/W13) routes and "fails loud", and `agent.py:586-589` round-robins Groq
keys. But all of this is **sequential failover**: detect failure → reconnect → retry. On the hot path
that is **1–3s of added dead air at exactly the worst moment** (provider already degraded). The plan
never specifies:
- **Hedged requests** (industry best practice, confirmed in research: fire a duplicate to the backup
  provider only *after a delay tuned near p95*, take whichever returns first, cancel the loser). This is
  the standard way to cut the *tail* without doubling cost on the median.
- **Warm standby connections** — keep the backup TTS websocket and a backup LLM client **pre-opened and
  warm** so failover is a "switch", not a "dial". LiveKit ElevenLabs bug #4135/#4676 (research):
  ElevenLabs WS drops mid-synthesis and the retry **fails with the same error** → the agent dies. A
  cold reconnect on the hot path is the trap.

**Fix:** W5 must specify (a) **hedged LLM** for the live path (backup = a *second Groq key/model*, NOT
OpenRouter which adds a router hop — research confirms OpenRouter adds latency and some providers incl.
Groq don't support stream-cancel, so a hedge there double-bills); (b) **pre-warmed backup TTS websocket
per call**, so a Sarvam→ElevenLabs (or EL-primary→EL-backup-voice) switch is instant; (c) explicit
**handling of the LiveKit EL-retry-fails-with-same-error bug** (pin plugin version / wrap with our own
reconnect-to-fresh-WS, not retry-same-dead-WS).

### Gap 2C — Groq stream-cancel is unsupported → an aborted hot-path generation keeps billing AND keeps the old WS busy (MEDIUM)
Research: **Groq does not support stream cancellation** — when you barge-in / abort a turn, Groq keeps
generating (and billing) on their side. On a barge-in-heavy telecaller (the founder *wants* aggressive
barge-in, `agent.py:628`), every interruption leaks a few hundred tokens of cost AND the underlying
connection isn't cleanly freed, which can serialize the next turn behind a still-draining stream → a
**self-inflicted latency tail right after a barge-in** (the highest-engagement moment).

**Fix:** W5/W1 — on barge-in, **open a fresh request for the next turn rather than reusing the
aborted stream's connection**; account for the leaked tokens in W17 cost-per-appointment. Add a golden
test: barge-in mid-reply, assert next-turn TTFA is not inflated by the drained stream.

### Gap 2D — STT (Sarvam saarika) has no failover at all; an STT stall stalls the WHOLE turn invisibly (HIGH)
The plan gives TTS a fallback (ElevenLabs↔Sarvam) and LLM a fallback (Groq keys), but **STT is
single-vendor Sarvam with no fallback** (`agent.py:592-601`). STT sits at the *front* of the turn — if
Sarvam STT TTFB spikes under load (same infra risk as 2A), the entire turn stalls before the LLM even
starts, and the "filler" trick can't help because the agent doesn't yet know the user finished. This is
a **single point of tail-failure on the most latency-sensitive stage.**

**Fix:** W5 — define an STT fallback (e.g. Deepgram **Mumbai** region — research confirms LiveKit
Inference hosts Deepgram STT in Mumbai = India-local, no US hop) behind a watchdog; at minimum, an
STT-stall watchdog that re-prompts ("sorry, you cut out — could you repeat?") rather than infinite
silence. Note: Mumbai-hosted STT also *fixes part of Gap 0* (keeps STT in-country).

---

## 3. RAG-on-hot-path — the plan says "precompute + Redis <50ms" but the tail is where the plan is thin

### Gap 3A — The plan still allows runtime RAG via `on_user_turn_completed`, which BLOCKS the turn on a vector query + (worse) an embedding API call (CRITICAL)
The plan (W4) wires retrieval into the call path with "Redis hot-cache (<50ms)" — good for the *cache
hit*. But it ALSO inherits LiveKit's `on_user_turn_completed` dynamic-RAG pattern (named in the research
anchors), which runs **synchronously in the turn**. Research is blunt: a vector query adds **50–300ms**,
and the **query embedding itself is usually a network call to an embedding API** (often US-hosted →
another transcontinental hop, see Gap 0) — so a **cache MISS on the hot path can add 300–800ms+**, and
an embedding-API stall can add **seconds**. The plan budgets the *hit* (<50ms) and is silent on the
*miss* and the *embedding call*, which is precisely the tail.

**Fix (W4, the decisive architecture):** adopt the **dual-agent "Slow Thinker / Fast Talker"** pattern
(Salesforce VoiceAgentRAG, 2026 — 316× speedup, 110ms→0.35ms on hit, 75% hit-rate, peaks 95%): a
**background thinker** watches the conversation stream and **pre-fetches likely chunks into an
in-process sub-ms cache while the user is still speaking**; the **foreground talker reads ONLY the
in-process cache and NEVER touches the vector DB or an embedding API on the hot path.** On a cache miss
the foreground path **does not block** — it answers from campaign-card/context-packet and the thinker
backfills for the *next* turn (or the agent speaks a filler, Gap 1B). **Make "the hot path never makes a
blocking network RAG/embedding call" a hard architectural invariant of W4, enforced by an eval.** The
current plan's wording ("inject at recap seam") is close but does not forbid the blocking miss.

### Gap 3B — Embeddings are computed on the hot path at all; no pre-embedded query cache / local embedder (HIGH)
Even with W4's precompute, the *query* must be embedded to search. If that embedding is an API call it's
a hop (Gap 0); if it's a cold local model it's a cold-start (Gap 4). Neither is budgeted.

**Fix:** W4 — embed queries with a **small LOCAL embedding model co-located on the box** (no network
hop) OR pre-embed a fixed set of "anticipated questions" per campaign at dial-time (warm path) so common
turns are zero-embed. Region-pin any remote embedder to India if a local one isn't viable.

### Gap 3C — "Redis <50ms" assumes Redis is local and warm; cross-box Redis or a cold connection blows it (MEDIUM)
The inbound design already shows the app Redis on `:6380` is on the box, but the v2 plan adds Redis
Streams (W8) and a hot-cache (W4) without stating **Redis must be on the same box / same VPC as the
voice worker** and the **connection must be pooled + pre-opened** (a first-call cold Redis connect can
be 10–50ms+ of TCP+auth). A network hop to a Redis on the hatchet box (`10.122.0.3`) across the VPC adds
RTT to *every* "fast" lookup.

**Fix:** W4/W8 — co-locate the hot-cache Redis with the voice worker (localhost), pre-open + pool the
connection at worker prewarm, and **budget the warm-cache read as <2ms localhost, not <50ms**. Reserve
the cross-VPC Redis for the durable event stream, not the hot lookup.

---

## 4. Cold-start — the single biggest tail the plan does not mention ONCE

### Gap 4A — LiveKit agent worker cold-start = several seconds on the FIRST turn / first call after idle (CRITICAL)
Research (LiveKit docs): on idle, **"any subsequent agent join experiences a start-up time of several
seconds"**; the fix is **a warm pool of 2–3 idle workers per region** + **prewarm the VAD/turn-detector
model**. `agent.py:620` loads `silero.VAD.load()` and the plan adds a semantic turn detector (W5) — a
**model load on the cold path is seconds**. The 18-wave plan **never mentions cold-start, prewarm, or a
warm worker pool.** For an *outbound* dialer this is acute: calls are *bursty* (a campaign fires N calls
at once after a quiet period) — the first wave of every campaign eats the cold-start, i.e. **the worst
first impression on the freshest leads.**

**Fix (NET-NEW concern, assign to W12 capacity-planner + W0 infra):**
- **Prewarm**: load VAD, semantic turn-detector, local embedder (Gap 3B), and **pre-open the
  Groq/ElevenLabs/Sarvam connections** in the worker `prewarm` hook BEFORE the first job — research
  explicitly recommends prewarming the turn-detection model.
- **Warm worker pool**: keep ≥2–3 idle workers hot per region so a campaign burst never cold-starts.
- **Connection warm-keep**: keep provider WS/HTTP connections alive between calls (ElevenLabs WS idle
  closes at 20s — research; so issue a keep-alive or accept a re-open but budget it). Note LiveKit
  issue #3841 (research): **workers can die silently after prewarm** → add a health probe so a dead
  prewarmed worker doesn't silently route every call to cold-start.

### Gap 4B — Per-CALL cold seams: first TTS WS open, first STT WS open, first Groq TCP, DNS (HIGH)
Even with a warm worker, **each new call** opens fresh provider sockets. The inbound design already
caught the analogous "new `httpx.Client()` per tool call" anti-pattern. On the outbound brain the
**opener** (the very first thing the lead hears) is synthesized on a **freshly-opened ElevenLabs WS** —
the highest-stakes utterance rides the coldest connection. TLS handshake + WS upgrade + (US hop) can add
300–700ms to the opener specifically.

**Fix:** W1/W5 — open all three provider connections **in parallel during the SIP-ring/connect window**
(before the human picks up there are ~2–6s of ring time = free warm-up budget) so by "hello" everything
is hot. Pre-render or pre-warm the **opener** specifically (it's static per campaign — can be
pre-synthesized and cached as audio, zero TTS latency on turn 0).

---

## 5. Region pinning — named in research, absent from every wave

### Gap 5A — No wave owns region pinning despite it being a research anchor AND a compliance need (HIGH)
The deep-research report explicitly says LiveKit "supports pinning traffic to specific regions, including
India" and "trunks can be region-restricted to satisfy local telephony regulations", and the plan's own
W12 mentions "India region-pin SIP" in passing — but **no wave actually owns configuring region
pinning**, and research confirms **region pinning is a LiveKit Scale-plan feature** (must contact
support / may need a plan upgrade) — a **procurement blocker** nobody has surfaced. Without pinning,
LiveKit may select a non-India media server → media crosses an ocean → **every audio frame eats RTT and
jitter**, which directly widens the TTFA tail *and* may violate TRAI data-residency.

**Fix:** W12 (owns it) + W0 (procurement) — (1) verify the LiveKit plan tier supports India region
pinning and pin media to India; (2) region-pin SIP trunk to India; (3) co-locate the agent worker in
India (already blr1) and ensure LiveKit media server is India too. Surface the **plan-tier cost** to the
founder as a gated action.

### Gap 5B — Provider region selection is unmanaged: ElevenLabs India region exists but is unused; Groq has no India POP (HIGH)
See Gap 0. ElevenLabs supports an **India isolated region** (research) but `agent.py:563` uses the
default. Switching the ElevenLabs endpoint to India removes one transcontinental hop from the *premium*
TTS path. Groq has no India POP, so the LLM hop is unavoidable *today* — which means the plan should
**weight provider choice by region**: prefer India-local providers on the hot path where quality is
comparable, and design so that **when Groq opens an India POP the router can pin to it without a
rewrite.**

**Fix:** W5/W13 — make provider endpoint/region a **config field** (not hardcoded), default ElevenLabs
to India region, log `x-groq-region` per call (research: Groq exposes it) so we can correlate TTFA tail
with which datacenter served the call, and add a "prefer-region=IN" router preference.

---

## 6. The warm-path "think-while-speaking" — the plan names it but doesn't engineer the hard parts

### Gap 6A — Think-while-speaking has a STALE-CONTEXT race: the foreground may answer before the background finishes thinking (HIGH)
The plan's three-speed runtime (W1) is exactly right in spirit — warm path runs "while the user speaks".
But the deep-research "Slow Thinker / Fast Talker" decoupling (Gap 3A) introduces a **race the plan never
addresses**: if the foreground talker generates a turn **before** the background thinker has loaded the
relevant chunk/memory, the answer is **stale or wrong** (the founder's exact complaint: "no context
about the campaign"). The plan treats warm-path as a pure latency win and **misses the
correctness-vs-latency tradeoff at the seam.**

**Fix:** W1 — define the **synchronization contract**: foreground answers from the **campaign-card +
context-packet that are guaranteed-loaded at dial-time** (warm path pre-call, not mid-turn), and only
*augments* with thinker output when the thinker has it ready; if the thinker is mid-flight on a
hard question, the foreground **speaks a filler and yields** rather than answering stale. Eval (W17):
golden test that a deep question asked on turn 1 (before any thinker warm-up) is either answered
correctly from the card or gets a filler — never a confident wrong answer.

### Gap 6B — Preemptive generation wastes/duplicates work and can speak a reply to a turn the user wasn't finished with (MEDIUM)
`agent.py:622` and the plan both enable `preemptive_generation=True` (start the LLM before the turn is
finalized). The **tail risk**: if the user keeps talking after the preemptive trigger, the preemptive
generation is **discarded and regenerated** — on a degraded provider that's a **doubled LLM call right
when capacity is tight** (compounds Gap 2B). Also interacts badly with Groq's no-stream-cancel (Gap 2C):
a discarded preemptive generation **keeps billing**. The plan never reconciles preemptive-generation
with the endpointing knobs or the cost model.

**Fix:** W1/W5 — tune preemptive generation to fire only after a **high-confidence end-of-utterance
signal** (semantic turn detector helps here), cap concurrent preemptive generations, and meter the
discarded-generation cost in W17 (it inflates cost-per-appointment).

### Gap 6C — No "buy-time" speech-act vocabulary; the warm path can't always hide its own latency (MEDIUM)
Even a perfect think-while-speaking pipeline sometimes needs >1.5s (cold RAG miss + slow provider). A
real telecaller covers this with **natural stalling speech** ("haan ji, ek second… main aapke liye exact
detail nikaal raha hoon"). The plan's Speech Planner (W5) owns normalization/fillers but **does not own a
latency-aware "buy-time" vocabulary** keyed to *how long the await is expected to take* (a 0.5s filler vs
a 2s "let me pull up your file" are different speech acts).

**Fix:** W5 + W6 (telecaller intelligence) — give the Speech Planner a **graded stall-vocabulary**
selected by the predicted await duration, language-mirrored and human, so the agent *never* exposes raw
dead air and the stall feels like rapport, not a glitch.

---

## 7. Cross-cutting tail risks the plan misses entirely

### Gap 7A — No load/concurrency tail model: providers degrade exactly when the founder dials 500 leads at once (CRITICAL)
The whole point is to replace a **500-person team** → **massive concurrency**. Every tail above (Sarvam
5–7s under load 2A, Groq 429/queueing, cold-start bursts 4A, embedding-API throttle 3B) is **triggered
by load**, and the plan's single-call latency work is validated on **one test call**. **There is no
wave that load-tests the tail** — that drives N concurrent synthetic calls and measures p95 TTFA *under
the load the product is designed for.* The acceptance criteria ("latency improves") are all single-call.

**Fix (NET-NEW, assign to W17 + W12):** a **concurrency tail harness** — drive 50/100/200 concurrent
synthetic sessions (shadow/held, never real PSTN burn) and report **p95/p99 TTFA and dead-air rate under
load**. Tie provider key-pool sizing (W12), warm-worker-pool sizing (4A), and hedging thresholds (2B) to
its output. **This is the only test that proves the 500-team claim won't collapse on tail latency.**

### Gap 7B — Barge-in → cancel → regenerate is a hidden latency+cost tail loop (HIGH)
Founder wants aggressive barge-in (`MIN_INT_DUR=0.25`). Each barge-in: cancels TTS (WS may need
re-sync), cancels/abandons LLM (Groq keeps billing 2C), and regenerates. **Rapid back-and-forth barge-in
can serialize into a stutter** where the agent never gets a clean turn out → perceived as a frozen agent.
The plan tunes barge-in for *responsiveness* but never models the **barge-in storm** tail.

**Fix:** W1 — debounce/cool-down on barge-in regeneration; ensure TTS WS resync after interruption is
**warm** (Gap 4); golden test: 5 rapid barge-ins, assert the agent recovers a clean utterance within
budget and TTFA doesn't degrade across the sequence.

### Gap 7C — `false_interruption_timeout=1.0` and endpointing are static, not adaptive to measured tail (MEDIUM)
`agent.py:629` hardcodes `false_interruption_timeout=1.0`; endpointing is static (`MIN/MAX_EP_DELAY`).
On a noisy line or a slow speaker these static values either **cut the user off** (false endpoint → user
repeats → +1 whole turn of latency) or **wait too long** (dead air). The plan never makes endpointing
**adaptive to the line's measured noise/RTT**.

**Fix:** W5 — adaptive endpointing keyed to per-call signal quality + the semantic turn detector;
measure "false-endpoint rate" as a W17 tail metric (each false endpoint = a wasted turn = a latency
tail the lead feels).

### Gap 7D — TTFA tail at TURN 0 (the opener) is uniquely bad and uniquely important (HIGH)
The opener rides every cold seam at once (cold worker 4A, cold WS 4B, first US hop 0) and is the moment
the lead decides whether to stay on the line. The plan treats all turns uniformly.

**Fix:** W1 — **pre-synthesize the opener to cached audio per campaign** (it's static; zero TTS latency,
zero US hop on turn 0) and warm all connections during ring (Gap 4B). The opener should hit the lead's
ear **the instant they say hello**, not after a 1–2s cold-stack spin-up.

### Gap 7E — No graceful degradation ladder: when the tail blows, what does the agent DO? (HIGH)
Every fix above reduces tail *probability*; none defines behavior when the tail **happens anyway** (it
will, at p99, on someone's call). The plan has no **degradation ladder**: filler → simpler/faster model
→ cached canned line → "let me have someone call you right back" (graceful exit) rather than dead air or
a hang. A 5s silence with no recovery loses the lead; a graceful "ek second sir, line thodi slow hai"
keeps them.

**Fix:** W1 + W6 — define an explicit **degradation ladder** as kernel behavior, eval'd in W17 (inject a
synthetic provider stall, assert the agent degrades gracefully and never dead-airs > the budget).

---

## 8. Summary — owning-wave map

| # | Gap | Sev | Owner |
|---|---|---|---|
| 0 | Box in India, brain (Groq) in US — unowned network/region RTT floor | CRITICAL | NEW / W12+W0 |
| 1A | No p95/p99 TTFA SLO + tail dashboard + alerting | CRITICAL | W17 |
| 1B | No universal "filler before slow await" on OUTBOUND path | HIGH | W1 |
| 2A | Sarvam TTS 5–7s silent stall under load | CRITICAL | W5 |
| 2B | Failover is sequential (1–3s dead air); no hedge / warm standby | HIGH | W5 |
| 2C | Groq no stream-cancel → barge-in leaks cost + connection | MEDIUM | W5/W1 |
| 2D | STT single-vendor, no fallback, front-of-turn SPOF | HIGH | W5 |
| 3A | Hot-path RAG miss + embedding call blocks the turn | CRITICAL | W4 |
| 3B | Query embedding on hot path (API hop / cold model) | HIGH | W4 |
| 3C | "Redis <50ms" assumes local+warm; cross-VPC blows it | MEDIUM | W4/W8 |
| 4A | LiveKit worker cold-start (several s) — never mentioned | CRITICAL | NEW / W12+W0 |
| 4B | Per-call cold sockets; opener on coldest WS | HIGH | W1/W5 |
| 5A | Region pinning unowned (+ Scale-plan procurement blocker) | HIGH | W12/W0 |
| 5B | ElevenLabs India region unused; provider region unmanaged | HIGH | W5/W13 |
| 6A | Think-while-speaking stale-context race | HIGH | W1 |
| 6B | Preemptive generation duplicates work + leaks cost | MEDIUM | W1/W5 |
| 6C | No latency-graded "buy-time" stall vocabulary | MEDIUM | W5/W6 |
| 7A | No concurrency/load tail harness (the 500-team proof) | CRITICAL | NEW / W17+W12 |
| 7B | Barge-in storm latency+cost loop | HIGH | W1 |
| 7C | Static endpointing/false-interruption not adaptive | MEDIUM | W5 |
| 7D | Turn-0 opener tail (every cold seam at once) | HIGH | W1 |
| 7E | No graceful-degradation ladder when the tail blows | HIGH | W1/W6 |

**The four CRITICALs the plan most needs to absorb:** (0) own the India↔US RTT/region floor; (3A) the
hot path must NEVER make a blocking RAG/embedding network call; (4A) cold-start / warm-worker-pool /
prewarm; (7A) a concurrency load harness that measures p95 TTFA under the 500-call burst the product
exists to handle. Two of these (0, 4A, 7A) are **NET-NEW** — the plan has no wave that owns them.

---

## Sources
- LiveKit — Understand & Improve Agent Latency; Region Pinning docs; cold-start / warm-pool / prewarm
  guidance; field guide for regional deployments; agents issue #3841 (workers die silently after prewarm).
- Salesforce AI Research — VoiceAgentRAG (dual-agent Slow-Thinker/Fast-Talker, 316× retrieval speedup,
  110ms→0.35ms, 75–95% hit rate) — arXiv 2603.02206 + MarkTechPost.
- Pipecat / Sarvam field report — Sarvam TTS TTFB 0.5–0.9s light / **5–7s under load**, silent drop on
  short timeout (Indian-language voice agent architecture write-ups).
- ElevenLabs — Flash v2.5 ~75ms inference; WebSocket 20s idle-close / 180s context timeout; India data
  residency region; LiveKit agents issues #4135 & #4676 (EL WS retry fails with same error).
- Groq — LPU TTFT 85–110ms (Llama 3.1 8B); automatic prompt caching (13–31% TTFT win, cache-break on
  any prefix/tool_choice change); no datacenter in India (community FAQ + DCD 2026 expansion); no
  stream-cancellation; `x-groq-region` response header for region correlation.
- TrueFoundry / OpenRouter — hedged requests fired near p95 to cut the tail; OpenRouter adds a router hop
  and some providers (incl. Groq) lack stream-cancel (double-bill on hedge/abort).
- Vector DB benchmarks (pgvector/pgvectorscale vs Qdrant) — sub-100ms p95 at 99% recall; vector query
  adds 50–300ms on the hot path.
