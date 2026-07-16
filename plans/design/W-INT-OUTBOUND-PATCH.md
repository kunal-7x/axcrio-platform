# W-INT-OUTBOUND-PATCH — the minimal `agent.py` hook (canonical doc)

> Branch `fix/realtime-voice-kernel-v2`. **DOC-ONLY in this wave** — see §0.
> 🚨 EARNER LAW: the OUTBOUND earner is `droplet_work/agent.py`, LIVE box md5 =
> **`98655dbfc71d5c3da36bcfe3f848082c`** (the founder's already-live voice fixes;
> NEVER restore an older hash). `droplet_work/` is GITIGNORED + box-only. The
> integration BULK is the TRACKED `voice_kernel/integrations/outbound.py`
> (git-revertable). This file is the exact, minimal, flag-gated hook to apply to the
> box `98655dbf`, documented so the deploy wave (the separate founder-gated step,
> `design/W-INT-OUTBOUND-PLAN.md §5`) applies it surgically.

The tracked façade exposes EXACTLY these functions (no `voice_kernel.*` type crosses
into the agent):

```
kernel_outbound_enabled, build_for_call, assemble_outbound_instructions,
on_turn, plan_speech, choose_tts, on_tts_error, persist_post_call
(+ bind_box_memory — box-startup memory wiring, see §7)
```

---

## 0. WHY DOC-ONLY (no-drift gate — read first)

Unlike inbound (whose local copy had DRIFTED from the box golden), the OUTBOUND
local copy is byte-identical to the box:

| file | md5 |
|---|---|
| `droplet_work/agent.py` (local working copy) | `98655dbfc71d5c3da36bcfe3f848082c` ✅ |
| LIVE box `/opt/famit-agent/agent.py` | `98655dbfc71d5c3da36bcfe3f848082c` ✅ (verify at deploy) |

So the hunks below ARE byte-representative of the box. Still, this wave keeps the
patch DOC-ONLY because applying it = mutating the SACRED EARNER, which is the
super-gated founder step (PLAN §5). Line anchors are against the `98655dbf` file;
the deploy wave MUST re-locate them by the surrounding code, not the raw line number
(the founder may bump lines with future env-gated fixes). Every hunk preserves the
existing legacy line verbatim as the OFF branch — `KERNEL_OUTBOUND=0` ⇒
byte-identical to today.

---

## 1. Patch A — flag + per-call façade slot (top of `entrypoint`)

`entrypoint` is at `:392`. Right after `lead_name` is read (`:404`), add:

```python
# --- W-INT outbound kernel façade (flag KERNEL_OUTBOUND, default OFF) ----------
_OK = None  # voice_kernel.integrations.outbound.OutboundKernel | None
_KERNEL_OUTBOUND = os.getenv("KERNEL_OUTBOUND", "0") in ("1", "true", "True")
```

OFF ⇒ `_OK` stays None and NOTHING from `voice_kernel` is imported on this path.

---

## 2. Patch C — instructions seam + Patch B — build the façade

The legacy code builds `base_instructions` across `:440`–`:461` (system_prompt +
optional lead-name append + optional `OPENER_ALREADY_SAID` block + optional `recap`),
then `instructions = base_instructions` at `:461`. Wrap that WHOLE block as a
zero-arg legacy lambda, build the façade (Patch B), and choose the instruction
source (Patch C). The `camp` dict (from `_load_campaign`, `:407`) carries the
authoritative owning tenant.

**Replace** the existing `:461`:
```python
    instructions = base_instructions
```

**with:**
```python
    # --- W-INT-B: build the per-call outbound kernel façade (flag-gated) --------
    # OUTBOUND TENANT (C2 fail-closed): the tenant is the CAMPAIGN RECORD's OWNER
    # (caller.py:1458 wrote `rec["tenant_id"]` under that tenant's auth) — NEVER a
    # dispatch-metadata body value. A forged campaign_id either has no file
    # (_load_campaign -> None) or carries its TRUE owner. `camp` is the dict loaded
    # at :407 (None if no campaign -> _camp_owner "" -> build returns None -> legacy).
    if _KERNEL_OUTBOUND:
        try:
            from voice_kernel.integrations import outbound as _ko
            _camp_owner = str((camp or {}).get("tenant_id", "")).strip()
            _OK = _ko.build_for_call(
                tenant_id=_camp_owner,            # campaign-record owner (server-written)
                call_id=room_name,
                lead_phone=phone,                 # mem.parse_phone(room_name), :438
                campaign_id=str(meta.get("campaign_id", "")),
                campaign_tenant_id=_camp_owner,   # same source -> consistency assert (armed for future divergence)
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

> WHY this anchor: at `:461` `base_instructions` is fully assembled (system_prompt
> from `build_system_prompt(fields)` + the lead-name/OPENER_ALREADY_SAID/recap
> appends), so the legacy lambda captures the EXACT current string. `_OK` must be
> built BEFORE the instruction choice — both happen here, right after `:461`, before
> the agent is constructed at `:851`. `_OK` then flows to Patches D/F below (same
> `entrypoint` scope — no kwarg plumbing needed, unlike inbound's two persona
> classes).

---

## 3. Patch D — provider/TTS seam (the Sarvam fix)

Outbound today HARD-CODES ElevenLabs at the TTS init (`:563`–`:567`). The kernel
router makes the provider AUTHORITATIVE (lean/standard → Sarvam, growth/premium → EL,
explicit field override wins). **Minimal, low-risk form:** decide the engine just
before the TTS block; OFF ⇒ the verbatim `elevenlabs.TTS(...)` runs unchanged.

Right BEFORE the `tts = elevenlabs.TTS(` block (`:563`), add:
```python
    # --- W-INT-D: provider router (Sarvam fix). OFF -> elevenlabs (today). -------
    _tts_engine = "elevenlabs"
    if _KERNEL_OUTBOUND and _OK is not None:
        try:
            from voice_kernel.integrations import outbound as _ko
            _choice = _ko.choose_tts(_OK, provider_pref=str(fields.get("tts_provider", "")))
            _tts_engine = _choice.tts or "elevenlabs"   # AUTHORITATIVE, honoured
        except Exception as _exc:
            logger.warning("outbound choose_tts failed -> elevenlabs: %r", _exc)
            _tts_engine = "elevenlabs"
```

Then gate the construction (the existing `elevenlabs.TTS(...)` becomes the
`elevenlabs` branch — VERBATIM, no edits inside it):
```python
    if _tts_engine == "elevenlabs":
        tts = elevenlabs.TTS(            # <-- the EXISTING :563-:582 block, UNCHANGED
            api_key=os.environ["ELEVENLABS_API_KEY"],
            voice_id=(fields.get("voice_id") or os.getenv("ELEVENLABS_VOICE_ID", "QTKSa2Iyv0yoxvXY2V8a")),
            ...
            auto_mode=True,
        )
    else:
        # ON-only branch: the kernel selected a non-EL engine (e.g. sarvam).
        # Build via the box's existing Sarvam TTS factory; on ANY error, fail-LOUD
        # back to EL (named swap) so the earner never goes silent.
        try:
            tts = _build_sarvam_tts(fields, _init_tts_lang)   # box-local factory (see note)
        except Exception as _exc:
            from voice_kernel.integrations import outbound as _ko
            _ko.on_tts_error(_OK, _tts_engine, 0)             # names the swap at INFO
            logger.warning("outbound %s TTS build failed -> elevenlabs: %r", _tts_engine, _exc)
            tts = elevenlabs.TTS(                              # EXACT EL fallback (copy of the block)
                api_key=os.environ["ELEVENLABS_API_KEY"],
                voice_id=(fields.get("voice_id") or os.getenv("ELEVENLABS_VOICE_ID", "QTKSa2Iyv0yoxvXY2V8a")),
                model=os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
                language=_init_tts_lang, apply_text_normalization=_el_text_norm,
                voice_settings=VoiceSettings(
                    stability=float(os.getenv("EL_STABILITY", "0.45")),
                    similarity_boost=float(os.getenv("EL_SIMILARITY", "0.80")),
                    style=0.0, use_speaker_boost=False, speed=float(os.getenv("EL_SPEED", "1.08"))),
                auto_mode=True)
```

> NOTE: `_build_sarvam_tts` is the OUTBOUND box's existing Sarvam TTS constructor.
> If `agent.py` (`98655dbf`) has no Sarvam TTS factory yet, the FIRST cutover ships
> WITHOUT the `else` branch — i.e. `_tts_engine` is computed and LOGGED (shadow), but
> the `elevenlabs.TTS(...)` block stays unconditional. That keeps the earner on EL
> (byte-identical) while proving the router selection in logs; wiring the real Sarvam
> build is a follow-up sub-step gated by its own canary. **Do not invent a Sarvam
> factory under the earner without its own ring-test.**

---

## 4. Patch F — post-call memory write (shutdown callback)

The `_persist_memory()` shutdown callback (`:497`) does `mem.save_memory` + flushes
usage + at `:537` `summ = _summarize(turns)` then writes the transcript JSON. The
legacy block STAYS. ADD, flag-guarded, AFTER the transcript write (`:551`):

```python
        # --- W-INT-F: kernel post-call lead-memory (additive; legacy save above) -
        if _KERNEL_OUTBOUND and _OK is not None:
            try:
                from voice_kernel.integrations import outbound as _ko
                await _ko.persist_post_call(
                    _OK, lead_phone=phone, turns=turns,
                    name=lead_name, raw_summary=summ.get("summary", ""),
                    outcome=summ.get("outcome", ""))
            except Exception as _exc:
                logger.warning("outbound kernel post-call persist failed (non-fatal): %r", _exc)
```

`_persist_memory` is already `async` and is registered via
`ctx.add_shutdown_callback(_persist_memory)` (`:553`), so `await` is valid here.
OFF ⇒ only the legacy `mem.save_memory` + transcript write run. `_OK` is in
`entrypoint` scope and `_persist_memory` is a closure over it — no plumbing needed.

---

## 5. Patch E — per-turn HOT hook (RAG + language) — SHADOW-safe, OPTIONAL

The outbound agent drives per-turn logic in `_on_item` (`:715`,
`conversation_item_added`) and `on_user_turn_completed`. For the FIRST cutover,
register (only under `_KERNEL_OUTBOUND`) a shadow call inside the existing user-turn
path that calls `await on_turn(_OK, user_text=..., detected_lang=..., history_len=...)`
and LOGS the L5 `rag_suffix` — NO behavior change until a pre-LLM inject hook lands
(the documented W5 deferral). OFF ⇒ the call is never made ⇒ the hot path is
unchanged. This is OPTIONAL for the first cutover and can be deferred entirely.

---

## 6. Closure seam — OUT OF SCOPE for the first cutover (kept byte-identical)

`_confirm_then_hangup` (`:682`) already generates the goodbye via the env-gated
`_llm_close` (`LLM_CLOSE`) or `_goodbye_line`. A future
`generate_outbound_closing(_OK, signal, ...)` could route this through the kernel,
but the first cutover leaves it VERBATIM (the legacy close is proven + already
env-gated). Documenting the seam so the follow-up knows where it lives; no patch
here.

---

## 7. Patch G — box memory wiring (one line at box startup)

So live lead-memory persists under tenant RLS, the box-startup (once, near where
`droplet_work.db.engine` is already imported in the famit-agent process) calls:

```python
if os.getenv("KERNEL_OUTBOUND", "0") in ("1", "true", "True"):
    try:
        from droplet_work.db.engine import asession as _box_asession
        from voice_kernel.integrations import outbound as _ko
        _ko.bind_box_memory(_box_asession)   # ON-BOX only; CI/local default = empty mem
    except Exception as _exc:
        logger.warning("outbound kernel memory bind skipped: %r", _exc)
```

This is the ONLY place a `droplet_work.db` import meets the kernel, and it is
flag-gated + box-only. Without it (CI / OFF) the façade is droplet-free and lead
memory degrades to empty — never an error. If the outbound box has no
`droplet_work.db.engine` asession factory, omit Patch G — W7 memory then degrades to
the in-process `mem.save_memory` (today's behavior) and the kernel W7 layer is a
no-op Null impl.

---

## 8. OFF byte-identity (DoD)

With `KERNEL_OUTBOUND` unset: every hunk's `if` is False ⇒ no `voice_kernel` import
⇒ `_OK is None` ⇒ `instructions == base_instructions` (the verbatim legacy string)
⇒ `_tts_engine == "elevenlabs"` ⇒ the unchanged `elevenlabs.TTS(...)` ⇒ only the
legacy `mem.save_memory` + `_summarize` + transcript write run. The rendered
system-prompt (for the golden campaign), the constructed TTS provider, the opener,
the closure, and the post-call write set are identical to the `98655dbf` golden.
Total agent edit ≈ **~35 lines, every one OFF-gated.** Revert = `KERNEL_OUTBOUND=0`
+ restart `famit-agent` (or restore the `98655dbf` backup).

_Deploy is the separate founder-gated wave (`design/W-INT-OUTBOUND-PLAN.md §5`) — the
MOST dangerous deploy in the product; one box-mutating change; revert path always
ready; founder REAL outbound ring-test is the only acceptance truth._
