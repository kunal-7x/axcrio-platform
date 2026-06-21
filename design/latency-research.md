# AI Manager Voice — Low-Latency Data/Response Pipeline: Diagnosis + Research + Architecture

**Status:** READ-ONLY diagnosis + deep web research + target architecture. No box mutation, no deploy, no git.
**Date:** 2026-06-12. **Box (read-only):** famit@168.144.153.145 — `aim-voice-agent.service`.
**Scope note:** A separate wave (#5 customer mode) is editing `aim_voice_agent.py`. This doc does NOT touch it; all fixes below are specified for a *later* build wave to apply.

---

## 0. TL;DR — the 3–5 minute silence is NOT a data-retrieval problem

The founder's symptom ("how many hot leads" → Riya goes silent 3–5 min → eventually answers, once said "I have to call the check-leads tool") is **not** caused by slow data. It is caused by a **tool-call schema rejection that LiveKit mis-classifies as a retryable connection error**, sending the turn into a retry storm that ends with the LLM task dying and producing **zero audio output** (dead air).

**Hard evidence from journald (last 24h on the live box):**
- `openai.APIError: tool call validation failed: parameters for tool check_leads did not match schema: errors: [missing properties: 'campaign']` — **48 occurrences**.
- `tool run_campaign did not match schema: errors: ['/confirmed': expected boolean, but got string, '/count': expected integer, but got string]` — **28 occurrences**.
- Each rejection is wrapped as `APIConnectionError(retryable=True)` → LiveKit retries `0.1s → 2.0s → 2.0s`, **re-sending the full prompt each time**; the model re-emits the same bad call → all 3 attempts fail identically → `recoverable=False` → `_llm_inference_task` raises → **no LLM output for that turn → silence**. The founder repeats himself → a new turn → a new retry storm. Compounded over repeats this is the multi-minute dead air. The ElevenLabs websocket then also dies (`1006`) after the LLM task crashes, adding more silence.

So the data files are tiny (`leads.json` 4 KB, `calls.json` 76 KB), the tool functions already run off the event loop via `asyncio.to_thread`, and the loopback HTTP to `caller.py:8209` is fast. **None of that is the bottleneck.** The bottleneck is a correctness bug at the LLM↔tool boundary that manifests *as* latency.

**The two-track fix:** (Track A) kill the schema-rejection bug so tools actually return — this alone removes the 3–5 min silences. (Track B) then layer the production low-latency data architecture below (warm cache, filler speech, what-goes-where) to get steady **<1–2 s** answers and make the system robust.

---

## 1. Diagnosis detail (live code + logs)

### 1.1 The hot path (as built)
```
SIP call → LiveKit room (agent_name=manager) → aim_voice_agent.py
  AgentSession(stt=Sarvam saarika:v2.5, llm=Groq llama-4-scout-17b temp=0.3 max_tokens=140,
               tts=ElevenLabs flash_v2_5, vad=silero, turn_detection=Multilingual semantic,
               preemptive_generation=True, min_endpointing_delay=0.25)
  ManagerAgent @function_tool check_leads/list_campaigns/recent_calls/analytics/wallet/run_campaign/...
    → asyncio.to_thread(voice_tools.<fn>)         # off the event loop ✓
      → httpx.Client GET/POST http://127.0.0.1:8209  (X-Auth FamitCall2026, timeout=12s)
        → caller.py reads var/*.json, returns JSON
```
This path is structurally fine. The tools are read-only, non-blocking, and fast.

### 1.2 Root cause #1 — required-vs-optional schema mismatch (`check_leads`)
`check_leads(self, context, campaign: str = "")` is **optional in Python** (has a default). But the JSON schema LiveKit emits to Groq does **not** mark `campaign` as having a default / being skippable in a way Groq's tool validator accepts, so when llama-4-scout (a small model at temp 0.3) emits `check_leads({})` — the natural call for "how many hot leads", where no campaign was named — Groq **rejects** it: `missing properties: 'campaign'`. The model did the *right* conversational thing; the schema makes it illegal.

### 1.3 Root cause #2 — type mismatch (`run_campaign`)
The system prompt explicitly says: *"it is SAFE to pass numbers and yes/no as plain strings (count="5", confirmed="true")"*. But the emitted schema types `count` as **integer** and `confirmed` as **boolean**. So the model obeys the prompt, emits strings, and Groq rejects: `expected boolean, but got string`. The prompt and the schema **contradict each other** → guaranteed failure on the risky dial path.

### 1.4 Root cause #3 — retry semantics turn a 4xx into a stall
A schema-validation failure is a **permanent 4xx** (the same input will always fail), but it is surfaced as `APIConnectionError(retryable=True)`. LiveKit then retries with backoff, **re-sending the entire prompt** each time (more tokens, more time), and only gives up after the backoff budget — producing the long pause and then *no answer at all*. A permanent client error should **fail fast and self-repair**, never retry blindly.

### 1.5 Why the founder heard "I have to call the check-leads tool"
With the tool result never returning, the model's *narration* of its intent ("let me check the leads…") is the only thing that reaches TTS before the turn dies — so he hears the agent *announce* the tool but never *deliver* the answer.

### 1.6 Contributing factors (secondary, real)
- **Telephony network tax:** SIP/PSTN adds ~600 ms+ vs WebRTC's ~100 ms (see §2). Even a perfect pipeline is ~900 ms–1 s on a phone call. Budget accordingly.
- **No filler speech during tool calls:** even when tools succeed, there is no "let me pull that up" played *while* the round-trip happens, so any real fetch time is perceived as silence.
- **No warm cache / precompute:** every read re-fetches from `caller.py` → JSON files on each turn; fine at this scale, but it scales poorly and offers no instant-answer path.
- **Cold connections:** a fresh `httpx.Client` is created per call (`with _client()`), so no connection pooling/keep-alive to the loopback.

---

## 2. The latency budget (research-grounded) — target per stage

Humans perceive **>300–500 ms** of dead air as unnatural; **>1.5 s** and the caller has mentally checked out. The metric that matters is **Time-To-First-Audio (TTFA)** = end-of-user-speech → first TTS byte. It decomposes as:

| Stage | What it is | WebRTC target | Notes / our stack |
|---|---|---|---|
| VAD + audio capture | detect speech start/stop | ~50 ms | silero VAD ✓ |
| **Turn detection / endpointing** | decide the user is *done* | **150–250 ms** | **biggest hidden cost.** Default settings on Vapi/others add **1.5 s+**. We use semantic Multilingual turn-detector + `min_endpointing_delay=0.25` ✓ |
| STT transcription | audio → text | 80–150 ms | Sarvam saarika:v2.5. AssemblyAI hit **90 ms** with formatting disabled |
| **LLM TTFT** | prompt → first token | **200–400 ms** | Groq llama-4 = **~200 ms** (proven by AssemblyAI on Maverick-17B). **Target sub-500 ms TTFT** |
| Tool / data fetch | function call round-trip | **<100–300 ms** | our loopback is <50 ms when it *works*; the bug makes it ∞ |
| **TTS TTFB** | text → first audio byte | **60–150 ms** | ElevenLabs Flash v2.5 = **~75 ms** ✓ (set streaming-latency = 4) |
| Network transport | round-trip | WebRTC ~100 ms / **telephony ~600 ms+** | we are on SIP → assume the higher tax |

**Reference end-to-end (AssemblyAI/Vapi, web deployment):** STT 90 + LLM 200 + TTS 75 = **365 ms pipeline** + 100 ms WebRTC ≈ **465 ms**. The same stack on **telephony ≈ 965 ms+**. 

**Our realistic target:** **<1.2 s TTFA on a phone call** for a cached/simple answer, **<1.8 s** when a real tool fetch is needed (masked by filler speech). The two places latency actually hides: **turn-taking and LLM TTFT** — *not* STT/TTS, and *not* (at our data scale) the database.

---

## 3. What data belongs where (the core architecture question)

The founder's question — what goes in the system prompt vs Redis vs Postgres vs per-session memory — answered as a layered model. Principle: **the closer to the model and the more static the fact, the cheaper to serve; the more volatile/large, the further out it lives behind a cache.**

### Layer 0 — STATIC facts → SYSTEM PROMPT (0 ms, free)
Things that never change within a call and rarely between calls. They cost only input tokens (and those can be **prompt-cached**, §6). Put here:
- Agent identity, persona, language policy, company name.
- The **list of tools and exactly how/when to call each** (this is where good tool descriptions live — they materially reduce wrong/empty calls).
- Hard business rules (PIN gate, "never hallucinate", risk-confirm flow).
- **NOT** live numbers (lead counts, balances) — those go-stale and must never be hallucinated. Keep them out of the prompt; fetch via tool.

> **Keep the prompt lean.** Larger prompts = more input tokens = higher TTFT. Our manager prompt inlines 8 verbose tool blurbs (~2 KB). That is acceptable but should be trimmed to the essential trigger phrases; move long examples out.

### Layer 1 — HOT, frequently-read, derived data → REDIS (sub-ms, warm)
Counts, short lists, "recent N", per-tenant rollups, resolved campaign list. These are **read on almost every manager call** and are **cheap to precompute**. Redis gives **<1 ms** reads. Strategy:
- **Precompute on write** (cache-on-write / CQRS read-model): when a lead is added/scored or a call completes, update a denormalized Redis hash `aim:counts:{tenant}` = `{total, hot, warm, cold, campaigns, calls_today, balance_minor}`. Reads become a single `HGETALL` — no scanning JSON, no `COUNT(*)`.
- **TTL + invalidate-on-write:** TTL 30–60 s as a safety net; explicit invalidation on the write path for freshness.
- **Warm at session start:** when a manager call connects and PIN-verifies, fire **one** background prefetch that loads that tenant's hot blob into the agent's session state, so the first "how many leads" answers from memory instantly (see §4).

### Layer 2 — DURABLE source of truth → POSTGRES (10–100 ms, authoritative)
The system of record. Today the AI-Manager reads `var/*.json` via `caller.py`; that is the durable store at current scale and is fine. As volume grows, the counts/lists should be **materialized** (a `materialized view` or a denormalized `tenant_counts` table refreshed on write) so even a cache-miss read is a single indexed row, never a full scan. Postgres + pgvector hits **sub-100 ms** at 99% recall, so it is a viable RAG store too (§5). Rule: **never run an unbounded `COUNT`/scan on the hot path** — pre-aggregate.

### Layer 3 — PER-SESSION / PER-CALLER memory → in-process + small JSON/Redis (loaded once)
Short-term: the conversation transcript + slots (which campaign we're discussing, PIN-verified flag, resolved audience) — held **in process** for the call, never re-fetched. Long-term: per-caller recap (`var/memory/{phone}.json`, already present) loaded **once at call start**, not per turn. This is exactly what production agents do: short-term context in memory, long-term in a fast store, **retrieved once and carried**, not re-derived every turn.

### Summary table

| Data | Where | Latency | Refresh |
|---|---|---|---|
| Persona, tools, rules, language policy | System prompt (prompt-cached) | 0 ms | static / on deploy |
| Lead counts, recent-N, campaign list, balance | **Redis hot blob** (precomputed) | <1 ms | cache-on-write + 30–60s TTL |
| Full lead/call/campaign rows, audit, money | Postgres / `var/*.json` (materialized counts) | 10–100 ms | source of truth |
| Conversation slots, PIN flag, resolved audience | In-process session state | 0 ms | per call |
| Per-caller recap / preferences | `var/memory/{phone}.json` (load once) | one read at start | per call |
| KB / product docs (semantic) | pgvector, prefetched (§5) | <100 ms cold / <5 ms cached | corpus updates |

---

## 4. Caching + precompute patterns (the fast-fix toolkit)

1. **Cache-on-write read model (CQRS-lite).** Maintain a per-tenant denormalized counts blob updated **when data changes**, not when it's read. Reads collapse to one `HGETALL`/one indexed row. This is the single highest-leverage data change.
2. **Warm the cache at session start.** On call-connect + PIN-verify, kick **one** async prefetch of the tenant hot blob into session state. The first data question then answers from memory in <5 ms. (PolyAI/contact-center pattern: connect to systems and pre-load customer context as part of session setup.)
3. **Materialized counts in Postgres** as the miss-path: a `materialized view` / denormalized table so even a cold read is one row, never a scan. Refresh on write or on a short schedule.
4. **Short TTL + explicit invalidation.** TTL (30–60 s) bounds staleness; the write path invalidates immediately so a just-added lead is reflected.
5. **Semantic / response cache for repeated questions.** "How many leads" asked twice in a call → serve the second from cache (~50 ms vs a full LLM+tool run). Self-hosted semantic cache answers in ~50 ms.
6. **Connection reuse.** Keep a **persistent `httpx` client / keep-alive** to the loopback (and a pooled PG connection) instead of opening a fresh client per call — removes TCP/handshake cost from every tool call.

---

## 5. Making tool/function calls fast

This is where our bug lives and where the biggest wins are.

1. **Fix the schema so tools never get rejected (Track A — do first):**
   - Make optional args **truly optional in the emitted schema** (don't require `campaign`); or give them a sentinel the model can always supply.
   - **Match the prompt to the schema:** if the prompt says "pass strings", type the args as `string` and coerce server-side (the code already has `_to_int`); OR change the prompt to pass native types. Today they contradict → guaranteed failure. Prefer **string args + server coercion** for small models — it is the most forgiving.
   - **Do not retry schema-validation (4xx) as a connection error.** Fail fast; on a tool-arg validation failure, **inject a corrective system turn** ("call check_leads with no arguments") or auto-default the missing arg and re-run **once**, rather than 3 blind retries that re-send the full prompt.
2. **Play filler / "thinking" speech during the tool round-trip.** LiveKit supports notifying the user and playing a thinking sound while a tool runs. "Let me pull that up…" makes any real fetch feel instant. **High impact, low effort.**
3. **Parallelize + consolidate tool calls.** Groq supports **parallel tool calls**; LiveKit caps with `max_tool_steps`. Consolidate multi-fetch answers into one tool that returns the whole hot blob (counts + campaigns + balance) so a broad question is **one** round-trip, not three.
4. **In-process vs HTTP loopback.** The loopback to `caller.py` is convenient and currently <50 ms, but it is still a network hop + JSON serialize + fresh client. For the hottest reads (counts/lists), prefer **reading the warmed session blob directly in-process**; reserve HTTP for writes/actions (`/run`).
5. **Keep `max_tokens` small for voice (150–200).** Already at 140 ✓ — short replies = lower generation time and snappier TTS start.
6. **Cap tool count and keep descriptions tight.** Fewer, clearly-described tools → the small model picks correctly and emits valid args more often. Eight tools is borderline for a 17B model; group the read tools.

---

## 6. RAG retrieval latency (kb/core.py, currently empty corpus)

RAG is **not** on the current manager hot path (the `kb` pgvector+FTS corpus is empty), but when product/FAQ knowledge is added for the customer-sales mode it must not blow the budget. A naive vector query adds **50–300 ms** — alone that breaks a 200 ms conversational budget. Patterns:
1. **Precompute embeddings; never embed at query time** for known corpus — similarity search becomes a lookup against an indexed store, not a fresh compute.
2. **Small k (2–3).** Start there; raise only if answer quality needs it. Each extra chunk is tokens + latency.
3. **pgvector is fine** — sub-100 ms at 99% recall — so no new vector DB needed; reuse Postgres.
4. **Prefetch at session start / speculatively per-turn.** The state-of-the-art (Salesforce VoiceAgentRAG, 2026) runs a background "slow thinker" that predicts likely topics and pre-fetches chunks into an in-memory cache the foreground "fast talker" reads at **~0.35 ms**, cutting retrieval latency up to **316×**. Practical version for us: when the campaign is resolved at call start, **prefetch that campaign's KB chunks into session memory once**, then read locally.
5. **In-memory cache for hot chunks:** frequently-asked context served from memory at **<5 ms**.

---

## 7. Realtime-LLM tool-calling tricks (Groq specifically)

- **Service tier `performance`** for latency-sensitive calls (prioritized) vs `flex` (throughput). Use `performance` for the voice path.
- **Prompt caching:** keep the large static prefix (persona + tool defs + rules) **stable and first** so the provider can cache the prefix and only bill/process the variable suffix → lower TTFT on every turn. Don't reshuffle the prompt per turn.
- **Constrained decoding / strict structured outputs** *guarantee* schema-valid JSON — but Groq notes **streaming + tool use are not supported with Structured Outputs**, so for the streaming voice path the right move is **forgiving schemas + server-side coercion + fail-fast-and-repair**, not strict mode.
- **Keep the model small & fast** (llama-4-scout/maverick-17B at ~200 ms TTFT is already the right class). Don't swap to a bigger reasoning model on the hot path.
- **Speculative / preemptive generation** (already on) starts the reply from the partial transcript; good — but ensure tool-call turns don't get double-fired.
- **Parallel SLM+LLM:** a small fast model can handle the trivial/most-common intents (counts, yes/no) while the larger model handles open dialog, reducing average latency.

---

## 8. Recommended target architecture (for a later build wave)

```
                         ┌──────────────────────────────────────────┐
   PSTN/SIP ──► LiveKit ──┤ AgentSession (Sarvam STT · Groq llama-4 · │
                          │  ElevenLabs Flash TTS · semantic turn-det) │
                          │  preemptive_generation, max_tokens≈160     │
                          └───────────────┬──────────────────────────┘
                                          │ @function_tool (FORGIVING schema:
                                          │  string args, optional truly optional,
                                          │  fail-fast no-retry on 4xx, +filler speech)
                          ┌───────────────▼───────────────┐
   call connect ─► WARM ─►│  SESSION STATE (in-process)     │  ◄─ counts/campaigns/balance
   + PIN verify           │  counts · campaign list · recap │     read here = 0 ms
                          └───────────────┬─────────────────┘
                                 miss / write │
                          ┌───────────────────▼───────────────┐
                          │  REDIS hot blob  aim:counts:{tenant}│  <1 ms, cache-on-write + TTL
                          └───────────────────┬───────────────┘
                                 miss          │  invalidate on write
                          ┌───────────────────▼───────────────┐
                          │  POSTGRES / var/*.json (durable)    │  materialized counts, no scans
                          │  + pgvector KB (prefetched, k=2-3)  │
                          └─────────────────────────────────────┘
   Writes/actions (/run dial) ───────────────► caller.py:8209 (keep-alive httpx)
```

**Build order (each a small verifiable unit, for the wave that owns the file):**
1. **Track A — schema fix (kills the silences):** make tool args forgiving (string + coerce; optional truly optional); stop retrying schema 4xx as connection errors; auto-repair/auto-default once. *Verify:* the 48+28 daily schema errors drop to ~0 in journald; "how many hot leads" answers every time.
2. **Filler speech** on every tool call ("let me pull that up"). *Verify:* no silent gap during fetch.
3. **Persistent httpx keep-alive + pooled PG.** *Verify:* tool round-trip time in metrics drops.
4. **Redis hot blob + cache-on-write + warm-at-session-start.** *Verify:* first data Q answers <5 ms from session state.
5. **Materialized counts in Postgres** as miss path. *Verify:* no scan on hot path.
6. **(Later) KB prefetch at session start, k=2–3** for customer mode. *Verify:* RAG turn <1.8 s.

---

## 9. Sources

- [LiveKit — Understand and Improve Agent Latency](https://livekit.com/blog/understand-and-improve-agent-latency)
- [LiveKit — Agent speech and audio (filler/thinking, tools)](https://docs.livekit.io/agents/build/audio/)
- [AssemblyAI — Lowest-latency voice agent in Vapi (~465 ms breakdown)](https://www.assemblyai.com/blog/how-to-build-lowest-latency-voice-agent-vapi)
- [Vapi — Speech Latency: sub-500 ms guide](https://vapi.ai/blog/speech-latency)
- [Retell — How real-time voice AI works (STT→LLM→TTS)](https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts)
- [Sayna — Sub-second voice agent latency architecture](https://sayna.ai/blog/sub-second-voice-agent-latency-practical-architecture-guide)
- [Prodinit — Production voice AI sub-300 ms architecture](https://www.prodinit.com/blog/production-voice-ai-agents-latency-architecture)
- [Twilio — Core latency in AI voice agents](https://www.twilio.com/en-us/blog/developers/best-practices/guide-core-latency-ai-voice-agents)
- [Smallest.ai — Designing voice assistants: latency budget](https://smallest.ai/blog/designing-voice-assistants-stt-llm-tts-tools-and-latency-budget)
- [Groq — Tool use](https://console.groq.com/docs/tool-use) · [Structured outputs](https://console.groq.com/docs/structured-outputs) · [Optimizing latency](https://console.groq.com/docs/production-readiness/optimizing-latency)
- [Redis — Build AI agents with memory management](https://redis.io/blog/build-smarter-ai-agents-manage-short-term-and-long-term-memory-with-redis/) · [Prompt vs semantic caching](https://redis.io/blog/prompt-caching-vs-semantic-caching/) · [Context retrieval for AI agents](https://redis.io/blog/context-retrieval-for-ai-agents/)
- [Salesforce VoiceAgentRAG — dual-agent router cuts voice RAG latency 316×](https://www.marktechpost.com/2026/03/30/salesforce-ai-research-releases-voiceagentrag-a-dual-agent-memory-router-that-cuts-voice-rag-retrieval-latency-by-316x/) · [arXiv](https://arxiv.org/html/2603.02206v2)
- [Medium — Lessons implementing RAG in a real-time voice agent (LiveKit)](https://medium.com/@jorge.jarne/lessons-from-implementing-rag-in-a-real-time-voice-agent-livekit-43f0689bf565)
- [Microsoft — CQRS pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs) · [Materialized View pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/materialized-view)
- [PolyAI — context-aware voice agents: latency & knowledge bases](https://dev.to/surrealdb/polyai-on-building-context-aware-voice-agents-latency-knowledge-bases-and-what-actually-ships-1pk8)
- [WebRTC.ventures — Reducing voice agent latency with parallel SLMs and LLMs](https://webrtc.ventures/2025/06/reducing-voice-agent-latency-with-parallel-slms-and-llms/)
