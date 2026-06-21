# WAVE — Smart LLM Provider Pool + Hot-Reload Key-Store + Run-Campaign Fix

Date: 2026-06-13 (IST). Box: famit@168.144.153.145 /opt/famit-agent ; venv /opt/capsy-agent/.venv.
Frontend: famit-panel -> FORTRESS root@143.110.247.249:/opt/famit-panel (panel.famit.in).

## WHY (incident)
Inbound AIM went dead ("thoda sa system slow hua hai") = shared Groq org 500k/day pool exhausted by
testing + DUMB linear key rotation (always key#1 -> #2 -> #3, so #1 hits the daily wall while #4-9 idle).

## WHAT WAS BUILT (6 deliverables)
1. NEW `llm_router/` module on box (`provider_pool.py` + `key_store.py` + `pool_llm.py` + `__init__.py`):
   least-used pick(), mark_429() cools a key (TTL from Retry-After, 60s default / 3600s cap / 1.0s floor)
   and INSTANTLY skips it (no linear walk of dead keys). `PoolLLM` wraps a groq/openai-compatible
   delegate, swaps `_client.api_key` per request from pool.pick(), re-picks on 429, raises when the whole
   provider is cooling so FallbackAdapter advances providers.
2. Keys loaded into ENCRYPTED store `var/provider_keys.json.enc` (Fernet, 0600): 9 Groq (z_groq_2.md,
   multiple accounts = independent daily pools; fixed `gGROQ_API_KEY_6` typo -> `gsk_`) + 4 SambaNova
   (z_samba.md). Live merged pool = Groq 15 / SambaNova 5 / Sarvam 5 / OpenRouter 1.
3. SambaNova final fallback: base_url https://api.sambanova.ai/v1, OpenAI-compatible,
   model Meta-Llama-3.3-70B-Instruct (~282-430 t/s ~= Groq). Free 200k TPD / ~10 RPM; Dev 20M TPD / 60 RPM.
   Chain = FallbackAdapter([PoolLLM(groq) -> PoolLLM(sambanova) -> PoolLLM(openrouter-free)]).
   Sarvam STT now pool-picks the same way.
4. Frontend /super-admin/api-keys page (commit a8e9ca9 feat/premium-ui) — per-provider Card, masked
   password add-modal, enable Switch, delete, live status dot (5s poll). DEPLOYED to FORTRESS (public 200).
5. Hot-reloadable key-store + 5 super-admin CRUD routes in caller.py (6155-6240), all require_super_admin
   (legacy FamitCall2026 -> 403 verified). GET returns list_all_masked() (raw key NEVER returned).
6. Run-campaign EXECUTION fix: root cause = `force` only suppressed the 202; run_job re-checked _in_window
   each tick and idled sleep(60) out-of-window even when forced. Fix: `now` param -> JOBS[id].force_window=True
   -> run_job bypasses the window idle (caller.py:2470-2472, :3885-3897); voice_tools run_campaign +
   single-call send now=1 (:343, :520). SIP/trunk/agent.py UNTOUCHED.

## VERIFICATION (this pass, read-only, ZERO quota burn)
- tests/test_provider_pool.py PROOF_EXIT=0: sim-429 on k1 -> picks k2/k3, k1 NEVER returned while cooling
  (NOT linear); 90 picks -> perfect 10/10/10 even spread; all-cooling -> None; cooldown TTL; hot-reload
  (panel-added key picked w/o restart; disable removes live); Retry-After parse.
- tests/test_pool_llm.py PROOF_EXIT=0: k1 429 -> instant re-pick k2 (calls=['k1AAAA','k2BBBB']);
  all-429 -> tries each distinct key once then raises (advances Groq->SambaNova).
- Live merged pool counts confirmed on box: groq 15 / sambanova 5 / sarvam 5 / openrouter 1 (all available).
- 5 routes present + all require_super_admin; legacy pw -> 403 over HTTP (GET + POST).
- FallbackAdapter chain order on box = Groq pool -> SambaNova pool -> OpenRouter free.
- Frontend live: https://panel.famit.in/super-admin/api-keys = 200.
- EARNER GATE before & after = PASS: agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED;
  famit-agent MainPID 1477083 ActiveEnter 2026-06-10 19:58:18 (NEVER restarted); only famit-caller(2228794)
  + aim-voice-agent(2228800) + famit-panel restarted; 0 5xx / tracebacks in caller/aim since restart.
- Secrets: z_groq_2.md / z_samba.md / z_groq_api.md gitignored (check-ignore exit 0), NOT tracked
  (git ls-files match exit 1); encrypted store 0600; gitleaks clean.

## RESIDUALS (founder, not blocking)
- The EARNER still shares the same Groq org pool until its OWN provider-fallback is separately approved
  (do NOT do it in this wave — agent.py / trunks / firewall / SIP are off-limits).
- Outbound rings only after a Vobiz recharge (balance ~Rs.0.19 -> 402). Code path reachable; that's billing.
- SambaNova free tier 200k TPD / ~10 RPM is thin as a real fallback — link a payment method for Dev tier
  (20M TPD / 60 RPM) if AIM volume grows.
- Real end-to-end proof = the founder calling inbound (rotation now spreads load so no single key dies).
