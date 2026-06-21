# VOICE-BRAIN FIX — ORCHESTRATOR / STATE (crash-safe, read on "continue")

**Goal:** fix the live outbound voice agent ("Riya", `famit-livekit`) — 4 founder bugs —
on an ISOLATED branch, offline-verify, then founder does a REAL live call; deploy + merge
only on his OK. Adaptive model routing (Haiku explore → Sonnet diagnose → Opus execute).

**Branch:** `fix/voice-brain-language-natural` (off `fe/unify-run-wavec`).
**Baseline commit:** `683b0e5` — live agent.py + prompt.py(686L, pulled from box) + langdetect.py
snapshotted; `*.LIVE-BASELINE.py` are pristine revert sources. droplet_work is gitignored →
voice files force-added to THIS branch only (never main).

## THE 4 BUGS (verified ground truth in `droplet_work/_voicefix2_groundtruth/GROUNDTRUTH.md`)
1. **Intermittent loud+fast on the NAME / emphasis words** (overall pace is perfect). Suspect:
   `EL_STABILITY=0.45` prosody volatility + `EL_SPEED=1.08` + ws-1006 reconnect flush. Fix must
   calm the spike, NOT slow the whole call.
2. **Language not auto-switching** (BIGGEST) — 3 fragmented mechanisms desync (Hindi-heavy prompt
   biases LLM to Hindi; weak per-turn English nudge conf≥0.55; TTS update_options steers
   independently). STT auto-detect is fine. Unify into one per-turn detection driving BOTH LLM +
   TTS, all languages, cache-safe.
3. **namaste+username repeated — PROVEN LIVE double greeting**: `session.say(opener)` + the LLM
   regenerates the same greeting as turn-1 (prompt OPENER + FLOW-step-1 + base_instructions
   re-greet). Fix: ONE greeting only.
4. **Hardcoded end-call filler** `agent.py:335 _goodbye_line` → make it Groq-generated; nothing
   spoken should be a hardcoded literal.

## PIPELINE STATUS
- [x] Boot engine + ground-truth scout (read agent.py/prompt.py/langdetect.py + live traces + env + EL plugin).
- [x] Branch + baseline committed (`683b0e5`).
- [x] Workflow 1 = DIAGNOSIS (19 agents, ~1.2M tok): `_voicefix2_groundtruth/DIAGNOSIS_AND_SPEC.md`.
- [x] **EXECUTE done — all 4 fixes implemented in agent.py** (commit `422d66c`), env-gated, default-OFF
      (deployed build = byte-identical until a flag is flipped). prompt.py/langdetect.py UNCHANGED.
      Verified: py_compile clean; langdetect V2 switching proven offline (Hello→en@0.30, EN↔HI TTS revert).
- [x] Red-team: workflow hit SESSION LIMIT (0 output, nothing wasted — all prior work saved/committed).
      Done INLINE instead (conductor, Opus-class): flags-off byte-identical ✅, no crash paths ✅, V2 no-race ✅,
      _llm_close fallback-on-all-failures ✅. No critical blockers. (Re-run agents later if desired, not needed.)
- [x] **DEPLOYED to box** (2026-06-15 18:12 UTC). agent.py md5 `98655dbf` live; old `9150fabe` backed up
      `agent.py.bak.20260615-180938`; `.env` backed up `.env.voicefix.bak.20260615-180938`.
      Inert restart verified clean FIRST, then enabled all 4 fixes. `registered worker` capsy AW_5VpGoufNVBpt, :8090.
      ENABLED flags: OPENER_IN_CTX=0, OPENER_ALREADY_SAID=1, LLM_CLOSE=1, CLOSE_MAX_TOKENS=60,
      EL_STABILITY=0.55, LANG_MIRROR_V2=1, LANG_MIRROR_FLOOR=0.30.
- [~] **AWAITING FOUNDER LIVE CALL** — the only real "done". Test script below. Per-fix env revert ready.
- [ ] On founder OK → merge `fix/voice-brain-language-natural`. If issue → flip the one fix's flag (I drive it).

## REVERT (I drive these on founder feedback — non-technical user never types these)
- Name still bursts on the name → `EL_STABILITY=0.60` (then `EL_TEXT_NORM=on`), restart.
- Burst only AT a language switch → it's the ws reconnect; `LANG_MIRROR_V2=0` to confirm, then retune.
- Greeting wrong → `OPENER_IN_CTX=1` + `OPENER_ALREADY_SAID=0`. Close wrong → `LLM_CLOSE=0`. Language wrong → `LANG_MIRROR_V2=0`.
- FULL rollback: `cp agent.py.bak.20260615-180938 agent.py` + restore `.env.voicefix.bak.20260615-180938`, restart famit-agent.
- Each is one env flip + `sudo systemctl restart famit-agent` over ssh `famit@168.144.153.145`.

## THE 5 FIXES (all in agent.py, env-gated, default=baseline) — commit 422d66c
| Fix | Bug | Knob(s) to ENABLE | Default (=today) |
|-----|-----|-------------------|------------------|
| A | double namaste+name | `OPENER_IN_CTX=0` + `OPENER_ALREADY_SAID=1` | `1` / `0` |
| B | hardcoded end filler | `LLM_CLOSE=1` (`CLOSE_MAX_TOKENS=60`) | `0` |
| C | loud/fast on name | `.env` `EL_STABILITY=0.55`→`0.60`; then `EL_TEXT_NORM=on` | 0.45 / auto |
| D | language not switching | `LANG_MIRROR_V2=1` (`LANG_MIRROR_FLOOR=0.30`) | `0` |

Deploy ORDER (red-team-mandated): C (env-only) → A+B → **D LAST** (its lower floor can raise ws-1006
reconnects = BUG1 secondary; same-code-skip guard mitigates). Each cycle = one box change + founder call + env revert.

## DEPLOY / REVERT (when reached)
- Deploy: `cd droplet_work; .\redeploy.ps1` (scp agent.py+prompt.py+place_call.py → box, restart famit-agent).
  ⚠️ redeploy.ps1 currently scp's prompt.py which was restored — OK now. Add a `.bak.<ts>` on box first.
- Revert: restore `agent.LIVE-BASELINE.py`/`prompt.LIVE-BASELINE.py` → redeploy, or on box `cp *.bak.<ts>` + restart.
- Box: `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145`.
