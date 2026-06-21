# RVK2 — GRAND RED-TEAM (Architecture Pass): is the design actually right?

> READ-ONLY adversarial review. No code touched, no box mutated. Date 2026-06-18.
> **Target of attack:** the *architecture itself* — RealtimeVoiceKernel v2, the
> three-speed hot/warm/cold runtime, the `ContextPacket` + prompt-layering design
> (`design/W1-KERNEL-ARCH.md`), and the **cross-vertical single-brain + brain-packs**
> claim (W2). Not security (covered by `RVK2-SECURITY-ISOLATION-MASTER-GAPS.md`),
> not latency tails (covered by `LATENCY-TAILS-GAP-ANALYSIS.md`), not failover
> (covered by `RVK2-PROVIDER-FAILOVER-KEYHEALTH-GAPS.md`). This doc attacks the
> *shape of the system* and whether it survives scale + real call pressure.
> Grounded in: the plan, `W1-KERNEL-ARCH.md`, both founder deep-research reports,
> live file:line from the audit, and 2026 web verification (sources at bottom).

---

## TL;DR — the one-paragraph verdict

The architecture is **directionally correct and far better than the 10k-prompt
monolith** it replaces — the three-speed split, the context packet, the speech
planner, and the modular service contracts are the right instincts and match the
2026 literature. **But it has one fatal category error and four structural
blind-spots that will break it under real load.** The fatal error: **the plan is
an offline-batch architecture wearing a realtime costume.** Every hard part of a
realtime voice system — concurrency, the stateful FSM under non-linear human
turns, the warm-path race, provider saturation, cold-start — is treated as a
*module to build later* rather than as *the actual product*. The single biggest
architectural blind-spot is **#1 below: there is no concurrency model anywhere in
the design** — every contract, every budget, every test is written for ONE call,
and the product exists to run 500 at once. The kernel as specified is a
single-call simulator. Ship it as-is and it works beautifully in a demo and
collapses the first time a campaign fires.

**Two design premises are also provably stale / wrong** (verified this pass):
the kernel's prompt-cache reasoning (B1) and the all-async COLD-path assumption
(B5). Fix those before any code, or W1's foundation contracts encode the mistake.

---

## TOP BLOCKERS (ranked by "will this break the 500-team product in production")

### BLOCKER 1 — There is NO concurrency model. The whole design is single-call. 🔴 THE BIG ONE
**This is the single biggest architectural blind-spot.** Read `W1-KERNEL-ARCH.md`
end to end: `ContextPacket` is per-call, `build_kernel(cfg)` is per-process, the
token budget is per-call, `assemble_prefix`/`assemble_turn` are per-call, every
test (`test_packet_budget`, `test_adapter_off_identity`) is single-call, the
acceptance criteria ("latency improves", "tokens drop") are single-call. **The
word "concurrency" does not appear in the kernel architecture at all.** Yet the
product's entire reason to exist is "replace a 500-person team" = 500 simultaneous
calls. The architecture answers "how do I make ONE call great" and never answers
"what happens to call #200 when calls #1–199 are live."

Why this is fatal and not a tuning detail — at N concurrent calls EVERY shared
resource saturates *simultaneously* and the failures *correlate*:
- **Provider quotas saturate together.** Groq rate limits are PER-ORG, not
  per-key (confirmed: `RVK2-PROVIDER-FAILOVER` G-PF3) — 500 calls hit one bucket.
  ElevenLabs concurrency cap is **2–15 streams per plan** (G-PF4). 500 seats vs a
  15-slot plan is not a failover problem, it's an *impossibility* the design never
  surfaces. The context packet being smaller doesn't help: you still need 500
  concurrent LLM streams.
- **The warm path's "think while you speak" multiplies load.** Every call runs a
  *background thinker* in parallel with the *foreground talker* (the dual-agent
  pattern the research mandates). That is **2× the LLM/embedding load per call**,
  so 500 calls = up to 1000 concurrent model streams, exactly when the provider is
  already walling.
- **Cold-start bursts are correlated.** Outbound dialers are bursty by nature — a
  campaign fires N calls at the same instant after a quiet period. The first wave
  eats LiveKit worker cold-start (several seconds — `LATENCY-TAILS` 4A) *all at
  once*, on the freshest leads.
- **Per-process circuit/cooldown state doesn't share** (G-PF11) — each worker
  re-learns "key dead" independently, so under burst they all 429 in parallel
  before any of them cools the key fleet-wide.

**What MUST change in the plan:** add a **NET-NEW W-CONCURRENCY wave** (or make it
W12's spine) that owns: (a) a **per-call resource admission controller** — before a
call is even dialed, reserve an LLM-quota slice + a TTS concurrency slot + a worker;
if the fleet can't admit it, **queue or pace the campaign**, never dial into a wall.
(b) a **concurrency budget as a first-class dimension of `KernelConfig`** (max live
sessions/worker, max in-flight thinker tasks). (c) the **load/concurrency tail
harness** (`LATENCY-TAILS` 7A) promoted from "eval debt" to a **gate**: nothing
deploys until p95 TTFA + dead-air rate are measured at 50/100/200 concurrent
synthetic sessions. **The 500-team claim is unproven and unprovable until this
exists.** Today the plan validates everything on one test call — that is the
demo-survives-luck trap both deep-research reports explicitly warn about.

### BLOCKER 2 — The dialogue FSM is too rigid for real human turns; it will fight the conversation. 🔴
The kernel hard-codes a linear `Stage` enum (`greet → permission → intro → qualify
→ objection → booking → close → followup`) with a per-`UseCase` transition table
(`W1-KERNEL-ARCH.md §4`). **Real telecaller conversations are not a DAG.** A lead
opens with a price objection *before* you've introduced yourself; asks a booking
question during qualify; circles back to an objection you "closed" two turns ago;
goes silent; says "actually my wife handles this, call back at 6." A strict FSM
forces every one of these into a wrong state, and the literature is blunt about
the failure mode: in 30-turn conversations *the best models still make a
significant error in at least one turn*, and FSM-driven agents "stray from exact
wording or choose the wrong branch after interruptions." Worse, a Feb-2026
production test of an FSM-style agent hit **API-error/phantom-tool cascades in 52%
of turns** when state and message history desynced — the FSM didn't add
reliability, it added a corruption surface.

The deeper architectural error: **the FSM is being asked to be both a *constraint*
(keep the agent on-protocol) and a *driver* (decide what happens next).** Those are
different jobs. Letting the LLM "drive the state machine" is exactly the
anti-pattern the 2026 voice-agent writeups call out — but so is a brittle
hard-coded DAG that the messy human keeps violating. The plan picks the brittle
horn without acknowledging the tradeoff.

**What MUST change:** make the FSM a **soft, non-linear policy layer, not a
linear pipeline.** (a) Stages are **tags/affordances, not a forced sequence** — any
stage can transition to any stage; the table encodes *defaults and guards*
(e.g. "can't `close` before a qualifying signal"), not a single allowed path.
(b) Add an explicit **"off-script / unknown" state** and a **re-entry** path —
the human can always pull the conversation sideways and the agent must follow
gracefully, then steer back. (c) **Decouple constraint from drive:** the FSM
*vetoes* illegal moves (compliance, "don't promise a discount") deterministically;
the LLM *chooses* the next move within what's legal. (d) **State must be derived
from the conversation, not just incremented** — re-classify stage each turn from
the transcript (cheap model), don't blindly advance a counter that desyncs from
reality (that desync is the 52%-cascade trigger). This is a W1 + W6 change and it
is **as load-bearing as the context packet** — a rigid FSM makes the agent feel
*more* robotic, not less, defeating the entire human-touch goal.

### BLOCKER 3 — The warm-path "think while you speak" has an unsolved correctness race that the contracts bake in. 🟠→🔴
The three-speed split is right, but the seam between WARM (background thinker
pre-fetching context) and HOT (foreground talker answering) is a **classic
read-before-write race**, and the architecture *encodes the race into the
contracts* rather than solving it. Look at `RagRuntime` in `contracts.py`:
`precompute(ctx)` (warm, fire-and-forget) and `retrieve(turn)` (hot). **Nothing in
the contract guarantees `precompute` finished before `retrieve` runs.** On turn 1 —
the highest-stakes turn, the opener answer — the thinker has had *zero* warm-up
time. A deep question on turn 1 ("what's the exact possession date and the
per-sqft after the festive discount?") hits an empty cache and the foreground
either **blocks** (dead air — the thing the whole design exists to prevent) or
**answers stale/wrong from a half-loaded packet** (the founder's exact original
complaint: "no context about the campaign"). The plan treats the warm path purely
as a latency win and **never names the latency-vs-correctness tradeoff at the
seam** (`LATENCY-TAILS` 6A flags this too).

**What MUST change:** the contract must encode a **synchronization discipline**, not
a hope. (a) The foreground answers ONLY from state that is **guaranteed-loaded at
dial-time** (campaign card + lead memory fetched on the WARM pre-call path, before
"hello"), and *augments* with thinker output only when `precompute` has signaled
ready for that topic. (b) Add a **readiness signal** to `RagRuntime` (`retrieve`
returns "not-ready" distinctly from "empty") so the kernel can choose **filler +
yield** over a confident wrong answer. (c) Make "**the hot path never blocks on a
network RAG/embedding call**" a hard, eval-enforced invariant of W4 (`LATENCY-TAILS`
3A) — on a miss it answers from the card and backfills for the *next* turn. Without
this, the warm path trades a latency bug for a *correctness* bug, which is worse.

### BLOCKER 4 — "One cross-vertical brain + packs" is an under-tested bet; the failure mode is silent vertical-leakage, and it's not gated. 🟠
The product's headline claim is "one adaptive software brain replaces a 500-person
team across sales/support/after-sales/booking/renewal/inbound." The architecture
implements this as **one LLM + a stack of text layers** (L1 use-case pack, L2
industry pack). This is a reasonable v1 *bet*, but it is presented as settled
architecture, and the 2026 industry signal is going the *other way*: serious
production voice systems are moving to **context-routing → specialized
models/templates per vertical** (medical → domain-tuned, financial → finance-tuned
variant), not one universal prompt-brain. The risk isn't that the single-brain
*can't* work — it's that its failure mode is **silent**: a support-mode pack with a
sales reflex underneath will, under pressure, **leak the sales behavior** ("while I
have you, can I book you a visit?") in a *complaint* call — and nobody will notice
until a customer does. The founder's own acceptance criterion ("a support campaign
behaves support, no sales leak") is exactly this fear, but the plan provides **no
architectural mechanism that prevents the leak — only a stronger text instruction**,
which the FSM rigidity (Blocker 2) and the injection surface (security doc) both
prove the model will violate under real input.

**What MUST change:** (a) Treat single-brain-+-packs as a **falsifiable hypothesis
with a kill criterion**, not a foundation. W17 must ship a **per-vertical
behavioral-leakage eval** *before* W2 is declared done: run a complaint call,
assert zero sales moves; run a support call, assert no unsolicited booking push.
(b) Build the contracts so a vertical can later be **promoted to its own
model/policy** without a rewrite — i.e. the `BrainPackProvider` and `DialoguePolicy`
must be swappable *per use-case at runtime*, so "support uses a different model than
sales" is a config change, not a re-architecture. The plan's modular contracts
*almost* allow this, but `ProviderRouter.resolve(ctx)` keys off the campaign, not
the use-case — **add use-case to the routing key now** so the escape hatch exists.
(c) Be honest in the plan: the single-brain is the *cheap* bet; budget the
*specialized-model* fallback as a known Phase-2, not a failure.

### BLOCKER 5 — The COLD path writes feed the HOT path as ground truth, with no validation gate — a correctness time-bomb. 🟠
The three-speed diagram draws COLD as "post-call, async, cheap model — doesn't
touch the live call." **That's the trap.** COLD produces the **lead memory summary**
and the **RAG index** — both of which are read by the *next* call's HOT/WARM path as
authoritative. So an error or injection in the cheap async summarizer (which runs
`is_admin=True` over an untrusted transcript — security doc #10/#12) is **written as
ground truth and replayed into the next live call**: "notes: customer approved 90%
discount" comes back as fact, and rides the daily WhatsApp exec report too. The
architecture treats COLD as a harmless backwater because it's "offline," but it is
actually a **privileged write path into the brain** with no validation gate. The
plan has no schema-validation, no confidence threshold, no human-review seam, no
"summaries are claims not facts" fence between COLD output and HOT input.

**What MUST change:** (a) COLD writes are **untrusted until validated** — the
`MemoryService.persist` contract must enforce a typed schema + a "this is an
extracted claim, not a verified fact" provenance tag that the HOT-path prompt
fences as DATA (ties to security G-ROOT-2). (b) High-impact extracted facts
(price/discount commitments, lead-state flips) require a **confidence gate or a
review queue**, never silent auto-write. (c) The COLD model must be the cheap one
for *latency* but its *output* is on the *correctness*-critical path — give it the
same eval rigor as HOT, not "it's just a summary."

---

## SECONDARY ARCHITECTURAL DEFECTS (real, but downstream of the blockers)

### B1 — The kernel's prompt-cache premise is STALE / WRONG (verified this pass). 🟡 but foundational
`W1-KERNEL-ARCH.md:43-46` states as ground truth: *"Groq prompt-caching does NOT
support llama-4-scout today → context packet and prompt caching are TWO INDEPENDENT
levers; the kernel captures lever 1 now, lever 2 is a separate decision."*
**This is now false.** Groq's own model docs (verified 2026-06) list **Prompt
Caching as a supported feature of `meta-llama/llama-4-scout-17b-16e-instruct`**,
automatic, halving the cost of repeated input prefixes, and — critically — **cached
tokens don't count toward rate limits.** That last point is huge for Blocker 1: a
stable cached prefix directly *buys concurrency headroom* against the per-org quota.
The kernel was designed around a premise that no longer holds, which means: (a) the
"most-stable-prefix-first" layer ordering (L0..L3 cached once/call) isn't just a
latency nicety — it's a **quota-headroom lever** and should be treated as such; (b)
the stable-prefix must be **byte-identical across turns AND across calls of the same
campaign** to actually hit the cache — the design caches "once per call" but to win
the *cross-call* discount the prefix must be campaign-stable, which the per-call
`PacketMeta` (call_id, room, ts_iso embedded high) currently *breaks*. **Fix:** move
ALL per-call/per-turn volatile fields (call_id, room, ts, lead_name) strictly below
the cache boundary, and re-validate the whole cache design against current Groq docs
*before* freezing the W1 contracts — this assumption is load-bearing.

### B2 — Token-budget-by-clamp silently destroys campaign truth (the original sin, reintroduced). 🟡
The founder's #1 complaint was the **lossy 4000-char JSON extract** that dropped
campaign context (`caller.py:1409-1435`). The kernel's fix is... **a different lossy
clamp**: `product_summary<=600c`, `usps<=5`, `objections<=6`, `last_call_summary<=300c`,
`rag<=3 @ <=120c`, "on overflow drop L5, then trim L4" (`W1-KERNEL-ARCH.md §2`). This
is *better-organized* lossiness, but it's still **hard truncation of vendor-authored
truth**, and the founder explicitly asked to **preserve the full brief**. A 600-char
summary cap will silently drop the 7th USP or the specific clause the lead asks about
— reproducing the exact "the agent doesn't know our campaign" failure in a new place.
**Fix:** the architecture needs a **retrieval-over-truncation** discipline: keep the
FULL brief in the RAG store (lossless), put a *compact card* in the packet for the
common path, and let stage-aware retrieval pull the *specific* dropped detail when the
lead asks — so nothing is *destroyed*, only *deferred*. The plan gestures at this
("raw preserved + structured card") but the kernel's clamp logic still treats the card
as the source of truth on the hot path. Make "clamp = what's in the packet now,
NOT what exists" an explicit invariant, with retrieval as the recall path.

### B3 — Inbound-first integration proves the kernel on the WRONG shape of call. 🟡
The integration plan (`§6`) sequences **inbound first** (`aim_voice_agent.py`) because
it's "lower risk." True for *safety*, but architecturally it means **the kernel is
first validated on the call type that least resembles the product's purpose.** Inbound
is receptionist-shaped: single caller, they initiated, low concurrency, no dialer
burst, no cold-start storm, no 500-at-once. **Outbound is the product** and has every
hard property inbound lacks. Proving the kernel inbound tells you almost nothing about
whether it survives Blocker 1. **Fix:** keep inbound-first for *deploy safety*, but
make the **concurrency/load harness (Blocker 1) the real acceptance gate**, run against
*synthetic outbound* sessions — don't let "inbound works" be mistaken for "the kernel
is proven."

### B4 — `null_impls` everywhere = a system that "runs green" while doing nothing real. 🟡
The kernel ships with conformant no-op impls for all 9 contracts so it "constructs and
runs end-to-end before any workflow lands" (`§3`). Pragmatically fine for unit tests —
but it is **exactly the failure pattern the founder's own standing rule names**: "a
green sub-agent report on an isolated component is NOT success." A kernel that passes
`pytest` with null RAG, null memory, null provider-routing, and null brain-packs is a
**hollow pass** that can read as "W1 done." **Fix:** gate "W1 complete" not on null-impl
green, but on **at least one real impl per critical contract wired end-to-end on a real
(synthetic) call** — null impls are scaffolding, not a deliverable, and the
orchestrator must not let a null-green kernel be marked shippable.

### B5 — "COLD = always async/cheap" is wrong for the writes that gate the next call. 🟡
(Companion to Blocker 5.) The diagram's "cheap model, async, off the hot path"
framing is right for *analytics* but wrong for the *memory summary*, because the next
call **can't start until the summary is durable** if calls to the same lead are close
together (callback in 10 min, the founder's "call me at X" feature). An async
fire-and-forget summary that hasn't landed when the callback fires means the
follow-up call starts **memory-blind** — re-creating discontinuity. **Fix:** classify
COLD writes into *truly-async* (analytics, index) vs *next-call-gating* (lead summary,
commitments) and make the gating writes **durable-before-ack with a short SLA**, not
fire-and-forget.

---

## WHERE THE ARCHITECTURE IS ACTUALLY RIGHT (so we don't throw out the good)

Be fair — most of this design is sound and should be kept:
- **Three-speed hot/warm/cold split** — correct, matches both deep-research reports
  and the 2026 consensus. The *seams* are buggy (Blockers 3, 5), not the shape.
- **Context packet replacing the 10k prompt** — correct and necessary; the layer
  ordering is right (just re-validate the cache premise, B1).
- **Speech planner as a separate mandatory layer** — correct; the single best-
  leverage idea in the plan for the "human touch" goal, and well-grounded (Sarvam v3
  has no preprocessing flag, EL normalization off by default).
- **Modular `typing.Protocol` contracts** — correct discipline; it's what makes the
  per-use-case-model escape hatch (Blocker 4) cheap *if* we add the routing key now.
- **OFF-is-byte-identical adapter + earner-gate** — exemplary; the EARNER LAW and the
  golden byte-diff are exactly right and must not be diluted.
- **Provider-neutral SIP, India-first STT, two-tier TTS** — correct stack choices.

The problem is **not** the components. It's that the architecture is **specified for
one call** and the product is **500 calls**, and the **stateful seams** (FSM, warm-
path race, cold-path writeback) are the parts left vaguest — which is backwards,
because they are the parts that actually fail under real human conversation.

---

## THE SINGLE BIGGEST ARCHITECTURAL BLIND-SPOT (if you read nothing else)

**The design has no concurrency model. It is a single-call simulator dressed as a
realtime fleet.** Every artifact — packet, budget, kernel, contracts, tests,
acceptance criteria — is per-call. The product's entire thesis ("replace 500
telecallers") is a *concurrency* claim, and concurrency is the one thing the
architecture never models. The provider math (Groq per-org quota, EL 2–15 concurrent
streams), the warm-path 2× load, the correlated cold-start burst, and the
per-process circuit state all converge to the same conclusion: **the system will be
gorgeous on call #1 and fall over somewhere around call #20–50, exactly when the
founder finally trusts it enough to run a real campaign.** Fix the concurrency model
(admission control + load-harness-as-gate + cache-as-quota-headroom) before writing
the per-call kernel, or W1's foundation contracts will encode the single-call
assumption into everything downstream.

---

## WHAT MUST CHANGE IN THE PLAN — the surgical list

1. **NET-NEW W-CONCURRENCY (or W12 spine):** per-call resource admission controller
   (reserve LLM-quota + TTS-slot + worker before dialing; pace/queue the campaign
   when the fleet can't admit), concurrency as a first-class `KernelConfig` dimension,
   and the **load/tail harness promoted from eval-debt to a hard deploy GATE** at
   50/100/200 concurrent synthetic sessions. *(Blocker 1 — the big one.)*
2. **W1+W6 FSM redesign:** soft non-linear policy (any-stage→any-stage with guards),
   explicit off-script/re-entry state, **constraint decoupled from drive** (FSM vetoes
   illegal moves; LLM chooses within legal), stage **re-derived from transcript each
   turn** not blindly incremented. *(Blocker 2.)*
3. **W1+W4 warm-path sync contract:** `RagRuntime.retrieve` returns a distinct
   "not-ready" vs "empty"; foreground answers only from dial-time-guaranteed state;
   **hot path never blocks on a network RAG/embedding call** (eval-enforced invariant).
   *(Blocker 3.)*
4. **W2+W17 single-brain kill-criterion:** per-vertical behavioral-leakage eval as a
   gate before W2 "done"; add **use-case to the `ProviderRouter` routing key now** so a
   vertical can be promoted to its own model/policy without a rewrite. *(Blocker 4.)*
5. **W7+W9 cold-path validation gate:** COLD writes untrusted-until-validated, typed
   schema + claim-not-fact provenance fence, confidence/review gate on high-impact
   extracted facts, **next-call-gating writes durable-before-ack with an SLA**.
   *(Blockers 5 + B5.)*
6. **W1 re-validate the prompt-cache premise (B1) against current Groq docs BEFORE
   freezing contracts** — llama-4-scout now caches; make the stable prefix
   campaign-stable (not just call-stable) to win the cross-call quota-headroom
   discount; push ALL volatile fields below the cache boundary.
7. **Retrieval-over-truncation (B2):** make "clamp = what's in the packet, not what
   exists; the full brief lives losslessly in RAG and is recalled on demand" an explicit
   architectural invariant — so the founder's "preserve the full brief" is actually true.
8. **Acceptance reframe (B3, B4):** "W1 complete" requires ≥1 real impl per critical
   contract on a synthetic call (not null-impl green); the **concurrency load harness on
   synthetic OUTBOUND** is the real proof, not "inbound works."

---

## SOURCES (verified this pass)
- Groq — Llama 4 Scout model card lists **Prompt Caching as supported**, automatic,
  halves cost of repeated prefixes, **cached tokens don't count toward rate limits**
  (console.groq.com/docs/model/meta-llama/llama-4-scout-17b-16e-instruct;
  console.groq.com/docs/prompt-caching) — **contradicts W1-KERNEL-ARCH.md:43-46.**
- Daily.co — *Benchmarking LLMs for Voice Agent Use Cases*: in 30-turn conversations
  the best models still err in ≥1 turn; FSM agents stray/choose wrong branch after
  interruptions.
- Production FSM-agent field report (Medium / hashnode "Stop Letting the LLM Drive
  Your Voice Agent's State Machine"; "Treat Prompts Like State Machines"): FSM-style
  agent hit phantom-tool / API-error cascades in ~52% of turns on state↔history desync;
  constraint-vs-drive separation guidance.
- nextlevel.ai / Daily.co (2026) — production voice systems trending to
  **context-routing → specialized per-vertical models/templates**, not one universal
  prompt-brain — challenges the single-brain claim (Blocker 4).
- Salesforce AI Research VoiceAgentRAG / LTS-VoiceAgent — dual-agent Slow-Thinker /
  Fast-Talker (the warm-path pattern; source of the Blocker-3 race).
- Companion red-team docs (this repo): `RVK2-SECURITY-ISOLATION-MASTER-GAPS.md`,
  `LATENCY-TAILS-GAP-ANALYSIS.md` (4A cold-start, 6A warm race, 7A load harness),
  `RVK2-PROVIDER-FAILOVER-KEYHEALTH-GAPS.md` (G-PF3 per-org quota, G-PF4 EL concurrency,
  G-PF11 per-process circuit state) — the concurrency blocker is the *union* of their
  load-triggered findings, which is exactly why no single dimension-doc names it.
```
