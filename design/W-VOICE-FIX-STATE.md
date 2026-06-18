# W-VOICE-FIX-STATE — build progress (branch fix/realtime-voice-kernel-v2)

Branch-only. No box edits, no caller.py, no agent restart. Baseline tests: 340 passed.

## UNITS (each = one verified commit)
- [x] Unit A — kill "AI assistant" in legacy outbound. COMMITTED 7869f21.
- [x] Unit A2 — inbound aim_voice_agent.py self-label kill (incl. :2839 spoken greeting + :2109 spoken error). COMMITTED 3a361d9.
- [x] Unit B — double-greeting: OPENER_ALREADY_SAID default "1", OPENER_IN_CTX default "0"; OPENER section conditional in prompt.py; FLOW step-1 greet verb stripped; systemd drop-in shipped. DONE (commit pending w/ C+D+E).
- [x] Unit C — grammar: agent.py Groq prompt pins first-person; prompt.py FLOW step-2 + anti-pattern "never आपने call किया". DONE.
- [x] Unit D — neutral prosody: EL_STABILITY 0.65, EL_SPEED 1.0 (agent.py defaults); prosody fillers OFF by default (VOICE_FILLERS gate); SARVAM_TTS_PACE 1.0. DONE.
- [x] Unit E — kernel reconcile MISS#2: _guardrail "never admit, redirect" both langs. Wire-on cutover stays gated OFF (KERNEL_OUTBOUND default OFF — not flipped). DONE.
- [x] Tests — voice_kernel/tests/test_voicefix_w_voice_fix.py: 27 tests (no-AI-label x7 shapes, one-greeting, neutral prosody, hinglish grammar, kernel disclosure, repo-wide grep). 367 total green.
- [ ] memory/wave_runs/W-VOICE-FIX.md append. IN PROGRESS.

## STATUS: all units built + green (367 passed). Kernel OFF-identity intact (46 passed). Committing B-E + test + drop-in, then memory append.

## KEY DECISIONS
- Reconcile MISS#2: founder rule overrides kernel's honest-disclose. _guardrail reworded to "never admit, warmly redirect" in BOTH eng+hinglish.
- Output-boundary scrub (MISS#3): _llm_opener asserts contains_banned_phrase==False, else clean fallback. Negative guards use generic "kabhi AI/bot/assistant mat kehna", never quote the banned token.
- Prosody fillers: gate behind apply_prosody(..., fillers=False) for outbound; default keeps inbound behavior.
