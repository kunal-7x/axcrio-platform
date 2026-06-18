"""voice_kernel.brain_packs.model — the brain-pack DATA model (W2).

A brain pack is DATA (a declarative behavior spec), never code-per-pack. Two
ORTHOGONAL axes that COMPOSE at assembly time (the single most important
structural decision — see W2 research):

  - UseCasePack (L1) = the OBJECTIVE + STANCE engine. Answers *what are we
    trying to achieve and how do we behave* (sales=advance/push, support=
    resolve/no-push, reminder=one-clean-decision, ...). Keyed by the FROZEN
    `UseCase` enum (packet.py).
  - IndustryPack (L2) = the VOCABULARY/NORMS layer. Answers *what vertical are
    we in* (real-estate -> site-visit/lakh/possession; insurance -> premium/
    grace-period/IRDAI). Supplies `vertical_terms` only — NEVER campaign content.

Why orthogonal: SALES x real_estate, SUPPORT x real_estate, SALES x insurance
are all valid. Collapsing them = N*M packs (combinatorial blow-up). Orthogonal =
N+M packs that compose. The kernel's L1/L2 split (packet.py) was designed for
exactly this.

FOUNDER LAWS honoured by the model itself (W6 §0):
  - Law 2 NEVER hardcode the words: `objective_template` / `success_criteria` /
    `stance` describe BEHAVIOR in the abstract. The runtime campaign goal
    (`fields["goal"]`) is LAYERED IN, never replaced. A pack stores no campaign
    sentence, no product noun, no price, no slot.
  - Cross-vertical: a pack is mode-only (L1) or vertical-only (L2). Real-estate
    vocabulary lives ONLY in the real_estate IndustryPack and can never leak into
    a SUPPORT/insurance/clinic call (proven in tests).
  - §D objections are PRINCIPLES (stance + hooks), never canned Q->A pairs.

Pure stdlib (dataclasses/enum) — import-safe; imports ZERO droplet_work modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..packet import Stage, UseCase


# --------------------------------------------------------------------------- #
# Stance — the behavioral posture a use-case takes toward the lead.
# This is what makes SUPPORT structurally unable to "push sales".
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Stance:
    """The behavioral posture of a use-case pack. `pushes_sale` is the load-
    bearing flag: support / complaint / feedback / after_sales packs set it
    False, so the objective engine NEVER renders a sales-advance directive for
    them (the 'support does not push sales' guarantee)."""

    key: str  # advance | resolve | serve | confirm | neutral_listen | de_escalate
    description: str  # behavior, abstract — NO campaign words
    pushes_sale: bool = False  # True ONLY for revenue-advancing modes
    empathy_first: bool = False  # validate before solution (support/complaint)


@dataclass(frozen=True)
class UseCasePack:
    """L1 — a use-case BEHAVIOR pack. Declarative; the LLM interprets it.

    `objective_template` / `success_criteria` are BEHAVIOR strings describing the
    goal/stance in the abstract. They contain NO campaign content — the campaign's
    own `fields["goal"]` is composed IN at render time, never substituted.
    """

    id: str  # e.g. "sales.v1" — provenance pointer (ModeLayer.brain_pack_id)
    use_case: UseCase
    stance: Stance
    objective_template: str  # abstract behavioral objective (no campaign nouns)
    success_criteria: str  # the terminal-state definition (aligns with fsm terminal)
    opening_style: str  # how to open (full skeleton / inverted / apology-first ...)
    closing_style: str = ""  # how to CLOSE (warm LLM goodbye per outcome; never a canned line)
    data_to_collect: tuple[str, ...] = ()  # generic fields (need/budget/ticket_id ...)
    push_stop_handoff: str = ""  # when to push / stop / hand off (behavioral)
    memory_fields: tuple[str, ...] = ()  # which lead-memory keys this mode writes
    stage_skips: frozenset[Stage] = field(default_factory=frozenset)  # advisory to fsm/W6
    behavior_pack_ids: tuple[str, ...] = ()  # pointers to micro-packs (objection/discovery) for W4

    def __post_init__(self) -> None:
        if not (self.id or "").strip():
            raise ValueError("UseCasePack.id is required (provenance pointer)")
        if not isinstance(self.use_case, UseCase):
            raise TypeError(f"UseCasePack.use_case must be a UseCase enum, got {type(self.use_case)!r}")


@dataclass(frozen=True)
class IndustryPack:
    """L2 — an industry VOCABULARY/NORMS pack. Supplies ONLY vertical terminology
    and vertical do/don't *norm nudges* — never campaign content (no product name,
    no price, no project). `match` is the set of keywords/aliases that resolve a
    campaign's `fields` to this pack."""

    id: str  # e.g. "real_estate.v1"
    label: str  # human label, e.g. "Real Estate"
    match: tuple[str, ...] = ()  # keywords/aliases -> resolve fields to this pack
    vertical_terms: tuple[str, ...] = ()  # the L2 payload (vocabulary)
    norm_nudges: tuple[str, ...] = ()  # vertical do/don't (behavioral, no campaign words)
    compliance_ref: str = ""  # e.g. "IRDAI" / "RBI" — a pointer, not a clause

    def __post_init__(self) -> None:
        if not (self.id or "").strip():
            raise ValueError("IndustryPack.id is required")


# A NEUTRAL industry default — used when a campaign's fields resolve to no known
# vertical. It carries NO vocabulary, so nothing vertical-specific can leak.
NEUTRAL_INDUSTRY = IndustryPack(
    id="neutral.v1",
    label="Neutral",
    match=(),
    vertical_terms=(),
    norm_nudges=(),
)
