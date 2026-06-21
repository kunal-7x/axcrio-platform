# AI Manager — Current Data Layout & Access-Cost Map (DIAGNOSE-3)

**Status:** READ-ONLY diagnosis, 2026-06-12. Box `famit@168.144.153.145` (`famit-livekit`), app root `/opt/famit-agent`.
**Scope:** Map exactly where AI-Manager-relevant data lives today, its per-request access cost, and the fast-storage recommendation. No box mutation. `voice_tools.py` is being actively edited by Wave #5 (customer mode) — observed, not touched.

---

## ⚠️ HEADLINE FINDING — the 3–5 minute silence is NOT a data-latency problem

The founder's symptom ("how many hot leads / how many campaigns" → Riya silent 3–5 min → "I have to call the check-leads tool" → eventually answers) is **NOT** caused by slow data retrieval. Measured live on the box:

| Loopback endpoint (caller.py:8209, X-Auth) | Measured latency |
|---|---|
| `/leads` | **4.5 ms** |
| `/campaigns` | **5.8 ms** |
| `/stats` | **7.1 ms** |
| `/calls?limit=5` | **5.5 ms** |
| `/wallet` | **9.3 ms** |

Data volumes are tiny: **6 leads, 141 calls, 8–11 campaigns.** The retrieval path is already millisecond-fast and is correctly offloaded off the event loop (every voice tool uses `await asyncio.to_thread(_vt.<fn>, ...)`). **A Redis/precompute cache would shave ~5 ms off a 180,000 ms stall — it does not fix the bug.**

### Real root cause (from live `journalctl -u aim-voice-agent.service`)
```
openai.APIError: tool call validation failed: parameters for tool check_leads
  did not match schema: errors: [missing properties: 'campaign']
→ livekit.agents._exceptions.APIConnectionError: Connection error. (retryable=False)
→ LLMError(... label='livekit.plugins.groq...LLM', recoverable=False)
→ ElevenLabs websocket connection closed unexpectedly (1006)
```
The Groq (OpenAI-compatible) endpoint **rejects the tool call** because the emitted JSON schema marks `campaign` as **required**, but the model (correctly, per the docstring "ALWAYS optional") calls `check_leads()` with no `campaign`. The hard `APIError` is wrapped as a non-retryable `APIConnectionError`, which stalls/loops the LiveKit LLM inference task and tears down the TTS websocket → multi-minute dead air, then a recovery cycle answers. `aim_voice_agent.py:1000` sets only `temperature=0.3`; no `tool_choice`/`parallel_tool_calls` override. `check_leads` is `async def ... campaign: str = ""` (a Python default → should be optional), so the required-flag is leaking from how the schema is generated/served — a **pipeline+schema bug, not a storage bug.** (Fix belongs to Wave #5, which owns this file — flagged, not touched.)

**Conclusion for the architecture wave:** the low-latency win is in the **voice/LLM control loop** (tool-schema correctness, single-shot tool calling, prompt/turn-detection tuning, LLM failover), and a hot-cache + precompute layer is the *secondary* hardening that makes the data side bulletproof at scale. Both are designed below; the cache is cheap and worth doing, but it is not the cure.

---

## 12-LINE DATA MAP (where each type lives · access cost · fast-storage recommendation)

1. **Campaigns** → `var/campaigns/*.json` (11 files, ~127 KB) **+** PG `campaigns` (8 rows). Per-request: full-dir read + JSON parse via `/campaigns`, ~6 ms. Cacheable. → **Redis hash `aim:{tenant}:campaigns` (TTL 60 s) + precomputed count key; PG `campaigns` is the durable source of truth.**
2. **Leads** → `var/leads.json` (1.7 KB, 6 rows) **+** PG `leads` (6 rows). Counts (hot/warm/cold) recomputed in Python per call (`lead_counts`), ~4.5 ms. Cacheable. → **Redis precomputed JSON `aim:{tenant}:lead_counts` (TTL 30–60 s), invalidate on lead write.**
3. **Calls** → `var/calls.json` (74 KB, 141 rows) **+** PG `calls` (142 rows). `/calls?limit=N` reads file, ~5.5 ms. Cacheable. → **Redis list/sorted-set `aim:{tenant}:recent_calls` (last 20, TTL 30 s); PG `calls` durable.**
4. **Analytics / stats** → computed on the fly by `/stats` from calls (total/answered/voicemail/#campaigns), ~7 ms. Also PG `daily_rollups`-style data in `var/daily_rollups.json`. → **Precompute nightly + on-write into Redis `aim:{tenant}:stats` (TTL 60 s); durable rollup table in PG.**
5. **Per-person memory** → `var/memory/*.json` (7 files, name/interest/last-seen per phone). Read once at call start via `resolve_contact_by_phone` (`to_thread`). Tiny, fine. → **Keep on disk now; mirror to Redis `aim:mem:{phone}` (TTL 1 h) + PG `ai_manager_profiles` (currently 0 rows) for durability.**
6. **KB / RAG corpus** → PG `kb_chunks=0`, `kb_documents=0`, `kb_sources=0` — **EMPTY**. `pgvector` extension **IS installed**. `kb/core.py` does pgvector + FTS hybrid. → **RAG should hold STATIC business knowledge** (how Famit works, plan/pricing/policy, FAQ, "what is a hot lead", playbook) — NOT live counts. Seed the corpus; it is dormant infrastructure today.
7. **Wallet / billing** → `var/billing.json`, `var/wallet*`, PG `wallet_accounts(2)/wallet_transactions(119)/wallet_holds(38)/billing(5)`. `/wallet` ~9 ms. → **Durable in PG (ACID, already there); Redis `aim:{tenant}:wallet` cache TTL 15–30 s for spoken balance.**
8. **System prompt (static identity/policy/tool-use rules)** → lives in `aim_voice_agent.py` instruction builders (7 `instructions` refs). Loaded into LLM context every turn. → **Stays STATIC in the prompt; keep it tight — bloated prompts raise first-token latency. Move volatile facts OUT of the prompt into tools/cache.**
9. **Redis (app, :6380)** → **EMPTY (dbsize=0), no password, currently UNUSED.** → **This is the hot-cache home. Fully available — adopt for all `aim:*` cache keys above.**
10. **Redis (:6379)** → LiveKit's own Redis, **password-protected (NOAUTH)** — reserved for LiveKit; do NOT repurpose for app cache.
11. **Postgres (`famit` DB, :5432)** → already the durable store: cost_ledger(435), events(346), usage_events(289), calls(142), wallet_transactions(119), contact_timeline(63), campaigns(8), leads(6), contacts(8), `ai_manager_*` tables **all empty (0)**. → **PG is the source of truth / write-through target; var/*.json should become a cache/export, not the primary store, at scale.**
12. **Session memory (live call state)** → `var/aim_sessions.jsonl`, `var/transcripts/*` (134 files), PG `ai_manager_sessions=0`/`session_turns=0` (empty). Per-call state held in-process. → **Per-session: in-process dict + Redis `aim:sess:{room}` (TTL = call) for crash-safe resume; persist turns to PG `ai_manager_session_turns` after the call.**

---

## WHAT SHOULD GO WHERE (the four-tier model the founder asked about)

- **System prompt (static, in-context every turn):** identity ("you are Riya, Famit's AI manager"), tone, PIN/security policy, the *rules* for when to call each tool, units/format for spoken numbers. Keep it lean — never put live counts here.
- **Redis (hot cache, ms reads, :6380 app instance — currently empty/available):** precomputed `lead_counts`, `recent_calls`, `stats`, `campaigns` summary + count, `wallet` balance, per-person memory mirror, per-session live state. Short TTL (15–60 s) + invalidate-on-write. This is the "fast retrieval" layer.
- **Postgres (durable source of truth):** leads, calls, campaigns, wallet/ledger, contact_timeline, `ai_manager_*` (sessions, turns, profiles, audit) — write-through; rollups/precompute jobs populate the cache.
- **RAG / pgvector (`kb_*`, currently empty, ext installed):** STATIC business knowledge & policy/FAQ/playbook for semantic Q&A — NOT live operational numbers (those are tool calls, not retrieval).

## Precompute / caching recommendation (data side — secondary to the LLM fix)
- A small **rollup worker** (or on-write hook) maintains `aim:{tenant}:{lead_counts,recent_calls,stats,campaigns,wallet}` in Redis :6380; tools read cache-first, fall through to caller.py loopback on miss. Invalidate the relevant key on every lead/call/campaign/wallet write.
- Counts become **O(1) key GET** instead of fetch-list-then-count-in-Python — irrelevant at 6 leads, meaningful at 100k.
- **But ship the tool-schema/single-shot-tool-call fix FIRST** — that is what removes the 3–5 minute silence.

---
*Companion: this file feeds the latency/architecture spec for the AI-Manager voice retrieval pipeline. The empty `ai_manager_*` PG tables + empty `kb_*` corpus + empty app-Redis are all dormant-but-ready infra — the design should activate them, not build new stores.*
