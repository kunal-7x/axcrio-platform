# 🔧 voice-agent-v2 — CLEAN REBUILD, CRASH-SAFE STATE (ROUND-10, 2026-06-21)

Authoritative plan: `caps/.claude/plans/you-have-digitalocean-api-imperative-mist.md` → ROUND-10.
Branch: `rebuild/voice-telecaller-v2`. Direct build (NO ultracode). Live earner UNTOUCHED.

## WHAT THIS IS
A new, self-contained LiveKit voice-telecaller worker that runs SIDE-BY-SIDE with the live one
(`capsy`) as `capsy-v2`. The perfect VOICE is preserved byte-for-byte; the bug machinery + scripts
are gone; the brain runs on a bigger model. Founder's real call = the only verdict. I do NOT say "done".

## THE 3 CHANGES (everything else is byte-identical to live agent.py f4d75e49)
1. **Clean script-free prompt** — `prompt.py` rebuilt: role + hard rules + FACTS only. No objection/
   closing/step scripts (killed premature-close + CoT-recite). Keeps the field contract
   (GODREJ_FIELDS, _gender_of, build_system_prompt) so campaigns + agent.py import unchanged.
2. **Closure trimmed to explicit end-signals** — `agent.py` `_CLOSE_NO` now lists ONLY real hang-up /
   do-not-call phrases (bye/रखता हूँ/cut the call/do-not-call). Objections ("महंगा"/"नहीं चाहिए"/
   "अभी नहीं") REMOVED → the #1 bug (objection→call-cut) is gone. `_closure_signal` no longer
   auto-books/auto-closes (returns 'no' on an explicit end-signal only; booking = the LLM tool).
3. **Bigger model** — `.env` `GROQ_LLM_MODEL=llama-3.3-70b-versatile` (kills number-loop / role-flip /
   CoT-recite = small-model signatures). NOT a code change — `_mk_groq_llm` already reads this env.
   Proven on these keys (live AI-Manager runs the same model).

## PRESERVED BYTE-IDENTICAL (untouched in agent.py)
ElevenLabs Flash TTS constructor (voice_id QTKSa2Iyv0yoxvXY2V8a, EL_STABILITY via env=0.55) ·
Groq LLM factory + room-seeded key-spread + FallbackAdapter (dead-air fix) · Sarvam saarika-v2.5 STT ·
AgentSession/VAD/endpointing/barge-in tuning · opener (_llm_opener + OPENER flags) · per-turn language
mirror (_normalize_indic + langdetect note + cache-safe TTS nudge) · booking tool (_do_booking_http) ·
cross-call memory · metrics. All copied verbatim from the live f4d75e49.

## FILES (in repo, branch rebuild/voice-telecaller-v2)
- `agent.py`   — clean entrypoint (= live f4d75e49 minus closure machinery; 2 subtractive edits). py_compile OK.
- `prompt.py`  — NEW clean brain (role+rules+facts). py_compile OK.
- `memory.py` `langdetect.py` `voice_ops/booking/datetime_resolve.py` — VERBATIM copies from the box.
- `.env.example` — env contract (NO secrets).
- `tests/replay.py` — offline live-Groq replay gate (run on the box venv).
- `README.md` — deploy + flip + rollback runbook.

## DEPLOY (isolated, gated — see README)
Box scratch `/opt/famit-agent-v2/`. `.env` = copy of `/opt/famit-agent/.env` with ONLY:
`GROQ_LLM_MODEL=llama-3.3-70b-versatile` + `LIVEKIT_AGENT_NAME=capsy-v2` (+ AGENT_HTTP_PORT distinct).
systemd unit `famit-agent-v2`. Live `famit-agent` / `capsy` NEVER touched.

## ROLLBACK
There is nothing to roll back on the live earner — `capsy` keeps running untouched the whole time.
To stop v2: `systemctl stop famit-agent-v2`. To flip live→v2 later (only after founder OK): point the
live dispatch / unit at the v2 code; rollback = point back to `capsy` (instant).

## PROGRESS
- [x] Branch + pull live source (md5 f4d75e49 / b9a974cf confirmed)
- [x] Copy proven support modules verbatim (memory/langdetect/voice_ops)
- [x] prompt.py clean (py_compile OK)
- [x] agent.py — 2 subtractive edits (closure→end-signal-only) (py_compile OK)
- [ ] README + .env.example + tests/replay.py
- [ ] commit + gitleaks scan + push
- [ ] DEPLOY isolated `famit-agent-v2` (capsy-v2) + health-check + live capsy byte-identical
- [ ] PROVE: offline replay on box (70b) — objection-not-cut, no number-loop, lang-mirror
- [ ] FOUNDER real call to capsy-v2 = the verdict
