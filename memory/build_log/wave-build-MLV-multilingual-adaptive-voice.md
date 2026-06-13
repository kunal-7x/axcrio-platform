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

## Pass 2 — VERIFY-driven hardening (2026-06-14, integrated smoke exposed a residual)
The integrated smoke (now N=2/case + Hinglish-aware AND live-shape scenarios) surfaced a real residual the
first pass missed: **the mid-call SWITCH (the reported bug) was fixed and reliable, but a COLD-OPEN where the
caller's first words are English still got a Hindi reply.** Root cause: (a) the reused OUTBOUND earner
KNOWLEDGE PACK is large and Hindi-heavy, so on a single English turn with little prior context the model's
Hindi gravity won; (b) the AI's OWN spoken greeting was in Hindi (`"...bataiye, main kaise help karoon?"`),
which primed the whole conversation toward Hindi/Hinglish even when the caller answered in English.

Three additive hardenings (INBOUND only, earner untouched):
1. **Mirror rule strengthened for the FIRST reply** (point 3): added *"from their VERY FIRST words... INCLUDING
   your first reply. Your spoken greeting may have been in Hindi, but that does NOT set the language — the
   CALLER does."*
2. **FINAL LANGUAGE LOCK appended as the last text of the prompt** (`_build_sales_instructions` return,
   `lang_lock`): highest-recency override — *"Reply in the SAME language the CALLER used in their LAST
   message... The Hindi text in the knowledge pack above is reference material ONLY and must NOT make you
   reply in Hindi when the caller spoke English."*
3. **LANGUAGE-NEUTRAL greeting** (`:2664-2682`): the decisive structural fix. The greeting is now a universal
   `"Namaste{who}, this is {agent} from {company}. ...how can I help you today?"` (English question; returning /
   disambig / default variants). `"Namaste"` keeps the warm Indian register without committing the call to
   Hindi, and the ENGLISH question means the AI's own opener no longer pins Hindi — the CALLER's first reply
   sets the language and the mirror rule follows. A Hindi caller is still mirrored straight into Hindi.

### Final integrated smoke (real builder + real Groq llama-4-scout, N=2/case, live-shape):
- `1` Hindi → Hindi: **PASS**
- `2` (degenerate: NO greeting turn, lone English msg) → Hindi: FAIL — **artifact only; this shape never
  occurs live** (the AI always greets first). Kept in the suite as the worst-case stress probe.
- `3` mid-call Hindi→English switch → English: **PASS** (the reported bug — fixed, reliable)
- `2b` LIVE shape: neutral greeting said, caller opens ENGLISH → English: **PASS** (the founder's recipe)
- `2c` LIVE shape: neutral greeting said, caller opens HINDI → Hindi: **PASS** (no English regression)
- `4` no language announcing in any reply: **PASS**
The live-accurate scenarios (2b/2c/3) — the ones that match a real call — all PASS.

### Deploy (pass 2)
- Backups chained: `.MLVbak.20260613-205414`, `-205545`, `-205925` (+ the pass-1 `-020515`). ROLLBACK to any.
- py_compile OK each step; aim-voice-agent restarted ONLY (re-registered clean, agent_name=manager, 0 traceback).
- Box `aim_voice_agent.py` md5 `3152539f31f6d0073d1a3c8997a1bee9` == repo `_inbound_ref/aim_voice_agent.DEPLOYED.py`.
- EARNER GATE held GREEN through every restart: agent.py md5 `9150fabe...` UNCHANGED, famit-agent ActiveEnter
  `2026-06-10 19:58:18` (never restarted), famit-caller `/health` 200, **0 real 5xx** (the only `5xx`-regex
  hits were `304 Not Modified` on `/me/entitlements` — false positives).

## Residual / final acceptance (HONEST)
- **The reported bug is fixed**: mid-call Hindi↔English switching mirrors reliably in the real LLM chain.
- **The founder's recipe works in the live-accurate smoke**: neutral greeting → caller English → English reply;
  caller Hindi → Hindi reply.
- **Only a REAL inbound call to +918071583488 is the true end-to-end proof** — the smoke proves the LLM chain;
  STT (Sarvam auto) + TTS in the wild is what the founder must hear. STT is confirmed auto/multilingual
  (`SARVAM_STT_LANG` unset → `"unknown"`).
- Known soft edge: on a turn the model may sprinkle a little Hinglish ("Haan ji", "kaun sa") into an otherwise
  English reply — natural Indian phone register, not a regression; substance mirrors the caller.
- STT `"unknown"` can occasionally mis-detect Hindi as a neighbouring Indic script; not regressed here.
- Smoke harness kept at `_inbound_ref/_mlv_mirror_smoke.py` (reads keys from `.env` at runtime — no secrets in repo).
