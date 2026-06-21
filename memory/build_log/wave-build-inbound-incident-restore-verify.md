# Wave: Inbound AI Manager — production incident DIAGNOSE → RESTORE → VERIFY (2026-06-12/13)

**Box:** `famit@168.144.153.145` `/opt/famit-agent` · venv `/opt/capsy-agent/.venv` · caller :8209 · aim worker :8091.
**Branch context:** `feat/premium-ui`. Box-only change (panel untouched this wave).

## The incident
AI Manager greeted fine, then repeated the canned filler **"thoda sa system slow hua hai"** on EVERY
turn (PIN, any query) and never processed anything; inbound CUSTOMER call also dead. Regressed after
several voice waves (handoff-pertenant-backend etc.) touched the voice path in one day.

## Root cause — NOT a code regression (falsified the prime suspect)
The strong prime suspect was the handoff wave's 3 new `@function_tool`s breaking the Groq tool schema
→ 400 storm. **The live logs FALSIFIED this:** histogram of the last 3000 journal lines = **496
`rate_limit_exceeded` / 248 `status_code=429`** vs only 6 stray "400" (all inside unrelated STT-INFO
strings; ZERO `tool_use_failed`/`json_validate_failed`/`BadRequestError`).

Actual error every turn:
```
APIStatusError: 429 - Rate limit reached for model meta-llama/llama-4-scout-17b-16e-instruct
  service tier on_demand on tokens per day (TPD): Limit 500000, Used ~498000, Requested ~7216
→ APIConnectionError: failed to generate LLM completion after 2 attempts
→ @session.on("error") → _speak_recovery() (aim_voice_agent.py:2095) speaks the filler.
```
Greeting survives because it's a static `session.say()` (no LLM). The first real user turn needs an
LLM completion → 429 → filler, forever, until the daily bucket refills. **Smoking gun:** all 6 Groq
keys (`GROQ_API_KEY`+`_2..._6`) return the IDENTICAL `x-ratelimit-remaining-tokens` → **same Groq org
→ ONE shared 500k/day TPD pool** → key-rotation gives ZERO daily headroom. Both ManagerAgent and
CustomerSalesAgent share the same `_aim_llm` → both inbound paths die identically.

## Fix — capacity, not revert (a revert does nothing for a depleted token bucket)
One file edited: `/opt/famit-agent/aim_voice_agent.py` (backup `*.EMERGbak.20260612-182751`).
Wrapped AIM's LLM in `llm.FallbackAdapter([groq_member, openrouter_free_member])`:
- **Groq stays PRIMARY** (fast/cheap; auto-recovers the instant its 500k/day TPD refills).
- On 429/connection-error → **FREE OpenRouter model** `openai/gpt-oss-120b:free` (tool-capable,
  SEPARATE daily pool, **$0** — `OPENROUTER_API_KEY` already in `.env`).
- `_strict_tool_schema=False` forced on every member + the adapter. Import-guarded → degrades to
  pure-Groq if the OR key/plugin/adapter is ever absent. Knobs `AIM_LLM_FALLBACK=1`,
  `AIM_FALLBACK_OR_MODEL`. Code at `aim_voice_agent.py` ~lines 2045-2099 (`_mk_groq_llm` /
  `_mk_openrouter_llm` / `FallbackAdapter` assembly).
- NOT changed: tools, manager prompt, warm-transfer bridge, caller.py, the earner, trunks, firewall,
  SIP. py_compile OK; worker re-registered clean (`agent_name:"manager"`, openai plugin present,
  zero startup Traceback).

## Verification (2026-06-13 — INTEGRATED, not isolated)
Built two harnesses on the box that construct `_aim_llm` exactly as `entrypoint()` does, attach the
REAL agent tool schemas (`agent.tools`), and drive real turns inside `http_context` (plugins need it):
- `/tmp/aim_turnloop_smoke.py` (ManagerAgent, 15 tools) and `/tmp/aim_customer_smoke.py`
  (CustomerSalesAgent, 5 tools). Run with `cd /opt/famit-agent && set -a; . ./.env; set +a;
  /opt/capsy-agent/.venv/bin/python /tmp/<harness>.py`.

Ran **while Groq's daily bucket was STILL 429ing** so the OpenRouter failover was actually exercised
(logs: `livekit.plugins.groq.services.LLM failed, switching to next LLM`). Results:

| Item | Turn | Result |
|------|------|--------|
| (1) Manager LLM completion w/ tools | T1 "Hello" | "Namaste! How can I assist you today?" — completion SUCCEEDED, no 400/schema-reject. **PASS** |
| (1) PIN-verify path | T2 "Mera PIN hai 4827" | `verify_pin({pin:'4827'})` → `verified=true`, `agent._verified=True`. **PASS** |
| (1) Real data query | T3 "Kitne hot leads hain?" | `check_leads` → REAL "You have 7 leads total — 5 hot, 1 warm, 1 cold" → spoke "Aapke paas 5 hot leads hain". **PASS** |
| (1) Real data query | T4 "campaigns list karo" | `list_campaigns` → REAL 8 campaigns (Codename Joy 3.0, DLF The Crest, …). **PASS** |
| (2) Customer reactive | C1 open question | "Boliye, kis tarah help kar sakti hoon?" **PASS** |
| (2) Customer reactive | C2 "3 BHK price?" | `lookup` RAG tool → REAL "lagbhag ₹1.32 crore se shuru…". **PASS** |

NONE of the turns hit the "thoda sa system slow" filler.

## Earner gate (before + after) — PASS
- agent.py md5 **`9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED**.
- famit-agent **active** PID **1477083** / ActiveEnter **2026-06-10 19:58:18** — **never restarted**.
- A FRESH out-of-window outbound **RANG**: throwaway campaign `58723234c8` (window 00:00-23:59) →
  `/run` to +917861019021 (count:1, suppressed:0) → SIP room `famit-917861019021-3f2db7`,
  `participant: phone-+917861019021` joined (= rang; founder didn't pick up → no_answer), same PID
  1477083. Throwaway campaign DELETED (200); founder NOT in suppression.
- caller core 401-alive (auth-gated, not 5xx); 0 5xx in 60 min; only famit-caller + aim-voice-agent
  ever restarted this wave.

## Honest residual
- Only a real founder phone call fully proves the AUDIO leg end-to-end (STT→LLM→TTS over the live SIP
  room). The harness proves the LLM+tools+data leg — the exact part that was broken — conclusively.
- ⚠️ The earner's `agent.py` shares the SAME Groq org TPD pool → heavy AIM test-burn can still starve
  the live earner's LLM on a busy outbound day. Founder action (not blocking): give the earner its own
  fallback too OR a second Groq org, and gate AIM test volume.

## LESSON
Isolated backend tests passed on EVERY handoff wave (earner-gate + loopback CRUD green) yet the
INTEGRATED inbound voice turn-loop was DEAD — because nobody drove a real LLM turn THROUGH `_aim_llm`
with the tools loaded after stacking 4 voice waves in one day. **Every wave touching the voice path
MUST run an integrated turn-loop smoke (build `_aim_llm` like `entrypoint()` → attach `agent.tools`
→ drive greeting+PIN+a real-data query in `http_context` → assert NO filler + REAL data) before
declaring done; never stack multiple box-mutating voice waves without it.** A passing isolated test
≠ a working call. And: 429/rate_limit = quota → add capacity (never revert code); 400/tool_use_failed
= code bug → fix/revert the tool.
