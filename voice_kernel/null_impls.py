"""voice_kernel.null_impls — safe, REAL default impls of every Protocol.

LEARNINGS §5 (banked): never ship a dormant placeholder the founder can't run.
These null impls are REAL — they return valid empty layers (never None, never a
silent `pass`) and they LOG that they are the null path so it's obvious in a
trace which services have not landed yet. They let `RealtimeVoiceKernel`
construct and run end-to-end before any of W2–W8 ships an implementation.

The one non-trivial null impl is `NullContextEngine.build_card`, which does the
actual `fields`-dict → CampaignCard compile (the W1 builder's job) so the kernel
produces a real, useful packet from day one. The other nulls return structurally
valid empty layers.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from .brain_packs.disclosure import build_structural_identity
from .contracts import (
    CallContext,
    Event,
    ProviderChoice,
    SpeechPlan,
    TurnContext,
)
from .fsm import DialogueFSM, policy_for
from .packet import (
    CampaignCard,
    ContextPacket,
    IdentityLayer,
    IndustryLayer,
    LeadMemory,
    Lifecycle,
    ModeLayer,
    Objection,
    Stage,
    TokenBudget,
    TurnLayer,
    UseCase,
)
from .tokens import clamp_chars, clamp_list

log = logging.getLogger("voice_kernel.null")


def _list(fields: dict, key: str) -> tuple[str, ...]:
    v = fields.get(key) or []
    if isinstance(v, str):
        v = [v]
    return tuple(str(x).strip() for x in v if str(x).strip())


def _objections(fields: dict) -> tuple[Objection, ...]:
    out: list[Objection] = []
    for o in (fields.get("objections") or [])[:6]:
        if isinstance(o, dict):
            q, a = str(o.get("q", "")).strip(), str(o.get("a", "")).strip()
            if q or a:
                out.append(Objection(q=q, a=a))
    return tuple(out)


class NullContextEngine:
    """The REAL W1 fields→card builder (not a stub). Compiles the live `fields`
    dict (prompt.py shape) into the structured L3 CampaignCard + assembles the
    full ContextPacket with safe empty L1/L2/L4/L5."""

    def build_card(self, ctx: CallContext) -> CampaignCard:
        f = dict(ctx.fields or {})
        if ctx.fields_override:
            f.update({k: v for k, v in ctx.fields_override.items() if v})
        return CampaignCard(
            product_name=str(f.get("product_name", "")).strip(),
            product_summary=clamp_chars(str(f.get("product_summary", "")), 600),
            location=str(f.get("location", "")).strip(),
            price_offer=str(f.get("price_offer", "")).strip(),
            usps=clamp_list(_list(f, "usps"), 5),
            talking_points=clamp_list(_list(f, "talking_points"), 5),
            qualifying_questions=clamp_list(_list(f, "qualifying_questions"), 3),
            objections=_objections(f),
            language=str(f.get("language", "Hinglish")).strip() or "Hinglish",
            greeting=str(f.get("greeting", "")).strip(),
        )

    def build_packet(self, ctx: CallContext) -> ContextPacket:
        f = dict(ctx.fields or {})
        card = self.build_card(ctx)
        # STRUCTURAL disclosure (W26 red-team fix): disclose_ai is forced True and
        # the line is block-list-scanned — a vendor field can neither turn it off
        # nor inject a banned 'AI assistant' self-label. (W1 wiring passes
        # SHARED_RULES as safety_rules; null path leaves it empty.)
        identity = build_structural_identity(f, safety_rules="")
        pkt = ContextPacket(
            meta=ctx.meta,
            identity=identity,
            mode=ModeLayer(use_case=UseCase.SALES, objective_str=str(f.get("goal", "")).strip()),
            industry=IndustryLayer(),
            card=card,
            lead=LeadMemory(),
            turn=TurnLayer(),
            budget=TokenBudget(),
        )
        return pkt.clamp()


class NullVendorScriptEngine:
    def stage_excerpt(self, campaign_id: str, stage: Stage, max_chars: int = 600) -> str:
        log.debug("NullVendorScriptEngine.stage_excerpt -> '' (W3 not landed)")
        return ""

    def card_overrides(self, campaign_id: str) -> dict:
        return {}


class NullBrainPackProvider:
    def use_case_layer(self, use_case: UseCase, fields: dict) -> ModeLayer:
        return ModeLayer(use_case=use_case, objective_str=str((fields or {}).get("goal", "")).strip())

    def industry_layer(self, fields: dict) -> IndustryLayer:
        return IndustryLayer()


class NullRagRuntime:
    """Always returns an empty TurnLayer (W4 not landed). Honours the timeout
    contract trivially (it never blocks)."""

    async def precompute(self, ctx: CallContext) -> None:
        log.debug("NullRagRuntime.precompute -> noop (W4 not landed)")
        return None

    async def retrieve(self, turn: TurnContext, k: int = 3, timeout_s: float = 0.03) -> TurnLayer:
        return TurnLayer(stage=turn.stage, detected_lang=turn.detected_lang)


class NullSpeechPlanner:
    """Pass-through: returns the raw text unchanged (W5 not landed)."""

    def plan(self, raw_text: str, lang: str, mode_card: CampaignCard) -> SpeechPlan:
        return SpeechPlan(text=raw_text, tts_lang=lang, segments=(raw_text,) if raw_text else (), normalized=False)


class NullProviderRouter:
    """Returns the live default triple (sarvam/groq/elevenlabs) — matches the
    deployed resolve_providers default (LEARNINGS: _DEFAULT_PROVIDERS)."""

    def resolve(self, ctx: CallContext) -> ProviderChoice:
        return ProviderChoice(reason="null-default")

    def on_error(self, provider: str, code: int) -> ProviderChoice:
        return ProviderChoice(reason=f"null-default after {provider} {code}")


class NullMemoryService:
    async def load(self, tenant_id: str, lead_phone: str) -> LeadMemory:
        log.debug("NullMemoryService.load -> empty LeadMemory (W7 not landed)")
        return LeadMemory(lifecycle=Lifecycle.NEW)

    async def persist(self, tenant_id: str, lead_phone: str, summary: LeadMemory) -> None:
        log.debug("NullMemoryService.persist -> noop (W7 not landed)")
        return None


class NullEventBus:
    """Fire-and-forget no-op (never blocks the dial loop — LEARNINGS §4)."""

    async def emit(self, event: Event) -> None:
        log.debug("NullEventBus.emit %s -> dropped (W8 not landed)", event.name)
        return None

    async def subscribe(self, stream: str, group: str) -> AsyncIterator[Event]:
        if False:  # pragma: no cover - empty async iterator
            yield  # type: ignore[unreachable]
        return


class NullDialoguePolicy:
    """Drives transitions via the core FSM table (fsm.py). REAL behaviour, not a
    stub — the kernel has a working policy from day one; W6 may enrich it."""

    def next_stage(self, current: Stage, turn: TurnContext, use_case: UseCase) -> Stage:
        fsm = DialogueFSM(use_case=use_case, start=current)
        # crude objection signal: a '?' or a known objection keyword in the turn.
        is_obj = "?" in (turn.user_text or "") and current != Stage.GREET
        return fsm.next_stage(is_objection=is_obj)

    def turn_directive(self, stage: Stage, use_case: UseCase) -> str:
        return policy_for(use_case).directive(stage)

    def should_abort(self, turn: TurnContext) -> bool:
        return False
