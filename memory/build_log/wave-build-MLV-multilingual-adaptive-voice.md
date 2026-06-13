# Wave: MLV — Multilingual Adaptive Voice (INBOUND aim_voice_agent.py)

**Date:** 2026-06-14
**Box:** famit@168.144.153.145 `/opt/famit-agent/aim_voice_agent.py` · venv `/opt/capsy-agent/.venv`
**Scope:** INBOUND `aim_voice_agent.py` ONLY. Earner (`agent.py`/trunks/firewall/SIP) UNTOUCHED. No outbound test calls (DID +918071583488 resting). Additive.

## Problem (founder)
He calls in; if he speaks Hindi the AI replies Hindi, but when he switches to English mid-call the AI
stays stuck in Hindi. Also the opener stutters ("Hello/Haan" — English "Hello!" jammed against a Hindi
question).

## Diagnosis (ground truth)
1. **PRIME CAUSE — the language PIN, `_build_sales_instructions` point 3, `aim_voice_agent.py:1480-1485`:**
   `"3. LANGUAGE = CASUAL HINGLISH: ... default to easy Hinglish."` This sat inside the block marked
   "HIGHEST PRIORITY — this OVERRIDES anything below", so it beat the (already-adaptive) `head` line
   `:1372-1373` ("in the SAME language/code-mix the caller uses"). The "if pure English reply English"
   clause was buried and dominated by "default to easy Hinglish" → the model defaulted/anchored to
   Hindi/Hinglish and did not switch when the caller switched to English.
2. **STT — NOT pinned (already auto).** `_build_stt` `:359` = `language=os.getenv("SARVAM_STT_LANG","unknown")`
   and `SARVAM_STT_LANG` is **not** set in `/opt/famit-agent/.env` → `"unknown"` = Sarvam saarika
   AUTO-DETECT. Verified in the live journal: a caller's "Hello" was transcribed verbatim under auto;
   pinning `hi-IN` would garble English (per the existing code comment). So STT was already multilingual
   — the task's "if pinned, set to auto" had nothing to unpin. (Side note from the journal: `"unknown"`
   occasionally over-detects Hindi as Bengali/Punjabi script — left as-is; the LLM mirror rule now drives
   reply language regardless of script.)
3. **Greeting glitch — `:2645-2655`.** Customer openers mashed English "Hello!"/"Hi!" immediately against
   a Hindi question (`"Hello! ... Aap kis project ke baare mein jaanna chahte hain?"`) → the "Hello/Haan"
   stutter.

## Fixes applied (3, additive)
1. **ADAPTIVE mirror rule** replaces the Hinglish pin (`:1480-...`): *"LANGUAGE = MIRROR THE CALLER, EVERY
   TURN: reply in the SAME language the caller just used... the MOMENT they switch language mid-call —
   switch WITH them on your very next line, immediately... There is NO default language and NO house
   style... NEVER announce, explain, ask about, or apologise for the language — just speak it."* Kept it
   minimal/casual; one or two short sentences then listen. Handoff / no-AI-disclosure / no-recording /
   `session.aclose()` / the bridge are all UNTOUCHED.
2. **STT docstring** (`_build_stt`) clarified to state `"unknown"` is the AUTO-DETECT/multilingual mode
   that lets the caller switch language mid-call and be heard, and to NOT pin a fixed language (pinning
   hi-IN garbles English — verified). Functional param unchanged (already auto); still env-overridable
   via `SARVAM_STT_LANG`.
3. **Clean greeting** (`:2645-2655`): single warm opener with no English→Hindi jolt —
   `"Namaste{who}, {agent} from {company} here. Call karne ke liye shukriya{proj} — bataiye, main kaise
   help karoon?"` (returning / disambig / default variants), and the LLM mirrors the caller's language
   from their first reply.

## Verification
- **EARNER GATE (before + after) = PASS.** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED;
  famit-agent active, ActiveEnter `2026-06-10 19:58:18`, NEVER restarted; famit-caller `/health` 200;
  0 5xx. NO `/run`, NO ring (DID resting).
- **INTEGRATED mirror smoke = 3/3 PASS** (`/tmp/mlv_smoke2.py`, real Groq `GROQ_LLM_MODEL`
  llama-4-scout via the deployed module's REAL `_build_sales_instructions`): TURN1 Hindi→AI Hindi;
  TURN2 switch to English→AI clean English (the exact bug, now fixed); TURN3 switch back to Hindi→AI
  Hindi. No language announcement in any reply. Detector is Hinglish-aware (romanized Hindi = Hindi,
  the natural phone register).
- aim-voice-agent restarted ONLY; re-registered clean ("registered worker", agent_name="manager"),
  0 Tracebacks.

## Deploy / rollback
- Backup-first: `/opt/famit-agent/aim_voice_agent.py.MLVbak.20260614-020515`.
- Staged → py_compile (venv) → copied live → py_compile live → restart aim-voice-agent ONLY.
- Deployed-ref snapshot synced to repo: `_inbound_ref/aim_voice_agent.DEPLOYED.py`.
- ROLLBACK: `cp .MLVbak.20260614-020515 aim_voice_agent.py && systemctl restart aim-voice-agent`.

## Residual / final acceptance
- Only the founder's REAL inbound call to +918071583488 (speak Hindi, then switch to English mid-call)
  is the true end-to-end proof — the smoke proves the LLM chain mirrors; STT/TTS on a live call is what
  the founder must hear.
- STT `"unknown"` can mis-detect Hindi as a neighbouring Indic script occasionally; not regressed here.
  If it bothers the founder, a future option is biasing to hi-IN+en code-mix (tradeoff: risks English).
