# GROQ 21-KEY ROTATION — PLAN (2026-06-20) — implement AFTER the voice fix is confirmed clean

## KEY FINDING — the smart system ALREADY EXISTS (just not wired into outbound)
`llm_router/` on the voice box already implements exactly what the founder asked for:
- `key_store.py` — encrypted, hot-reloadable key store (Fernet). The ~15 panel-added keys ALREADY live in `var/provider_keys.json.enc` (on box). Atomic writes bump mtime → mtime-cached reads reload live.
- `provider_pool.py` — SMART least-used pool: per-key 429 COOLDOWN (parses Retry-After), merges `.env` seed + store keys on every `pick()`, de-dupes by secret, health/pick-count snapshot.
- `pool_llm.py` — `PoolLLM` LiveKit LLM: on a 429 transparently RE-PICKS the next healthy key (caller never sees a 429), then falls through to the next provider.
- `caller.py:9400-9490` — super-admin CRUD `/admin/provider-keys` (GET/POST/PUT/DELETE + `/status`) the panel already calls.
- `famit-panel/app/super-admin/api-keys/page.tsx` — the "N in rotation / 6 from server config / live status dots" page, polling `/status` every 5s. Already built.
- WIRED into INBOUND (`aim_voice_agent.py:2455-2496` via `FallbackAdapter([PoolLLM(GROQ_POOL), ...])`). DELIBERATELY NOT wired into `agent.py` (outbound earner) — `grep llm_router agent.py` = empty.

## THE 2 BUGS (both confirmed, exact lines)
1. `agent.py:107` `_GROQ_CYCLE = itertools.cycle(_GROQ_KEYS)` is module-level → each forked LiveKit worker re-imports → starts at index 0 → ALL workers hammer key #1 (no real distribution; also consumed by 4 sites :910/:226/:383/:565).
2. `agent.py:98-106` `_collect_groq_keys()` reads ONLY `.env` `GROQ_API_KEY`+`_2..6` (6 keys) → never imports `key_store` → the ~15 panel keys never reach the earner.

## FIX = wire the existing `GROQ_POOL` into `agent.py`, behind an OFF-by-default flag (OFF = byte-behavior-identical to today)
- `agent.py:92-98` (new): guarded `try: from llm_router import GROQ_POOL; from llm_router.pool_llm import PoolLLM … except: fall through to legacy` (copy `aim_voice_agent.py:91-98`).
- `agent.py:907-940`: behind `EARNER_POOL_LLM=1` — build `groq.LLM(api_key="placeholder", <same model/temp/max_completion_tokens/freq_penalty as now>)` → `PoolLLM(GROQ_POOL, delegate)` → `FallbackAdapter`. Else the legacy `_next_groq_key()`/`groq.LLM(api_key=_call_groq_key)` path UNCHANGED. (Ref `aim_voice_agent.py:2455-2496`.)
- `agent.py:226/383/565` (3 raw httpx scout calls — opener/close/QA, off the TTS hot path): replace `_next_groq_key()`+manual cooldown with a `GROQ_POOL.pick()` retry helper (`mark_429`/`mark_ok`/`is_429`/`parse_retry_after` already exist).
- KEEP `_collect_groq_keys`/`_next_groq_key`/`mark_groq_key_cooling` as the OFF-path fallback (do NOT delete).
- NO backend/frontend change needed (CRUD + store + panel already built). Optional later: an agent `/agent-health` endpoint so the panel shows EARNER pick-counts (currently `/status` is caller.py-process-local — cosmetic, not a 429 risk).

## VOICE-SAFE + DEPLOY
- `PoolLLM` only swaps `delegate._client.api_key` per request + forwards chunks verbatim → STT(Sarvam)/TTS(ElevenLabs+VoiceSettings)/VAD/model/temp/max_tokens UNTOUCHED → voice BYTE-IDENTICAL. Do NOT change TTS/STT/session tuning in this change.
- OFFLINE-VERIFY before deploy: byte-diff `agent.py` (flag-OFF path identical to golden); `py_compile` + `python -c "import agent"` import-smoke; reuse `llm_router/tests` (simulate 429 → assert re-pick + cooldown + no surfaced error; assert a store-add appears in `pick()` without restart); confirm `GROQ_POOL.available_count()` == 21 (6 env + 15 store) on the box before flipping the flag.
- Backup `agent.py.GROQbak.<ts>`; rollback = restore backup OR `EARNER_POOL_LLM=0` + restart (no code revert).
- RISK FLAGS: verify the outbound `groq.LLM` kwargs survive the delegate wrap (note `agent.py:937` `max_tokens` is a TypeError — use `max_completion_tokens`); enable the flag on low traffic first; `var/provider_keys.json.enc` decrypt needs `PROVIDER_KEYSTORE_SECRET` in the earner's `.env` scope (`agent.py:57-58`) — if unset, pool degrades to the 6 seed keys (never keyless), the 15 panel keys silently drop → verify the secret is present.

## FOUNDER REFINEMENT (correct — implement this way): STICKY KEY PER CALL
The brain is multi-turn (each turn re-sends the conversation history + new user msg, like ChatGPT). So:
- **Assign ONE key per CALL/conversation** at call-start (least-used at that moment → spreads concurrent calls across keys), and **reuse that same key for ALL turns** of the conversation. This preserves Groq's prompt-cache (the static ~2k prefix stays cached on that key → lower latency + cost) and matches per-key rate accounting. Do NOT rotate keys per-turn within one call.
- **Switch keys mid-call ONLY on a 429** (instant fallback to the next healthy key — the `PoolLLM` re-pick), then stick to the new key.
- **21 keys = CONCURRENCY capacity** (call#1→keyA, call#2→keyB, …), NOT for one call. One key handles one call fine; the pool exists so many SIMULTANEOUS calls never overload a single key → never a surfaced 429 at scale.
- Implementation note: the shipped `PoolLLM` picks per-request (per-turn). Add a **per-call sticky binding** — pin the key chosen at the call's first turn into the call/session context and have `PoolLLM` reuse it unless that key is cooling (429). Small change in the `agent.py` PoolLLM wiring / a `sticky_key` on the session; the pool's `mark_429`/re-pick stays as the only switch trigger.

## SEQUENCE
Implement ONLY after the voice fix (ROUND-6 brain + frequency_penalty) is founder-confirmed clean. Deploy flag OFF → flip `EARNER_POOL_LLM=1` → founder test a call. NEVER bundle with a voice/brain change. (Full design: agent task `a3398356389405414`.)
