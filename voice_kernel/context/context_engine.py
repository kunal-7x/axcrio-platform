"""voice_kernel.context.context_engine — the W1+W3 ContextEngine implementation.

Assembles the full ContextPacket from:
  - a CompiledCampaign  (T0 lossless raw + T1 full_* + T2 compact card)   [W3 §1]
  - the Campaign Understanding (use_case / industry / objective)          [W3 §2]
  - the VendorScriptEngine (authoritative blueprint, when present)        [W3 §4]
  - the live `fields` dict (back-compat: campaigns with no compiled artifact yet)

It is the concrete `ContextEngine` Protocol impl (build_card + build_packet) that
downstream waves register via `build_kernel(cfg, context=..., vendor_script=...)`.

Trust boundary (C3) — enforced structurally:
  - L0 (identity + SHARED_RULES safety) is PLATFORM, authored by us, rendered
    FIRST by position (packet._render_platform_layer). It is NEVER fenced.
  - The campaign card (L3) is UNTRUSTED vendor content; the packet renderer wraps
    it in a CAMPAIGN_BRIEF fence BELOW L0. The vendor script blueprint is folded
    into the card's talking_points/greeting (still inside the same fence) so it
    can guide the flow but can NEVER sit above or override the safety layer.

When a campaign has a compiled artifact, build_card reads it (no per-turn
distillation). When it doesn't (legacy campaign mid-migration), build_card
falls back to compiling the live `fields` on the fly — so the engine is a
drop-in for NullContextEngine and never regresses an un-migrated campaign.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from ..brain_packs.disclosure import build_structural_identity
from ..contracts import CallContext, ContextEngine, VendorScriptEngine
from ..packet import (
    CampaignCard,
    ContextPacket,
    IdentityLayer,
    IndustryLayer,
    LeadMemory,
    ModeLayer,
    Objection,
    Stage,
    TokenBudget,
    TurnLayer,
    UseCase,
)
from .campaign_compiler import CompiledCampaign, compile_campaign
from .understanding import CampaignUnderstanding, classify


class ContextEngineImpl:
    """The real W1+W3 ContextEngine.

    Parameters
    ----------
    campaigns : dict[campaign_id -> CompiledCampaign]
        Save-time artifacts. Hot reads are pure dict lookups.
    vendor_script : VendorScriptEngine | None
        The authoritative-blueprint engine; folded into the card when a script
        exists for the campaign. None -> default flow (no script overrides).
    safety_rules : str
        The PLATFORM SHARED_RULES text (L0). Passed in at wiring time so the
        kernel stays disjoint from droplet_work/prompt.py (no import). When the
        integration seam wires it, it passes prompt.SHARED_RULES verbatim.
    budget : TokenBudget | None
        Per-layer caps; defaults to the standard TokenBudget.
    """

    def __init__(
        self,
        campaigns: Optional[dict] = None,
        *,
        vendor_script: Optional[VendorScriptEngine] = None,
        safety_rules: str = "",
        budget: Optional[TokenBudget] = None,
    ):
        self._campaigns: dict[str, CompiledCampaign] = dict(campaigns or {})
        self._vendor = vendor_script
        self._safety_rules = safety_rules or ""
        self._budget = budget or TokenBudget()

    # -- registration (save-time) -------------------------------------------
    def register(self, compiled: CompiledCampaign) -> None:
        self._campaigns[compiled.campaign_id] = compiled

    # -- the compiled artifact (or an on-the-fly compile of live fields) -----
    def _compiled_for(self, ctx: CallContext) -> CompiledCampaign:
        cid = ctx.meta.campaign_id
        cached = self._campaigns.get(cid)
        if cached is not None:
            return cached
        # legacy / un-migrated campaign: compile the live fields on the fly so we
        # NEVER regress an existing campaign. (vendor-authored fields win.)
        f = dict(ctx.fields or {})
        if ctx.fields_override:
            f.update({k: v for k, v in ctx.fields_override.items() if v})
        brief = str(f.get("raw_script", "")) or str(f.get("product_summary", ""))
        return compile_campaign(
            tenant_id=ctx.meta.tenant_id,
            campaign_id=cid,
            brief=brief,
            fields=f,
        )

    # -- ContextEngine.build_card -------------------------------------------
    def build_card(self, ctx: CallContext) -> CampaignCard:
        compiled = self._compiled_for(ctx)
        card = compiled.card
        # fold vendor-script overrides (e.g. the vendor's own greeting/opener) —
        # the script is AUTHORITATIVE when present (Founder's #1 fix).
        card = self._apply_vendor_overrides(ctx, card)
        return card

    # -- ContextEngine.build_packet -----------------------------------------
    def build_packet(self, ctx: CallContext) -> ContextPacket:
        compiled = self._compiled_for(ctx)
        f = dict(ctx.fields or {})
        if ctx.fields_override:
            f.update({k: v for k, v in ctx.fields_override.items() if v})

        card = self._apply_vendor_overrides(ctx, compiled.card)
        und = compiled.understanding

        identity = build_structural_identity(f, safety_rules=self._safety_rules)

        mode = ModeLayer(
            use_case=und.use_case,
            objective_str=und.objective,
            success_criteria=self._success_criteria(und),
            brain_pack_id=f"{und.use_case.value}/{und.industry}" if und.industry else und.use_case.value,
        )
        industry = IndustryLayer(
            pack_id=und.industry,
            vertical_terms=self._vertical_terms(card, und),
        )

        pkt = ContextPacket(
            meta=ctx.meta,
            identity=identity,
            mode=mode,
            industry=industry,
            card=card,
            lead=LeadMemory(),  # L4 enriched later by the kernel (memory.load)
            turn=TurnLayer(),
            budget=self._budget,
        )
        return pkt.clamp()

    # -- vendor-script authoritative overrides ------------------------------
    # The FLOW stages the vendor authors and where each lands on the card so the
    # WHOLE blueprint (greet→permission→intro→qualify→pitch→objection→close)
    # reaches the rendered prompt — not just the opening three (RED-TEAM BLOCKER 1
    # fix). Each stage is surfaced through its NATURAL card slot so the packet
    # renderer already prints it (_render_card_body): TALKING POINTS / QUALIFY /
    # OBJECTIONS / CLOSE. The card is fenced below the PLATFORM safety layer, so
    # authoritative-on-flow never means authoritative-over-safety (C3 holds).
    _FLOW_TO_TALKING = (Stage.GREET, Stage.PERMISSION, Stage.INTRO)

    def _apply_vendor_overrides(self, ctx: CallContext, card: CampaignCard) -> CampaignCard:
        """When a vendor script exists, it is the AUTHORITATIVE blueprint. We fold
        the FULL ordered flow into the card's matching fields so the model follows
        the vendor's stage ordering end-to-end — opener→permission→intro into the
        talking points, QUALIFY into the qualifying questions, PITCH appended to
        the talking points, OBJECTION into the objections, CLOSE into the closing
        lines. The script text stays UNTRUSTED — it lands inside the card, which
        the packet renderer fences below the PLATFORM safety layer.

        Two RED-TEAM fixes folded here:
          - BLOCKER 1: QUALIFY/PITCH/OBJECTION/CLOSE are no longer dropped — each
            reaches the prompt through its own card slot.
          - BLOCKER 2: vendor blueprint is MERGED with (never evicts) the vendor's
            own authored card content — vendor content leads, dedup avoids repeats,
            and packet.clamp() (not a raw slice here) does the final cap so the
            authoritative head always survives.
        """
        if self._vendor is None:
            return card
        cid = ctx.meta.campaign_id
        new = card

        overrides = self._vendor.card_overrides(cid) or {}
        greeting = overrides.get("greeting")
        if greeting:
            new = replace(new, greeting=greeting)

        # 1. opener + value-prop flow (greet+permission+intro) leads the talking
        # points. The vendor's PITCH/value-prop has no separate Stage enum member;
        # vendors write it under an "intro/reason/why-calling" heading (mapped to
        # Stage.INTRO) or it rides into the QUALIFY segment — either way it reaches
        # the prompt (INTRO -> talking_points here, QUALIFY -> qualifying below).
        talking_lead = [
            ex
            for stage in self._FLOW_TO_TALKING
            if (ex := self._vendor.stage_excerpt(cid, stage, max_chars=240))
        ]
        if talking_lead:
            # vendor flow FIRST, then the vendor-authored talking_points — merge,
            # don't evict (BLOCKER 2). clamp() applies the final cap downstream.
            new = replace(
                new,
                talking_points=_merge_unique(talking_lead, new.talking_points),
            )

        # 3. QUALIFY -> qualifying_questions (vendor's discovery flow, leading).
        qualify = self._vendor.stage_excerpt(cid, Stage.QUALIFY, max_chars=240)
        if qualify:
            new = replace(
                new,
                qualifying_questions=_merge_unique([qualify], new.qualifying_questions),
            )

        # 4. OBJECTION -> objections (the vendor's rebuttal blueprint, leading).
        objection = self._vendor.stage_excerpt(cid, Stage.OBJECTION, max_chars=300)
        if objection:
            vendor_obj = Objection(q="(vendor-scripted objection handling)", a=objection)
            existing = tuple(o for o in new.objections if o.a != objection)
            new = replace(new, objections=(vendor_obj,) + existing)

        # 5. CLOSE -> closing_lines (the vendor's authored ask, leading).
        close = self._vendor.stage_excerpt(cid, Stage.CLOSE, max_chars=240)
        if close:
            new = replace(
                new,
                closing_lines=_merge_unique([close], new.closing_lines),
            )
        return new

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _success_criteria(und: CampaignUnderstanding) -> str:
        bits = []
        if und.needs_booking:
            bits.append("a concrete booking/visit is scheduled")
        if und.needs_handoff:
            bits.append("a qualified lead is handed to a human")
        if und.needs_whatsapp:
            bits.append("agreed details are sent on WhatsApp")
        return "; ".join(bits)

    @staticmethod
    def _vertical_terms(card: CampaignCard, und: CampaignUnderstanding) -> tuple[str, ...]:
        """A small set of vertical terms for L2. Derived from the understanding's
        winning industry-signal hits (the vendor's OWN words), NOT a hardcoded
        glossary — so it stays campaign-faithful."""
        terms = tuple(t for t in und.industry_scores.keys())
        return terms[:8]


def _merge_unique(lead, existing) -> tuple[str, ...]:
    """Merge `lead` (authoritative vendor flow, kept FIRST) ahead of `existing`
    (the vendor's own authored card content, kept after) WITHOUT evicting either
    (RED-TEAM BLOCKER 2) and WITHOUT duplicating a line that already appears
    (the unsegmented-opener duplicate bug). Dedup is whitespace/case-insensitive
    and substring-aware: an `existing` item that is already wholly contained in a
    leading blueprint excerpt is dropped (the blueprint says it better/in-order).
    The final per-field cap is applied later by packet.clamp(), so the
    authoritative head always survives the trim."""
    out: list[str] = []
    seen: list[str] = []  # normalized forms already emitted

    def _norm(s: str) -> str:
        return " ".join(str(s).split()).casefold()

    for item in list(lead) + list(existing):
        s = (item or "").strip()
        if not s:
            continue
        n = _norm(s)
        if any(n == k or n in k or k in n for k in seen):
            continue
        seen.append(n)
        out.append(s)
    return tuple(out)


# Sanity: the impl conforms to the Protocol surface (build_card + build_packet).
_PROTOCOL_CHECK: type[ContextEngine] = ContextEngineImpl  # type: ignore[assignment]
