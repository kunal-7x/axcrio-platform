"""voice_kernel.integrations.outbound — the OUTBOUND kernel integration façade.

The agent-facing API for `droplet_work/agent.py` (the LIVE OUTBOUND voice agent —
the SACRED EARNER, box md5 `98655dbf`). This is the TRACKED, git-revertable BULK
of the outbound integration: it builds the RealtimeVoiceKernel once per call with
ALL the real W2-W7 impls, stamps a fail-closed KernelSession with
`direction="outbound"`, and exposes the small set of functions the agent calls. No
`voice_kernel.*` type ever crosses into the agent — the agent imports only the
functions below and uses plain values/dicts.

SAME KERNEL, ONE BRAIN: this module is a near-mirror of
`voice_kernel/integrations/inbound.py`. The kernel that serves inbound serves
outbound; only the dial direction differs. The outbound-specific deltas are:
  * the base agent file is `agent.py` (FROZEN earner), not `aim_voice_agent.py`;
  * the flag is `KERNEL_OUTBOUND` (default OFF), not `KERNEL_INBOUND`;
  * the tenant + campaign come from the CAMPAIGN RECORD the caller wrote (the
    campaign's OWNING tenant), not a DID / contact lookup (see §4 of the PLAN);
  * `direction="outbound"` is stamped on the session + packet;
  * `is_manager` is always False (an outbound lead dial has no manager persona).

DESIGN (design/W-INT-OUTBOUND-PLAN.md):
  * Flag KERNEL_OUTBOUND DEFAULT OFF => `build_for_call` returns None => every
    helper short-circuits to the legacy-equivalent => the outbound call is
    BYTE-IDENTICAL to today. The agent's OFF branch never imports this module.
  * FAIL-SAFE: any internal error logs a WARNING and returns the legacy-equivalent
    so a kernel fault can never break or drop a live lead call (the earner).
  * FAIL-CLOSED tenant (C2): the per-call KernelSession is stamped from the
    CAMPAIGN RECORD's owning tenant (`camp["tenant_id"]`, server-written by
    caller.py:save_campaign) — never the dispatch-metadata body — and cross-checked
    against itself. A blank/mismatch raises TenantIdentityError -> caught -> None ->
    the call runs on the legacy path (kernel disengaged, logged LOUD), never
    cross-tenant.

IMPORT ISOLATION: importing this module pulls ZERO droplet_work modules and ZERO
heavy kernel impls at module top-level — every kernel/impl import is LAZY (inside
a function). `import voice_kernel.integrations.outbound` is cheap and droplet-free.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

log = logging.getLogger("voice_kernel.integrations.outbound")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kernel_outbound_enabled() -> bool:
    """Single source of truth for the flag (config-native pattern).

    OFF (default) => the agent never constructs a session, never imports impls.
    Reads KERNEL_OUTBOUND (or the master KERNEL_ENABLED) via KernelConfig, so the
    gate is the same one the adapter + the rest of the kernel already use.
    """
    try:
        from voice_kernel.config import KernelConfig

        return KernelConfig.from_env().enabled_for("outbound")
    except Exception as exc:  # config error must never crash the earner
        log.warning("kernel_outbound_enabled() failed -> treating as OFF: %r", exc)
        return False


@dataclass
class OutboundKernel:
    """Per-call façade. Holds the built RealtimeVoiceKernel + the C2 KernelSession
    + the resolved base CallContext. Constructed ONCE per call by `build_for_call`.
    Every module function degrades to a legacy-equivalent on error (never raises
    into the live lead call — the earner is protected by construction)."""

    kernel: Any  # RealtimeVoiceKernel (typed Any to keep the type off the agent)
    session: Any  # KernelSession
    base_ctx: Any  # CallContext
    _provider_choice: Any = None  # cached ProviderChoice
    _lang_resolver: Any = None  # per-call TurnLanguageResolver (sticky, adaptive, lazy)


# --------------------------------------------------------------------------- #
# CONSTRUCTION (once per call, after the campaign + tenant resolve)
# --------------------------------------------------------------------------- #
def build_for_call(
    *,
    tenant_id: str,  # the campaign record's OWNING tenant (camp["tenant_id"]) — NOT a body value
    call_id: str,  # = room_name (the outbound room id)
    lead_phone: str,  # parsed from the room name (mem.parse_phone)
    campaign_id: str,  # from dispatch metadata (meta["campaign_id"])
    campaign_tenant_id: str,  # the campaign record's owner (same source) — fail-closed cross-check
    fields: Optional[dict] = None,  # the live campaign `fields` dict (prompt.py shape)
    recap: str = "",
    pg_memory: str = "",
    locale: str = "hi-IN",
) -> Optional[OutboundKernel]:
    """Construct the per-call outbound kernel façade, or None.

    Returns None on ANY failure OR if the flag is OFF — the caller then uses its
    legacy path unchanged. C2 fail-closed: stamps a server-side KernelSession from
    the CAMPAIGN RECORD's owning tenant (see §4 of the PLAN) and cross-checks it
    against `campaign_tenant_id`; a mismatch/blank raises TenantIdentityError,
    caught here -> None -> legacy path (the call still proceeds; the kernel simply
    disengages, logged LOUD). Never raises into the agent (the earner).
    `is_manager` is intentionally absent — an outbound lead dial is never a manager
    persona.
    """
    if not kernel_outbound_enabled():
        return None
    try:
        from voice_kernel import CallContext, KernelConfig, KernelSession
        from voice_kernel.packet import PacketMeta

        cfg = KernelConfig.from_env()
        session = KernelSession(
            tenant_id=tenant_id,  # campaign-record owner (server-written), never a body value
            call_id=call_id,
            direction="outbound",
            stamped_by="server",
        )
        # fail-closed cross-check (raises on mismatch/blank -> caught below).
        session.assert_matches_campaign(campaign_tenant_id or tenant_id)
        meta = PacketMeta(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            call_id=call_id,
            room=call_id,
            lead_phone=lead_phone,
            locale=locale,
            direction="outbound",
            ts_iso=_now_iso(),
        )
        base_ctx = CallContext(
            meta=meta,
            fields=dict(fields or {}),
            recap=recap,
            session=session,
        )
        kernel = _build_kernel_with_impls(cfg, tenant_id, campaign_id, dict(fields or {}))
        return OutboundKernel(kernel=kernel, session=session, base_ctx=base_ctx)
    except Exception as exc:  # never break the earner; disengage the kernel, run legacy
        log.warning(
            "outbound kernel build failed (tenant=%s call=%s) -> legacy: %r",
            tenant_id, call_id, exc,
        )
        return None


# --------------------------------------------------------------------------- #
# BOX MEMORY BINDING (droplet-free by default; the box injects its RLS asession)
# --------------------------------------------------------------------------- #
_BOX_ASESSION: Any = None  # set once on the box via bind_box_memory(); None in CI


def bind_box_memory(asession: Any) -> None:
    """ON-THE-BOX seam: the outbound agent's box-startup calls this ONCE with the
    box's RLS `asession` factory (droplet_work.db.engine.asession) so live lead
    memory persists under tenant RLS. Until called, the façade defaults to
    empty-memory and imports ZERO droplet modules (the kernel-isolation guarantee
    + clean CI). Idempotent; pass None to unbind (tests)."""
    global _BOX_ASESSION
    _BOX_ASESSION = asession


def _resolve_box_asession() -> Any:
    """Return the box-injected asession (or None). NEVER imports droplet_work
    itself — the box must inject via bind_box_memory(); this keeps the façade
    droplet-free by construction so importing/using it in CI cannot pull the box
    DB layer into sys.modules (the isolation tests depend on this)."""
    return _BOX_ASESSION


def _script_vars(fields: dict) -> dict:
    """Variables for the vendor-script {{placeholders}}, sourced from the live
    fields dict (agent / company / product names etc.)."""
    f = fields or {}
    out = {}
    for k in ("agent_name", "company_name", "product_name", "price_offer", "city"):
        v = f.get(k)
        if v:
            out[k] = str(v)
    return out


def _build_kernel_with_impls(cfg, tenant_id: str, campaign_id: str, fields: dict):
    """The ONE place that registers the W2-W7 concretes. A missing/disabled wave
    degrades to its Null impl automatically (the kernel ships Null defaults), so a
    partial deployment is always safe. This is also the single point that adapts
    to the EXACT exported impl factory names — if a wave renamed a factory, only
    this function changes, never the agent.

    Byte-for-byte the same wiring as inbound._build_kernel_with_impls (one brain);
    the only structural difference upstream is the session's direction='outbound'.
    """
    from voice_kernel import build_kernel

    impls: dict = {}

    # W3 context + vendor script (authoritative campaign compile). The vendor
    # script is the AUTHORITATIVE blueprint when present (Founder fix #1).
    try:
        from voice_kernel.context import (
            ContextEngineImpl,
            VendorScriptEngineImpl,
            compile_campaign,
        )

        vs = VendorScriptEngineImpl()
        raw_script = str((fields or {}).get("raw_script", ""))
        if raw_script:
            vs.register(campaign_id, raw_script, variables=_script_vars(fields))
        brief = raw_script or str((fields or {}).get("product_summary", ""))
        compiled = compile_campaign(
            tenant_id=tenant_id, campaign_id=campaign_id, brief=brief, fields=fields,
        )
        impls["context"] = ContextEngineImpl(
            {campaign_id: compiled}, vendor_script=vs, safety_rules="",
        )
        impls["vendor_script"] = vs
    except Exception as exc:
        log.warning("W3 context impl unavailable -> Null: %r", exc)

    # W2 brain packs (use-case L1 + industry L2 + L0 disclosure with banned-phrase
    # guard — kills "AI assistant").
    try:
        from voice_kernel.brain_packs import build_brain_packs

        impls["brain_packs"] = build_brain_packs()
    except Exception as exc:
        log.warning("W2 brain_packs unavailable -> Null: %r", exc)

    # W4 rag (stage-aware; degrades to EMPTY with no backends wired — safe).
    try:
        from voice_kernel.rag import build_rag_runtime

        impls["rag"] = build_rag_runtime()
    except Exception as exc:
        log.warning("W4 rag unavailable -> Null: %r", exc)

    # W5 speech planner + provider router (the Sarvam authoritative-routing fix).
    try:
        from voice_kernel.providers import build_provider_router
        from voice_kernel.speech import build_speech_planner

        impls["router"] = build_provider_router()
        impls["speech"] = build_speech_planner()
    except Exception as exc:
        log.warning("W5 speech/router unavailable -> Null: %r", exc)

    # W7 lead memory (PG-backed, RLS-isolated). Constructed WITHOUT eagerly binding
    # the box DB session (droplet-free by default); the box-deploy hook injects the
    # real RLS asession via bind_box_memory() so live persistence is wired ON THE
    # BOX ONLY, never in CI.
    try:
        from voice_kernel.memory import LeadMemoryService

        asession = _resolve_box_asession()
        impls["memory"] = (
            LeadMemoryService(asession=asession) if asession is not None
            else LeadMemoryService(asession=None)
        )
    except Exception as exc:
        log.warning("W7 memory unavailable -> Null: %r", exc)

    return build_kernel(cfg, **impls)


# --------------------------------------------------------------------------- #
# THE FUNCTIONS THE AGENT HOOK CALLS
# --------------------------------------------------------------------------- #
def assemble_outbound_instructions(
    ik: Optional[OutboundKernel],
    *,
    legacy_render: Callable[[], str],
    fields: Optional[dict] = None,
    recap: str = "",
    grounding: str = "",
    pg_memory: str = "",
) -> str:
    """The system-prompt / instruction string for the outbound persona.

    OFF / None ik / ANY error => EXACTLY `legacy_render()` (byte-identical to
    today's `build_system_prompt(fields)` + the lead-name / OPENER_ALREADY_SAID /
    recap appends — the caller passes the WHOLE legacy block as the lambda). ON =>
    the kernel packet prefix assembled from the WIRED kernel (all real W2-W7
    impls). We do NOT route the ON path through `voice_kernel.adapter.
    instructions_provider` because that builds a FRESH Null-impl kernel — we must
    use the per-call wired kernel `ik.kernel`. The OFF branch (`ik is None`)
    returns `legacy_render()`, the same byte-identical guarantee
    `test_adapter_off_identity` proves (the W1 OFF-identity test covers BOTH
    inbound and outbound field shapes — it exercises the legacy renderer)."""
    if ik is None:
        return legacy_render()
    try:
        from dataclasses import replace

        ctx = ik.base_ctx
        if fields is not None or recap or grounding or pg_memory:
            new_fields = dict(fields) if fields is not None else dict(ctx.fields)
            if grounding:
                new_fields.setdefault("grounding", grounding)
            if pg_memory:
                new_fields.setdefault("pg_memory", pg_memory)
            ctx = replace(ctx, fields=new_fields, recap=recap or ctx.recap)
        return ik.kernel.assemble_prefix(ctx)
    except Exception as exc:  # never emit a broken prompt — fall back to legacy
        log.warning("assemble_outbound_instructions failed -> legacy: %r", exc)
        return legacy_render()


def _lang_resolver_for(ik: "OutboundKernel"):
    """Return (lazily constructing) the per-call TurnLanguageResolver, seeded from
    the call locale (default Hinglish — NEVER English). Stored on the façade so the
    sticky 'keep prior on uncertain' state survives across turns of one call."""
    if ik._lang_resolver is None:
        from voice_kernel.language import TurnLanguageResolver

        locale = ""
        try:
            locale = ik.base_ctx.meta.locale or ""
        except Exception:
            locale = ""
        ik._lang_resolver = TurnLanguageResolver(seed_locale=locale)
    return ik._lang_resolver


async def on_turn(
    ik: Optional[OutboundKernel],
    *,
    user_text: str,
    detected_lang: str,
    stage: Any = None,
    history_len: int = 0,
) -> dict:
    """HOT path, per turn. Returns a plain dict the agent can use WITHOUT importing
    kernel types:

        {"reply_lang": str, "tts_lang": str, "lang_switched": bool,
         "rag_suffix": str|None, "speech_plan": None}

    LANGUAGE (the founder's correct adaptive spec): `detected_lang` is the RAW
    Sarvam STT language for this utterance (or "" / "unknown" when STT auto-detect
    did not surface one). We resolve it ADAPTIVELY each turn — prefer the real STT
    code, else light-classify the transcript text, else (uncertain/short) KEEP the
    PRIOR turn's language. We NEVER force English. The resolved language is fed
    BOTH into the LLM (the soft `USER LANGUAGE: <lang> — mirror it.` turn directive,
    via TurnContext.detected_lang) AND back to the agent as `tts_lang` (the
    SPEAKABLE TTS code, e.g. hi-IN / en-IN) so the agent sets the per-turn TTS code.

    Never blocks beyond the RAG hard deadline (retrieve runs parallel to the LLM
    start; on timeout it returns empty). On OFF / None ik it returns an inert dict
    so the agent's legacy turn is unchanged (the earner is protected).
    """
    if ik is None:
        return {
            "reply_lang": detected_lang,
            "tts_lang": "",
            "lang_switched": False,
            "rag_suffix": None,
            "speech_plan": None,
        }
    try:
        from voice_kernel.contracts import TurnContext
        from voice_kernel.packet import Stage

        # ADAPTIVE per-turn language resolution (sticky, never-force-English).
        resolved = _lang_resolver_for(ik).resolve(stt_lang=detected_lang, user_text=user_text)

        turn = TurnContext(
            call_id=ik.session.call_id,
            user_text=user_text,
            detected_lang=resolved.lang,  # RESOLVED (sticky) -> the soft mirror directive
            stage=stage or Stage.GREET,
            history_len=history_len,
        )
        try:
            rag_layer = await ik.kernel.retrieve_turn_layer(turn)  # hard-deadline, never raises
            rag_suffix = ik.kernel.assemble_turn(turn, rag_layer=rag_layer)  # in-memory, no await
        except Exception as exc:
            log.warning("on_turn rag/assemble failed (-> no L5): %r", exc)
            rag_suffix = None
        return {
            "reply_lang": resolved.lang,
            "tts_lang": resolved.tts_lang,
            "lang_switched": resolved.switched,
            "rag_suffix": rag_suffix,
            "speech_plan": None,
        }
    except Exception as exc:  # any setup failure -> inert turn
        log.warning("on_turn failed (-> inert): %r", exc)
        return {
            "reply_lang": detected_lang,
            "tts_lang": "",
            "lang_switched": False,
            "rag_suffix": None,
            "speech_plan": None,
        }


def plan_speech(ik: Optional[OutboundKernel], *, raw_text: str, lang: str):
    """Optional HOT step between LLM and TTS (W5 SpeechPlanner). Returns a
    SpeechPlan or None. OFF / None ik / error => None => the agent uses raw_text
    as-is."""
    if ik is None:
        return None
    try:
        card = ik.kernel.svc.context_engine.build_card(ik.base_ctx)
        return ik.kernel.svc.speech.plan(raw_text, lang, card)
    except Exception as exc:
        log.warning("plan_speech failed (-> raw text): %r", exc)
        return None


def choose_tts(ik: Optional[OutboundKernel], *, provider_pref: str = ""):
    """W5 ProviderRouter authoritative resolve (the Sarvam fix). Returns a
    ProviderChoice whose `.tts` the agent feeds to `_build_tts()`. OFF / None ik
    => a ProviderChoice(tts='elevenlabs') so the legacy default is preserved
    (outbound today hard-codes ElevenLabs at agent.py:563).

    The router is AUTHORITATIVE: there is NO "skip the resolver" branch on the ON
    path — the SELECTED provider is honoured (lean/standard -> sarvam,
    growth/premium/enterprise -> elevenlabs, explicit `tts_provider`/`voice_id`
    field override wins).
    """
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


def on_tts_error(ik: Optional[OutboundKernel], provider: str, code: int):
    """Fail-LOUD fallback: on a Sarvam build/stream error the agent calls this to
    get an EXPLICIT next ProviderChoice (router.on_error). Logged at INFO with the
    named swap so 'selected vs actual' can never silently diverge."""
    if ik is None:
        from voice_kernel.contracts import ProviderChoice

        return ProviderChoice(tts="elevenlabs", reason="kernel-off")
    try:
        choice = ik.kernel.svc.router.on_error(provider, code)
        ik._provider_choice = choice
        log.info(
            "outbound TTS fail-loud swap: %s(code=%s) -> %s (%s)",
            provider, code, choice.tts, choice.reason,
        )
        return choice
    except Exception as exc:
        from voice_kernel.contracts import ProviderChoice

        log.warning("on_tts_error failed (-> elevenlabs): %r", exc)
        return ProviderChoice(tts="elevenlabs", reason=f"on_error-failed:{exc!r}")


async def persist_post_call(
    ik: Optional[OutboundKernel],
    *,
    lead_phone: str,
    turns: Sequence[dict],
    name: str = "",
    raw_summary: str = "",
    outcome: str = "",  # accepted for forward-compat; not yet consumed by W7
) -> None:
    """COLD path, post-call (W7). Writes structured lead memory using the
    SERVER-STAMPED session tenant (the campaign-record owner). Never raises into
    the shutdown callback. OFF / None ik => no-op (the agent's legacy
    `mem.save_memory` + transcript write still run)."""
    if ik is None:
        return
    try:
        await ik.kernel.svc.memory.extract_and_persist(
            tenant_id=ik.session.tenant_id,  # server-stamped, never a body value
            lead_phone=lead_phone,
            turns=list(turns or []),
            raw_summary=raw_summary,
            name=name,
            llm=None,
        )
    except Exception as exc:
        log.warning("persist_post_call failed (non-fatal COLD): %r", exc)


__all__ = [
    "kernel_outbound_enabled",
    "OutboundKernel",
    "build_for_call",
    "bind_box_memory",
    "assemble_outbound_instructions",
    "on_turn",
    "plan_speech",
    "choose_tts",
    "on_tts_error",
    "persist_post_call",
]
