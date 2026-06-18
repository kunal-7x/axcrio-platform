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

from ..contracts import CallContext, ContextEngine, VendorScriptEngine
from ..packet import (
    CampaignCard,
    ContextPacket,
    IdentityLayer,
    IndustryLayer,
    LeadMemory,
    ModeLayer,
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

        identity = IdentityLayer(
            agent_name=str(f.get("agent_name", "")).strip() or "Riya",
            company_name=str(f.get("company_name", "")).strip(),
            disclose_ai=bool(f.get("disclose_ai", True)),
            ai_disclosure_str=str(f.get("ai_disclosure", "")).strip(),
            safety_rules=self._safety_rules,  # L0 PLATFORM safety, never fenced, first
        )

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
    def _apply_vendor_overrides(self, ctx: CallContext, card: CampaignCard) -> CampaignCard:
        """When a vendor script exists, it is the AUTHORITATIVE blueprint. We fold
        its card-level overrides (greeting/opener) and surface its GREET/INTRO
        blueprint as a leading talking point so the model follows the vendor's
        flow ordering. The script text remains UNTRUSTED — it lands inside the
        card, which the packet renderer fences below the PLATFORM safety layer."""
        if self._vendor is None:
            return card
        cid = ctx.meta.campaign_id
        overrides = self._vendor.card_overrides(cid) or {}
        new = card
        greeting = overrides.get("greeting")
        if greeting:
            new = replace(new, greeting=greeting)
        # surface the opening blueprint (greet+intro) as the FIRST talking points,
        # so the flow ordering the vendor wrote takes precedence over the default.
        blueprint_bits: list[str] = []
        for stage in (Stage.GREET, Stage.PERMISSION, Stage.INTRO):
            ex = self._vendor.stage_excerpt(cid, stage, max_chars=240)
            if ex:
                blueprint_bits.append(ex)
        if blueprint_bits:
            # prepend blueprint (authoritative) ahead of any existing talking points.
            merged = tuple(blueprint_bits) + tuple(new.talking_points)
            new = replace(new, talking_points=merged[:5])
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


# Sanity: the impl conforms to the Protocol surface (build_card + build_packet).
_PROTOCOL_CHECK: type[ContextEngine] = ContextEngineImpl  # type: ignore[assignment]
