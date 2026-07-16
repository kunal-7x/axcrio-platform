# W-INT — Flag-Gated INBOUND Kernel Integration PLAN

> Status: **DESIGN ONLY — no live file edited by this doc.**
> Branch: `fix/realtime-voice-kernel-v2`.
> EARNER LAW: outbound `droplet_work/agent.py` md5 = `98655dbf` FROZEN — never
> imported / edited / restarted by this wave. INBOUND target =
> `droplet_work/aim_voice_agent.py` (box golden `1614be09`; local
> `.LIVEBOX.py` matches). `droplet_work/` is GITIGNORED, so the integration BULK
> lives in TRACKED `voice_kernel/integrations/inbound.py` (git-revertable). The
> `aim_voice_agent.py` change is a MINIMAL, flag-gated hook (a few lines),
> documented below as an exact patch + applied only to the local gitignored copy
> for a smoke. Flag `KERNEL_INBOUND` DEFAULT OFF ⇒ inbound is byte-identical to
> today. NO box deploy in this wave (deploy is a separate founder-gated step, §6).

The kernel is built + green (212 tests). This plan wires W2–W7 into inbound via
ONE tracked façade module so `aim_voice_agent.py` gains only ~5 call sites, each
`if KERNEL_INBOUND:` with the existing legacy line as the unchanged `else`.

---

## 0. Why a façade module (the design choice)

`aim_voice_agent.py` is box-only/gitignored and is a live earner-adjacent file.
Putting the wiring (build_kernel, all W2–W7 impl construction, the per-hook glue)
inside it would be (a) un-revertable via git and (b) a large diff on a sensitive
file. Instead:

- **TRACKED** `voice_kernel/integrations/inbound.py` holds ALL the bulk: it
  builds the kernel once, constructs every W2–W7 impl, and exposes four small
  functions the agent calls. Reverting the integration = `git revert` of that one
  tracked module + delete the ~5-line hook.
- The agent hook is a **few lines**, each gated by `KERNEL_INBOUND`, with the
  legacy expression preserved verbatim as the OFF branch. The agent NEVER imports
  `voice_kernel.*` at module top-level on the OFF path beyond a cheap lazy import
  guarded by the flag (see §3 — import is inside the `if` so OFF pays nothing).

---

## 1. THE TRACKED MODULE API — `voice_kernel/integrations/inbound.py`

A thin, stateful-per-call façade. It owns kernel construction + impl wiring and
hides every `voice_kernel.*` type from the agent. All functions are **fail-safe**:
any internal error logs a WARNING and returns the legacy-equivalent so a kernel
fault can never break an inbound call.

### 1.1 Build the session façade (once per call, after tenant resolves)

```python
# voice_kernel/integrations/inbound.py
from __future__ import annotations
import logging, os
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger("voice_kernel.integrations.inbound")


def kernel_inbound_enabled() -> bool:
    """Single source of truth for the flag (config-native pattern).
    OFF (default) => the agent never constructs a session, never imports impls."""
    from voice_kernel.config import KernelConfig
    return KernelConfig.from_env().enabled_for("inbound")


@dataclass
class InboundKernel:
    """Per-call façade. Holds the built RealtimeVoiceKernel + the C2
    KernelSession + the resolved CallContext seed. Constructed ONCE per call by
    `build_for_call(...)`. Every method degrades to a legacy-equivalent on error
    (never raises into the live call)."""
    kernel: "RealtimeVoiceKernel"
    session: "KernelSession"
    base_ctx: "CallContext"
    _provider_choice: Optional["ProviderChoice"] = None


def build_for_call(
    *,
    tenant_id: str,
    call_id: str,            # = room_name (the inbound room id)
    caller_id: str,
    campaign_id: str,
    campaign_tenant_id: str, # the OWNING tenant of the resolved campaign (fail-closed cross-check)
    fields: dict | None,     # the live campaign `fields` dict (prompt.py shape); {} for manager
    recap: str = "",
    pg_memory: str = "",
    is_manager: bool = False,
    locale: str = "hi-IN",
) -> Optional[InboundKernel]:
    """Construct the per-call kernel façade. Returns None on ANY failure or if
    the flag is OFF — the caller then uses its legacy path unchanged.

    C2 fail-closed: stamps a server-side KernelSession from the SERVER-RESOLVED
    tenant (see §4) and cross-checks it against the campaign's owning tenant; a
    mismatch/blank tenant raises TenantIdentityError, which we catch → return None
    → legacy path (the call still proceeds, kernel simply disengaged, logged LOUD).
    """
    if not kernel_inbound_enabled():
        return None
    try:
        from voice_kernel import (
            KernelConfig, KernelSession, CallContext, build_kernel,
        )
        from voice_kernel.packet import PacketMeta
        cfg = KernelConfig.from_env()
        session = KernelSession(
            tenant_id=tenant_id,        # SERVER-resolved (DID/contact lookup), never a body value
            call_id=call_id,
            direction="inbound",
            stamped_by="server",
        )
        # fail-closed cross-check (raises on mismatch/blank → caught below).
        session.assert_matches_campaign(campaign_tenant_id or tenant_id)
        meta = PacketMeta(
            tenant_id=tenant_id, campaign_id=campaign_id, call_id=call_id,
            room=call_id, lead_phone=caller_id, locale=locale,
            direction="inbound", ts_iso=_now_iso(),
        )
        base_ctx = CallContext(
            meta=meta, fields=dict(fields or {}), recap=recap, session=session,
        )
        kernel = _build_kernel_with_impls(cfg, campaign_id, fields or {}, is_manager)
        return InboundKernel(kernel=kernel, session=session, base_ctx=base_ctx)
    except Exception as exc:  # never break a call; disengage kernel, run legacy
        log.warning("inbound kernel build failed (tenant=%s call=%s) -> legacy: %r",
                    tenant_id, call_id, exc)
        return None
```

`_build_kernel_with_impls(cfg, campaign_id, fields, is_manager)` is the ONE place
that registers the W2–W7 concretes (so a missing/disabled wave degrades to its
Null impl automatically — the kernel ships Null defaults):

```python
def _build_kernel_with_impls(cfg, campaign_id, fields, is_manager):
    from voice_kernel import build_kernel
    impls = {}
    # W3 context + vendor script (authoritative campaign compile)
    try:
        from voice_kernel.context import ContextEngineImpl, VendorScriptEngineImpl
        vs = VendorScriptEngineImpl()
        if (raw := (fields or {}).get("raw_script", "")):
            vs.register(campaign_id, raw, variables=_script_vars(fields))
        impls["context"] = ContextEngineImpl(campaign_id=campaign_id, fields=fields, vendor_script=vs)
        impls["vendor_script"] = vs
    except Exception as exc:
        log.warning("W3 context impl unavailable -> Null: %r", exc)
    # W2 brain packs
    try:
        from voice_kernel.brain_packs import BrainPackProvider
        impls["brain_packs"] = BrainPackProvider()
    except Exception as exc:
        log.warning("W2 brain_packs unavailable -> Null: %r", exc)
    # W4 rag
    try:
        from voice_kernel.rag import RagRuntime
        impls["rag"] = RagRuntime.from_env()
    except Exception as exc:
        log.warning("W4 rag unavailable -> Null: %r", exc)
    # W5 speech + provider router (Sarvam fix, §5)
    try:
        from voice_kernel.providers import build_provider_router
        from voice_kernel.speech import build_speech_planner
        impls["router"] = build_provider_router()
        impls["speech"] = build_speech_planner()
    except Exception as exc:
        log.warning("W5 speech/router unavailable -> Null: %r", exc)
    # W7 memory
    try:
        from voice_kernel.memory import LeadMemoryService
        impls["memory"] = LeadMemoryService()
    except Exception as exc:
        log.warning("W7 memory unavailable -> Null: %r", exc)
    return build_kernel(cfg, **impls)
```

> NOTE: the impl class/factory names above (`ContextEngineImpl`,
> `BrainPackProvider`, `RagRuntime.from_env`, `build_provider_router`,
> `build_speech_planner`, `LeadMemoryService`) mirror the seam docs
> (W3/W4/W5/W7); the integration module is the single place that adapts to the
> exact exported names — if a wave exported a slightly different name, only this
> file changes, never the agent.

### 1.2 The four functions the agent hook calls

```python
def assemble_inbound_instructions(
    ik: InboundKernel,
    *,
    legacy_render: Callable[[], str],
    fields: dict | None = None,
    recap: str = "",
    grounding: str = "",
    pg_memory: str = "",
) -> str:
    """ON: kernel packet prefix for this persona. OFF/None ik / error:
    EXACTLY legacy_render() (byte-identical). This is the SAME guarantee as
    voice_kernel.adapter.instructions_provider — we delegate to it so the
    OFF==legacy invariant is the already-tested one (test_adapter_off_identity)."""
    if ik is None:
        return legacy_render()
    from voice_kernel.adapter import instructions_provider
    from dataclasses import replace
    ctx = ik.base_ctx
    if fields is not None or recap or grounding or pg_memory:
        ctx = replace(ctx, fields=dict(fields or ctx.fields), recap=recap or ctx.recap)
    return instructions_provider(legacy_render, ctx, cfg=ik.kernel.cfg)


async def on_turn(ik: InboundKernel, *, user_text: str, detected_lang: str,
                  stage=None, history_len: int = 0) -> dict:
    """HOT path, per turn. Returns a plain dict the agent can use WITHOUT importing
    kernel types:
        {"reply_lang": str, "rag_suffix": str|None, "speech_plan": SpeechPlan|None}
    Never blocks beyond the RAG hard deadline (parallel to LLM start). On OFF/None
    ik returns an inert dict (all empties) so the agent's legacy turn is unchanged."""
    if ik is None:
        return {"reply_lang": detected_lang, "rag_suffix": None, "speech_plan": None}
    from voice_kernel.contracts import TurnContext
    from voice_kernel.packet import Stage
    turn = TurnContext(call_id=ik.session.call_id, user_text=user_text,
                       detected_lang=detected_lang, stage=stage or Stage.GREET,
                       history_len=history_len)
    try:
        rag_layer = await ik.kernel.retrieve_turn_layer(turn)   # hard-deadline, never raises
        rag_suffix = ik.kernel.assemble_turn(turn, rag_layer=rag_layer)  # in-memory, no await
    except Exception as exc:
        log.warning("on_turn rag/assemble failed (-> no L5): %r", exc)
        rag_suffix = None
    return {"reply_lang": detected_lang or turn.detected_lang,
            "rag_suffix": rag_suffix, "speech_plan": None}


def plan_speech(ik: InboundKernel, *, raw_text: str, lang: str):
    """Optional HOT step between LLM and TTS (W5 SpeechPlanner). Returns a
    SpeechPlan or None. OFF/None ik/error => None => agent uses raw_text as-is."""
    if ik is None:
        return None
    try:
        card = ik.kernel.svc.context_engine.build_card(ik.base_ctx)
        return ik.kernel.svc.speech.plan(raw_text, lang, card)
    except Exception as exc:
        log.warning("plan_speech failed (-> raw text): %r", exc)
        return None


def choose_tts(ik: InboundKernel, *, provider_pref: str = "") -> "ProviderChoice":
    """W5 ProviderRouter authoritative resolve (Sarvam fix, §5). Returns a
    ProviderChoice whose `.tts` the agent feeds to _build_tts(). OFF/None ik =>
    a ProviderChoice(tts='elevenlabs') so the legacy default is preserved."""
    if ik is None:
        from voice_kernel.contracts import ProviderChoice
        return ProviderChoice(tts="elevenlabs", reason="kernel-off-legacy-default")
    if ik._provider_choice is not None:
        return ik._provider_choice
    try:
        ctx = ik.base_ctx
        if provider_pref:
            from dataclasses import replace
            ctx = replace(ctx, fields={**ctx.fields, "tts_provider": provider_pref})
        ik._provider_choice = ik.kernel.svc.router.resolve(ctx)
    except Exception as exc:
        from voice_kernel.contracts import ProviderChoice
        log.warning("choose_tts resolve failed (-> elevenlabs): %r", exc)
        ik._provider_choice = ProviderChoice(tts="elevenlabs", reason=f"resolve-error:{exc!r}")
    return ik._provider_choice


def on_tts_error(ik: InboundKernel, provider: str, code: int) -> "ProviderChoice":
    """Fail-LOUD fallback: on a Sarvam build/stream error the agent calls this to
    get an EXPLICIT next ProviderChoice (router.on_error). Logged at INFO with the
    named swap so 'selected vs actual' can never silently diverge (§5)."""
    if ik is None:
        from voice_kernel.contracts import ProviderChoice
        return ProviderChoice(tts="elevenlabs", reason="kernel-off")
    choice = ik.kernel.svc.router.on_error(provider, code)
    ik._provider_choice = choice
    log.info("inbound TTS fail-loud swap: %s(code=%s) -> %s (%s)",
             provider, code, choice.tts, choice.reason)
    return choice


async def persist_post_call(
    ik: InboundKernel, *, lead_phone: str, turns: list, name: str = "",
    raw_summary: str = "", outcome: str = "",
) -> None:
    """COLD path, post-call (W7). Writes structured lead memory using the
    SERVER-STAMPED session tenant. Never raises into the hangup hook (double belt:
    here AND the agent's try/except). OFF/None ik => no-op (legacy
    enqueue_episode still runs in the agent)."""
    if ik is None:
        return
    try:
        await ik.kernel.svc.memory.extract_and_persist(
            tenant_id=ik.session.tenant_id,   # server-stamped, never a body value
            lead_phone=lead_phone, turns=turns, raw_summary=raw_summary,
            name=name, outcome=outcome, llm=None,
        )
    except Exception as exc:
        log.warning("persist_post_call failed (non-fatal COLD): %r", exc)
```

**Public API surface (what the agent imports):**
`kernel_inbound_enabled`, `build_for_call`, `assemble_inbound_instructions`,
`on_turn`, `plan_speech`, `choose_tts`, `on_tts_error`, `persist_post_call`.
Nothing else. No `voice_kernel.*` type crosses into the agent.

---

## 2. THE MINIMAL `aim_voice_agent.py` HOOK (exact patch)

All hunks are `if KERNEL_INBOUND:` with the existing line preserved as the OFF
branch. `_IK = None` is the per-call façade (None ⇒ every helper is a legacy
no-op). The import is LAZY and flag-guarded — the OFF path imports nothing.

### Patch A — flag + lazy façade import (top of `entrypoint`, near caller-id read ~`:2169`)

```python
# --- W-INT inbound kernel façade (flag KERNEL_INBOUND, default OFF) -----------
_IK = None  # voice_kernel.integrations.inbound.InboundKernel | None
_KERNEL_INBOUND = os.getenv("KERNEL_INBOUND", "0") in ("1", "true", "True")
```

### Patch B — build the façade AFTER tenant resolves (after the customer branch, ~`:2279`, before agent construction)

```python
# Build the per-call kernel façade ONLY when the flag is on. tenant_id here is
# the SERVER-RESOLVED tenant (DID identity.resolve / resolve_contact_by_phone /
# ADMIN_TENANT) — never a caller-supplied value. (§4 fail-closed.)
if _KERNEL_INBOUND:
    try:
        from voice_kernel.integrations import inbound as _ki
        _cid = str((cust_fields or {}).get("_campaign_id", "")) if cust_fields else ""
        _IK = _ki.build_for_call(
            tenant_id=tenant_id, call_id=room_name, caller_id=caller_id,
            campaign_id=_cid, campaign_tenant_id=tenant_id,
            fields=cust_fields, recap=cust_recap, pg_memory=cust_pg_memory,
            is_manager=is_manager,
        )
    except Exception as _exc:  # never break a call
        logger.warning("AIM kernel façade build failed -> legacy: %r", _exc)
        _IK = None
```

### Patch C — instructions seam (two persona sites)

**Customer (`CustomerSalesAgent.__init__`, ~`:1684`):** wrap the existing
`_build_sales_instructions(...)` in a zero-arg legacy lambda; OFF ⇒ identical.

```python
# was: super().__init__(instructions=_build_sales_instructions(... ))
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

**Manager (`ManagerAgent.__init__`, ~`:1007`):** same shape with
`_build_instructions(caller_id, is_manager, role)` as the legacy lambda. (Manager
has empty `fields`; the kernel's identity/safety layers still render — but the OFF
default keeps it identical until canary.)

**Per-turn re-render (`pick_campaign` match, ~`:1739`):** when the campaign
resolves mid-call, the existing `update_instructions(_build_sales_instructions(...))`
gets the SAME wrapper (re-render with the resolved campaign + grounding). OFF ⇒
unchanged.

### Patch D — provider/TTS seam (Sarvam fix, replaces the `INBOUND_PROV_LOCK` block ~`:2468`)

```python
# was the _prov / _prov_lock_on block + `_tts_provider = ... else "elevenlabs"`
if _KERNEL_INBOUND and _IK is not None:
    from voice_kernel.integrations import inbound as _ki
    _choice = _ki.choose_tts(_IK, provider_pref=(cust_fields or {}).get("tts_provider", ""))
    _tts_provider = _choice.tts          # AUTHORITATIVE — honoured, not gated off
    _prov = {"stt": _choice.stt, "llm": _choice.llm, "tts": _choice.tts}
else:
    # OFF: EXACT legacy block (INBOUND_PROV_LOCK default-OFF => elevenlabs)
    _prov = dict(_DEFAULT_PROV_TRIPLE)
    _prov_lock_on = _env_flag("INBOUND_PROV_LOCK", False)
    if _prov_lock_on and _prompt is not None and hasattr(_prompt, "resolve_providers"):
        try: _prov = _prompt.resolve_providers(cust_fields or {})
        except Exception as exc: _prov = dict(_DEFAULT_PROV_TRIPLE)
    _tts_provider = _prov.get("tts") if _prov_lock_on else "elevenlabs"
# tts=_build_tts(_tts_provider)  ← unchanged line below
```

Optional fail-loud belt: where `_build_tts` catches a Sarvam construction error,
add (flag-guarded) `_choice = _ki.on_tts_error(_IK, "sarvam", code)` so the swap
is named + the metering label reads `actual_tts`.

### Patch E — per-turn HOT hook (RAG + language)

The inbound agent emits turns via `conversation_item_added` (fires after the
LLM). For the **shadow-safe** first cutover, register a `user_input_transcribed`
listener that, when `_KERNEL_INBOUND`, calls `await _ki.on_turn(_IK, ...)` and (if
a pre-LLM `add_message` hook is wired in a later sub-step) appends `rag_suffix`.
Until that pre-LLM hook lands, `on_turn` runs in SHADOW (computes + logs the L5
suffix, no behavior change) — this is the documented W5 deferral, not a blocker
for the instruction/provider/memory cutover. OFF ⇒ the listener is never
registered.

### Patch F — post-call memory write (~`:2823`, room-disconnect)

```python
# existing legacy block stays (LEAD_MEMORY_PG enqueue_episode). ADD, flag-guarded:
if _KERNEL_INBOUND and _IK is not None:
    try:
        from voice_kernel.integrations import inbound as _ki
        asyncio.run_coroutine_threadsafe(
            _ki.persist_post_call(
                _IK, lead_phone=caller_id, turns=list(getattr(_slog, "_turns", [])),
                name=getattr(agent, "_caller_name", ""), outcome="completed"),
            _loop)
    except Exception as _exc:
        logger.warning("AIM kernel post-call persist failed (non-fatal): %r", _exc)
```

**Total agent edit:** flag line + façade build + 3 instruction wraps + 1 provider
block swap + 1 turn listener + 1 post-call add ≈ ~40 lines, every one OFF-gated.

---

## 3. HOW `KERNEL_INBOUND=0` STAYS BYTE-IDENTICAL

1. **No import on the OFF path.** Every `from voice_kernel.integrations import
   inbound` sits INSIDE an `if _KERNEL_INBOUND` (Patches B–F). With the flag off,
   `voice_kernel` is never imported by the agent, so even an import-time bug in
   the kernel cannot affect inbound.
2. **`_IK is None` ⇒ legacy.** `build_for_call` returns None when the flag is off
   (it checks `kernel_inbound_enabled()` first). Every helper short-circuits on
   `ik is None` and returns the legacy-equivalent.
3. **Instructions delegate to the proven seam.** `assemble_inbound_instructions`
   routes through `voice_kernel.adapter.instructions_provider`, whose OFF branch
   is `return legacy_render()` — covered by `test_adapter_off_identity.py`
   (OFF == legacy, byte-for-byte). So OFF emits the EXACT
   `_build_sales_instructions` / `_build_instructions` string.
4. **No per-turn kernel calls when OFF.** The `user_input_transcribed` listener
   is registered only under `if _KERNEL_INBOUND`. OFF ⇒ no extra event handler,
   no RAG, no speech plan — the hot path is unchanged.
5. **Provider default preserved.** OFF branch of Patch D is the verbatim legacy
   block ⇒ `_build_tts("elevenlabs")` exactly as today.
6. **Post-call.** OFF ⇒ only the legacy `enqueue_episode` runs (its own
   `LEAD_MEMORY_PG` guard). No kernel write.

DoD for the OFF claim: with `KERNEL_INBOUND` unset, the rendered instruction
strings (manager + customer, returning + new), the constructed TTS provider, and
the post-call write set are identical to the `1614be09` golden — verified by an
md5 of the rendered prompt and a flag-OFF smoke (§6).

---

## 4. KERNELSESSION TENANT STAMPING FOR INBOUND (fail-closed)

The whole C2 point: a forged `campaign_id` in a dispatch body must not smuggle a
tenant. On inbound there IS no trusted body — the tenant is derived server-side:

| Source (in resolution order) | Where | Trust |
|---|---|---|
| Registered manager DID | `_identity.resolve(caller_id)` → `tenant_id` (`:2177`) | server-resolved (DID table) |
| Returning lead contact | `resolve_contact_by_phone(caller_id)` → `tenant_id` (`:2211`) | server-resolved (contacts table) |
| Fallback | `ADMIN_TENANT` (`:2173`) | platform default |

`build_for_call(tenant_id=...)` receives THIS resolved value (never `caller_id`,
never any caller attribute as a tenant). It stamps
`KernelSession(tenant_id=<resolved>, call_id=room_name, direction="inbound",
stamped_by="server")`. `__post_init__` fail-closes on a blank tenant/call_id, and
`assert_matches_campaign(campaign_tenant_id)` fail-closes on a mismatch. For
inbound, the campaign is itself resolved under the same tenant (returning lead's
own campaign, or an active campaign of that tenant), so the cross-check is
`campaign_tenant_id == tenant_id`; we pass `campaign_tenant_id=tenant_id` and the
assert guards against a future code path that resolves a campaign from a different
owner. A raise is caught in `build_for_call` → returns None → **the call still
runs on the legacy path** (kernel disengaged, logged LOUD) — fail-closed for the
KERNEL but never a dropped customer call.

> Net: inbound tenant = server-resolved DID/contact, stamped immutably, never a
> body value; mismatch ⇒ kernel disengages (legacy), never serves a cross-tenant
> packet.

---

## 5. THE SARVAM-SILENCE FIX (via ProviderRouter, fail-loud)

Root cause (W5 seam): `INBOUND_PROV_LOCK` defaults OFF ⇒
`_tts_provider = "elevenlabs"` is hard-wired ⇒ the Sarvam build path is
unreachable; lean/standard tiers that should speak Sarvam always speak EL. And on
a Sarvam construction error `_build_tts` silently falls back EL while metering
records the intended provider ("billed Sarvam, spoke EL").

The fix (Patch D + `on_tts_error`):

1. **Authoritative, not gated-off.** When `KERNEL_INBOUND`, `choose_tts` always
   calls `router.resolve(ctx)` — there is NO "skip the resolver" branch. The
   router maps plan tier → engine (`lean/standard → sarvam`,
   `growth/premium/enterprise → elevenlabs`) with an explicit `tts_provider`
   field override winning. The SELECTED provider is HONOURED (fed straight to
   `_build_tts(choice.tts)`). We do NOT reintroduce an off-by-default flag that
   strands Sarvam — the single master flag `KERNEL_INBOUND` is the only gate.
2. **Fail-LOUD fallback.** On a Sarvam build/stream failure the agent calls
   `on_tts_error(_IK, "sarvam", code)` → `router.on_error` returns an EXPLICIT
   `ProviderChoice` whose `.reason` names the swap, logged at INFO. The metering
   label reads `actual_tts` (the returned choice), never the intended one — kills
   the cost divergence.
3. **Reversible.** `KERNEL_INBOUND=0` ⇒ Patch D's OFF branch (verbatim legacy)
   ⇒ EL default, resolver dormant. One env to revert.

---

## 6. GATED DEPLOY RUNBOOK (outline — founder-signed, separate wave)

> NOT executed in this wave. agent.py / famit-agent NEVER touched. Only the
> `aim-voice-agent` service is restarted, and only at the canary step.

**Pre-flight (read-only):**
1. Earner gate BEFORE: confirm outbound `agent.py` md5 = `98655dbf` on box +
   famit-agent PIDs running (`3039438/3112900`) + caller `/health` 200 + no ring.
   Abort if `98655dbf` is not the live earner (do NOT "restore baseline" to the
   stale `9150fabe`).
2. **Backup the box inbound agent:** `cp /opt/famit-agent/aim_voice_agent.py
   /opt/famit-agent/aim_voice_agent.py.WINTbak.<ts>`; record its md5 — MUST be the
   golden `1614be09`. If the box md5 ≠ `1614be09`, STOP: box→local drift; pull the
   box copy, reconcile to `.LIVEBOX.py`, restart the runbook.
3. **Box→local drift check:** md5 of box `aim_voice_agent.py` == local
   `droplet_work/aim_voice_agent.LIVEBOX.py` (`1614be09`). The deployable = golden
   + the §2 patch hunks applied on top. Diff must be ONLY the flag-gated hunks.
4. Ship the TRACKED module: `voice_kernel/integrations/inbound.py` (+ `__init__`)
   to the box's importable path (same venv as `aim_voice_agent`). It is inert
   without the flag.

**Step 1 — deploy flag-OFF FIRST (byte-identical smoke):**
5. Deploy the patched `aim_voice_agent.py` with `KERNEL_INBOUND` UNSET (or `=0`)
   in the `aim-voice-agent.service.d` drop-in (NOT the shared `.env` — LEARNINGS
   §2: a shared-.env flag leaks to the earner on its next restart).
6. Restart ONLY `aim-voice-agent` (`systemctl restart aim-voice-agent`).
   famit-agent / agent.py untouched.
7. **Flag-OFF smoke:** place a real inbound test call. Assert: greeting +
   language + flow identical to pre-deploy; TTS still ElevenLabs; transcript +
   session row + recording written as before; no new errors; earner gate
   re-checked (md5 `98655dbf` unchanged, PIDs unchanged, /health 200, no
   ring). This proves the patch is inert OFF.

**Step 2 — flag-ON synthetic canary (one test call):**
8. Set `KERNEL_INBOUND=1` in the `aim-voice-agent.service.d` drop-in ONLY.
   Verify via `/proc/<aim-pid>/environ` that the flag is on for aim AND ABSENT
   from the famit-agent process env.
9. Restart ONLY `aim-voice-agent`.
10. **Flag-ON canary:** place a real inbound call on a LEAN/STANDARD tenant test
    campaign. Assert: (a) Sarvam Bulbul audio is actually heard (not EL); (b) logs
    show `selected==actual==sarvam` (no silent swap; if a swap, it is NAMED at
    INFO); (c) instructions render via the kernel (packet prefix present in the
    debug log) yet the persona/flow is coherent; (d) post-call lead memory row
    written under the correct tenant (RLS check: visible only under that tenant);
    (e) NO cross-tenant bleed; (f) earner gate re-checked, unchanged.
11. Hold 24h on the single canary tenant; watch error rate + latency
    (RAG deadline respected, no per-turn stall).

**Rollback (instant, any step):**
- `KERNEL_INBOUND=0` in the drop-in + `systemctl restart aim-voice-agent` ⇒
  byte-identical to today (all helpers no-op, EL default).
- If the patch itself is suspect: restore
  `aim_voice_agent.py.WINTbak.<ts>` (the `1614be09` golden) + restart
  `aim-voice-agent`. The tracked `voice_kernel/integrations/inbound.py` is inert
  without the flag, so it can stay.
- agent.py / famit-agent are NEVER part of any step ⇒ the earner cannot be
  affected by this wave.

**Invariants enforced at every step:** one box-mutating change at a time; earner
gate before AND after; flag in the systemd drop-in not the shared .env; restart
ONLY `aim-voice-agent`; the `1614be09` backup is the one-command revert.

---

## 7. Acceptance (this design wave)

- [x] Module API defined: `build_for_call` + `assemble_inbound_instructions` +
  `on_turn` + `plan_speech` + `choose_tts` + `on_tts_error` + `persist_post_call`,
  all fail-safe, no kernel type leaks to the agent.
- [x] Minimal agent patch specified as exact hunks (Patches A–F), every one
  OFF-gated with the verbatim legacy `else`.
- [x] OFF byte-identity argued via no-OFF-path-import + the proven
  `instructions_provider` OFF==legacy invariant + no per-turn calls when OFF.
- [x] Inbound tenant stamping mapped to the real server-resolved sources
  (`:2177`/`:2211`/`ADMIN_TENANT`), fail-closed, never a body value.
- [x] Sarvam fix wired authoritatively via `ProviderRouter` (honour selection,
  fail-loud `on_error`, no off-by-default flag).
- [x] Gated deploy runbook: backup `1614be09`, drift check, flag-OFF smoke →
  flag-ON canary, restart only `aim-voice-agent`, agent.py/famit-agent untouched,
  one-command rollback.

_Branch `fix/realtime-voice-kernel-v2`. No box deploy in this wave._
