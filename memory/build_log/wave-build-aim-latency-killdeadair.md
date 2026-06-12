# WAVE: AIM VOICE LATENCY — KILL THE 3-5 MIN DEAD AIR (2026-06-12)

run-id: lat-killdeadair · box `famit@168.144.153.145` · /opt/famit-agent
ISOLATION: edited `aim_voice_agent.py` + `ai_manager/voice_tools.py` ONLY; caller.py READ-ONLY;
agent.py / outbound earner / trunks / firewall / SIP UNTOUCHED; restarted ONLY aim-voice-agent.

## ROOT CAUSE (proven, not data latency)
A STRICT-SCHEMA tool-call REJECTION RETRY STORM. The livekit-plugins-openai layer builds a STRICT
JSON tool schema (`openai/llm.py: _strict_tool_schema=True`, consumed at `chat()` line 1026 →
`to_fnc_ctx(strict=True)` → `build_strict_openai_schema`). That marks EVERY tool param `required` and
`strict:true`. PROVEN on the live ManagerAgent tools:
  - `check_leads`  STRICT required = ['campaign']                          (small llama-4-scout omits it)
  - `run_campaign` STRICT required = ['campaign','segment','count','confirmed'] + strict:true (LLM sends count/confirmed as STRINGS)
Groq then 400s "did not match schema" → the 400 is wrapped retryable → LiveKit retries
(APIConnectOptions max_retry=3, retry_interval=2s = 4 doomed attempts) re-sending the whole prompt →
all re-fail → `_llm_inference_task` dies → ZERO audio (dead air) → founder repeats → another storm →
minutes stacked. Journal: **57 "did not match schema" in the prior 24h.**

## FIXES APPLIED (A–E)
(A)(i) **STRICT TOOL SCHEMA DISABLED** — groq.LLM is a thin OpenAILLM subclass that does NOT forward
   the private `_strict_tool_schema` kwarg, so after constructing the LLM we flip
   `_aim_llm._strict_tool_schema = False` (aim_voice_agent.py, session-build block). PROVEN: with it OFF
   `to_fnc_ctx(strict=False)` → `build_legacy_openai_schema` → check_leads & run_campaign now have
   **required = None, strict = None** → no arg required, loose types accepted. The LLM can NEVER emit a
   rejected call. Logs "AIM LLM strict_tool_schema DISABLED".
(A)(ii) Body coercion already present (`_to_int`/`_to_bool`) + optional-arg defaults; check_leads with no
   campaign returns whole-pool counts; run_campaign omitting campaign → graceful need_campaign. Kept as
   belt-and-suspenders.
(B) **FAIL-FAST + never-dead-air** — per-session `conn_options=SessionConnectOptions(llm_conn_options=
   APIConnectOptions(max_retry=1, retry_interval=0.5, timeout=12))` (env AIM_LLM_MAX_RETRY/…); kills the
   4x doomed-retry stack. PLUS the `session.on("error")` handler now, on an LLM-source error, speaks a
   short recovery line (AIM_RECOVER_LINE, debounced 4s) so a turn can never stall into silence.
(C) **FILLER SPEECH** — `_say_filler(context)` speaks a brief rotating Hinglish holding phrase
   ("Ek second, dekh rahi hoon…") WHILE a tool fetch runs (add_to_chat_ctx=False, not awaited → zero
   added latency). Wired into check_leads, recent_calls, analytics, wallet_status, list_campaigns,
   campaign_details, campaign_analytics, run_campaign (resolve + dial), test_call_me. Toggle AIM_FILLER=0.
(D) **WARM HOT SNAPSHOT at connect** — for a manager call, a fire-and-forget task prefetches lead_counts
   + campaigns_summary into `agent._hot_leads_summary` / `_hot_campaigns_summary` once at connect (never
   delays the greeting). check_leads (no campaign) and list_campaigns answer from that snapshot in <5ms.
(E) **KEEP-ALIVE POOLED httpx** — voice_tools `_client()` was a NEW httpx.Client per call; now a single
   module-level pooled client (httpx.Limits keepalive 8/16, 30s expiry), lazy + thread-safe + self-heals
   if closed. `_get`/`_post_form` reuse it. Also tuned: max_endpointing_delay VAD default 0.45→0.6s;
   GROQ_MAX_TOKENS 140→160.

## SMOKE — the previously-rejecting calls now SUCCEED (replayed the LLM's exact arg shapes)
- check_leads(omit campaign)                  → "You have 6 leads total — 5 hot, 0 warm, and 1 cold." (real)
- run_campaign(count="5", confirmed="false")  → read-back "I'll start calling 5 hot leads for …" (dial path resolved)
- run_campaign(all args omitted)              → graceful need_campaign (no crash)
- WIRE SCHEMA: strict ON → required=['campaign'] / strict:True ; strict OFF → required=None / strict=None
- voice_tools pooled client OK (Client, not closed); lead_counts/campaigns_summary return real data
- **"did not match schema" since restart (10:10:52 UTC) = 0** (was 57 in prior 24h)
- aim-voice-agent re-registered CLEAN: `registered worker agent_name="manager" id=AW_y9GuFRVKebg7`, VAD
  prewarmed, 0 tracebacks.

## EARNER REGRESSION-GATE = PASS (before AND after)
Real outbound POST /run to founder **+917861019021** via campaign c17e55e9f3:
- BEFORE: job 28888f4662 → earner job AJ_XaQ6om8gmdvG room RM_2yDVG6bcRc58 (phone rang)
- AFTER : job 55366d00d1 → earner job AJ_gaw9ZtAuWYfM room RM_bhwEJVaKoeDw, STT WS connected, tts_ttfb 0.836s (phone rang)
- **agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED** before+after
- famit-agent + aim-voice-agent both active before+after; **ZERO 5xx/tracebacks**

## FILES / BACKUPS / ROLLBACK
- Deployed md5: aim_voice_agent.py `b8125961557ae241d490fb137dc352b7`; voice_tools.py `4c3e205648e8c7654911672ff68a9b4b`
- Backups on box: `aim_voice_agent.py.LATbak.20260612-100154`, `ai_manager/voice_tools.py.LATbak.20260612-100154`
- Repo mirror: `.wf/aim_brain/{aim_voice_agent.py,voice_tools.py}` + `droplet_work/{aim_voice_agent.py,voice_tools.py}`
- ROLLBACK: restore the two .LATbak files + `systemctl restart aim-voice-agent` (earner untouched).

## PROVEN vs PENDING
PROVEN at service level: strict-off (schema can't reject), fail-fast retry, filler + warm-snapshot +
pooled-client all live; the exact failing arg shapes now run + return real data; 0 schema rejects since
deploy; earner 100% intact. PENDING (needs founder's real INBOUND call): the full live voice round-trip
where the LLM itself fires check_leads/run_campaign mid-conversation and we observe sub-2s answers +
audible filler instead of dead air. FOUNDER TEST: dial the manager DID → key PIN 4827 → "how many leads"
(answers instantly from warm snapshot) and "run Codename Joy, all leads, yes" (filler then dials).
