# W-VOICE-FIX — outbound voice regressions fixed (kill AI self-label, single greeting, neutral prosody, grammar)

Branch: `fix/realtime-voice-kernel-v2` · Date: 2026-06-18 · Scope: BRANCH-ONLY
(no box edits, no caller.py, no agent restart). Earner already rolled back to
`98655dbf` (KERNEL_OUTBOUND=0, live, good). The kernel cutover stays gated OFF.

## What was wrong (founder report + diagnosis + red-team)
The brain cutover made OUTBOUND worse than the old `98655dbf`:
1. Agent self-labeled as "AI assistant" (founder #1 ABSOLUTE rule — never say it).
2. DOUBLE greeting (opener spoken, then the LLM re-greets on turn 1).
3. Variable pace/loudness (sometimes too fast / too loud).
4. Wrong Hinglish grammar ("aapne call kiya" on an OUTBOUND call).
Root cause (diagnosis `design/W-VOICE-FIX-DIAGNOSIS.md`): the clean `voice_kernel`
was NEVER wired into the live agent (`agent.py:27` imports only `prompt`); all four
regressions live in the LEGACY `agent.py` + `prompt.py` defaults. Red-team addendum
found the fix was NOT airtight: it missed the live INBOUND agent (`aim_voice_agent.py`
SPEAKS "AI manager") and a cross-path admit/never-admit contradiction.

## Fixes shipped (all branch-only, reversible, kernel cutover NOT flipped)

- **Unit A (commit 7869f21)** — kill "AI assistant" in the LEGACY OUTBOUND path:
  - `prompt.py` `_opener_verbs` ex_role "AI assistant" -> brand-human "की तरफ़ से";
    `disc_default` -> brand-human framing; curveball/guard rewritten to "never say
    AI/bot/assistant, redirect as the team" (generic, no banned token quoted);
    `GODREJ_FIELDS["ai_disclosure"]` default "" (never bake the phrase).
  - `agent.py` `_llm_opener`: brand-human disclosure default + OUTPUT-BOUNDARY SCRUB —
    a hallucinated "AI assistant" opener is discarded for the clean fallback. Reuses
    `voice_kernel.brain_packs.disclosure.contains_banned_phrase` (single source of truth;
    local fallback block-list when the kernel isn't on the path).

- **Unit A2 (commit 3a361d9)** — kill AI self-label in the LIVE INBOUND agent
  (`aim_voice_agent.py`, red-team MISS #1):
  - `:2839` manager SPOKEN greeting drop "your AI manager" -> "from the {company} team".
  - `:2109` SPOKEN error "the Famit AI Manager hit a problem" -> "the {company} team".
  - `:585/:588` (manager) + `:1452` (customer) prompts: single-phrase negative guard
    replaced with the full block-list pattern from the already-correct `:1560-1567`
    template (never AI/bot/assistant/automated/virtual; if asked, do NOT admit).
  - `:1569` reworded to NOT quote the banned token (MISS #3 priming risk).

- **Units B-E (commit 3ae9318)**:
  - **B (double greeting)** — in-code defaults flipped `OPENER_ALREADY_SAID=1` +
    `OPENER_IN_CTX=0`; the `=== OPENER ===` section is now CONDITIONAL in `prompt.py`
    (default = "you already opened, do NOT re-greet"); the fresh-greet verb is stripped
    from FLOW step-1 (now "CONFIRM IDENTITY"). The spoken opener is the ONE greeting;
    turn-1 is a pure response. Shipped `voice_kernel/systemd/famit-agent.service.d-voicefix.conf`
    (drop-in, NOT shared .env — LEARNINGS §2) pinning the flags + neutral TTS.
  - **C (grammar)** — Groq opener prompt pins first-person ("हमने आपको call किया") + an
    explicit anti-pattern "never आपने call किया — this is OUTBOUND" in FLOW step-2/framing.
  - **D (neutral prosody)** — `EL_STABILITY` 0.45->0.65, `EL_SPEED` 1.08->1.0 (in-code
    defaults; env still overrides). Kernel filler injection gated OFF by default
    (`VOICE_FILLERS`, default 0) so pace/loudness stays consistent (punctuation prosody
    unaffected). `SARVAM_TTS_PACE` 1.05->1.0.
  - **E (MISS #2 reconcile)** — kernel disclosure `_guardrail` reworded from "answer
    honestly" to "never admit, warmly redirect" (eng+hinglish) so the gated-OFF kernel
    cutover can never re-introduce self-disclosure on a direct "are you AI?". KERNEL_OUTBOUND
    stays default OFF (NOT flipped — that's a separate founder-gated box step).

## Greeting now follows the campaign PATTERN dynamically (not hardcoded)
FLOW + OPENER are built from campaign fields per call ({company}/{product}/{credibility}/
{eoi}/{value}). The only hardcoded greeting literal (FLOW step-1's "नमस्ते/good morning")
was stripped. GODREJ_FIELDS is just the fallback dict, overridden per campaign. Pattern:
single warm greet+company (spoken opener) -> confirm name -> WAIT -> reason+permission ->
proceed. No double greeting, no "AI assistant", first-person grammar, neutral delivery.

## Verification (branch-only — NO live calls)
- `python -m pytest voice_kernel/ -q` => **367 passed** (340 baseline + 27 new W-VOICE-FIX).
- New `voice_kernel/tests/test_voicefix_w_voice_fix.py` (27 tests): no AI-label across 7
  field shapes + banned-custom scrub; exactly-one-greeting in both flag states;
  fillers-off-by-default + force-on; neutral EL/Sarvam source defaults; hinglish
  first-person grammar; kernel disclosure clean + guardrail-never-admit; REPO-WIDE grep
  that no shipped path SPEAKS an AI self-label.
- OFF-identity intact: `test_adapter_off_identity` + outbound integration = **46 passed**
  (kernel OFF == byte-identical legacy; `agent.py` md5 path unchanged on OFF).

## Every "AI assistant" path is dead (8 outbound + 4 inbound + kernel guardrail)
- Outbound: prompt.py `_opener_verbs` x2, `disc_default`, curveball, guard, GODREJ default,
  OPENER example line; agent.py `_llm_opener` default + Groq disc_clause — ALL brand-human now,
  + a runtime block-list scrub at the output boundary.
- Inbound: aim_voice_agent.py manager greeting (:2839), spoken error (:2109), manager prompt
  (:585/:588), customer prompt (:1452) — ALL never-admit now.
- Kernel: disclosure builder is clean by construction (asserts no banned phrase); guardrail
  now "never admit, redirect".

## Founder-gated NEXT step (NOT done here — needs a real call)
The branch fix is verified by unit tests only. The REAL proof is a live outbound call:
install the `famit-agent.service.d-voicefix.conf` drop-in on the OUTBOUND box, restart
`famit-agent`, and place ONE real test call. Revert path: remove the drop-in + daemon-reload
+ restart (or set OPENER_ALREADY_SAID=0 / EL_STABILITY=0.45 / EL_SPEED=1.08). KERNEL_OUTBOUND
remains OFF — the kernel cutover is a separate one-box-mutating change with its own smoke.
