"""voice_kernel.brain_packs — W2: the swappable use-case (L1) + industry (L2)
brain packs that bind the FROZEN BrainPackProvider Protocol.

PUBLIC SURFACE
--------------
Factory (register into the kernel):
    from voice_kernel.kernel import build_kernel
    from voice_kernel.brain_packs import build_brain_packs
    kernel = build_kernel(brain_packs=build_brain_packs())            # shipped defaults
    kernel = build_kernel(brain_packs=build_brain_packs(store=store)) # with overrides

Provider:
    BrainPacks(store=None, default_disclosure_tier=DisclosureTier.BRAND_IDENTITY)
      .use_case_layer(use_case, fields) -> ModeLayer     # L1 (Protocol)
      .industry_layer(fields)           -> IndustryLayer  # L2 (Protocol)
      .identity_layer(fields, safety_rules=..) -> IdentityLayer  # L0 disclosure (W1 wiring)

Data model + content:
    UseCasePack, IndustryPack, Stance, NEUTRAL_INDUSTRY
    all_use_case_packs(), all_industry_packs(), get_use_case_pack(use_case)

Disclosure (W26, structural):
    DisclosureTier, DisclosureConfig, build_disclosure_str(brand, purpose, cfg)
    BANNED_PHRASES, contains_banned_phrase(text)

Versioned store (draft/test/publish/rollback + campaign->version binding):
    BrainPackStore, JsonBrainPackStore, PackVersion, VersionState

Objection PRINCIPLES (no canned replies) + casual-Hinglish:
    UNIVERSAL_OBJECTION_STANCE, OBJECTION_HOOKS, stance_for(), render_objection_directive()
    language_directive(), BANNED_LITERARY, contains_banned_literary()

This package imports ZERO droplet_work modules and never touches agent.py /
caller.py / aim_voice_agent.py — it is pure, additive, flag-OFF inert (it is only
reached when a kernel is built with it AND the kernel is enabled).
"""
from __future__ import annotations

from typing import Optional

from .disclosure import (
    BANNED_PHRASES,
    DisclosureConfig,
    DisclosureTier,
    build_disclosure_str,
    contains_banned_phrase,
    strip_guardrail,
)
from .language import (
    BANNED_LITERARY,
    contains_banned_literary,
    language_directive,
)
from .model import (
    NEUTRAL_INDUSTRY,
    IndustryPack,
    Stance,
    UseCasePack,
)
from .objection import (
    OBJECTION_HOOKS,
    UNIVERSAL_OBJECTION_STANCE,
    hooks_for,
    render_objection_directive,
    stance_for,
)
from .packs_data import (
    all_industry_packs,
    all_use_case_packs,
    get_use_case_pack,
)
from .provider import BrainPacks
from .registry import (
    BrainPackStore,
    JsonBrainPackStore,
    PackVersion,
    VersionState,
)


def build_brain_packs(
    store: Optional[BrainPackStore] = None,
    *,
    default_disclosure_tier: DisclosureTier = DisclosureTier.BRAND_IDENTITY,
) -> BrainPacks:
    """The factory the kernel wires in: `build_kernel(brain_packs=build_brain_packs())`.
    With no store it serves the shipped default packs; pass a BrainPackStore to
    layer in published/pinned vendor overrides."""
    return BrainPacks(store=store, default_disclosure_tier=default_disclosure_tier)


__all__ = [
    "build_brain_packs",
    "BrainPacks",
    # disclosure
    "DisclosureTier",
    "DisclosureConfig",
    "build_disclosure_str",
    "BANNED_PHRASES",
    "contains_banned_phrase",
    "strip_guardrail",
    # model + content
    "UseCasePack",
    "IndustryPack",
    "Stance",
    "NEUTRAL_INDUSTRY",
    "all_use_case_packs",
    "all_industry_packs",
    "get_use_case_pack",
    # objection + language
    "UNIVERSAL_OBJECTION_STANCE",
    "OBJECTION_HOOKS",
    "stance_for",
    "hooks_for",
    "render_objection_directive",
    "language_directive",
    "BANNED_LITERARY",
    "contains_banned_literary",
    # versioned store
    "BrainPackStore",
    "JsonBrainPackStore",
    "PackVersion",
    "VersionState",
]
