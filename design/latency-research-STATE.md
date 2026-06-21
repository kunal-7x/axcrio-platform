# latency-research wave — STATE

TASK: diagnose + research + architect low-latency data/response pipeline for inbound AI Manager voice agent.
READ-ONLY. Write only docs under caps/design/. DO NOT touch aim_voice_agent.py (wave #5 editing it).

## Plan
1. [DONE] SSH diagnose box (read-only). ROOT CAUSE = tool-schema rejection retry storm, NOT data latency.
2. [DONE] Deep web research (LiveKit, AssemblyAI/Vapi, Groq, Redis, CQRS, VoiceAgentRAG, PolyAI).
3. [DONE] Wrote design/latency-research.md (full report, 9 sections + sources).
4. [DONE] 16-line summary returned.

## Findings (append as we go)

### ROOT CAUSE (CONFIRMED via journald, NOT data latency)
- Data files are TINY (leads.json 4K, calls.json 76K). Tools use asyncio.to_thread + loopback HTTP — fast. Data retrieval is NOT the bottleneck.
- REAL CAUSE: Groq server-side TOOL-SCHEMA VALIDATION rejects the LLM's tool calls:
  - 48x/24h: `tool check_leads did not match schema: missing properties: 'campaign'` (the exact "how many hot leads" symptom)
  - 28x/24h: `tool run_campaign ... /confirmed expected boolean but got string, /count expected integer but got string`
- The rejection surfaces as openai.APIError -> wrapped APIConnectionError(retryable=True) -> LiveKit retries 0.1s/2s/2s, each retry re-sends full prompt, model re-omits arg, same fail -> recoverable=False -> _llm_inference_task DIES -> NO speech output = DEAD AIR. Founder repeats -> new turn -> new retry storm -> minutes of silence. ElevenLabs WS also dies (1006) after.
- check_leads python sig is `campaign: str = ""` (optional) but the emitted JSON schema marks it required (llama-4-scout strict validation). run_campaign: prompt tells model to pass strings ("true","5") but schema types are bool/int -> guaranteed reject.
- Model: llama-4-scout-17b, temp 0.3, max_tokens 140. Plain AgentSession, preemptive_generation=True, min_ep 0.25.
- FIXES (for the design doc, handed to a build wave — NOT done here): make tool args truly optional & string-typed in schema (or coerce), don't mark APIError schema-fails as retryable, add a tool-call fallback/repair, filler speech while tool runs, warm-cache counts.

### Box facts
- aim-voice-agent.service (livekit agent_name=manager). Redis: livekit-redis :6379 (NOAUTH from us), app redis :6380 (localhost). Postgres on box. kb/core.py pgvector+FTS corpus EMPTY (RAG not in this path).
- System prompt ~ large manager prompt (~2KB) listing 8 tools inline.
