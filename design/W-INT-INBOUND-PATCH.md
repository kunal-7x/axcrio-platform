# W-INT-INBOUND-PATCH — the minimal `aim_voice_agent.py` hook (canonical doc)

> Branch `fix/realtime-voice-kernel-v2`. **DOC-ONLY in this wave** — see §0.
> EARNER LAW: outbound `agent.py` md5 `98655dbf` is FROZEN — NOT touched here.
> The INBOUND agent `droplet_work/aim_voice_agent.py` is GITIGNORED + box-only.
> The integration BULK is the TRACKED `voice_kernel/integrations/inbound.py`
> (git-revertable). This file is the exact, minimal, flag-gated hook to apply to
> the box golden, documented so the deploy wave applies it surgically.

The tracked façade exposes EXACTLY these functions (no `voice_kernel.*` type
crosses into the agent):

```
kernel_inbound_enabled, build_for_call, assemble_inbound_instructions,
on_turn, plan_speech, choose_tts, on_tts_error, persist_post_call
(+ bind_box_memory  — box-startup memory wiring, see §7)
```

---

## 0. WHY DOC-ONLY (drift gate — read first)

Per the EARNER LAW, the smoke patch may be applied to the LOCAL gitignored
`aim_voice_agent.py` ONLY IF `KERNEL_INBOUND` default-OFF keeps it byte-identical.
That guarantee requires the local copy to BE the box golden so the diff is
provably "only the flag-gated hunks". It is NOT:

| file | md5 |
|---|---|
| `droplet_work/aim_voice_agent.py` (local working copy) | `8335d4ba…` |
| `droplet_work/aim_voice_agent.LIVEBOX.py` (box golden) | `1614be09…` ✅ |

The local working copy has DRIFTED from the box golden (`8335d4ba` ≠ `1614be09`).
Applying the patch to a drifted copy would (a) not be byte-representative of the
box, and (b) violate the "byte-identical when OFF vs the golden" gate. So this
wave leaves the patch **doc-only** (the plan's documented fallback) and ships the
tracked integration module + this exact patch as the canonical deliverables. The
deploy wave applies the hunks below to the **golden `1614be09`** on the box (the
runbook in `design/W-INT-INBOUND-PLAN.md §6` backs up the golden first and asserts
the box md5 == `1614be09` before patching). Line anchors below are given against
BOTH the golden (from the plan) and the current local copy for convenience; the
deploy wave must re-locate them in the golden by the surrounding code, not by raw
line number.

---

## 1. Patch A — flag + per-call façade slot (top of `entrypoint`)

`entrypoint` is at local `:2095`. Right after `caller_id` is read, add:

```python
# --- W-INT inbound kernel façade (flag KERNEL_INBOUND, default OFF) -----------
_IK = None  # voice_kernel.integrations.inbound.InboundKernel | None
_KERNEL_INBOUND = os.getenv("KERNEL_INBOUND", "0") in ("1", "true", "True")
```

OFF ⇒ `_IK` stays None and NOTHING from `voice_kernel` is imported on this path.

---

## 2. Patch B — build the façade AFTER the tenant resolves

The server-resolved tenant is computed by `:2141` (`tenant_id = ADMIN_TENANT`),
the manager DID branch (`:2145`), and the returning-lead contact lookup
(`resolve_contact_by_phone`, `:2172`). AFTER that block (tenant_id final),
BEFORE the agent is constructed:

```python
if _KERNEL_INBOUND:
    try:
        from voice_kernel.integrations import inbound as _ki
        _cid = str((cust_fields or {}).get("_campaign_id", "")) if cust_fields else ""
        _IK = _ki.build_for_call(
            tenant_id=tenant_id,            # SERVER-resolved (DID/contact/ADMIN_TENANT)
            call_id=room_name, caller_id=caller_id,
            campaign_id=_cid, campaign_tenant_id=tenant_id,
            fields=cust_fields, recap=cust_recap, pg_memory=cust_pg_memory,
            is_manager=is_manager,
        )
    except Exception as _exc:           # never break a call
        logger.warning("AIM kernel façade build failed -> legacy: %r", _exc)
        _IK = None
```

`tenant_id` here is the SERVER-RESOLVED value, never a caller-supplied body field
(C2). `build_for_call` stamps a fail-closed `KernelSession` and returns None on
the OFF flag or ANY error ⇒ legacy path.

---

## 3. Patch C — instructions seam (three sites)

### C1 — Customer persona (`CustomerSalesAgent.__init__`, local `:1652`)

Replace:

```python
super().__init__(instructions=_build_sales_instructions(
    fields or {}, recap, caller_name, is_returning, pending_disambig, campaign_options,
    grounding=grounding, pg_memory=pg_memory))
```

with (legacy preserved verbatim as the zero-arg lambda / OFF branch):

```python
_legacy = lambda: _build_sales_instructions(
    fields or {}, recap, caller_name, is_returning, pending_disambig,
    campaign_options, grounding=grounding, pg_memory=pg_memory)
if _KERNEL_INBOUND and _IK is not None:
    from voice_kernel.integrations import inbound as _ki
    super().__init__(instructions=_ki.assemble_inbound_instructions(
        _IK, legacy_render=_legacy, fields=fields, recap=recap,
        grounding=grounding, pg_memory=pg_memory))
else:
    super().__init__(instructions=_legacy())   # OFF: byte-identical to today
```

> NOTE: `CustomerSalesAgent.__init__` has no `_IK`/`_KERNEL_INBOUND` in scope. Pass
> them in (add `kernel_facade=None` + `kernel_on=False` kwargs and the entrypoint
> passes `_IK` / `_KERNEL_INBOUND`), OR build the façade as a module-global the
> agent reads. The kwarg form is cleaner; either way the OFF branch is `_legacy()`.

### C2 — Per-turn re-render on campaign match (`pick_campaign`, local `:1728` + `:2565`)

The existing `await self.update_instructions(_build_sales_instructions(...))` (and
the entrypoint twin at `:2565`) gets the SAME wrapper: OFF ⇒ the verbatim
`_build_sales_instructions(...)`; ON ⇒ `_ki.assemble_inbound_instructions(_IK,
legacy_render=<that call as a lambda>, fields=<resolved>, grounding=<resolved>)`.

### C3 — Manager persona (`ManagerAgent.__init__`, local `:1000`)

Replace `super().__init__(instructions=_build_instructions(caller_id, is_manager,
role))` with the same shape, `_legacy = lambda: _build_instructions(caller_id,
is_manager, role)`. Manager has empty `fields`; the kernel's identity/safety
layers still render. (OFF default keeps it identical until the canary.)

---

## 4. Patch D — provider/TTS seam (the Sarvam fix), replaces the `INBOUND_PROV_LOCK` block

The legacy block is local `:2436`–`:2445` (`_prov = dict(_DEFAULT_PROV_TRIPLE)` +
`_prov_lock_on = _env_flag("INBOUND_PROV_LOCK", False)` + the resolve). Replace
with:

```python
if _KERNEL_INBOUND and _IK is not None:
    from voice_kernel.integrations import inbound as _ki
    _choice = _ki.choose_tts(_IK, provider_pref=(cust_fields or {}).get("tts_provider", ""))
    _tts_provider = _choice.tts            # AUTHORITATIVE — honoured, not gated off
    _prov = {"stt": _choice.stt, "llm": _choice.llm, "tts": _choice.tts}
else:
    # OFF: EXACT legacy block (INBOUND_PROV_LOCK default-OFF => elevenlabs)
    _prov = dict(_DEFAULT_PROV_TRIPLE)
    _prov_lock_on = _env_flag("INBOUND_PROV_LOCK", False)
    if _prov_lock_on and _prompt is not None and hasattr(_prompt, "resolve_providers"):
        try:    _prov = _prompt.resolve_providers(cust_fields or {})
        except Exception:  _prov = dict(_DEFAULT_PROV_TRIPLE)
    _tts_provider = _prov.get("tts") if _prov_lock_on else "elevenlabs"
# tts=_build_tts(_tts_provider)  ← unchanged line below
```

Optional fail-loud belt where `_build_tts` catches a Sarvam construction error
(local `:444` region): flag-guarded `_choice = _ki.on_tts_error(_IK, "sarvam",
code)` then rebuild with `_choice.tts`, so the metering label is `actual_tts` and
the swap is NAMED at INFO (no "billed Sarvam, spoke EL").

---

## 5. Patch E — per-turn HOT hook (RAG + language) — SHADOW-safe first

The inbound agent emits turns via `user_input_transcribed` /
`conversation_item_added`. For the first cutover, register (only under
`_KERNEL_INBOUND`) a `user_input_transcribed` listener that calls
`await _ki.on_turn(_IK, user_text=..., detected_lang=..., history_len=...)`. Until
a pre-LLM `add_message` hook is wired, `on_turn` runs in SHADOW (computes + logs
the L5 `rag_suffix`, NO behavior change) — the documented W5 deferral, not a
blocker for the instruction/provider/memory cutover. OFF ⇒ the listener is never
registered ⇒ the hot path is unchanged.

---

## 6. Patch F — post-call memory write (room-disconnect, local `:2794`)

The legacy `_lead_memory.enqueue_episode(...)` block STAYS. ADD, flag-guarded:

```python
if _KERNEL_INBOUND and _IK is not None:
    try:
        from voice_kernel.integrations import inbound as _ki
        asyncio.run_coroutine_threadsafe(
            _ki.persist_post_call(
                _IK, lead_phone=caller_id,
                turns=list(getattr(_slog, "_turns", [])),
                name=getattr(agent, "_caller_name", ""), outcome="completed"),
            _loop)
    except Exception as _exc:
        logger.warning("AIM kernel post-call persist failed (non-fatal): %r", _exc)
```

OFF ⇒ only the legacy `enqueue_episode` runs (its own `LEAD_MEMORY_PG` guard).

---

## 7. Patch G — box memory wiring (one line at box startup)

So live lead-memory persists under tenant RLS, the box-startup (once, near where
`droplet_work.db.engine` is already imported) calls:

```python
if os.getenv("KERNEL_INBOUND", "0") in ("1", "true", "True"):
    try:
        from droplet_work.db.engine import asession as _box_asession
        from voice_kernel.integrations import inbound as _ki
        _ki.bind_box_memory(_box_asession)   # ON-BOX only; CI/local default = empty mem
    except Exception as _exc:
        logger.warning("AIM kernel memory bind skipped: %r", _exc)
```

This is the ONLY place a `droplet_work.db` import meets the kernel, and it is
flag-gated + box-only. Without it (CI / OFF) the façade is droplet-free and lead
memory degrades to empty — never an error.

---

## 8. OFF byte-identity (DoD)

With `KERNEL_INBOUND` unset: every hunk's `if` is False ⇒ no `voice_kernel`
import ⇒ `_IK is None` ⇒ every persona renders via the verbatim legacy
`else` branch ⇒ `_tts_provider == "elevenlabs"` ⇒ only the legacy
`enqueue_episode` runs. The rendered instruction strings, the constructed TTS
provider, and the post-call write set are identical to the `1614be09` golden.
Total agent edit ≈ ~40 lines, every one OFF-gated. Revert = `KERNEL_INBOUND=0` +
restart `aim-voice-agent` (or restore the `1614be09` backup).

_Deploy is the separate founder-gated wave (`design/W-INT-INBOUND-PLAN.md §6`)._
