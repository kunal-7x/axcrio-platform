"""voice_kernel.brain_packs.objection — objection handling as PRINCIPLES (W6 §D).

FOUNDER'S EXPLICIT HATE: canned objection -> reply pairs. The model already
handles generic objections. The brain needs the *stance* + *business-context
hooks*, then it reasons the rebuttal live over the FULL campaign brief / FAQs /
uploaded docs / RAG.

So this module ships ZERO canned replies. It ships:
  - the universal 5-step objection STANCE (acknowledge -> isolate -> reframe-from-
    context -> honest -> re-close-soft), and
  - business-context HOOKS (price/trust/not-interested/...) that are *pointers to
    how to reason*, never replies, and never campaign content.

Per-mode tilt: SALES objections push toward the close; SUPPORT/COMPLAINT
"objections" (frustration) are de-escalation, NOT counter-selling — the stance
flips with the use-case's `pushes_sale` flag.

Pure stdlib. Imports ZERO droplet_work modules.
"""
from __future__ import annotations

from ..packet import UseCase

# The universal stance — a principle ladder, identical across every mode. The
# model fills the *content* of step 3 from the live campaign context, never from
# here.
UNIVERSAL_OBJECTION_STANCE: tuple[str, ...] = (
    "Acknowledge first — a genuine 'I hear you' beat; never argue or talk over.",
    "Isolate the real concern — price, trust, timing, authority (needs spouse/boss), or a competitor; ask ONE clarifying question if unclear.",
    "Reframe from the FULL campaign context — answer from the campaign's actual facts/USP/proof, not a script; specific + consistent beats clever.",
    "Stay honest — no fabricated urgency, no invented discounts; defer concessions to the human team.",
    "Re-close softly — return to the nearest low-commitment next step.",
)

# Business-context HOOKS: *how to reason*, with a pointer to the deep pack. NOT
# replies, NOT campaign content. Keys are concern categories the model detects.
OBJECTION_HOOKS: dict[str, str] = {
    "price": (
        "establish VALUE before price; break price into per-unit / EMI / "
        "appreciation / cost-of-inaction framing; defer discounts to the team"
    ),
    "not_interested": (
        "respect-first; find the real door-reason; agree a CONCRETE callback "
        "instead of a vague 'later'"
    ),
    "trust": (
        "proof + transparency; name the honest human-handoff for high-ticket; "
        "set a specific follow-up tied to the real decision blocker"
    ),
    "competitor": (
        "do not bad-mouth; reframe on the campaign's genuine differentiators; "
        "stay specific and consistent"
    ),
    "think_over": (
        "uncover the real hesitation behind 'let me think'; set a specific "
        "follow-up tied to that blocker, not a vague one"
    ),
    "family_authority": (
        "respect the decision-maker; offer to include them / a concrete callback "
        "when they can decide together"
    ),
    "urgency": (
        "only REAL, honest scarcity (genuine slot/inventory/offer deadlines); "
        "never fabricate urgency"
    ),
    "deep_fact": (
        "for deep factual questions the campaign brief doesn't hold, reach into "
        "RETRIEVAL over the uploaded docs rather than inventing — grounded, "
        "consistent, specific (the exact facts come from the vertical's own docs, "
        "never assumed)"
    ),
}

# Hooks that coach a SALES MOVE (price-framing, competitor-reframe, scarcity).
# They belong ONLY to revenue-advancing modes. Surfacing them in a support /
# complaint / reminder / feedback call would inject sell-coaching into a no-push
# mode — the exact cross-vertical leak the founder forbids. Non-pushing modes get
# the universal hooks only (trust, respect, routing, honest retrieval); the
# sales-only hooks below are filtered OUT for them. (Behavior-only; no campaign
# content; parallel to the step-5 re-close swap in `stance_for`.)
_SALES_ONLY_HOOKS: frozenset[str] = frozenset({"price", "competitor", "urgency"})


def hooks_for(use_case: UseCase) -> dict[str, str]:
    """The objection hooks for a mode. Revenue-advancing modes get the full menu;
    service modes (pushes_sale False) get the universal hooks ONLY — the sales-
    coaching hooks (price/competitor/urgency) are dropped so no sell move leaks
    into support/complaint/reminder/feedback."""
    from .packs_data import get_use_case_pack  # local import avoids a cycle

    pack = get_use_case_pack(use_case)
    if pack.stance.pushes_sale:
        return dict(OBJECTION_HOOKS)
    return {k: v for k, v in OBJECTION_HOOKS.items() if k not in _SALES_ONLY_HOOKS}


def stance_for(use_case: UseCase) -> tuple[str, ...]:
    """Return the objection stance, tilted by mode.

    Revenue-advancing modes (sales/renewal/booking) end on a soft re-close.
    Service modes (support/complaint/feedback/after_sales) replace the re-close
    with de-escalation — frustration is validated, NEVER counter-sold. This is a
    structural guarantee that support 'objection' handling does not push sales.
    """
    from .packs_data import get_use_case_pack  # local import avoids a cycle

    pack = get_use_case_pack(use_case)
    base = list(UNIVERSAL_OBJECTION_STANCE)
    if not pack.stance.pushes_sale:
        base[-1] = (
            "Do NOT counter-sell — validate the frustration, confirm the next "
            "service step, and (if needed) escalate; there is no 'close' here."
        )
    return tuple(base)


def render_objection_directive(use_case: UseCase) -> str:
    """A compact one-block directive (stance + hook menu) for the prompt. The
    model picks the relevant hook live; we never pre-select a reply."""
    steps = "; ".join(f"{i+1}) {s}" for i, s in enumerate(stance_for(use_case)))
    hooks = "; ".join(f"{k}: {v}" for k, v in hooks_for(use_case).items())
    return f"OBJECTION STANCE: {steps}. CONTEXT HOOKS (reason live, do not recite): {hooks}."
