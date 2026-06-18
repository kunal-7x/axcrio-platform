"""voice_kernel.packet — the ContextPacket schema + the layered builder.

This REPLACES the ~13k-token single f-string with a layered, ordered, budgeted
packet (W1-KERNEL-ARCH §2). Ordered most-stable-prefix FIRST → most-volatile
LAST (the universal prompt-cache rule):

    STABLE PREFIX = L0+L1+L2+L3   -> rendered ONCE per call, byte-identical/turn
    PER-CALL SUFFIX = L4          -> rendered once per call (lead memory)
    PER-TURN SUFFIX = L5 + dynamic -> re-rendered each turn (turn evidence)

Critical rule (fixes a live cache bug): per-call/per-turn dynamic text
(lead_name, recap, opener-said, lang-lock) goes in the SUFFIX, NEVER interleaved
into the stable prefix.

The packet is PURE (frozen dataclasses, same input → same output) so the
double-render at agent.py:416+431 is idempotent.

Pure-stdlib only (dataclasses/enum/typing) — import-safe for aim_voice_agent.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional

from .errors import BudgetExceededError
from .tokens import clamp_chars, clamp_list, estimate_tokens


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class UseCase(str, Enum):
    SALES = "sales"
    SUPPORT = "support"
    AFTER_SALES = "after_sales"
    BOOKING = "booking"
    REMINDER = "reminder"
    FEEDBACK = "feedback"
    COMPLAINT = "complaint"
    RENEWAL = "renewal"
    ONBOARDING = "onboarding"
    INBOUND = "inbound"
    AI_MANAGER = "ai_manager"


class Lifecycle(str, Enum):
    NEW = "new"
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    DEAD = "dead"


class Stage(str, Enum):
    GREET = "greet"
    PERMISSION = "permission"
    INTRO = "intro"
    QUALIFY = "qualify"
    OBJECTION = "objection"
    BOOKING = "booking"
    CLOSE = "close"
    FOLLOWUP = "followup"


# --------------------------------------------------------------------------- #
# Layer dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PacketMeta:
    tenant_id: str
    campaign_id: str
    call_id: str
    room: str
    lead_phone: str = ""
    locale: str = "hi-IN"
    agent_gender: str = "female"
    ts_iso: str = ""
    packet_version: str = "1"
    direction: str = "outbound"  # outbound | inbound


@dataclass(frozen=True)
class IdentityLayer:  # L0 — static, byte-identical forever
    agent_name: str
    company_name: str
    disclose_ai: bool = True
    ai_disclosure_str: str = ""
    safety_rules: str = ""  # SHARED_RULES verbatim from prompt.py


@dataclass(frozen=True)
class ModeLayer:  # L1 — use-case brain pack ref
    use_case: UseCase = UseCase.SALES
    objective_str: str = ""
    success_criteria: str = ""
    brain_pack_id: str = ""


@dataclass(frozen=True)
class IndustryLayer:  # L2
    pack_id: str = ""
    vertical_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Objection:
    q: str
    a: str


@dataclass(frozen=True)
class CampaignCard:  # L3 — structured persona+facts (NOT the raw 4k brief)
    product_name: str = ""
    product_summary: str = ""  # <= 600 chars (clamped)
    location: str = ""
    landmark: str = ""
    price_offer: str = ""
    usps: tuple[str, ...] = ()  # <= 5
    talking_points: tuple[str, ...] = ()  # <= 5
    qualifying_questions: tuple[str, ...] = ()  # <= 3
    objections: tuple[Objection, ...] = ()  # <= 6
    negotiation_ladder: tuple[str, ...] = ()
    closing_lines: tuple[str, ...] = ()
    escalation_rules: str = ""
    raw_script_ref: str = ""  # POINTER to the full brief, never inlined
    tone: str = ""
    greeting: str = ""
    language: str = "Hinglish"
    do: tuple[str, ...] = ()
    dont: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeadMemory:  # L4 — structured facts, NOT transcript replay
    name: str = ""
    lifecycle: Lifecycle = Lifecycle.NEW
    last_call_summary: str = ""  # <= 300 chars (clamped)
    open_commitments: tuple[str, ...] = ()
    preferred_callback_ts: str = ""
    do_not_mention: tuple[str, ...] = ()


@dataclass(frozen=True)
class RagSnippet:
    source: str
    text: str  # <= 120 chars (clamped)


@dataclass(frozen=True)
class TurnLayer:  # L5 — per-turn, the only thing that changes each turn
    stage: Stage = Stage.GREET
    rag_snippets: tuple[RagSnippet, ...] = ()  # <= 3
    detected_lang: str = ""
    barge_in_hint: str = ""


@dataclass(frozen=True)
class TokenBudget:
    max_total_tokens: int = 2800
    l0_cap: int = 350
    l1_cap: int = 250
    l2_cap: int = 150
    l3_cap: int = 900
    l4_cap: int = 300
    l5_cap: int = 400


# Per-field char clamps (from the arch doc §2). Centralised so both the WARM
# builder and the per-turn assembler use the SAME caps.
_PRODUCT_SUMMARY_CHARS = 600
_LAST_CALL_SUMMARY_CHARS = 300
_RAG_TEXT_CHARS = 120
_USPS_MAX = 5
_TALKING_MAX = 5
_QUALIFYING_MAX = 3
_OBJECTIONS_MAX = 6
_RAG_MAX = 3


# --------------------------------------------------------------------------- #
# The packet
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ContextPacket:
    meta: PacketMeta
    identity: IdentityLayer
    mode: ModeLayer
    industry: IndustryLayer
    card: CampaignCard
    lead: LeadMemory
    turn: TurnLayer
    budget: TokenBudget = field(default_factory=TokenBudget)

    # -- render scopes ----------------------------------------------------- #
    def render_stable_prefix(self) -> str:
        """L0..L3 — rendered ONCE per call, sent byte-identical every turn.

        Contains ZERO per-call/per-turn dynamic text (no lead_name, no recap,
        no opener flag, no timestamp). That keeps the prefix cacheable.
        """
        out: list[str] = []

        # L0 — IDENTITY + SAFETY (never trimmed)
        ident = self.identity
        out.append(f"You are {ident.agent_name}, calling on behalf of {ident.company_name}.")
        if ident.disclose_ai and ident.ai_disclosure_str:
            out.append(ident.ai_disclosure_str)
        if ident.safety_rules:
            out.append(ident.safety_rules)

        # L1 — USE-CASE BRAIN PACK
        m = self.mode
        if m.objective_str:
            out.append(f"OBJECTIVE: {m.objective_str}")
        if m.success_criteria:
            out.append(f"SUCCESS: {m.success_criteria}")

        # L2 — INDUSTRY PACK
        ind = self.industry
        if ind.vertical_terms:
            out.append("VERTICAL TERMS: " + ", ".join(ind.vertical_terms))

        # L3 — CAMPAIGN CARD (structured, not the raw brief)
        c = self.card
        card_lines: list[str] = []
        if c.product_name:
            card_lines.append(f"PRODUCT: {c.product_name}")
        if c.product_summary:
            card_lines.append(f"ABOUT: {c.product_summary}")
        if c.location:
            loc = c.location + (f" (near {c.landmark})" if c.landmark else "")
            card_lines.append(f"LOCATION: {loc}")
        if c.price_offer:
            card_lines.append(f"OFFER: {c.price_offer}")
        if c.usps:
            card_lines.append("USPS: " + "; ".join(c.usps))
        if c.talking_points:
            card_lines.append("TALKING POINTS: " + "; ".join(c.talking_points))
        if c.qualifying_questions:
            card_lines.append("QUALIFY: " + " | ".join(c.qualifying_questions))
        if c.objections:
            obj = " | ".join(f"Q:{o.q} A:{o.a}" for o in c.objections)
            card_lines.append("OBJECTIONS: " + obj)
        if c.negotiation_ladder:
            card_lines.append("NEGOTIATION: " + " -> ".join(c.negotiation_ladder))
        if c.closing_lines:
            card_lines.append("CLOSE: " + "; ".join(c.closing_lines))
        if c.do:
            card_lines.append("DO: " + "; ".join(c.do))
        if c.dont:
            card_lines.append("DON'T: " + "; ".join(c.dont))
        if c.escalation_rules:
            card_lines.append(f"ESCALATE: {c.escalation_rules}")
        if c.language:
            card_lines.append(f"LANGUAGE: speak in {c.language}.")
        if card_lines:
            out.append("\n".join(card_lines))

        return "\n\n".join(p for p in out if p)

    def render_call_suffix(self) -> str:
        """L4 — lead memory, rendered ONCE per call (below the cache boundary)."""
        l = self.lead
        parts: list[str] = []
        if l.name:
            parts.append(f"LEAD NAME: {l.name}")
        if l.lifecycle and l.lifecycle != Lifecycle.NEW:
            parts.append(f"LIFECYCLE: {l.lifecycle.value}")
        if l.last_call_summary:
            parts.append(f"LAST CALL: {l.last_call_summary}")
        if l.open_commitments:
            parts.append("OPEN COMMITMENTS: " + "; ".join(l.open_commitments))
        if l.preferred_callback_ts:
            parts.append(f"PREFERRED CALLBACK: {l.preferred_callback_ts}")
        if l.do_not_mention:
            parts.append("DO NOT MENTION: " + "; ".join(l.do_not_mention))
        if not parts:
            return ""
        return "LEAD MEMORY:\n" + "\n".join(parts)

    def render_turn_suffix(self) -> str:
        """L5 + dynamic — re-rendered each turn, appended after the cached prefix.

        This is the ONLY scope that changes per turn. It is also hard-clamped
        here (the red-team fix): we never trust the caller to have pre-clamped.
        """
        t = self.turn
        parts: list[str] = []
        if t.stage:
            parts.append(f"STAGE: {t.stage.value}")
        if t.detected_lang:
            parts.append(f"USER LANGUAGE: {t.detected_lang} — mirror it.")
        # hard per-turn clamp on RAG snippets (cap count + per-item chars)
        if t.rag_snippets:
            snips = t.rag_snippets[:_RAG_MAX]
            rendered = "; ".join(
                f"[{s.source}] {clamp_chars(s.text, _RAG_TEXT_CHARS)}" for s in snips if s.text
            )
            if rendered:
                parts.append("RELEVANT: " + rendered)
        if t.barge_in_hint:
            parts.append(t.barge_in_hint)
        if not parts:
            return ""
        return "\n".join(parts)

    # -- budget ------------------------------------------------------------ #
    def _layer_text(self) -> dict[str, str]:
        return {
            "prefix": self.render_stable_prefix(),
            "call": self.render_call_suffix(),
            "turn": self.render_turn_suffix(),
        }

    def token_estimate(self) -> int:
        return sum(estimate_tokens(v) for v in self._layer_text().values())

    def clamp(self) -> "ContextPacket":
        """Return a budget-enforced COPY (pure — never mutates self).

        Order of operations (arch §2):
          1. Hard per-field clamps on every layer (lists capped, chars trimmed).
          2. If still over budget: drop L5, then trim L4 — NEVER trim L0.
          3. If L0..L3 alone are still over budget -> BudgetExceededError (a
             campaign-config bug; we refuse to silently send an over-budget
             prompt — LEARNINGS §1).
        """
        b = self.budget

        # 1. per-field hard clamps -------------------------------------------------
        card = replace(
            self.card,
            product_summary=clamp_chars(self.card.product_summary, _PRODUCT_SUMMARY_CHARS),
            usps=clamp_list(self.card.usps, _USPS_MAX),
            talking_points=clamp_list(self.card.talking_points, _TALKING_MAX),
            qualifying_questions=clamp_list(self.card.qualifying_questions, _QUALIFYING_MAX),
            objections=tuple(self.card.objections[:_OBJECTIONS_MAX]),
        )
        lead = replace(
            self.lead,
            last_call_summary=clamp_chars(self.lead.last_call_summary, _LAST_CALL_SUMMARY_CHARS),
        )
        turn = replace(
            self.turn,
            rag_snippets=tuple(
                replace(s, text=clamp_chars(s.text, _RAG_TEXT_CHARS))
                for s in self.turn.rag_snippets[:_RAG_MAX]
            ),
        )
        pkt = replace(self, card=card, lead=lead, turn=turn)

        if pkt.token_estimate() <= b.max_total_tokens:
            return pkt

        # 2a. drop L5 (turn evidence) first ----------------------------------------
        pkt = replace(pkt, turn=replace(pkt.turn, rag_snippets=()))
        if pkt.token_estimate() <= b.max_total_tokens:
            return pkt

        # 2b. trim L4 (lead memory) ------------------------------------------------
        pkt = replace(
            pkt,
            lead=LeadMemory(name=pkt.lead.name, lifecycle=pkt.lead.lifecycle),
        )
        if pkt.token_estimate() <= b.max_total_tokens:
            return pkt

        # 3. L0..L3 alone are over budget -> loud failure --------------------------
        raise BudgetExceededError(
            f"stable prefix (L0..L3) alone exceeds budget "
            f"({pkt.token_estimate()} > {b.max_total_tokens} tokens) — "
            f"campaign {pkt.meta.campaign_id} card is too large; trim it."
        )
