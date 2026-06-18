"""voice_kernel.memory.lifecycle — deterministic lead LIFECYCLE classifier +
conversion probability.

Founder wants simple BUSINESS BADGES (hot/warm/cold/dead) the panel shows, plus
an INTERNAL score (0..100) that is NOT a badge. The robust production pattern
(HubSpot/Salesforce lead-status + lead-scoring): a DETERMINISTIC finite-state
machine for the state transition (auditable, cheap, drift-free) and a SEPARATE
probabilistic score for likelihood. We do NOT let an LLM pick the lifecycle
freely (it drifts) — the state is DERIVED from observed signals. The model is
only used to SUMMARIZE and to SUGGEST the next action.

The 5 states are the FROZEN `Lifecycle` enum (packet.py:47): NEW/HOT/WARM/COLD/DEAD.

Transition rules (signals come from extraction.py, all deterministic):
  * DEAD  is terminal+sticky — once dead (DND / opt-out / abuse), only an
    explicit re-engagement would move it; a single call never resurrects DEAD.
  * BOOKED or asked-for-handoff       -> HOT  (strongest positive intent).
  * NEW->engaged-with-commitment       -> WARM (interested, follow-up pending).
  * objection-without-commitment       -> COLD (disengaging; needs re-warming).
  * was HOT, no fresh positive signal  -> WARM (cools one notch, never jumps to COLD).
  * no engagement at all (silence)     -> COLD (or stays NEW if first touch).

Pure-stdlib + voice_kernel only. No droplet_work import.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from ..packet import Lifecycle


def classify_lifecycle(
    *,
    prior: Lifecycle = Lifecycle.NEW,
    booked: bool = False,
    handoff: bool = False,
    dead: bool = False,
    had_objection: bool = False,
    had_commitment: bool = False,
    engaged: bool = False,
) -> Lifecycle:
    """Deterministic FSM transition. Returns the NEW lifecycle given the prior
    state + this call's observed signals. Pure function, drift-free, auditable.
    """
    prior = prior or Lifecycle.NEW

    # DEAD is terminal+sticky: a dead lead stays dead unless this very call shows
    # a hard positive (booked) — an explicit re-engagement. A plain follow-up
    # call never resurrects an opted-out lead (compliance: respect the opt-out).
    if prior == Lifecycle.DEAD and not booked:
        return Lifecycle.DEAD

    # Fresh hard-negative this call -> DEAD (DND / opt-out / abuse).
    if dead:
        return Lifecycle.DEAD

    # Strongest positive intent -> HOT.
    if booked or handoff:
        return Lifecycle.HOT

    # Engaged + made a commitment (will check budget / call back) -> WARM.
    if engaged and had_commitment:
        return Lifecycle.WARM

    # Engaged but only objected, no forward commitment -> COLD (needs re-warming).
    if engaged and had_objection and not had_commitment:
        return Lifecycle.COLD

    # A previously HOT lead with no fresh positive cools ONE notch to WARM
    # (monotone cooling — never HOT->COLD in a single step).
    if prior == Lifecycle.HOT:
        return Lifecycle.WARM

    # Engaged at all (talked, no strong signal) -> WARM if we had prior contact,
    # else stays NEW->WARM on a real conversation.
    if engaged:
        return Lifecycle.WARM if prior in (Lifecycle.NEW, Lifecycle.WARM, Lifecycle.COLD) else prior

    # No engagement (silence / no-pickup content): first touch stays NEW,
    # otherwise the lead is cooling -> COLD.
    return Lifecycle.NEW if prior == Lifecycle.NEW else Lifecycle.COLD


# Per-state probability floor/anchor (the INTERNAL score, 0..100). The badge is
# the lifecycle; this number is the hidden conversion likelihood the panel can
# sort on but does not show as a badge.
_BASE: dict[Lifecycle, int] = {
    Lifecycle.NEW: 20,
    Lifecycle.HOT: 75,
    Lifecycle.WARM: 45,
    Lifecycle.COLD: 15,
    Lifecycle.DEAD: 0,
}


def conversion_probability(
    *,
    lifecycle: Lifecycle,
    booked: bool = False,
    handoff: bool = False,
    n_commitments: int = 0,
    n_objections: int = 0,
    engaged_chars: int = 0,
) -> int:
    """Internal conversion score 0..100 (deterministic). Anchored on the
    lifecycle, then nudged by signal strength. DEAD is hard-zero. Clamped.
    """
    if lifecycle == Lifecycle.DEAD:
        return 0
    score = _BASE.get(lifecycle, 20)
    if booked:
        score += 15
    if handoff:
        score += 8
    score += min(n_commitments, 3) * 5        # forward intent
    score -= min(n_objections, 4) * 4         # friction
    if engaged_chars > 400:                    # a real, substantive conversation
        score += 6
    elif engaged_chars == 0:                   # no lead utterance captured
        score -= 8
    return max(0, min(100, score))


async def classify_with_llm(
    *,
    prior: Lifecycle,
    deterministic: Lifecycle,
    transcript_excerpt: str = "",
    llm: Optional[Callable[[str], Awaitable[str]]] = None,
    timeout_s: float = 6.0,
) -> Lifecycle:
    """OPTIONAL async LLM-ASSIST hook. The deterministic FSM remains the
    AUTHORITY (no drift). The LLM may only DOWNGRADE a borderline positive to a
    cooler state when the transcript clearly contradicts the rules (e.g. polite
    words but a real refusal). It can NEVER upgrade past the deterministic state
    and can NEVER move a DEAD lead. On any error/timeout -> the deterministic
    state. This is advisory hardening, not the source of truth.
    """
    import asyncio

    if llm is None or deterministic == Lifecycle.DEAD or not transcript_excerpt:
        return deterministic
    order = [Lifecycle.DEAD, Lifecycle.COLD, Lifecycle.WARM, Lifecycle.HOT]
    try:
        prompt = (
            "Given this call excerpt, is the lead's real interest at most as warm "
            f"as '{deterministic.value}'? Reply with ONE of: hot, warm, cold, dead.\n\n"
            + transcript_excerpt[:1200]
        )
        raw = (await asyncio.wait_for(llm(prompt), timeout=timeout_s) or "").strip().lower()
        try:
            suggested = Lifecycle(raw)
        except ValueError:
            return deterministic
        # only allow a DOWNGRADE (cooler), never an upgrade; never resurrect DEAD.
        if order.index(suggested) < order.index(deterministic):
            return suggested
        return deterministic
    except Exception:
        return deterministic
