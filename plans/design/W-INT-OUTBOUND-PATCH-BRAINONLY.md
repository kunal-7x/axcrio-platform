# W-INT-OUTBOUND-PATCH-BRAINONLY — the SURGICAL brain-only `agent.py` hook

> Branch `fix/realtime-voice-kernel-v2`. **DOC-ONLY / BUILD-ONLY in this wave — NO deploy.**
> 🚨 EARNER LAW: the OUTBOUND earner is `droplet_work/agent.py`, LIVE box md5 =
> **`98655dbfc71d5c3da36bcfe3f848082c`** (the founder's already-live voice fixes;
> NEVER restore an older hash). `droplet_work/` is GITIGNORED + box-only. The
> integration BULK is the TRACKED `voice_kernel/integrations/outbound.py`.
>
> This is the **BRAIN-ONLY** subset of `design/W-INT-OUTBOUND-PATCH.md`, executing
> **`design/W-VOICE-SURGICAL-PLAN.md` Part B**: the W1–W7 kernel feeds **ONLY the
> SYSTEM PROMPT** to the old worker, via the existing façade
> `voice_kernel/integrations/outbound.py`, gated `KERNEL_OUTBOUND` (default OFF).
> The deployable patch = **ONLY Patches A + B + C** (the instruction swap + the
> OFF-gated entrypoint lines). It **DELIBERATELY OMITS Patch D / E / F / G** — those
> are the **VOICE PATH** and must stay the old worker's, **byte-identical**. The
> opener is still SPOKEN by the old worker's `session.say()` (untouched). The founder
> greeting PATTERN is already learned (`prompt.py:308-310`, kept). **NO
> voice/TTS/prosody/opener-mechanics/turn-taking change.**

The tracked façade exposes these functions; the **brain-only** cutover imports and
calls **ONLY `assemble_outbound_instructions`** (plus the flag check). No
`voice_kernel.*` type crosses into the agent:

```
kernel_outbound_enabled, build_for_call, assemble_outbound_instructions   <- USED (A+B+C)
on_turn, plan_speech, choose_tts, on_tts_error, persist_post_call, bind_box_memory  <- NOT used (D/E/F/G — omitted)
```

---

## 0. GOVERNING PRINCIPLE (one line)

**The voice path is sacred and stays byte-identical to `98655dbf`. Only the SYSTEM
PROMPT (the brain) changes.** Every edit below is on the BRAIN side of the clean
split (DIAGNOSIS §5). The TTS/STT/LLM-construct/endpointing/VAD/opener-`say()`/
language-mirror code is NEVER touched. With `KERNEL_OUTBOUND=0` (default) every hunk
is inert ⇒ the call is byte-identical to today.

Line anchors below are against the `98655dbf` golden; the deploy wave MUST re-locate
them by the **surrounding code, not the raw line number** (the founder may bump lines
with future env-gated fixes; the local working copy may differ — e.g. `6c577b9b`).
The companion static test `voice_kernel/integrations/tests/test_voice_unchanged_brainonly.py`
proves, by code landmark, that these two anchors fall OUTSIDE every voice-constructor
span on the real `agent.py`, whatever its current hash.

---

## 1. Patch A — flag + per-call façade slot (top of `entrypoint`)

`entrypoint` is at `:416`. Right after `lead_name` is read, add:

```python
# --- W-INT outbound kernel façade (flag KERNEL_OUTBOUND, default OFF) ----------
_OK = None  # voice_kernel.integrations.outbound.OutboundKernel | None
_KERNEL_OUTBOUND = os.getenv("KERNEL_OUTBOUND", "0") in ("1", "true", "True")
```

OFF ⇒ `_OK` stays None and NOTHING from `voice_kernel` is imported on this path.

---

## 2. Patch B (build the façade) + Patch C (instruction seam)

The legacy code builds `base_instructions` (system_prompt + optional lead-name
append + optional `OPENER_ALREADY_SAID` block + optional `recap`), then
`instructions = base_instructions` at **`:485`** (local `6c577b9b`; re-locate by the
literal line `instructions = base_instructions`). Wrap that WHOLE assembled string as
a zero-arg legacy lambda, build the façade (B), and choose the instruction source (C).
`camp` (loaded by `_load_campaign`) carries the authoritative owning tenant.

**Replace** the single line:
```python
    instructions = base_instructions
```

**with:**
```python
    # --- W-INT-B: build the per-call outbound kernel façade (flag-gated) --------
    # OUTBOUND TENANT (C2 fail-closed): the tenant is the CAMPAIGN RECORD's OWNER
    # (caller.py wrote `rec["tenant_id"]` under that tenant's auth) — NEVER a
    # dispatch-metadata body value. A forged campaign_id has no file (camp=None ->
    # owner "" -> build returns None -> legacy) or carries its TRUE owner.
    if _KERNEL_OUTBOUND:
        try:
            from voice_kernel.integrations import outbound as _ko
            _camp_owner = str((camp or {}).get("tenant_id", "")).strip()
            _OK = _ko.build_for_call(
                tenant_id=_camp_owner,            # campaign-record owner (server-written)
                call_id=room_name,
                lead_phone=phone,                 # mem.parse_phone(room_name)
                campaign_id=str(meta.get("campaign_id", "")),
                campaign_tenant_id=_camp_owner,   # same source -> consistency assert
                fields=fields, recap=recap,
            )
        except Exception as _exc:                 # never break the earner
            logger.warning("outbound kernel facade build failed -> legacy: %r", _exc)
            _OK = None

    # --- W-INT-C: instruction source (OFF/None _OK == byte-identical legacy) ----
    _legacy_instr = lambda: base_instructions     # the verbatim legacy string
    if _KERNEL_OUTBOUND and _OK is not None:
        from voice_kernel.integrations import outbound as _ko
        instructions = _ko.assemble_outbound_instructions(
            _OK, legacy_render=_legacy_instr, fields=fields, recap=recap)
    else:
        instructions = _legacy_instr()             # OFF: byte-identical to today
```

> WHY this anchor: at the seam `base_instructions` is FULLY assembled (the system
> prompt from `build_system_prompt(fields)` + the lead-name/OPENER_ALREADY_SAID/recap
> appends), so the legacy lambda captures the EXACT current string. `instructions`
> (the string handed to the agent / `Agent(instructions=…)`) comes from the kernel
> when ON, from the verbatim legacy block when OFF. This is the ENTIRE brain swap.
> Net edit: the 2-line Patch-A slot + this seam block ≈ **~22 lines, every one
> OFF-gated**, ALL in `entrypoint` BEFORE the agent/session is constructed.

**What the kernel system prompt brings (ON) — SYSTEM PROMPT ONLY:**
- **Vendor-script flow** authoritative (W3): greet→confirm→intro→reason→qualify→pitch→objections→close from the vendor's `raw_script` overrides the default framework.
- **Full lossless campaign brief** (W3) inside the `<campaign_brief>` C3 fence (fixes the lossy 3–5-field compression; injection-safe).
- **RAG prefix** (W4) + **cross-call/WhatsApp memory** (W7) folded into the prompt prefix — never into TTS.
- **The greeting PATTERN** (kept, `prompt.py:308-310`): warm greet → "greetings from {company}" → "क्या मैं {lead_name} जी से बात कर रही हूँ?" → **WAIT** → reason + permission → proceed. Learned/parameterized per campaign, never a hardcoded script. The kernel authors EXACTLY ONE `OPENING:` directive and the "warm human, named once, never AI/assistant" rule — so the **single-greeting / no-username-repeat** behaviour now lives in the PROMPT (the `OPENER_ALREADY_SAID` env hack is **NOT** reintroduced ON).

---

## 3. ❌ DELIBERATELY OMITTED — the VOICE PATH (Patches D / E / F / G)

These are **NOT applied** in the brain-only cutover. Each is the old worker's
voice/turn/memory path and must stay byte-identical. The static test
`test_voice_unchanged_brainonly.py` enforces that A+B+C never edit these spans.

| Patch | Region (`98655dbf` landmark) | What it would change | WHY OMITTED (voice path) |
|---|---|---|---|
| **D** — TTS/Sarvam router | `elevenlabs.TTS(...)` + `VoiceSettings(...)` (`agent.py:~563-582`) | Routes which TTS engine is constructed (lean→Sarvam etc.) | The perfect earner voice IS ElevenLabs `QTKSa2Iyv0yoxvXY2V8a` @ stability `0.45` / speed `1.08`. Omitting D leaves `elevenlabs.TTS(...)` unconditional and untouched ⇒ provider/voice_id/stability/speed identical ON or OFF. The Sarvam router is a SEPARATE, later, ring-gated wave. |
| **E** — per-turn HOT hook | user-turn path / `on_user_turn_completed` (`agent.py:~715`) | Calls `on_turn(...)`, injects a RAG suffix + language directive into the LLM each turn | Touches turn-taking / per-turn LLM injection during the LIVE call. Flagged OPTIONAL even in the full patch doc. The brain-only cutover keeps the turn loop the old worker's — no per-turn behaviour change. (Shadow log-only at most, later.) |
| **F** — post-call memory write | `_persist_memory()` shutdown callback (`agent.py:~497`) | `await persist_post_call(...)` — additive COLD-path DB write after hangup | Safe (post-call only, never touches voice), but DEFERRED: the first brain cutover needs ONLY the system prompt. Adding it now expands the change surface for zero brain benefit. |
| **G** — box memory bind | box startup (`droplet_work.db.engine` import) | `bind_box_memory(asession)` wires the box RLS session into the façade | Requires a `droplet_work.db` import at startup (breaks the droplet-free isolation guarantee in CI) and is only meaningful WITH F. Deferred alongside F; W7 memory degrades to the in-process `mem.save_memory` (today's behaviour). |

> The closure seam (`_confirm_then_hangup` / `_llm_close`) is also left VERBATIM
> (the legacy close is proven + already env-gated) — out of scope for the first cutover.

---

## 4. OFF byte-identity (DoD) + ON proof

**OFF (default, `KERNEL_OUTBOUND` unset):** every `if` is False ⇒ no `voice_kernel`
import ⇒ `_OK is None` ⇒ `instructions == base_instructions` (the verbatim legacy
string) ⇒ the unchanged `elevenlabs.TTS(...)` ⇒ the old opener `session.say()` ⇒
old turn loop ⇒ old post-call write. The rendered system prompt (for the golden
campaign), the constructed TTS provider, the opener, the closure, and the post-call
write set are **identical to the `98655dbf` golden**. Total agent edit ≈ **~22 lines,
every one OFF-gated.** Revert = `KERNEL_OUTBOUND=0` + restart (or restore the
`98655dbf` backup).

**ON proof (BUILD-time, no box):**
- **OFF-identity** — `voice_kernel/integrations/tests/test_outbound_integration.py`
  proves `assemble_outbound_instructions(None, legacy_render=…)` is BYTE-IDENTICAL to
  the real `build_system_prompt` across the FIVE outbound field shapes.
- **ONLY-the-system-prompt** —
  `voice_ops/eval/tests/test_surgical_b_brainonly.py::test_brainonly_assemble_provides_only_system_prompt_no_tts_router`
  spies on the provider router + speech planner and proves assembling instructions
  touches NEITHER (no TTS/prosody side-effect).
- **VOICE-UNCHANGED static** —
  `voice_kernel/integrations/tests/test_voice_unchanged_brainonly.py` proves, by code
  landmark, the two brain anchors fall OUTSIDE every voice-constructor span on the real
  `agent.py` (so A+B+C edit ZERO voice lines).
- **Single greeting / no username-repeat / no double-greet** — the brain-only replay
  suite (`test_surgical_b_brainonly.py`) on a real regressed-transcript shape.
- **W17 deploy gate** — `run_all_gates().passed is True` (R1/R2/R3/R5/R7/R10 green).

---

## 5. GATED DEPLOY RUNBOOK — the LATER `KERNEL_OUTBOUND` flip (founder-gated)

> This wave is **BUILD/verify ONLY — NO deploy.** The flip is the separate, most
> dangerous, founder-gated step (`W-VOICE-SURGICAL-PLAN.md` Part C). Sequence:

1. **Pre-flight (no mutation).** Confirm live md5 `agent.py 98655dbf`, `prompt.py
   fb87ea56`, `KERNEL_OUTBOUND` unset. Back up: `cp /opt/famit-agent/agent.py
   agent.py.RESTOREbak.<ts>` and `cp .env .env.RESTOREbak.<ts>`. `python -m pytest
   voice_kernel/ voice_ops/` green + `run_all_gates().passed` True.
2. **Apply A+B+C only** to the box `agent.py` (re-locate anchors by surrounding code,
   NOT raw line). Deploy the tracked `voice_kernel/` package to the box (import-safe,
   droplet-free). Do **NOT** apply D/E/F/G. Keep `KERNEL_OUTBOUND` UNSET.
3. **OFF-identity on the box.** Restart `famit-agent`. A real ring is byte-identical to
   today (perfect voice + old brain). The brain code is present but dormant. Run a
   real call to confirm ZERO change with the flag OFF.
4. **Gate before the flip.** `python -m pytest voice_kernel/ voice_ops/` green +
   `run_all_gates().passed` True + replay the regressed transcript green — BEFORE
   touching the flag.
5. **Flip via a systemd DROP-IN — NOT the shared `.env`.** Shared-`.env` flags can leak
   across units (W3 LEARNINGS §2); isolate `KERNEL_OUTBOUND` to the outbound unit only:
   ```ini
   # /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
   [Service]
   Environment=KERNEL_OUTBOUND=1
   ```
   `systemctl daemon-reload && systemctl restart famit-agent`.
6. **Real-call canary (the only acceptance truth).** Founder places a small number of
   REAL outbound calls. Confirm: voice UNCHANGED (the perfect ElevenLabs voice),
   brain UPGRADED (full brief + vendor flow + objection handling), **single greeting**,
   **name said once**, **no "AI assistant"**. Watch the journal for R1 violations,
   double-greets, latency regressions.
7. **Instant revert path (always armed).** ANY regression ⇒ delete the drop-in (or set
   `KERNEL_OUTBOUND=0`) + `systemctl restart famit-agent` ⇒ back to the old brain +
   perfect voice INSTANTLY. Because the voice path was NEVER touched (D/E omitted), the
   worst case is the old brain with the perfect voice — there is no voice risk. Disclosure/
   voice issue ⇒ `cp agent.py.RESTOREbak agent.py` + restore `.env` + restart ⇒ `98655dbf`.
8. **Voice-path-proven-untouched evidence at flip time.** On the box, before/after the
   flip: `md5sum agent.py` changes ONLY by the A+B+C insert; the voice-constructor
   range-diffs (`elevenlabs.TTS`/`VoiceSettings`/`sarvam.STT`/`groq.LLM`/`AgentSession`/
   `session.say(opener`) against the `98655dbf` golden are EMPTY (the static test asserts
   this off-box; re-run on-box as the deploy check).

> One box-mutating change at a time. Revert path armed BEFORE each step. The founder's
> REAL outbound ring is the only acceptance truth — a green gate proves the cutover PATH,
> never the box itself.
