# W-VOICE-SURGICAL-PLAN — old PERFECT voice, new BRAIN (design, NO deploy)

**Date:** 2026-06-18
**Box:** `famit@168.144.153.145` · `/opt/famit-agent/`
**Live verified now:** `agent.py` md5 `98655dbf` · `prompt.py` md5 `fb87ea56` · `KERNEL_OUTBOUND` UNSET.
Offending env still live: `.env:164 OPENER_IN_CTX=0`, `:165 OPENER_ALREADY_SAID=1`, `:168 EL_STABILITY=0.55` (+`:169 LANG_MIRROR_V2=1`, `:170 LANG_MIRROR_FLOOR=0.30`).
**Companion:** `design/W-VOICE-RESTORE-DIAGNOSIS.md` (the diagnosis this plan executes).

> SCOPE: design only. This file does NOT mutate the box, edit any `.py`, deploy, or rebuild. It specifies (A) the minimal "AI assistant" fix, (B) the old-voice + new-brain integration behind a flag default OFF, and (C) a gated rollout. The deploy itself is the separate founder-gated step.

---

## 0. THE GOVERNING PRINCIPLE (one line)

**The voice path is sacred and stays byte-identical to `98655dbf`. Only the SYSTEM PROMPT (the brain) and ONE disclosure string change.** Every edit below is on the BRAIN side of the clean split in DIAGNOSIS §5. The TTS/STT/LLM-construct/endpointing/VAD/opener-`say()`/language-mirror code is NEVER touched.

Two independent, separately-gated changes — ship and validate them in order:

| Step | What | Risk | Gate |
|---|---|---|---|
| **A** | Minimal "AI assistant" → neutral disclosure (1 source line + 3 env removals) | LOW | voice byte-identical except the one phrase; real ring-test |
| **B** | Old voice + NEW brain (W1–W7 kernel system prompt only) behind `KERNEL_OUTBOUND`, default OFF | HIGH (brain swap) | W17 green + real ring-test; OFF = byte-identical |

A is shipped and proven FIRST (perfect voice, no "AI assistant", brain otherwise unchanged). B is shipped second, behind its own flag, only after A is validated live.

---

## PART A — THE MINIMAL "AI ASSISTANT" FIX (surgical, voice untouched)

### A.1 What changes (exactly three things, nothing else)

1. **ONE source line** — `agent.py:218`, the hardcoded disclosure FALLBACK string.
2. **THREE `.env` line removals** — restore the perfect-voice code defaults (DIAGNOSIS §2a/§2b). These are NOT new edits; they DELETE my regressions so the byte-identical defaults take over.
3. **Nothing else.** No prosody knob, no opener flow, no `ex_role`, no `_llm_opener` sysmsg restructure, no drop-in, no `prompt.py` change.

### A.2 The exact minimal diff — `agent.py:218`

**Current (live `98655dbf`):**
```python
    disc_phrase = (disclosure_phrase or f"{company} की एक AI assistant").strip()
```

**After (neutral company affiliation — no AI self-label volunteered):**
```python
    disc_phrase = (disclosure_phrase or f"{company} से").strip()
```

Rationale for the replacement text:
- `f"{company} से"` = "from {company}" — a neutral affiliation. When a campaign passes its own `disclosure_phrase` (today's live campaigns do), behaviour is unchanged — the fallback is only the `or` branch. When a campaign passes NOTHING, the model now says "मैं {agent_name}, {company} से बोल रही हूँ" instead of "…{company} की एक AI assistant…". This kills the latent landmine (710 historical journal hits) with zero new behaviour for configured campaigns.
- It deliberately MATCHES the existing `disclose=False` fallback wording already in the file (`agent.py:225`: `f"…{company} से {speaking}…"`) — so we are reusing a phrase the perfect build already speaks, not inventing one.

**Downstream consumers — verified safe, no further edit needed:**
- `agent.py:220-222` fallback line: `…मैं {agent_name}, {disc_phrase} {speaking}।` → becomes `…मैं {agent_name}, {company} से बोल रही हूँ।` (grammatical, matches the `disclose=False` line).
- `agent.py:231-232` `disc_clause`: `…तुम {disc_phrase} हो…` → becomes `…तुम {company} से हो…` ("you are from {company}"). Grammatical Hinglish, no AI label. The LLM is instructed to give "a short natural disclosure that you are {disc_phrase}" — with the neutral phrase it discloses company affiliation only, which is exactly the founder's intent and TRAI-friendly (company identity is disclosed; no machine self-label is forced).

> Note: this is intentionally the SMALLEST possible change — only the fallback DEFAULT. We do NOT restructure `_llm_opener`, do NOT remove the `disclose` parameter, do NOT touch the `gender_clause`/`speaking` logic. One token-string swap.

### A.3 The three `.env` removals (restore perfect-voice defaults)

Delete these lines from `/opt/famit-agent/.env` (DIAGNOSIS §2a/§2b — none ever existed in the 43 working-build backups):

```
EL_STABILITY=0.55          # → code default 0.45 (expressive prosody = the perfect voice)
OPENER_ALREADY_SAID=1      # → code default off (old build never set it)
OPENER_IN_CTX=0            # → code default 1   (old build never set it)
```

Leave `LANG_MIRROR_V2=1` / `LANG_MIRROR_FLOOR=0.30` for now (language behaviour, not the prosody regression — DIAGNOSIS §3; non-load-bearing, defer to Part B validation).

### A.4 The PROOF test for Part A — "voice byte-identical except that one phrase"

Goal: prove the voice PATH is unchanged and ONLY the disclosure phrase differs. Three layers, all runnable WITHOUT a live call first, then the real ring.

**A.4.1 — Static voice-constructor diff (must be EMPTY).**
Diff the new `agent.py` against the `98655dbf` golden, restricted to the voice-path line ranges (DIAGNOSIS §5). The only allowed hunk is line 218.
```bash
# on box, doc-only verification recipe (NOT run in this wave)
diff <(sed -n '563,631p' agent.py.NEW) <(sed -n '563,631p' agent.py.98655dbf)   # MUST be empty (TTS/STT/LLM/session)
diff <(sed -n '878,884p' agent.py.NEW) <(sed -n '878,884p' agent.py.98655dbf)   # MUST be empty (opener say())
diff <(sed -n '451,457p' agent.py.NEW) <(sed -n '451,457p' agent.py.98655dbf)   # MUST be empty (opener gating)
diff agent.py.NEW agent.py.98655dbf | grep -c '^[<>]'                            # MUST be exactly 2 (the one line, -/+)
md5sum agent.py.NEW                                                               # records the new single-line hash
```
ACCEPT only if the three range-diffs are empty AND the whole-file diff is exactly the one line.

**A.4.2 — Disclosure unit assertion (the phrase actually changed, nothing else).**
A tiny offline harness importing the `_llm_opener` fallback logic (or replaying it) asserts:
- with `disclosure_phrase=""` (fallback path): output contains `"{company} से"` and DOES NOT contain `"AI assistant"`, `"AI "`, `"असिस्टेंट"`, or any R1 banned self-label (reuse `voice_ops/eval/regression_gates.contains_banned_phrase`).
- with `disclosure_phrase="<campaign value>"` (configured path): output is IDENTICAL to the `98655dbf` output (the `or` short-circuits — configured campaigns see ZERO change).
- the `disclose=False` branch output is byte-identical to `98655dbf` (untouched).

**A.4.3 — W17 R1 gate (the #1 rule, automated).**
Run `pytest voice_ops/eval/tests/test_regression_gates.py -k R1` and `scan_repo_for_ai_self_label()` against the patched sources — must stay GREEN, and the negative control (a leaky builder) must still FAIL. This proves no AI self-label can reach the spoken disclosure.

**A.4.4 — `.env` parity check.**
After the three removals: `grep -E 'EL_STABILITY|OPENER_ALREADY_SAID|OPENER_IN_CTX' /opt/famit-agent/.env` returns EMPTY → code defaults `0.45` / off / `1` apply.

**A.4.5 — The real ring-test (the only acceptance truth).**
Founder places ONE real outbound call on a campaign with NO `ai_disclosure` configured. Listen for: (1) voice subjectively == the perfect old worker (expressive, right pace/loudness, single greeting, name said once); (2) the agent says "{company} से" affiliation, NEVER "AI assistant". Revert path armed (restore `agent.py.98655dbf` + the `.env` lines) before the call.

---

## PART B — OLD VOICE + NEW BRAIN (W1–W7 system prompt only, behind a flag)

### B.1 The architecture — the brain seam ALREADY exists and is voice-isolated

The W1–W7 kernel was built precisely to provide the BRAIN through ONE tracked façade without touching the voice path. The seam is `voice_kernel/integrations/outbound.py` (git-tracked, revertable), gated by `KERNEL_OUTBOUND` (default OFF), documented in `W-INT-OUTBOUND-PATCH.md`. **For THIS wave we apply ONLY the instruction (brain) seam of that patch and DELIBERATELY OMIT the voice seams.**

What the brain seam provides to the OLD worker — the SYSTEM PROMPT ONLY:
- **Vendor-script flow** authoritative (W3): greet→confirm→intro→reason→qualify→pitch→objections→close ordering from the vendor's raw_script overrides the default framework.
- **Full lossless campaign brief** (W3): the whole brochure reaches the prompt inside the `<campaign_brief>` fence — fixes the lossy 3-5-field compression.
- **RAG** (W4/W5 suffix) and **cross-call + WhatsApp memory** (W7): folded into the prompt prefix/`enrich_prefix`, never into TTS.
- **The greeting PATTERN** (already in `prompt.py:308-310`, KEPT): good-morning → "greetings from {company}" → "क्या मैं {lead_name} जी से बात कर रही हूँ?" → **WAIT** → reason + permission → proceed. The kernel renders this same learned-not-hardcoded pattern; it tunes wording/objection-handling around it.

### B.2 The clean wiring — apply ONLY Patch A + Patch B + Patch C of W-INT-OUTBOUND-PATCH

From `W-INT-OUTBOUND-PATCH.md`, apply EXACTLY these (the brain), and NOTHING else:

- **Patch A** (`:404` area) — the flag + `_OK` façade slot. OFF ⇒ no `voice_kernel` import.
- **Patch B** (`:461` area) — build the per-call façade `_OK = build_for_call(...)` from the campaign-record owner tenant (C2 fail-closed). Wrapped in `try/except → _OK=None` so it can NEVER break the earner.
- **Patch C** (`:461` area) — the instruction source swap:
  ```python
  _legacy_instr = lambda: base_instructions      # verbatim 98655dbf system prompt
  if _KERNEL_OUTBOUND and _OK is not None:
      instructions = _ko.assemble_outbound_instructions(_OK, legacy_render=_legacy_instr, fields=fields, recap=recap)
  else:
      instructions = _legacy_instr()              # OFF: byte-identical to today
  ```
  This is the ENTIRE brain swap: `instructions` (the system prompt string handed to the agent) comes from the kernel when ON, from the legacy `build_system_prompt(fields)` when OFF.

**EXPLICITLY DO NOT APPLY (these are the VOICE path — keep `98655dbf` verbatim):**
- ❌ **Patch D** (TTS provider router / Sarvam swap, `:563-582`). The perfect voice IS ElevenLabs `QTKSa2Iyv0yoxvXY2V8a` @ stability `0.45`/speed `1.08`. The brain wave must NOT route TTS. Leave the `elevenlabs.TTS(...)` block unconditional and untouched. (The Sarvam router is a SEPARATE, later, ring-gated wave — not part of "new brain".)
- ❌ **Patch E** (per-turn HOT hook / RAG inject) — OPTIONAL even in the patch; for the brain-only cutover keep it SHADOW (log-only) or omit. No per-turn behaviour change to the voice/turn-taking.
- ❌ **Patch F/G** (post-call memory write + box memory bind) — additive and safe, but defer to a follow-up; the first brain cutover needs only the system prompt. (If included, they only ADD a post-call DB write; they do not touch the voice path. Acceptable but not required for B.)

> Net agent.py edit for Part B = Patches A+B+C only ≈ **~22 lines, every one OFF-gated**, ALL in `entrypoint` before the agent is constructed, NONE inside any voice constructor. Total over A+B: the single line 218 + ~22 gated brain lines. Voice constructors: **zero edits.**

### B.3 The greeting pattern (founder's requirement) — learned, enforced, not hardcoded

The kernel's rendered system prompt MUST carry the founder's pattern as a parameterized flow (it already does via the W3 vendor-script fold + the kept `prompt.py:308-310` shape):
1. WARM GREET ("good morning / नमस्ते") + "greetings from {company}".
2. CONFIRM IDENTITY: "Am I speaking with Mr/Ms {lead_name}?" → **WAIT for the caller's yes** (a hard PAUSE directive, not a monologue).
3. REASON + PERMISSION: "I called about {product} — do you have two minutes?" → wait.
4. Proceed with the campaign flow.

This is `{company}`/`{lead_name}`/`{product}`-parameterized per campaign — LEARNED from the vendor brief, never a hardcoded script. W17 **R5** enforces EXACTLY ONE structural `OPENING:` directive (no double-greet, no missing opener). The opener itself is still DELIVERED by the OLD worker's `session.say()` at `:884` (voice path untouched) — the brain only AUTHORS the words, the perfect voice SPEAKS them.

### B.4 The regression gate for Part B — W17 + the brain-specific invariants

**B.4.1 — W17 full suite (the automated deploy gate).** `pytest voice_ops/eval/` must be GREEN, driving the REAL `voice_kernel.integrations.outbound` seam (the same one Patch C uses) with `KERNEL_OUTBOUND` flipped ON in-process. The binding decision is `run_all_gates().passed`. Negative controls must still BITE. This proves, before any box mutation:
- **R1** — no "AI assistant"/any self-label in the spoken disclosure (the #1 rule) + repo scan.
- **R2** — vendor script DRIVES a flow slot (not echoed) — the brain upgrade is real.
- **R3** — full campaign brief lossless inside `<campaign_brief>`.
- **R5** — EXACTLY ONE greeting (no double-greet) — the founder's pattern, once.
- **R7** — language adapts per turn, keeps prior, never English-only.
- **R10** — cross-vertical isolation (no leak).

**B.4.2 — VOICE-UNCHANGED proof (the part W17 does not cover).** Because Part B must prove the VOICE path is byte-identical with the brain ON:
- Static: the same range-diffs as A.4.1 (`:563-631`, `:878-884`, `:451-457`) MUST be empty against `98655dbf` even AFTER Patches A+B+C — confirming the brain seam added NO voice-constructor edit.
- `choose_tts` is NOT wired (Patch D omitted) ⇒ TTS is unconditionally the EL block ⇒ provider/voice_id/stability/speed identical ON or OFF.
- OFF-identity: with `KERNEL_OUTBOUND` unset, the rendered system prompt for the golden campaign == the `98655dbf`+legacy output byte-for-byte (the `_legacy_instr()` branch).

**B.4.3 — The four founder hard checks on the brain ON (real ring + replay):**
1. **No double-greeting** — W17 R5 + a real call: single greeting only.
2. **No username-repeat** — the name is said once in the opener, never re-greeted (the kernel prompt instructs "you have already opened"; this is now in the PROMPT, not the `OPENER_ALREADY_SAID` env hack — so we do NOT re-introduce that env var; the brain owns it).
3. **No "AI assistant"** — W17 R1 + real call.
4. **Voice unchanged + brain upgraded** — founder hears the perfect voice AND a smarter conversation (uses the full brief, follows the vendor flow, handles objections).

**B.4.4 — Replay before deploy.** Take a REAL recorded transcript that previously showed the dumb-brain behaviour (`transcripts/{room}.json`), run it through `replay.replay_conversation(...)` with the kernel ON, and confirm the brain WOULD now handle it correctly (R1/R2/R3/R5/R7 invariants hold) — offline, no call, no box.

---

## PART C — THE GATED ROLLOUT (step-by-step, one box-mutating change at a time)

Each step is ONE box mutation with a revert path armed BEFORE it, then validated on a REAL call before the next.

### Step 0 — Pre-flight (no mutation)
- Confirm live md5: `agent.py 98655dbf`, `prompt.py fb87ea56`, `KERNEL_OUTBOUND` unset. ✅ (verified 2026-06-18).
- Back up: `cp /opt/famit-agent/agent.py agent.py.RESTOREbak.<ts>` and `cp .env .env.RESTOREbak.<ts>`.
- `pytest voice_ops/eval/` GREEN on the current kernel (gate is alive).

### Step 1 — Ship Part A ONLY (perfect voice + no "AI assistant")
1. Apply the single `agent.py:218` edit (A.2).
2. Remove the three `.env` lines (A.3).
3. Run A.4.1–A.4.4 (static diff = 1 line, disclosure unit, R1 gate, env parity) — ALL must pass.
4. `systemctl restart famit-agent`.
5. **Founder real ring-test (A.4.5):** voice == perfect old worker; says "{company} से", never "AI assistant".
6. **VALIDATE & SOAK:** run live for a real session window. If anything is off → revert (`cp agent.py.RESTOREbak agent.py` + restore `.env` + restart). Do NOT proceed to Step 2 until A is confirmed good on a real call.

> After Step 1: the founder has the PERFECT VOICE with NO "AI assistant" — the immediate win — and the brain is still the old (rolled-back) brain. This already resolves the cosmetic landmine and restores prosody, independent of the bigger brain change.

### Step 2 — Ship Part B behind the flag, default OFF (brain code present, dormant)
1. Apply Patches A+B+C from W-INT-OUTBOUND-PATCH (B.2). Do NOT apply D/E/F/G.
2. Deploy `voice_kernel/` to the box (tracked package; import-safe, droplet-free).
3. Keep `KERNEL_OUTBOUND` UNSET. Restart.
4. **OFF-identity proof:** the live behaviour is byte-identical to end-of-Step-1 (B.4.2 OFF-identity; real ring still the perfect voice + old brain). The brain code is present but dormant.
5. VALIDATE: a real call confirms ZERO change from Step 1 with the flag OFF.

### Step 3 — Flip the brain ON (the one dangerous mutation) — canary
1. `pytest voice_ops/eval/` GREEN (B.4.1) + replay the regressed transcript (B.4.4) GREEN — BEFORE touching the flag.
2. Set `KERNEL_OUTBOUND=1` via the **systemd drop-in** (NOT the shared `.env` — W3 LEARNINGS §2: shared `.env` flags can leak; isolate to the outbound unit). Restart.
3. **Founder real ring-test (B.4.3):** voice unchanged (perfect), brain upgraded (full brief + vendor flow + objections), single greeting, name once, no "AI assistant".
4. Canary: a small number of real calls. Watch the journal for R1 violations, double-greets, latency regressions.
5. If ANY regression → `KERNEL_OUTBOUND=0` + restart (instant revert; voice path was never touched so the floor is the perfect voice + old brain). Diagnose in the kernel/prompt, NOT by editing the voice path.
6. Only after the canary is clean → leave ON.

### Rollback ladder (always available)
- Brain misbehaves → `KERNEL_OUTBOUND=0` + restart → back to old brain, perfect voice. (No voice risk — Patches D/E not applied.)
- Disclosure/voice issue → `cp agent.py.RESTOREbak agent.py` + restore `.env` + restart → back to `98655dbf`.
- Each step is independently revertable; B never built on an unproven A.

---

## RECOMMENDATION FOR THE FOUNDER (plain)

**Do it in two clean moves, not one.**

1. **First, the tiny fix (Part A) — ship today.** It is a ONE-WORD change in the code (replace the hidden default "AI assistant" with "from {company}") plus deleting three settings lines that were quietly flattening the voice. This INSTANTLY gives you back the perfect voice you spent a month tuning AND stops the agent ever calling itself an "AI assistant" — with essentially zero risk, because the voice machinery is not touched at all. One real test call proves it.

2. **Then, the smarter brain (Part B) — ship behind an OFF switch, flip it only after a real call.** The new brain (full brochure, follows your vendor script, your exact greeting — "greetings from {Company}, am I speaking with Mr/Ms ___?" → wait → reason → permission) plugs in as the system PROMPT ONLY, through a switch that is OFF by default. The voice stays your perfect voice — we deliberately do NOT let the new system touch how it SOUNDS (no TTS/Sarvam swap, no prosody, no opener mechanics). We turn the brain ON only after the automated gate (W17) is green and YOU hear a real call confirm: same great voice, smarter conversation, one greeting, no "AI assistant". If anything is off, one switch flips it back instantly — and because we never touched the voice, the worst case is just the old brain with the perfect voice.

**Why two moves:** you get the perfect voice back immediately and safely (Part A), without waiting on or risking it against the bigger brain change (Part B). They are fully independent — A is the guaranteed win, B is the upgrade gated behind a reversible switch and your own ears.

---

## APPENDIX — file:line index (for the deploy wave; re-locate by surrounding code, not raw line #)

| Region | file:line (`98655dbf`/`fb87ea56`) | Part | Action |
|---|---|---|---|
| Disclosure fallback default | `agent.py:218` | A | EDIT (one line → `f"{company} से"`) |
| Fallback opener line | `agent.py:220-222` | A | no edit (consumes :218, stays grammatical) |
| `_llm_opener` `disc_clause` sysmsg | `agent.py:231-232` | A | no edit (consumes :218) |
| Flag + façade slot | `agent.py:~404` | B | ADD Patch A (gated) |
| Build façade `_OK` | `agent.py:~461` | B | ADD Patch B (gated, try/except) |
| Instruction source swap | `agent.py:~461` | B | ADD Patch C (gated) |
| Greeting pattern (KEEP) | `prompt.py:308-310` | B | no edit (kernel renders same pattern) |
| TTS / VoiceSettings | `agent.py:563-582` | — | NEVER touch (Patch D OMITTED) |
| Sarvam STT | `agent.py:592-601` | — | NEVER touch |
| Groq LLM construct | `agent.py:602-618` | — | NEVER touch |
| Session latency/turn knobs | `agent.py:621-631` | — | NEVER touch |
| Opener delivery `say()` | `agent.py:878-884` | — | NEVER touch |
| Opener gating | `agent.py:451-457` | — | NEVER touch |
| `.env` EL_STABILITY/OPENER_* | `/opt/famit-agent/.env:164,165,168` | A | REMOVE (restore defaults) |
| Brain flag (drop-in, not shared .env) | systemd drop-in | B | `KERNEL_OUTBOUND` (default OFF) |
