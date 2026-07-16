# VOICE_ARCHITECTURE_RESEARCH — Building a Truly Human AI Voice Salesperson for Famit

**Status:** RESEARCH ONLY (no code, no product changes). Feeds a future planning phase.
**Date:** 2026-06-05. **Author:** VOICE-ARCHITECTURE-RESEARCHER.
**Scope:** How to get *real human timing and sales behaviour* — "know when to speak, when to stop, when to ask, when to explain, when to push, when to back off" — beyond a single large system prompt. Honest verdicts + sources + a phased path tailored to Famit's actual stack.

> **DO NOT TOUCH PRODUCT CODE** off the back of this doc. Nothing under `droplet_work/` or `famit-panel/`. This is a map, not a change.

---

## 0. Famit's current stack (the baseline we are reasoning against)

- **Transport / orchestration:** LiveKit + livekit-sip (native **livekit-agents**, *not* Pipecat).
- **Pipeline:** Sarvam STT (auto-language Hindi/Hinglish/English) → Groq `llama-4-scout-17b` LLM → ElevenLabs Flash v2.5 TTS → **Silero VAD** for turn-taking.
- **Turn-taking:** Silero VAD + endpointing delays only (`max_endpointing_delay=0.5`, `min_endpointing_delay=0.3`). **No semantic / model-based turn detector.**
- **"Brain":** a single field-driven system prompt (`prompt.py`) implementing greet→confirm→permission→pitch→qualify→close, concise/interrupt-friendly, language auto-detect. This is **pure prompt engineering**.
- **Latency:** ~1.0–1.2 s/turn (eou ~0.75 + ttft ~0.35 + ttfb ~0.19). **This low latency is Famit's moat** — any change that regresses it is a real cost.
- **History that matters:** Famit *deliberately retired Pipecat* (`capsy-agent.service`, buggy `voice_agent_v2`, the **StartFrame race**). Recommendations must not quietly push Famit back onto a framework it already abandoned.

The founder's instinct is correct: the best human-feeling voice products are **not** one giant prompt. They layer (a) a structured flow/state controller, (b) a semantic turn-taking model, (c) grounding/retrieval, and (d) an eval+learning loop. Below, each lever is assessed for **how much it actually buys Famit**, at what cost/latency, and *when* it's worth it.

---

## 1. PROMPT ENGINEERING — where Famit is now, and its real ceiling

**Verdict: Necessary, not sufficient. It is genuinely fine for persona, tone, language behaviour and the *happy-path* script. It hits a hard ceiling on (a) reliable multi-turn state ("where am I in the conversation"), (b) deterministic branching/compliance, and (c) consistency under objection/curveball turns.**

What the field says in 2026:
- The reliability problem is not "more techniques" — it's that a prompt is not a *specification*. The most reliable prompts are treated as **contracts**: exact allowed inputs, constraints, output shape, and a check step. "Boring prompts are the most reliable prompts." ([Supercharge](https://www.supercharge.io/blog/ai-prompt-engineering-best-practices))
- Even the best 2026 models still **trail on complex multi-turn instruction following and multi-turn function-calling**; quality on natural conversational turns improved sharply but long, conditional instruction sets degrade. ([Retell — best LLM for voice](https://www.retellai.com/blog/best-llm-for-voice-agents), [Daily — benchmarking LLMs for voice](https://www.daily.co/blog/benchmarking-llms-for-voice-agents/))
- The core structural argument: **"the LLM doesn't inherently remember where it is in a conversation — you have to explicitly tell it what state it's in and which functions are available."** As scope grows (more objections, more campaigns, compliance rules), "relying solely on the LLM's raw context will lead to failure." ([Daily — Beyond the Context Window](https://www.daily.co/blog/beyond-the-context-window-why-your-voice-agent-needs-structure-with-pipecat-flows/))

**Famit-specific ceiling:** Famit's `llama-4-scout-17b` is a *small, fast* model chosen for latency. Small models follow long conditional prompts *worse* than frontier models. So Famit's prompt brain will be **more** prone to: forgetting it already asked permission, re-pitching, mis-ordering qualify→close, and "leaking" the whole flow when a user throws a curveball. That is exactly the symptom the founder senses.

**Honest bottom line:** Prompt engineering is the right *foundation* and Famit should keep refining it — but "make the prompt bigger/cleverer" will not produce reliable human timing on a small model. The next gains come from **moving state out of the prompt** (Section 2) and **moving turn-taking out of VAD** (Section 3).

---

## 2. DIALOGUE-FLOW / STATE-MACHINE LAYER — the biggest structural lever

**Verdict: YES, add a flow/state layer — but do it *inside LiveKit*, NOT by importing Pipecat Flows.** This is the single most important reframe in this report.

### Do production voice-sales agents use explicit flow graphs?
Yes, for scripted outbound specifically. The clearest example is **Bland AI's "Pathways"** — a graph of nodes where each node is a distinct conversational state with explicit transition labels, strict guardrails on what the agent may say per node, tool-call constraints, and version control as a first-class feature. The industry read: *"For heavily scripted outbound campaigns (compliance scripts, appointment reminders, surveys) Pathways is genuinely the best tool of the three"*, trading some latency for deterministic flow control. Caveat from the same sources: **non-technical teams cannot build/maintain Pathways without engineers** — it's powerful but heavy. ([Retell — Vapi vs Bland](https://www.retellai.com/blog/vapi-vs-bland), [Builts.ai comparison](https://builts.ai/blog/vapi-vs-bland-ai-vs-retell-ai/))

**Pipecat Flows** is the open analogue: an add-on that defines conversation paths and dynamically adjusts *what the bot knows and which tools it can use* based on conversation state — explicitly sitting *outside* the context window to guide the LLM step by step. The motivating principle is exactly Famit's pain: state machines for conversation management, because "voice conversations are inherently state-driven." Some regulated agents need *predictable, auditable execution paths, not just capable ones*. ([Pipecat Flows docs](https://docs.pipecat.ai/guides/features/pipecat-flows), [GitHub pipecat-flows](https://github.com/pipecat-ai/pipecat-flows))

### Why NOT Pipecat Flows for Famit
1. **Famit already abandoned Pipecat** over the StartFrame race. That class of bug is real and ongoing: a documented production gotcha is that **audio frames (e.g. the opening greeting) arriving before the pipeline's StartFrame/session is live get silently dropped** — partially/fully lost welcome messages. There's also a recent fix for `PipelineTask.cancel()` *hanging* when cancellation hits before StartFrame reaches the sink. ([Anam — frame processing](https://anam.ai/blog/pipecat-frame-processing-guide), [Pipecat production issues](https://luonghongthuan.com/en/blog/pipecat-voice-agent-production-scalable-guide/), [Pipecat CHANGELOG / PR#4380](https://github.com/pipecat-ai/pipecat/blob/main/CHANGELOG.md))
2. **Reintroducing Pipecat means a second orchestration framework alongside LiveKit** — more moving parts, the StartFrame-class races again, and a rewrite of working code.

### What Famit should use instead: LiveKit's *native* workflow primitives
LiveKit Agents (1.x) already ships the structured-flow building blocks Famit needs, **on the stack it already runs**:
- **Agents** = long-lived controllers with their own instructions + tools; one session can be composed of several. An agent can **hand off** control to another agent when different rules/capabilities are needed.
- **Tasks** = short-lived, run-to-completion units returning a *typed* result (e.g. "collect budget", "qualify").
- **Task Groups** = ordered sequences for multi-step ops that **share context and allow revisiting earlier steps**.
- **Handoff pattern** = the router *swaps the room's agent implementation mid-call without tearing down the call* — the user experiences one continuous conversation. ([LiveKit — Workflows](https://docs.livekit.io/agents/logic/workflows/), [LiveKit — Handoff pattern](https://livekit.com/blog/handoff-pattern-voice-agents), [LiveKit — Sequential pipeline](https://livekit.com/blog/sequential-pipeline-architecture-voice-agents))

**Honest nuance:** LiveKit's model is **code-driven conditional routing + per-phase tool/instruction swapping**, *not* a declarative drag-the-nodes graph like Pipecat Flows or Bland Pathways. You express the state machine in Python (agent classes + handoff calls in tools), not in a visual graph. For Famit that's a *feature*: it's the minimal change that gives per-stage instruction sets and tool gating (so the LLM only "sees" the greet rules during greet, the objection tools during pitch, the close logic during close) **without a new framework, without the StartFrame class of bug, and with negligible latency cost** (it's swapping which small prompt/toolset is active, not adding a pipeline hop).

**Bottom line:** The fix for "the agent forgets where it is / re-pitches / leaks the flow" is a **per-stage state layer**, and Famit can get ~80% of Pipecat-Flows/Pathways value by splitting `prompt.py` into a small LiveKit multi-agent/task flow (greet-agent → pitch-agent → qualify-task → close-agent) on its existing stack. **This is the highest-structural-leverage move and it stays same-framework.**

---

## 3. TURN-TAKING / SEMANTIC ENDPOINTING — the highest-leverage, lowest-risk "feels human" win

**Verdict: ADOPT a semantic turn-detection model. For Famit this is the #1 quickest win — same framework, same VAD, CPU-only, strong Hindi support, and it directly fixes "knowing when the human is done."**

Why VAD-only (Famit today) feels robotic: VAD detects *silence*, not *completion of thought*. It fires on natural mid-sentence pauses (false "your turn" → agent interrupts) and waits a fixed delay even when the human is obviously done (sluggish). VAD "lacks language understanding and frequently causes false positives." The three layers and how they compose:
- **VAD** (audio frames: speech vs silence) — foundational, Famit has this (Silero).
- **STT endpointing** (transcript signal of completion; "doesn't require silence, just a strong enough signal") — the recommended *default* for most production agents.
- **Model-based / semantic** (a small classifier reads the *partial transcript* and predicts turn completion from *semantic meaning*; **can trigger before trailing silence** → the main latency advantage, and avoids cutting people off mid-thought). ([LiveKit — Turn detection: VAD, endpointing, model-based](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection), [AssemblyAI — turn detection/endpointing](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent))

### The concrete option for Famit: LiveKit `turn-detector` (composes with Silero VAD)
From the model card — and this is the kicker for an Indic product:
- Base **Qwen2.5-0.5B-Instruct**, ~**0.1B params**, INT8 ONNX, **CPU-only, <500 MB**, runs alongside Silero VAD inside LiveKit Agents (it's a plugin; VAD still handles barge-in, the model supplies the *semantic "turn is complete"* signal). ([HF — livekit/turn-detector](https://huggingface.co/livekit/turn-detector))
- **14 languages incl. Hindi.** **Hindi: 99.4% true-positive / 96.3% true-negative** — best in the table, ahead of English (99.3% / 87.0%). ([HF — livekit/turn-detector](https://huggingface.co/livekit/turn-detector))
- Open-weights research lineage; LiveKit also documented the transformer approach. ([LiveKit blog — transformer EOU](https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection))

**Alternative (open, audio-based):** **Pipecat `smart-turn` v2/v3** predicts turn completion from the *raw waveform* (catches intonation/pace, not just text), 14 languages **incl. Hindi**, ~99% on its human test set, available self-hosted or via hosted inference (Fal/Cloudflare Workers AI). It's framework-agnostic in principle but is a Pipecat project — using it cleanly inside LiveKit is more integration work than LiveKit's own plugin. ([HF — smart-turn-v2](https://huggingface.co/pipecat-ai/smart-turn-v2), [Daily — Smart Turn v2](https://www.daily.co/blog/smart-turn-v2-faster-inference-and-13-new-languages-for-voice-ai/), [smart-turn-v3](https://huggingface.co/pipecat-ai/smart-turn-v3))

**Famit recommendation:** Use **LiveKit's `turn-detector` plugin** — it's same-framework, CPU-only (no GPU bill, no extra network hop), keeps Silero for barge-in, and its Hindi accuracy is exactly what Famit needs for Hinglish/Devanagari calls. This is the move that most directly converts "robotic timing" into "feels human," at the lowest risk. **Do this first.**

---

## 4. FINE-TUNING vs PROMPTING — real payoff for *tone/pacing*, but a latency trap for Famit

**Verdict: Worth it *eventually*, for tone/pacing/objection-style — NOT now, and NOT before an eval harness exists. The catch: fine-tuning means self-hosting the LLM, which threatens Famit's Groq-driven ~1s latency moat.**

The evidence is genuinely encouraging on *what fine-tuning is good for*:
- A 2026 study fine-tuned **Llama-3.2-1B-Instruct with LoRA** to hit a "natural, conversational voice tone" target and found **fine-tuning substantially outperformed system prompting**, and was **strikingly data-efficient — effective with as few as ~100 samples**. (Note: the paper reports the *direction* strongly but does **not** publish clean percentage deltas — do not cite invented numbers.) ([arXiv 2507.04889](https://arxiv.org/abs/2507.04889))
- 2026 consensus: **fine-tuning is for *form*, not *facts*** — style, tone, structured output, refusal/objection patterns — while RAG supplies facts. The recommended ordering is **Prompt → RAG → Fine-tune → Distill**, and the highest-ROI approach is a **thin LoRA/QLoRA adapter on a strong base, paired with retrieval, not replacing it.** ([BigData Boutique](https://bigdataboutique.com/blog/fine-tuning-llms-when-rag-isnt-enough), [Gauraw — LoRA/DPO 2026](https://www.gauraw.com/fine-tuning-llm-lora-dpo-guide-2026/), [Daily Dose of DS](https://blog.dailydoseofds.com/p/how-to-fine-tune-llms-in-2026))

**Why this is genuinely attractive for Famit:** the founder has *real Shapoorji-style telecaller scripts/training material*. That's exactly the asset that makes a LoRA on tone/pacing/objection-handling pay off — you'd be teaching the model *how a good Indian real-estate telecaller actually sounds and rebuts*, which a small fast model will never fully internalise from a prompt.

**Why NOT now — the honest blockers:**
1. **Latency / hosting.** Fine-tuning means you no longer call Groq's blazing hosted `llama-4-scout`; you self-host your LoRA'd model. Unless Famit stands up serious GPU inference (vLLM/TGI on an adequately fast GPU), **TTFT will likely regress vs Groq**, eroding the ~1s moat. "Founder will self-host anything" does not erase this — it's an infra-and-cost project, not a config flag.
2. **No eval harness yet (Section 6).** You *cannot know* whether a fine-tune beats the current prompt brain without a way to score calls. Fine-tuning before evals is flying blind — and risks shipping a model that *sounds* trained but converts *worse*.
3. **The current brain isn't exhausted.** The state layer (Sec 2) + turn model (Sec 3) will lift "human feel" a lot first. Fine-tune only the residual that prompting+flow genuinely can't reach (subtle tone, objection rebuttal style).

**When it flips to "worth it":** once (a) an eval harness exists, (b) you have a few hundred–thousand labelled good/bad turns from real Shapoorji-style calls, and (c) you've decided you can eat the self-hosting latency/cost — then a **LoRA/QLoRA on a small Llama/Qwen for tone + objection style** is the right tool. **LoRA, not full fine-tune** (cost/speed/quality balance is the 2026 default). ([ai-agentsplus](https://www.ai-agentsplus.com/blog/llm-fine-tuning-best-practices-2026), [n1n.ai LoRA/QLoRA guide](https://explore.n1n.ai/blog/fine-tune-llm-lora-qlora-guide-2026-2026-04-17))

---

## 5. RAG / MEMORY GROUNDING — yes for the objection bank + product facts; keep it simple and cached

**Verdict: Adopt a *small, pre-loaded* retrieval layer for the objection bank + project facts + per-lead memory. But do NOT build an exotic sub-200ms RAG system yet — Famit's scale doesn't need it.**

The why: a salesperson's answers must be *specific and consistent* ("what's the price per sq ft", "what about possession date", "isn't Sector 49 too far") — facts the LLM will otherwise hallucinate or vary. RAG grounds them. Famit already has the *memory* half (cross-call `memory.py` JSON recap injection) — the missing half is a **product-knowledge + objection-rebuttal store**.

The latency reality and how the field solves it:
- Voice wants sub-200ms responses; a naive vector DB query is 50–300ms network round-trip — it can eat the whole budget. ([Vonage — reducing RAG latency](https://developer.vonage.com/en/blog/reducing-rag-pipeline-latency-for-real-time-voice-conversations), [AutoInterviewAI — RAG in real-time calls](https://www.autointerviewai.com/blog/rag-real-time-voice-ai-calling-explained-2026))
- The cutting edge (Salesforce **VoiceAgentRAG**, 2026) decouples retrieval from generation with a "slow thinker" pre-fetcher feeding a FAISS cache the "fast talker" reads from — reported **~316× speedup (110ms→0.35ms) on cache hits, ~75% hit rate** (search-snippet figures — cite as such). ([arXiv 2603.02206](https://arxiv.org/abs/2603.02206), [Salesforce VoiceAgentRAG writeup](https://earezki.com/ai-news/2026-03-30-salesforce-ai-research-releases-voiceagentrag-a-dual-agent-memory-router-that-cuts-voice-rag-retrieval-latency-by-316x/))

**Famit-right approach (deliberately boring):** A single campaign's objection bank + project sheet is *small* (tens of Q&A pairs, one fact sheet). Don't run a live vector DB in the hot path. Instead: **pre-embed per-campaign into a tiny in-memory FAISS index loaded at call start**, or even **inject the whole compact objection/fact block into the active stage's prompt** (it's small enough). Per-lead memory stays the existing JSON recap. **The 316× dual-agent architecture is premature for Famit's scale — flagged in "don't bother yet."** Revisit live RAG only when knowledge grows beyond what fits comfortably in-context per stage.

---

## 6. FEEDBACK / LEARNING LOOPS — the *real* differentiator, and the gate for everything trainable

**Verdict: Build an eval/simulation harness. This is the prerequisite that unlocks fine-tuning, prompt/flow A/B, and honest "is this actually better?" decisions. It is more important than fine-tuning and should come *before* it.**

What "good" looks like in 2026:
- A standard eval loop: **define success criteria → build test sets (happy + edge + adversarial) → run automated evals → triage failures → regression-test on every change → monitor in prod.** An *agent eval harness* loads test cases, grades results, and **gates deployments**. ([Braintrust — agent evaluation](https://www.braintrust.dev/articles/agent-evaluation), [Hamming — how to evaluate voice agents](https://hamming.ai/resources/how-to-evaluate-voice-agents-2026))
- **Voice-specific simulation:** the 2026 method is to **simulate many synthetic personas placing *real audio* calls, score every turn, and use turn-level error localization** to debug in minutes (persona authoring, auto-generated scenarios, programmatic eval API as a CI primitive). ([Hamming — voice agent testing guide](https://hamming.ai/resources/voice-agent-testing-guide), [FutureAGI — voice agent simulation 2026](https://futureagi.com/blog/voice-agent-simulation-2026-guide/))
- **Learning from outcomes:** label good/bad turns (human + call-outcome signal: connected/qualified/booked), and feed that into prompt/flow A/B and (later) LoRA/DPO. Self-training from sparse dialogue rewards is an active, promising area but **not** something Famit should build bespoke yet. ([arXiv — sparse rewards self-train dialogue agents](https://arxiv.org/pdf/2409.04617))

**Famit-right approach:** Start *small and home-grown*. (1) Log every call transcript + outcome (Famit already records calls to `/calls`/`/stats`). (2) Write ~20–50 **scenario scripts** (interested, busy, hostile, "are you a robot?", price objection, wrong-number, language-switch). (3) Replay them against the agent and score with an **LLM-judge rubric** (did it greet→permission correctly? interrupt-friendly? handle the objection? respect compliance? push vs back-off appropriately?). (4) Gate every prompt/flow change on this. This harness is what turns "I think the new prompt is better" into evidence — and it's the thing that makes Sections 2 and 4 measurable rather than vibes-based.

---

## 7. WHAT PRODUCTION VOICE-SALES COMPANIES ACTUALLY DO

Patterns inferable from public docs/comparisons (2026):

- **Bland AI** — API-first, high-volume outbound; **"Pathways" = explicit graph state machine** (nodes = states, labelled transitions, per-node guardrails, version control). Best-in-class for *scripted compliance-heavy outbound*; needs engineers; lower latency via self-hosted infra. → **Validates: scripted sales = explicit flow graph.** ([Retell — Vapi vs Bland](https://www.retellai.com/blog/vapi-vs-bland), [Builts.ai](https://builts.ai/blog/vapi-vs-bland-ai-vs-retell-ai/))
- **Vapi** — middleware/orchestration: BYO LLM/TTS/telephony; flexible flow + tools. → Validates the *bring-your-own-pipeline* model Famit already lives in. ([Inworld — Vapi vs Pipecat vs LiveKit](https://inworld.ai/resources/vapi-vs-pipecat-vs-livekit))
- **Retell** — managed, **voice-quality + low-latency** focus. → Validates: latency is a first-class product axis (Famit's instinct to protect ~1s is correct). ([Retell](https://www.retellai.com/blog/vapi-vs-bland))
- **PolyAI** — enterprise customer-service voice; solves **ASR, TTS, barge-in, sub-second latency** with proprietary engines; heavy on robust turn-taking/barge-in. → Validates: **turn-taking/barge-in is a core, separately-engineered concern**, not an afterthought. ([PolyAI developers](https://poly.ai/developers))
- **Sarvam (India)** — foundation-model + **Sarvam Agents** framework, **Bulbul TTS / Saarika ASR** tuned for Indian accents + **code-switching**. Famit already uses Sarvam STT; Sarvam's Indic-first agent stack is the closest "what a serious Indian voice-sales stack looks like." → Validates: **Indic-tuned ASR + code-switch handling matters**, and is a potential future swap/benchmark. ([Caller.digital — Sarvam vs platform](https://www.caller.digital/blog/sarvam-ai-vs-caller-digital-foundation-model-vs-platform-2026), [Caller.digital — open-source voice AI India](https://www.caller.digital/blog/open-source-voice-ai-india-sarvam-ai4bharat-bhasini-2026))
- **Air.ai** — the cautionary data point. Much-hyped as a fully-autonomous "human-like" sales/CS voice agent, but **widely reported to have underdelivered** vs the demos in real deployments; comparisons now position it behind the API-first players. → The honest lesson: a *single very capable autonomous agent* marketed as "just talks like a human" is exactly the mega-prompt fantasy this report argues against — the durable products won on **structure + turn-taking + evals**, not on one magic conversational model. ([Retell — Bland vs Air AI](https://www.retellai.com/blog/bland-vs-air-ai))

**Cross-cutting pattern:** The serious players all have (1) a **structured flow/state layer**, (2) **dedicated turn-taking/barge-in engineering**, (3) **grounding/knowledge**, and (4) **eval/monitoring**. None rely on a single mega-prompt. Famit currently has only a strong prompt + VAD — which is exactly why the founder's instinct ("this isn't how the best do it") is right.

---

## RECOMMENDED ARCHITECTURE + PHASED PATH FOR FAMIT

**Guiding principle: stay on LiveKit, protect the ~1s latency moat, add structure where it measurably helps, and prove every change with evals before trusting it. Don't switch frameworks. Don't fine-tune blind.**

### Phase 0 — Instrument first (days; near-zero risk)
- Make sure every call logs **transcript + outcome + per-turn latency** (mostly exists via `/calls`,`/stats`, LATENCY logs). This is the raw material for everything trainable.

### Phase 1 — Semantic turn detection (1–2 weeks; **highest ROI, lowest risk**)
- Add **LiveKit `turn-detector` plugin** alongside the existing **Silero VAD**. CPU-only, <500MB, Hindi 99.4% TPR. Keep Silero for barge-in; let the model decide "human is done."
- Expected effect: the biggest single jump in "feels human" (fewer interruptions, snappier when the user *is* done), with **no new framework and no LLM change**. Watch eou latency — semantic detection can *cut* perceived lag, not add it.
- **Cost: ~free** (CPU inference, no GPU, no per-call API). Model card suggests a compute-optimized instance (avoid burstable) — may mean a slightly larger droplet, not a new vendor bill.
- **VERIFY before trusting "lowest risk":** the turn-detector is *text-first* — it reads the partial transcript. Confirm the **Sarvam STT plugin in LiveKit emits the streaming partial/transcript signal the model consumes**, and that the Hindi threshold behaves on Sarvam's *Devanagari* output (and on Hinglish/code-switched turns). Likely fine, but unverified on Famit's exact STT — pilot on a handful of calls before rollout.

### Phase 2 — Structured flow layer *inside LiveKit* (2–4 weeks; high structural ROI)
- Refactor the monolithic `prompt.py` into a **LiveKit multi-agent/task flow**: greet-agent → (permission gate) → pitch-agent → qualify-task(group) → close-agent, using **handoffs** to swap instructions+tools per stage so the LLM only ever sees the rules/tools for the *current* stage.
- This fixes "forgets where it is / re-pitches / leaks flow / mis-orders," gives deterministic compliance gates, and is **same-framework, negligible latency**.
- **Cost: engineering time only** — no new runtime/vendor cost (it's swapping which small prompt+toolset is active on the same Groq call).
- **Explicitly NOT Pipecat Flows / Bland Pathways** — Famit retired Pipecat (StartFrame race); reintroducing it is a regression risk.
- **Negotiation scope (deliberate):** the flow handles **objection handling** (rebut "too far / too pricey / are you a robot / call me later") well via the pitch-agent's objection tools/bank. **Hard *price* negotiation is intentionally kept downstream/human** — a tele-caller's job here is to book a site visit and qualify, not to close a price. So "push vs back off" in the rubric is about *persistence and tone*, not haggling. This is a scope choice, not an omission; revisit only if the business wants the agent to quote/negotiate.

### Phase 3 — Eval/simulation harness (2–4 weeks; the gate for all training)
- Home-grown: ~20–50 scenario personas (interested/busy/hostile/"are you a robot"/price-objection/language-switch) replayed against the agent, scored by an **LLM-judge rubric** on the timing+sales behaviours the founder cares about. Gate every prompt/flow change on it.
- This converts "I think it's better" into evidence and is the prerequisite for Phase 5.
- **Cost: engineering time + cheap batch LLM-judge API spend** (offline, not in the call hot path — pennies per eval run). No GPU.

### Phase 4 — Lightweight grounding (1–2 weeks; do the boring version)
- Per-campaign **objection bank + project fact sheet**: pre-embed into a tiny in-memory FAISS index at call start, or inject the compact block into the active stage's prompt. Keep per-lead memory as the existing JSON recap.
- **No live vector DB in the hot path; no dual-agent RAG.**
- **Cost: near-zero** (in-memory FAISS or in-context; one-time cheap embedding per campaign, no managed vector-DB bill).

### Phase 5 — Fine-tune on real telecaller data (LATER; only after Phases 1–3)
- Once the eval harness exists and enough labelled good/bad turns are collected from real Shapoorji-style calls: train a **LoRA/QLoRA on a small Llama/Qwen** for *tone, pacing, objection rebuttal style* (form, not facts — RAG still supplies facts).
- **Hard gate:** decide the **self-hosting latency/cost** question first (GPU vLLM/TGI vs the current Groq moat). Only ship the fine-tune if evals show it beats the prompt+flow brain *and* latency stays acceptable. If latency regresses, keep Groq + prompt/flow and bank the fine-tune research for later.
- **Cost: this is the only phase with real recurring cost.** LoRA *training* is cheap (a few GPU-hours, one-off). The expensive part is *serving*: leaving Groq's hosted endpoint for a self-hosted GPU running your adapter — an always-on GPU bill **and** the latency-moat risk. The dollar cost and the latency risk are the same decision wearing two hats.

### "DON'T BOTHER (yet)" LIST
- ❌ **Don't adopt Pipecat / Pipecat Flows.** Famit already left it (StartFrame race); LiveKit's native agents/tasks/handoffs cover the flow need.
- ❌ **Don't build sub-200ms dual-agent RAG (VoiceAgentRAG-style).** Premature for Famit's small per-campaign knowledge; in-context/tiny-FAISS is enough.
- ❌ **Don't fine-tune before the eval harness exists.** You'd be flying blind and risk a model that *sounds* trained but converts worse.
- ❌ **Don't full-fine-tune.** LoRA/QLoRA only.
- ❌ **Don't swap off Groq just to fine-tune** unless evals prove the gain AND you can hold latency. The ~1s moat is a real product asset.
- ❌ **Don't chase a visual node-graph builder.** Code-driven LiveKit handoffs are enough and avoid a new framework.
- ❌ **Don't try to fix human timing with a bigger system prompt.** That's the ceiling you're already hitting on a small model.

### One-line summary
**Keep LiveKit + Groq + the prompt brain. Add (1) LiveKit's semantic turn-detector now, (2) a LiveKit-native per-stage flow layer next, (3) a home-grown eval harness — and only *then*, gated on evals and latency, a LoRA on real telecaller transcripts. Skip Pipecat, skip exotic RAG, skip blind fine-tuning.**

---

## SOURCES
- Daily/Pipecat — Beyond the Context Window (why voice needs structure): https://www.daily.co/blog/beyond-the-context-window-why-your-voice-agent-needs-structure-with-pipecat-flows/
- Pipecat Flows docs: https://docs.pipecat.ai/guides/features/pipecat-flows | GitHub: https://github.com/pipecat-ai/pipecat-flows
- Pipecat production issues / StartFrame gotcha: https://anam.ai/blog/pipecat-frame-processing-guide | https://luonghongthuan.com/en/blog/pipecat-voice-agent-production-scalable-guide/ | https://github.com/pipecat-ai/pipecat/blob/main/CHANGELOG.md
- LiveKit Workflows (agents/tasks/handoffs): https://docs.livekit.io/agents/logic/workflows/ | Handoff pattern: https://livekit.com/blog/handoff-pattern-voice-agents | Sequential pipeline: https://livekit.com/blog/sequential-pipeline-architecture-voice-agents
- LiveKit turn detection (VAD/endpointing/model-based): https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection | transformer EOU: https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection
- LiveKit turn-detector model card (Qwen2.5-0.5B, Hindi 99.4%): https://huggingface.co/livekit/turn-detector
- AssemblyAI — turn detection/endpointing: https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent
- Pipecat smart-turn v2/v3 (waveform, Hindi): https://huggingface.co/pipecat-ai/smart-turn-v2 | https://huggingface.co/pipecat-ai/smart-turn-v3 | https://www.daily.co/blog/smart-turn-v2-faster-inference-and-13-new-languages-for-voice-ai/
- Fine-tuning beats prompting for tone (Llama-3.2-1B LoRA, ~100 samples): https://arxiv.org/abs/2507.04889
- Fine-tuning 2026 guidance (form-not-facts; Prompt→RAG→Fine-tune→Distill; LoRA): https://bigdataboutique.com/blog/fine-tuning-llms-when-rag-isnt-enough | https://www.gauraw.com/fine-tuning-llm-lora-dpo-guide-2026/ | https://blog.dailydoseofds.com/p/how-to-fine-tune-llms-in-2026 | https://www.ai-agentsplus.com/blog/llm-fine-tuning-best-practices-2026 | https://explore.n1n.ai/blog/fine-tune-llm-lora-qlora-guide-2026-2026-04-17
- RAG latency in voice (sub-200ms problem): https://developer.vonage.com/en/blog/reducing-rag-pipeline-latency-for-real-time-voice-conversations | https://www.autointerviewai.com/blog/rag-real-time-voice-ai-calling-explained-2026
- VoiceAgentRAG (dual-agent, 316x cache): https://arxiv.org/abs/2603.02206 | https://earezki.com/ai-news/2026-03-30-salesforce-ai-research-releases-voiceagentrag-a-dual-agent-memory-router-that-cuts-voice-rag-retrieval-latency-by-316x/
- Eval/sim harness: https://www.braintrust.dev/articles/agent-evaluation | https://hamming.ai/resources/how-to-evaluate-voice-agents-2026 | https://hamming.ai/resources/voice-agent-testing-guide | https://futureagi.com/blog/voice-agent-simulation-2026-guide/ | https://arxiv.org/pdf/2409.04617
- Prompt reliability ceiling: https://www.supercharge.io/blog/ai-prompt-engineering-best-practices | https://www.retellai.com/blog/best-llm-for-voice-agents | https://www.daily.co/blog/benchmarking-llms-for-voice-agents/
- Production companies (Bland/Vapi/Retell/PolyAI/Sarvam): https://www.retellai.com/blog/vapi-vs-bland | https://builts.ai/blog/vapi-vs-bland-ai-vs-retell-ai/ | https://inworld.ai/resources/vapi-vs-pipecat-vs-livekit | https://poly.ai/developers | https://www.caller.digital/blog/sarvam-ai-vs-caller-digital-foundation-model-vs-platform-2026 | https://www.caller.digital/blog/open-source-voice-ai-india-sarvam-ai4bharat-bhasini-2026
