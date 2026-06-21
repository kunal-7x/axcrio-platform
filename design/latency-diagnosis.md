# AI Manager Inbound Voice — Latency Diagnosis (DIAGNOSE-1)

**Date:** 2026-06-12 · **Mode:** READ-ONLY (no box mutation, no deploy, no git) ·
**Box:** `famit@168.144.153.145` (famit-livekit) · **Service:** `aim-voice-agent.service`
**Files:** `/opt/famit-agent/aim_voice_agent.py` · `/opt/famit-agent/ai_manager/voice_tools.py` ·
`/opt/famit-agent/caller.py` (:8209) · LiveKit Agents 1.5.17 in `/opt/capsy-agent/.venv`

> NOTE: Wave #5 (customer mode) is live-editing `aim_voice_agent.py` / `voice_tools.py` right now.
> This document is diagnosis + measurement only; it prescribes nothing destructive and touched nothing.

---

## TL;DR — the 3–5 minute silence is NOT the data layer

The founder's symptom ("how many hot leads" → Riya silent for minutes → "I have to call the
check-leads tool") is caused by an **LLM tool-call schema-validation retry storm**, not slow
retrieval. Every data route is **5–15 ms**. Raw Groq is **0.31 s**. The minutes are burned in
LiveKit's inference retry loop re-submitting a tool call that **Groq's strict server-side
validator keeps rejecting**, because the LLM (llama-4-scout) emits the call with a missing/
mistyped argument. The turn can never complete, so Riya stays silent until the TTS websocket
finally dies.

**Root cause (one line):** `strict_tool_schema=True` (hardcoded in the LiveKit Groq plugin) +
tool params the small LLM gets wrong (omits `campaign`, sends `count`/`confirmed` as strings)
= server-side `APIError` mid-stream → retry storm → multi-minute dead air.

---

## MEASURED EVIDENCE (all numbers real, collected this session)

### (a) HTTP tool calls → caller.py routes — FAST, not the bottleneck
`time curl` on loopback `:8209` with `X-Auth: FamitCall2026`:

| Route | HTTP | time_total | size |
|---|---|---|---|
| `/leads` | 200 | **0.0059 s** | 1322 B |
| `/campaigns` | 200 | **0.0068 s** | 1663 B |
| `/stats` | 200 | **0.0090 s** | 328 B |
| `/analytics` | 200 | **0.0054 s** | 337 B |
| `/wallet` | 200 | **0.0150 s** | 159 B |
| `/calls?limit=5` | 200 | **0.0059 s** | 2209 B |
| `/calls?limit=1000` | 200 | **0.0061 s** | 57954 B |

Even the 58 KB `/calls?limit=1000` (used by `resolve_contact_by_phone`, voice_tools.py:388)
returns in 6 ms. No route does seconds/minutes of O(n) work or blocks. **Data retrieval is innocent.**

### (b) LLM round-trip (Groq llama-4-scout) — fast in isolation, fatal under strict tools
- Raw `chat/completions` (simple prompt) from the box: **HTTP 200 in 0.313 s.**
- BUT with tools attached, Groq runs **`strict_tool_schema=True`** (hardcoded —
  `livekit/plugins/groq/llm.py:345`). Strict mode = the model is constrained to the JSON schema,
  and any tool call that violates it is **rejected server-side mid-stream** as
  `openai.APIError: tool call validation failed`.
- The LiveKit inference layer (`inference/llm.py:431`) catches that mid-stream APIError and
  re-raises it as `APIConnectionError(retryable=...)`. The voice generation loop
  (`llm/llm.py:215`) then retries up to `max_retry+1 = 4` attempts (`types.py:76`,
  `retry_interval=2.0`) — and because the *same* user turn re-prompts the *same* broken call,
  every attempt fails identically. The turn dies with `recoverable=False` and produces **no speech**.

**Schema-rejection volume (last 24h on this box):** `journalctl | grep -c 'did not match schema'`
= **57**. Breakdown:
```
48 × check_leads  : missing properties: 'campaign'
24 × run_campaign : /confirmed expected boolean got string, /count expected integer got string
 4 × run_campaign : /count expected integer got string, /confirmed expected boolean got string
```

### (c) STT / turn-detection / endpointing — secondary, adds up to ~2 s, not minutes
`AgentSession` (aim_voice_agent.py:995) config:
- `min_endpointing_delay=0.25`, `max_endpointing_delay` defaults to **1.8 s** when the semantic
  `MultilingualModel` loads (`_max_ep_default="1.8"`). `MIN_EP_DELAY`/`MAX_EP_DELAY`/`TURN_DETECTION`
  are **not set in `.env`**, so the 1.8 s semantic ceiling is in force.
- `preemptive_generation=True` (good), but it's wasted: the preemptive generation IS the call
  that gets schema-rejected, so it buys nothing on these turns.
- LiveKit warns these kwargs are **deprecated in v2.0** (`turn_handling=TurnHandlingOptions(...)`),
  cosmetic for now.
- Net: end-of-turn endpointing costs ≤ ~1.8 s. Real but an order of magnitude below the symptom.

### (d) Second fetch / huge payload the LLM slowly reads — minor
- `lead_counts()` (voice_tools.py:202–218) returns the **entire `leads` list** inside the payload
  (`"leads": leads`, line 216) in addition to the summary string. The tool *function return* to the
  LLM is only `res.get("summary")` (aim_voice_agent.py:364), so the big list is dropped before the
  model sees it — **not** a payload bloat into the LLM. Good. (Worth trimming the dict anyway.)
- `resolve_contact_by_phone` pulls `/calls?limit=1000` (58 KB) and linear-scans it — 6 ms, fine
  at current volume, but O(n) and will degrade as call history grows.

---

## THE ACTUAL SLOW-TURN TIMELINE (one real episode, `journalctl -o short-precise`)

Job `AJ_wuuGFtxQZHfS`, room `RM_yrRQMxE39mL9` — a single "how many leads" turn:

```
09:31:26.37  APIError: check_leads missing 'campaign'  → APIConnectionError(retryable=False)  → recoverable=False
09:31:28.70  same schema rejection again (next attempt) → recoverable=False
   …(dead air; founder repeats himself)…
09:32:41.37  retry attempt 1  "retrying in 0.1s"
09:32:41.91  retry attempt 2  "retrying in 2.0s"
09:32:44.55  retry attempt 3  "retrying in 2.0s"
09:32:46.68  attempts exhausted → APIError check_leads missing 'campaign' → recoverable=False
09:32:54.39  LLMError recoverable=False (Groq)
09:33:15.23  ElevenLabs websocket closed unexpectedly (status 1006) — TTS link dies after the dead turn
```

≈ **1 min 49 s of continuous failure for one turn**, and the founder hits it repeatedly:
distinct slow episodes **today alone**: 08:21, 08:37–08:40, 09:28–09:32 (multiple per call).
Stacked back-to-back across his repeats, this is exactly the "3–5 minutes of silence" he reports.

---

## RANKED BOTTLENECK LIST (12 lines, with measured times)

1. **[DOMINANT] Strict-schema tool-call rejection retry storm** — Groq `strict_tool_schema=True`
   rejects calls with missing/mistyped args → LiveKit retries 4× then aborts with no speech.
   **Cost: 1m49s+ per affected turn; 57 hits/24h.** This IS the 3–5 min silence.
2. **`check_leads` arg the LLM omits** — model calls it without `campaign` (48× in 24h). The arg is
   *optional in current source* (`campaign: str = ""`) yet strict-validation still demands the
   *property key be present*; small LLM drops it. **Cost: triggers #1.**
3. **`run_campaign` type coercion at the wire** — LLM sends `count`/`confirmed` as strings; strict
   schema wants int/bool (28× in 24h). Server rejects before the Python `_to_int`/`_to_bool` ever runs.
   **Cost: triggers #1 on dial turns.**
4. **Retry config makes it worse, not better** — `max_retry=3`, `retry_interval=2.0s`: 4 doomed
   attempts on a deterministic failure = ~6–8 s of pure backoff per cluster, repeated. **Cost: ~6–8 s × N.**
5. **No fast-path / fallback when the tool call fails** — the agent has no "answer from cache or say
   a holding phrase" path; it just goes silent until exhaustion. **Cost: full dead-air exposure.**
6. **Semantic turn-detection `max_endpointing_delay=1.8s`** (unset in `.env`, defaults high). **Cost: ≤1.8 s/turn.**
7. **`preemptive_generation` wasted on these turns** — the speculative gen is the call that fails. **Cost: 0 benefit when #1 fires.**
8. **ElevenLabs WS death after a dead turn** (status 1006) forces a TTS reconnect on recovery. **Cost: ~seconds on next turn.**
9. **`resolve_contact_by_phone` does `/calls?limit=1000` + O(n) scan** — 6 ms now, scales with history. **Cost: 0.006 s now, grows.**
10. **No hot cache / precompute for counts** — every "how many leads/campaigns" re-reads JSON via HTTP
    (cheap today at ~6 ms, but recomputed per turn; nothing memoised). **Cost: ~0.006 s now.**
11. **STT first-connect** (historically ~30 s blocking, already mitigated by the OWN rebuild to plain
    AgentSession per file header) — not seen in current journals. **Cost: 0 now (fixed).**
12. **Groq raw latency** — **0.31 s**, well within budget; NOT a bottleneck. (Listed to close it out.)

---

## WHY IT'S INTERMITTENT (and why it "eventually answers")

The small `llama-4-scout` model is non-deterministic at `temperature=0.3`. On a *good* sample it
emits `check_leads` with the `campaign` key present (even empty) and correct types → the call
passes strict validation → answer in ~1–2 s. On a *bad* sample it drops the key or stringifies a
number → strict reject → retry storm → silence. The founder's repeats eventually land a good
sample, which is why "she eventually answers." This is a **reliability-of-tool-emission** problem,
not a throughput problem.

## FIX DIRECTION (for the architecture wave — NOT applied here)

- Make the tool surface **impossible to get wrong**: either (a) turn OFF strict tool schema for this
  agent, or (b) give `check_leads`/`analytics`/`wallet_status` **zero parameters** (drop `campaign`
  entirely — the counts are tenant-wide anyway), and keep every numeric/bool arg as `string` types
  the Python side coerces (already done for `run_campaign` in source, but strict validation rejects
  before coercion — so the schema itself must declare `string`).
- Add a **retry-budget cap + spoken fallback**: on tool-call failure, say a 1-line holding phrase and
  answer from a precomputed snapshot, never go silent.
- Lower `max_endpointing_delay` to ~0.5 s and pin `MIN_EP_DELAY`/`MAX_EP_DELAY` in `.env`.
- Precompute lead/campaign counts into a **Redis hot snapshot** so the answer needs no tool call at
  all for the most common questions (covered in the retrieval-architecture design wave).

---

## REPRO COMMANDS (read-only, for re-verification)
```bash
# route timings
for p in /leads /campaigns /stats /analytics /wallet '/calls?limit=1000'; do
  curl -s -o /dev/null -w "$p %{http_code} %{time_total}s %{size_download}B\n" \
    -H 'X-Auth: FamitCall2026' "http://127.0.0.1:8209$p"; done
# raw groq
curl -s -o /dev/null -w "%{time_total}s\n" https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer $GROQ_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"meta-llama/llama-4-scout-17b-16e-instruct","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":20}'
# schema-rejection census
sudo journalctl -u aim-voice-agent.service --since '24 hours ago' | grep -c 'did not match schema'
sudo journalctl -u aim-voice-agent.service --since '24 hours ago' \
  | grep -oE 'tool [a-z_]+ did not match schema: errors: \[[^]]*\]' | sort | uniq -c | sort -rn
```
