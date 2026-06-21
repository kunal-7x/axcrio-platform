# SMART PROVIDER POOL + KEY-STORE + RUN-CAMPAIGN FIX — WAVE STATE

Box: famit@168.144.153.145 (famit-livekit) /opt/famit-agent ; venv /opt/capsy-agent/.venv
Frontend: famit-panel (deploy root@143.110.247.249:/opt/famit-panel)

## EARNER GATE (before) — captured 2026-06-13 13:41 IST — PASS baseline
- agent.py md5 = 9150fabe4ff62b4b4470f9a87df346e5 (UNCHANGED expected)
- famit-agent: active MainPID 1477083 ActiveEnter 2026-06-10 19:58:18 (never restart)
- famit-caller: active 2048506 ; aim-voice-agent: active 2048501
- NOTE: outbound currently 402-blocked by Vobiz balance (₹0.19) per AGENT_LEARNINGS#1 — earner safety proven by md5+PID+0-5xx, not by a live ring (founder must recharge Vobiz separately).

## RESEARCH (done)
- SambaNova: base_url https://api.sambanova.ai/v1 ; model Meta-Llama-3.3-70B-Instruct ; OpenAI-compatible.
  Free tier 200k TPD / ~10 RPM ; Dev tier 20M TPD / 60 RPM (70B). ~282-430 t/s output (competitive w/ Groq ~299). Strip presence/frequency_penalty (400s there).
- cryptography 49.0.0 present on venv -> encrypted key-store viable (Fernet).
- 9 new Groq keys = MULTIPLE accounts (pk7/learnig7x/kunal*x...) => independent daily pools (the real fix vs same-org rotation).
- GROQ_API_KEY_6 in z_groq_2.md has a TYPO: `gGROQ_API_KEY_6=sk_DsaIK...` -> real key = `gsk_DsaIK...` (fix on load).

## PLAN / PHASES
- [x] Pre-flight: secrets gitignored (check-ignore exit 0). DONE.
- [x] Phase A: llm_router/ module + unit tests. PROOF_EXIT=0: sim-429 skip(k2,k3 never k1)/90picks=10-10-10 even/all-cooling=None/cooldown-TTL/hot-reload/retry-after-parse ALL PASS. py_compile OK.
- [x] Phase B: seeded 9 Groq + 4 Samba into ENCRYPTED store (var/provider_keys.json.enc 0600). .env += PROVIDER_KEYSTORE_SECRET + SAMBANOVA_API_KEY/MODEL/BASE_URL (bak .env.LPRbak.20260613-081906). caller.py += 5 /admin/provider-keys* routes (bak caller.py.LPRbak.20260613-082325, compile OK). Pool merge verified: groq15/sarvam5/samba5/or1. CONNECTIVITY 1-call/provider: Groq OK(openai-sdk)/SambaNova OK(Llama-3.3-70B)/Sarvam OK(200). Seeders deleted local+box.
- [x] Phase C: PoolLLM wrapper (llm_router/pool_llm.py) — test_pool_llm PROOF_EXIT=0 (k1 429->instant re-pick k2, all-429->raise=advance provider). aim_voice_agent.py patched 3/3 (LPR-POOL): pool import + Sarvam STT pool-pick + FallbackAdapter[groq15 -> sambanova5 -> openrouter1] all PoolLLM-wrapped. Chain build verified + 1 integrated turn through PoolLLM[groq] -> "Hi!" (pick_count incremented). bak aim_voice_agent.py.LPRbak.20260613-082*.
- [x] Phase D: caller.py patched 4/4 (LPR-FORCE-WINDOW): /run +now param, JOBS.force_window, run_job bypasses out-of-window idle when force_window, /run 202-honesty when not now/force. voice_tools.py 2/2 (LPR-NOW): run_campaign+single-call send now=1. compile OK both.
- [ ] Phase E: frontend API Keys page + lib/api.ts
- [x] Backups *.LPRbak.* done, py_compile all OK, restarted famit-caller(2228794)+aim-voice(2228800) ONLY. Clean reg, 0 tracebacks/5xx.
- [x] API routes verified over HTTP: list/add/status/delete + HOT-RELOAD (samba 5->6 on add, ->5 on delete, NO restart). legacy_pw -> 403 (gate works). run_campaign force_window bypass asserted.
- [x] EARNER GATE after PASS: agent.py md5 9150fabe… UNCHANGED, famit-agent PID 1477083 ActiveEnter 2026-06-10 NEVER restarted, 0 5xx.
- [x] Phase E: frontend /super-admin/api-keys (commit a8e9ca9 on feat/premium-ui). lib/api.ts 5 fns + ADMIN_TABS tab + page (Card/provider, masked add-modal, Switch, delete, live status dot 5s poll). tsc EXIT 0, gitleaks 0, token-pure.
- [x] AGENT_LEARNINGS.md appended.

## WAVE COMPLETE. All 6 deliverables done. Earner UNTOUCHED (md5 9150fabe… / PID 1477083).
## OPEN (founder, not blocking): outbound rings only after Vobiz recharge (₹0.19, separate billing issue). SambaNova free-tier 200k TPD/10 RPM is thin as a real fallback — link a payment method for Dev tier (20M TPD/60 RPM) if AIM volume grows. Frontend not yet DEPLOYED to FORTRESS (separate deploy wave; build is committed).

## KEY FACTS
- aim_voice_agent.py:296 _collect_keys (COPY of agent.py logic — editing it CANNOT touch earner)
- :306 _GROQ_KEYS/_GROQ_CYCLE linear cycle ; :314 _next_groq_key ; :324 _next_sarvam_key
- :349 _build_stt (sarvam.STT) ; :2045 _mk_groq_llm ; :2058 _mk_openrouter_llm ; :2085 FallbackAdapter
- X-Auth FamitCall2026 ; caller listens :8209
