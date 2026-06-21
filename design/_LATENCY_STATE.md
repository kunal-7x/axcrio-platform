# LATENCY ARCHITECTURE — diagnosis+research+design (READ-ONLY)

Goal: diagnose 3-5min stall on AI Manager inbound voice; design <1-2s pipeline; write design/LATENCY-ARCHITECTURE.md
Constraints: READ-ONLY box (168.144.153.145, famit user). No mutation/deploy/git. Wave #5 editing aim_voice_agent/inbound_agent.py — DO NOT TOUCH.

## Plan — ALL DONE
- [x] P1-P4: pulled agent/tools/caller routes, measured backend (4-6ms), found schema storm in log
- [x] P5: architecture synthesized (what-goes-where: prompt/redis/pg/session/kb)
- [x] P6: design/LATENCY-ARCHITECTURE.md written + 2 mermaid diagrams validated (balanced, valid headers)

## Findings (append) — DIAGNOSIS COMPLETE
- LIVE agent = aim_voice_agent.py (PID running `start`, agent_name=manager, unit aim-voice-agent :8091). inbound_agent.py is legacy/separate.
- ROOT CAUSE (MEASURED, smoking gun): Groq llama-4-scout emits check_leads/run_campaign tool calls WITHOUT the optional defaulted arg (campaign=""); Groq strict tool-validator REJECTS: "tool call validation failed: parameters for tool check_leads did not match schema: errors: [missing properties: 'campaign']". LiveKit wraps as retryable APIConnectionError -> retries 2s,2s -> unrecoverable -> re-attempts whole turn -> MINUTES of silence. 76 such errors in last 2000 log lines (48 check_leads, 28 run_campaign). ElevenLabs WS 1006 drops during stall.
- NOT the data layer: GET /leads /campaigns /stats on loopback = 4-6ms. leads.json 1.7K (6 leads), 11 campaigns, calls.json 73K. Disk reads are trivially fast.
- Secondary: voice_tools opens NEW httpx.Client() per call (no pool), sync blocking; resolve_campaign does an extra list_campaigns() GET; 12s timeout. Minor vs the schema loop but real.
- app redis :6380 = rate-limit only (rl:ip:*), NOT data cache. livekit redis :6379 auth. kb corpus EMPTY (no PG kb tables). memory = var/memory/<digits>.json per person.
- endpointing: MIN_EP 0.25, MAX_EP 0.45(vad)/1.8(semantic), preemptive_generation=True. Not the main issue.
DOC WRITTEN: design/LATENCY-ARCHITECTURE.md
