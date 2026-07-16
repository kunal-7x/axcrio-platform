"""voice_kernel.brain_packs.provider — the BrainPackProvider implementation (W2).

Binds the FROZEN `BrainPackProvider` Protocol (contracts.py:170):
    use_case_layer(use_case, fields) -> ModeLayer   (L1)
    industry_layer(fields)           -> IndustryLayer (L2)

Both are PURE + SYNC (HOT-path safe). The kernel calls them in
`assemble_prefix_core` (kernel.py:130), wrapped in try/except -> degrades to the
core packet on any failure. This impl NEVER touches agent.py/caller.py/
aim_voice_agent.py and imports ZERO droplet_work modules.

The MODE-AWARE OBJECTIVE ENGINE:
  - use_case_layer looks up the pack (store override if published, else the
    shipped default) and composes ModeLayer.objective_str from the pack's
    abstract behavioral template + the campaign's own `fields["goal"]` (layered
    in, NEVER replacing — Law 2). success_criteria = the pack's terminal-state
    definition. brain_pack_id = provenance pointer for W4/W6.
  - industry_layer resolves the vertical from `fields` (explicit fields["industry"]
    first, else keyword-match against each IndustryPack.match), defaulting to a
    NEUTRAL pack that carries NO vocabulary — so nothing vertical leaks.

Also exposes `identity_layer(fields)` — the STRUCTURAL disclosure helper W1 wires
into IdentityLayer (the disclosure line sits in L0, rendered first, above every
fence). This is not a Protocol method (the Protocol owns L1/L2), but it is part
of W2's deliverable: the compliant Tier-0 default, config-gated.

Pure stdlib. Imports ZERO droplet_work modules.
"""
from __future__ import annotations

from typing import Optional

from ..packet import IdentityLayer, IndustryLayer, ModeLayer, Stage, UseCase
from .delivery import delivery_directive
from .disclosure import DisclosureConfig, DisclosureTier, build_disclosure_str
from .language import language_directive
from .model import NEUTRAL_INDUSTRY, IndustryPack, UseCasePack
from .objection import render_objection_directive
from .packs_data import all_industry_packs, get_use_case_pack
from .registry import BrainPackStore


def _str(fields: dict, key: str, default: str = "") -> str:
    return str((fields or {}).get(key, default) or "").strip()


def _use_case_pack_from_version(body: dict) -> Optional[UseCasePack]:
    """Rebuild a UseCasePack from a stored version body (JSON-round-trippable).
    Returns None if the body is malformed (provider then falls back to default)."""
    try:
        from .model import Stance
        st = body.get("stance") or {}
        stance = Stance(
            key=str(st.get("key", "advance")),
            description=str(st.get("description", "")),
            pushes_sale=bool(st.get("pushes_sale", False)),
            empathy_first=bool(st.get("empathy_first", False)),
        )
        return UseCasePack(
            id=str(body["id"]),
            use_case=UseCase(body["use_case"]) if not isinstance(body.get("use_case"), UseCase) else body["use_case"],
            stance=stance,
            objective_template=str(body.get("objective_template", "")),
            success_criteria=str(body.get("success_criteria", "")),
            opening_style=str(body.get("opening_style", "")),
            closing_style=str(body.get("closing_style", "")),
            data_to_collect=tuple(body.get("data_to_collect", ())),
            push_stop_handoff=str(body.get("push_stop_handoff", "")),
            memory_fields=tuple(body.get("memory_fields", ())),
            stage_skips=frozenset(Stage(s) if not isinstance(s, Stage) else s for s in body.get("stage_skips", ())),
            behavior_pack_ids=tuple(body.get("behavior_pack_ids", ())),
        )
    except Exception:
        return None


def _industry_pack_from_version(body: dict) -> Optional[IndustryPack]:
    try:
        return IndustryPack(
            id=str(body["id"]),
            label=str(body.get("label", "")),
            match=tuple(str(m).lower() for m in body.get("match", ())),
            vertical_terms=tuple(body.get("vertical_terms", ())),
            norm_nudges=tuple(body.get("norm_nudges", ())),
            compliance_ref=str(body.get("compliance_ref", "")),
        )
    except Exception:
        return None


class BrainPacks:
    """The concrete BrainPackProvider. Resolves L1/L2 from the store (published
    overrides) with a fall-through to the shipped defaults. Stateless on the HOT
    path beyond the injected store snapshot (reads only)."""

    def __init__(
        self,
        store: Optional[BrainPackStore] = None,
        *,
        default_disclosure_tier: DisclosureTier = DisclosureTier.BRAND_IDENTITY,
    ) -> None:
        self.store = store
        self.default_disclosure_tier = default_disclosure_tier
        # snapshot the shipped industry defaults once.
        self._industry_defaults: tuple[IndustryPack, ...] = all_industry_packs()

    # ---------------------------------------------------------- L1 (mode) #
    def _resolve_use_case_pack(self, use_case: UseCase, campaign_id: str) -> UseCasePack:
        """Store override (published, or pinned for the campaign) else shipped
        default. version_for_campaign already encodes pin-then-published, so any
        returned version is the one this campaign should use."""
        if self.store is not None:
            pv = self.store.version_for_campaign(campaign_id, "use_case", use_case.value)
            if pv is not None:
                pack = _use_case_pack_from_version(pv.body)
                if pack is not None:
                    return pack
        return get_use_case_pack(use_case)

    def use_case_layer(self, use_case: UseCase, fields: dict) -> ModeLayer:
        """L1 — the mode-aware objective engine. PURE + SYNC.

        Composes the pack's abstract behavioral objective with the campaign's own
        `fields["goal"]` (layered IN, never replaced). If the campaign configured
        no goal, the pack template stands alone (so a mis-configured vendor still
        gets correct mode behavior — the null-impl gap today)."""
        campaign_id = _str(fields, "campaign_id")
        pack = self._resolve_use_case_pack(use_case, campaign_id)

        goal = _str(fields, "goal")
        objective = pack.objective_template
        if goal:
            # the campaign goal SPECIALISES the behavioral objective; it does not
            # replace it (Law 2 — the pack gives how-to-behave, the campaign the
            # what-about). The objection stance + opening style ride along so the
            # mode's behavior is fully expressed in L1.
            objective = f"{pack.objective_template} For THIS campaign, the stated goal is: {goal}."
        # append the opening-style + objection stance directives (behavioral, mode-
        # tilted; support/complaint stance is de-escalation, never counter-sell).
        directives = [objective]
        if pack.opening_style:
            directives.append(f"OPENING: {pack.opening_style}")
        if pack.closing_style:
            directives.append(f"CLOSING: {pack.closing_style}")
        directives.append(render_objection_directive(use_case))
        directives.append(language_directive())
        # W-VOICE-HEART: human-delivery rules — exactly ONE greeting (no re-greet/
        # double-intro), a time-aware "good morning/afternoon, hello sir" wish (never
        # 'namaste'), identity confirmed BY THE LEAD'S REAL NAME, and the name said
        # sparingly at constant, un-emphasised volume. These are the PROMPT-side
        # guarantees that ride with the worker-opener suppression so the kernel-ON
        # outbound never re-greets or shouts the name. `lead_name` is threaded from the
        # live campaign fields (the agent injects it before assemble_prefix).
        directives.append(delivery_directive(_str(fields, "lead_name")))
        objective_str = " ".join(d for d in directives if d).strip()

        return ModeLayer(
            use_case=use_case,
            objective_str=objective_str,
            success_criteria=pack.success_criteria,
            brain_pack_id=pack.id,
        )

    # ------------------------------------------------------ L2 (industry) #
    def _resolve_industry_pack(self, fields: dict) -> IndustryPack:
        """Explicit fields['industry'] (id or label/keyword) wins; else keyword-
        match product/company text against each pack's `match`; else NEUTRAL."""
        f = fields or {}
        campaign_id = _str(f, "campaign_id")

        # explicit selection by id/label/keyword
        explicit = _str(f, "industry").lower()
        if explicit:
            for pack in self._all_industry_packs(campaign_id):
                if explicit == pack.id or explicit == pack.label.lower() or explicit in pack.match:
                    return pack

        # keyword match against the campaign's free-text fields
        hay = " ".join(
            _str(f, k) for k in ("product_name", "product_summary", "company_name", "vertical", "category")
        ).lower()
        if hay.strip():
            best: Optional[IndustryPack] = None
            best_hits = 0
            for pack in self._all_industry_packs(campaign_id):
                hits = sum(1 for kw in pack.match if kw and kw in hay)
                if hits > best_hits:
                    best, best_hits = pack, hits
            if best is not None and best_hits > 0:
                return best
        return NEUTRAL_INDUSTRY

    def _all_industry_packs(self, campaign_id: str) -> tuple[IndustryPack, ...]:
        """Shipped defaults, with any published store override replacing a default
        of the same id (and any extra store-only industry packs appended)."""
        if self.store is None:
            return self._industry_defaults
        by_id: dict[str, IndustryPack] = {p.id: p for p in self._industry_defaults}
        # collect every industry pack family the store knows
        seen_families: set[str] = set()
        for (kind, pack_id) in list(getattr(self.store, "_versions", {}).keys()):
            if kind == "industry":
                seen_families.add(pack_id)
        for fam in seen_families:
            pv = self.store.version_for_campaign(campaign_id, "industry", fam)
            if pv is not None:
                pack = _industry_pack_from_version(pv.body)
                if pack is not None:
                    by_id[pack.id] = pack
        return tuple(by_id.values())

    def industry_layer(self, fields: dict) -> IndustryLayer:
        """L2 — vertical vocabulary. PURE + SYNC. Defaults to NEUTRAL (empty
        vocabulary) so nothing vertical-specific leaks cross-vertical."""
        pack = self._resolve_industry_pack(fields)
        return IndustryLayer(pack_id=pack.id, vertical_terms=pack.vertical_terms)

    # ----------------------------------------- L0 disclosure (structural) #
    def identity_layer(
        self,
        fields: dict,
        *,
        safety_rules: str = "",
        agent_name_default: str = "Riya",
    ) -> IdentityLayer:
        """Build the L0 IdentityLayer with the STRUCTURAL disclosure line (W26).

        The disclosure is ALWAYS rendered (disclose_ai=True, ai_disclosure_str
        non-empty), config-gated by tier (default Tier 0 = brand-identity, no
        banned phrase). Vendor-script-compatible: a tenant may supply
        `fields['vendor_script_disclosure']`; a clean one is honoured, a banned
        one is rejected (disclosure cannot be weakened)."""
        f = fields or {}
        brand = _str(f, "company_name")
        purpose = _str(f, "purpose") or _str(f, "goal")
        tier_val = f.get("disclosure_tier", int(self.default_disclosure_tier))
        try:
            tier = DisclosureTier(int(tier_val))
        except Exception:
            tier = self.default_disclosure_tier
        cfg = DisclosureConfig(
            tier=tier,
            record_consent=bool(f.get("record_consent", False)),  # OPT-IN; never say recording unless campaign asks
            channel=_str(f, "direction", "outbound") or "outbound",
            language="english" if _str(f, "language").lower().startswith("eng") else "hinglish",
            vendor_script_disclosure=_str(f, "vendor_script_disclosure"),
        )
        disclosure = build_disclosure_str(brand, purpose, cfg)
        return IdentityLayer(
            agent_name=_str(f, "agent_name") or agent_name_default,
            company_name=brand,
            disclose_ai=True,  # STRUCTURAL — always on; the tier controls HOW, not WHETHER
            ai_disclosure_str=disclosure,
            safety_rules=safety_rules,
        )
