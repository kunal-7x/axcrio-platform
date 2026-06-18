"""voice_kernel.kernel — RealtimeVoiceKernel: the three-speed orchestrator.

Wires HOT / WARM / COLD around the contracts via dependency injection. Safe
no-op defaults (null_impls) so it runs end-to-end before W2–W8 land.

RED-TEAM LATENCY FIXES folded in (these are load-bearing, not cosmetic):

  1. RAG is NEVER awaited before the LLM. `assemble_turn` does an IN-MEMORY
     packet render only (no await). Live RAG retrieval runs PARALLEL to the
     preemptive LLM start via `retrieve_turn_layer(...)` with a hard deadline;
     on timeout it returns an empty layer and the turn proceeds. The HOT reply
     path never blocks on Qdrant/PG.

  2. The opener is independent of WARM I/O. `assemble_prefix_core(ctx)` is a
     PURE, SYNC, await-free assembly of L0..L3 (+ optional L4 if already
     loaded) used to construct the Agent and fire the opener immediately. The
     async `enrich_prefix(...)` applies L4 lead-memory afterwards via a
     background task — matching the proven inbound grounding-prefetch shape
     (create_task, NOT on the reply path). DoD: no await between prefix-core and
     the opener.

  3. L5 is hard-clamped INSIDE the per-turn render (packet.render_turn_suffix),
     not only in the WARM builder.

The kernel exposes exactly two assembly entry points the agents call:
  - assemble_prefix(ctx)  -> str   (WARM, once/call; convenience = core + L4)
  - assemble_turn(turn)   -> str|None (HOT, per turn; in-memory render, no await)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import Optional

from .config import KernelConfig
from .contracts import (
    BrainPackProvider,
    CallContext,
    ContextEngine,
    DialoguePolicy,
    EventBus,
    KernelSession,
    MemoryService,
    ProviderRouter,
    RagRuntime,
    SpeechPlanner,
    TurnContext,
    VendorScriptEngine,
)
from .errors import KernelError, TenantIdentityError
from .null_impls import (
    NullBrainPackProvider,
    NullContextEngine,
    NullDialoguePolicy,
    NullEventBus,
    NullMemoryService,
    NullProviderRouter,
    NullRagRuntime,
    NullSpeechPlanner,
    NullVendorScriptEngine,
)
from .packet import ContextPacket, LeadMemory, Stage, TurnLayer

log = logging.getLogger("voice_kernel")


@dataclass
class KernelServices:
    """The 9 injected services. Each defaults to its REAL null impl, so the
    kernel constructs and runs with zero downstream workflows landed."""

    context_engine: ContextEngine = field(default_factory=NullContextEngine)
    vendor_script: VendorScriptEngine = field(default_factory=NullVendorScriptEngine)
    brain_packs: BrainPackProvider = field(default_factory=NullBrainPackProvider)
    rag: RagRuntime = field(default_factory=NullRagRuntime)
    speech: SpeechPlanner = field(default_factory=NullSpeechPlanner)
    router: ProviderRouter = field(default_factory=NullProviderRouter)
    memory: MemoryService = field(default_factory=NullMemoryService)
    events: EventBus = field(default_factory=NullEventBus)
    policy: DialoguePolicy = field(default_factory=NullDialoguePolicy)


class RealtimeVoiceKernel:
    """Three-speed orchestrator. Holds NO live-call state itself beyond the
    per-call packet cache it is handed; pure assembly + delegation."""

    def __init__(self, cfg: KernelConfig, services: Optional[KernelServices] = None):
        self.cfg = cfg
        self.svc = services or KernelServices()

    # --------------------------------------------------------- C2 fail-closed #
    @staticmethod
    def _require_session(ctx: CallContext) -> KernelSession:
        """C2 PRECONDITION (control-flow, not a docstring): the kernel ON path
        REFUSES to assemble without a server-stamped tenant identity, and refuses
        if the session tenant does not match the campaign's owning tenant. A
        violation raises TenantIdentityError — the live call must hang up. This is
        the structural fail-closed gate; it is NOT reached on the OFF path (the
        adapter returns the legacy string before the kernel is ever built)."""
        sess = ctx.session
        if sess is None:
            raise TenantIdentityError(
                "kernel ON path requires a server-stamped KernelSession "
                "(tenant_id + call_id) — refusing to assemble (fail-closed)"
            )
        # cross-check the session tenant against the campaign/meta tenant.
        sess.assert_matches_campaign(ctx.meta.tenant_id)
        # call_id must be coherent across the session and the packet meta.
        if (ctx.meta.call_id or "").strip() and ctx.meta.call_id != sess.call_id:
            raise TenantIdentityError(
                f"call_id mismatch: session={sess.call_id!r} != meta={ctx.meta.call_id!r} "
                f"— refusing (fail-closed)"
            )
        return sess

    # ----------------------------------------------------------------- WARM #
    def assemble_prefix_core(self, ctx: CallContext) -> tuple[str, ContextPacket]:
        """SYNC, await-free. Builds L0..L3 (+ empty L4) and returns
        (prefix_text, packet). Used to construct the Agent and fire the opener
        WITHOUT waiting on any network I/O. Returns the packet so the caller can
        enrich it with L4 afterwards.

        C2: enforces the server-stamped tenant identity FIRST (fail-closed) — no
        packet is assembled under a missing or mismatched tenant."""
        self._require_session(ctx)  # C2 fail-closed precondition (raises -> hang up)
        packet = self.svc.context_engine.build_packet(ctx)
        # brain packs (L1/L2) are pure/sync — fold them in if a provider landed.
        try:
            mode = self.svc.brain_packs.use_case_layer(packet.mode.use_case, ctx.fields)
            industry = self.svc.brain_packs.industry_layer(ctx.fields)
            packet = replace(packet, mode=mode, industry=industry).clamp()
        except KernelError:
            raise
        except Exception as exc:  # never silently fail; degrade to the core packet
            log.warning("brain_pack layering failed, using core packet: %r", exc)
        text = packet.render_stable_prefix()
        suffix = packet.render_call_suffix()
        if suffix:
            text = text + "\n\n" + suffix
        return text, packet

    async def enrich_prefix(self, ctx: CallContext, packet: ContextPacket) -> ContextPacket:
        """ASYNC L4 enrichment. Runs AFTER the opener (background task). Loads
        lead memory and returns an updated packet; the agent applies it via
        update_instructions. Never blocks the opener path."""
        try:
            lead: LeadMemory = await self.svc.memory.load(ctx.meta.tenant_id, ctx.meta.lead_phone)
            return replace(packet, lead=lead).clamp()
        except Exception as exc:
            log.warning("memory.load failed, lead memory skipped: %r", exc)
            return packet

    def assemble_prefix(self, ctx: CallContext) -> str:
        """Convenience WARM entry the inbound adapter feeds into instructions=.
        Synchronous core only (no L4 await) — L4 is applied via enrich_prefix in
        the background. Byte-identical fallback handled by the adapter, not here.
        """
        text, _packet = self.assemble_prefix_core(ctx)
        return text

    async def precompute(self, ctx: CallContext) -> None:
        """WARM: warm the RAG room cache at dial. Fire-and-forget safe."""
        try:
            await self.svc.rag.precompute(ctx)
        except Exception as exc:
            log.warning("rag.precompute failed (non-fatal): %r", exc)

    # ------------------------------------------------------------------ HOT #
    def assemble_turn(self, turn: TurnContext, rag_layer: Optional[TurnLayer] = None) -> Optional[str]:
        """HOT, per turn. IN-MEMORY render only — NO await, NO network. Returns
        the L5 turn suffix to append via turn_ctx.add_message, or None.

        `rag_layer` is OPTIONAL pre-fetched evidence (from retrieve_turn_layer,
        which ran PARALLEL to the preemptive LLM start). If None, the turn
        proceeds with no RAG — the reply path never blocked on retrieval.
        """
        layer = rag_layer or TurnLayer(stage=turn.stage, detected_lang=turn.detected_lang)
        # render via a throwaway minimal packet's turn renderer (pure + clamped).
        suffix = _render_turn_layer(layer, turn)
        return suffix or None

    async def retrieve_turn_layer(self, turn: TurnContext, k: int = 3, timeout_s: float = 0.03) -> TurnLayer:
        """Run RAG retrieval with a HARD deadline, PARALLEL to the LLM start.
        On timeout/error returns an EMPTY TurnLayer — never raises, never blocks
        the reply beyond `timeout_s`."""
        empty = TurnLayer(stage=turn.stage, detected_lang=turn.detected_lang)
        try:
            return await asyncio.wait_for(self.svc.rag.retrieve(turn, k=k, timeout_s=timeout_s), timeout=timeout_s)
        except asyncio.TimeoutError:
            log.debug("rag.retrieve exceeded %.0fms deadline — skipping L5 this turn", timeout_s * 1000)
            return empty
        except Exception as exc:
            log.warning("rag.retrieve failed, skipping L5 this turn: %r", exc)
            return empty

    def next_stage(self, current: Stage, turn: TurnContext, use_case) -> Stage:
        return self.svc.policy.next_stage(current, turn, use_case)

    def should_abort(self, turn: TurnContext) -> bool:
        return self.svc.policy.should_abort(turn)

    # ----------------------------------------------------------------- COLD #
    async def persist_summary(self, tenant_id: str, lead_phone: str, summary: LeadMemory) -> None:
        try:
            await self.svc.memory.persist(tenant_id, lead_phone, summary)
        except Exception as exc:
            log.warning("memory.persist failed (non-fatal, COLD path): %r", exc)


def _render_turn_layer(layer: TurnLayer, turn: TurnContext) -> str:
    """Pure helper: render an L5 TurnLayer to its suffix string with the SAME
    hard clamp AND the SAME C3 fence as ContextPacket.render_turn_suffix
    (red-team: clamp + fence on the HOT path too). Standalone so assemble_turn
    needs no full packet per turn."""
    from .tokens import clamp_chars
    from .packet import _RAG_MAX, _RAG_TEXT_CHARS, FencedText, SourceTrust  # central caps + fence

    parts: list[str] = []
    stage = layer.stage or turn.stage
    if stage:
        parts.append(f"STAGE: {stage.value}")
    lang = layer.detected_lang or turn.detected_lang
    if lang:
        parts.append(f"USER LANGUAGE: {lang} — mirror it.")
    if layer.rag_snippets:
        snips = layer.rag_snippets[:_RAG_MAX]
        rendered = "; ".join(
            f"[{s.source}] {clamp_chars(s.text, _RAG_TEXT_CHARS)}" for s in snips if s.text
        )
        if rendered:
            # C3: retrieved knowledge is untrusted — fence it (data, not commands).
            parts.append(FencedText(SourceTrust.RETRIEVED_KNOWLEDGE, "RELEVANT: " + rendered).render())
    if layer.barge_in_hint:
        parts.append(layer.barge_in_hint)
    return "\n".join(parts)


# Friendly aliases for the keyword-override registration surface. The FROZEN
# registration spec is `build_kernel(cfg, context=impl, vendor_script=impl)`, but
# the dataclass field is `context_engine`. We accept the short, ergonomic names
# (and the field names) so callers can register either way. Additive — the
# existing `rag=`/`memory=` field-name overrides keep working unchanged.
_IMPL_ALIASES = {
    "context": "context_engine",
    "context_engine": "context_engine",
    "vendor_script": "vendor_script",
    "vendor": "vendor_script",
    "brain_packs": "brain_packs",
    "brain": "brain_packs",
}


def build_kernel(cfg: Optional[KernelConfig] = None, services: Optional[KernelServices] = None, **impls) -> RealtimeVoiceKernel:
    """Factory. `cfg` defaults to KernelConfig.from_env() (default OFF).
    Downstream waves register their impls either via a KernelServices instance
    or as keyword overrides, e.g. build_kernel(cfg, rag=MyRag()) or the FROZEN
    spec form build_kernel(cfg, context=ce, vendor_script=vs)."""
    cfg = cfg or KernelConfig.from_env()
    svc = services or KernelServices()
    if impls:
        normalized = {_IMPL_ALIASES.get(k, k): v for k, v in impls.items()}
        svc = replace(svc, **normalized)
    return RealtimeVoiceKernel(cfg, svc)
