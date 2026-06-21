# A2 / A3 BRAIN STEPS — STATE (crash-safe, read on "continue")

Earner-critical, BRAIN/LOGIC-ONLY, VOICE BYTE-IDENTICAL.
Baseline = A1 (deployed + founder-validated). NEW baseline files on box already have A1 edits.

## BOX
`ssh -i ~/.ssh/do-blr-test/id_ed25519 -o StrictHostKeyChecking=no famit@168.144.153.145`
files `/opt/famit-agent/`. Service `famit-agent` (worker "capsy").

## GROUND TRUTH (pulled 2026-06-19, pre-A2)
- agent.py live md5 `3cb618977345fa995a1e1b2377ebea20` (54882 B)
- prompt.py live md5 `c2ee6b03c64b4ee5d3512676ef9f0670` (55359 B)
- langdetect.py live md5 `0b1044ee86b82d8d57b99d5337525d6e`
- TTS region (agent.py sed 540,640) md5 `4d1a1226d4fe798aeb79fb5ee49b9245` — MUST stay identical
- env: OPENER_IN_CTX=0, OPENER_ALREADY_SAID=1, LLM_CLOSE=1, EL_STABILITY=0.55, LANG_MIRROR_V2=1
- KERNEL_OUTBOUND: NOT in agent.py at all (kernel path not referenced) ✓
- NRestarts=0, service active, MainPID 4155915

## THE ONE LAW
NEVER touch TTS constructors (agent.py ~540-640 elevenlabs.TTS/VoiceSettings/AgentSession voice
params), .env EL_STABILITY=0.55, KERNEL_OUTBOUND (stays 0). Read ACTUAL code before each edit.
Back up before each step. After deploy assert: TTS region byte-identical, EL_STABILITY=0.55,
KERNEL_OUTBOUND=0/absent, worker re-registers, NRestarts=0, zero new-PID errors, no active call.

## A2 — time-aware LLM greeting (never hardcoded)
Inject REAL IST time-of-day so opener "good morning/afternoon/evening" is correct + LLM-generated.
Sites: `_llm_opener()` sysmsg (agent.py ~235-243) [PRIMARY — opener is spoken here via session.say]
+ `build_system_prompt` (prompt.py). Reuse IST math (agent.py:166-168 pattern). Confirm LLM_CLOSE=1.
- backups: `agent.py.A2bak.20260619-084951` / `prompt.py.A2bak.20260619-084951`
- STATUS: [x] edit  [x] deploy  [x] verify  ==> DEPLOYED-VERIFIED
- deployed md5: agent.py `7791e50fa506e01d3bd9477dc5450421`, prompt.py `a158d1013365d899e8159ce937a08c29`
- TTS+session block md5 `805c4acb56dddb2b8dffaa642f19eb89` == A2bak (byte-identical) ✓
- worker "capsy" re-registered id AW_ktWWVvQZKR8J, NRestarts=0, MainPID 4167455, ZERO new-PID errors ✓
- A2 ROLLBACK: ssh ... 'cd /opt/famit-agent && cp agent.py.A2bak.20260619-084951 agent.py && cp prompt.py.A2bak.20260619-084951 prompt.py && sudo systemctl restart famit-agent'

## A3 — ElevenLabs-friendly output
A3a (prompt.py): ABSOLUTE brain rules — NEVER digits/₹/%/'/'or any symbol (numbers/prices in WORDS);
adaptive punctuation , . … — for pauses; adaptive NON-hardcoded fillers (vary every turn, never same,
never always-filler-first); ALL-CAPS only for English emphasis; NEVER non-Devanagari Indic script.
A3b: `tts_node` override in `_MirrorAgent` (agent.py ~795) gated by TTS_NORMALIZE (DEFAULT "0" =
identity passthrough = ZERO live change). When on, runs voice_kernel/speech/normalize.py normalize_text
on LLM text before TTS. BEFORE wiring: unit-test normalize_text vs 15+ real LLM lines from journal —
confirm NOT mangling acronyms (AC/ID)/phone/Devanagari; only wire if clean; keep TTS_NORMALIZE=0.
- backups: `agent.py.A3bak.20260619-085614` / `prompt.py.A3bak.20260619-085614`
- STATUS: [x] A3a edit  [x] unit-test normalize  [SKIP-WIRE] A3b  [x] deploy  [x] verify
- A3a = DEPLOYED-VERIFIED (prompt.py only). agent.py UNCHANGED (md5 7791e50f == A2). prompt.py md5 635d8205f0ed8ce324809f2a1a62a95c
  worker "capsy" re-registered AW_u2gS2vqoL8Ku, MainPID 4171653, NRestarts=0, ZERO new-PID errors,
  TTS block 805c4acb == A3bak ✓, EL_STABILITY=0.55, KERNEL_OUTBOUND absent.
- A3b = NOT WIRED (deliberate, earner-safe). normalize_text FAILED the real-line quality gate:
  test = droplet_work/_a2a3_live/test_normalize_realjournal.py (24 real journal lines). Structural
  asserts (acronyms/Devanagari/phone) PASSED, but adversarial review found 4 mangling bugs:
    BUG1 "3-5 din" -> "teen May din" (hyphen range misread as a DATE) — CRITICAL
    BUG2 "45000" -> "four five zero zero zero" (4-digit PRICE read digit-by-digit; should be "forty-five thousand")
    BUG3 "1250 sq ft" -> "one two five zero square feet" (same 4-digit bug)
    BUG4 Devanagari digits "६.५/१८%" NOT normalized (inconsistent w/ Latin)
  Task said "only wire if clean" -> NOT clean -> did NOT add the normalizer-calling tts_node to live.
  A3a's source-side "numbers in WORDS / no symbols" rules deliver the benefit WITHOUT the transform risk.
  TO ENABLE A3b LATER: fix normalize.py BUG1 (exclude hyphen ranges from _DATE_NUM_RE), BUG2/3
  (4-7 digit bare numbers in a money/qty context -> cardinal not digit-by-digit), BUG4 (Devanagari
  digit handling); re-run the test to PASS the quality bar; THEN add tts_node(self,text,model_settings)
  to _MirrorAgent gated by TTS_NORMALIZE (default "0"); buffer the full stream before normalize to avoid
  chunk-split mangling; keep default OFF; deploy + verify voice-safe.
- A3 ROLLBACK (prompt only): ssh ... 'cd /opt/famit-agent && cp prompt.py.A3bak.20260619-085614 prompt.py && sudo systemctl restart famit-agent'

## ROLLBACK (one command per step)
- A2: `ssh ... 'cd /opt/famit-agent && cp agent.py.A2bak.<ts> agent.py && cp prompt.py.A2bak.<ts> prompt.py && sudo systemctl restart famit-agent'`
- A3: `ssh ... 'cd /opt/famit-agent && cp agent.py.A3bak.<ts> agent.py && cp prompt.py.A3bak.<ts> prompt.py && sudo systemctl restart famit-agent'`
- TTS_NORMALIZE wiring only: set env TTS_NORMALIZE=0 (already default) → no-op.

## BRAIN RECON: read `sudo journalctl -u famit-agent --since "8 hours ago"` — report only.
