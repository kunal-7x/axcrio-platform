"""voice_kernel.context.understanding — the Campaign Understanding Engine.

Infers, from a vendor brief (+ any structured fields), the campaign's:
  - use_case      (SALES / SUPPORT / BOOKING / REMINDER / FEEDBACK / RENEWAL ...)
  - industry      (real_estate / insurance / healthcare / edtech / support ...)
  - objective     (a one-line goal string for L1)
  - needs_booking / needs_handoff / needs_whatsapp capability flags

Founder's #2 complaint context: the brief must DRIVE behaviour, not be discarded.
This engine reads the WHOLE brief (the full lossless text, not a 4k clamp) and
produces an EDITABLE classification — the vendor can override every field in the
Script Studio, and an explicit override always wins over inference (so the result
is a suggestion, never a lock).

V1 is a transparent, dependency-free keyword/heuristic classifier (no GPU, no
embedding box — matches the master-plan "FTS-only, few-shot over embeddings for
low-shot" decision). It is deliberately a PURE, SYNC function so it can run at
save-time AND be unit-tested deterministically. A later wave may swap the
internals for a one-shot LLM classification behind the SAME signature
(`classify(brief, fields) -> CampaignUnderstanding`) — the contract is the score
table + the editable result, not the heuristic.

NEVER hardcodes campaign content — only generic vertical/intent vocabulary used
to SCORE the vendor's own words. Pure-stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..packet import UseCase

# --------------------------------------------------------------------------- #
# Vocabulary tables (generic intent/vertical signal words — NOT campaign data).
# Each maps a label to signal tokens we COUNT in the vendor's own brief text.
# --------------------------------------------------------------------------- #
_USE_CASE_SIGNALS: dict[UseCase, tuple[str, ...]] = {
    UseCase.SALES: (
        "sell", "sale", "buy", "purchase", "offer", "discount", "price",
        "pitch", "lead", "prospect", "deal", "convert", "upsell", "cross-sell",
        "demo", "quote", "interested", "promotion", "launch",
    ),
    UseCase.SUPPORT: (
        "support", "help", "issue", "ticket", "complaint", "resolve",
        "troubleshoot", "problem", "not working", "error", "refund",
        "assist", "query", "grievance", "service request", "fix",
    ),
    UseCase.BOOKING: (
        "book", "booking", "appointment", "schedule", "slot", "reserve",
        "site visit", "visit", "meeting", "consultation", "calendar",
    ),
    UseCase.REMINDER: (
        "reminder", "remind", "due", "pending", "renewal date", "expire",
        "follow up", "follow-up", "overdue", "appointment reminder",
    ),
    UseCase.FEEDBACK: (
        "feedback", "survey", "rating", "review", "satisfaction", "nps",
        "experience", "how was", "csat",
    ),
    UseCase.RENEWAL: (
        "renew", "renewal", "expiry", "expiring", "subscription", "policy",
        "extend", "re-subscribe", "lapse",
    ),
    UseCase.COMPLAINT: (
        "complaint", "escalation", "angry", "dissatisfied", "unhappy",
        "compensation", "escalate",
    ),
    UseCase.ONBOARDING: (
        "onboard", "onboarding", "welcome", "getting started", "setup",
        "activation", "first time",
    ),
}

_INDUSTRY_SIGNALS: dict[str, tuple[str, ...]] = {
    "real_estate": (
        "flat", "apartment", "bhk", "property", "plot", "villa", "tower",
        "site visit", "possession", "carpet area", "rera", "builder",
        "project", "amenities", "sq ft", "sqft", "society", "construction",
        "booking amount", "eoi", "home loan",
    ),
    "insurance": (
        "policy", "premium", "claim", "coverage", "insured", "sum assured",
        "maturity", "nominee", "term plan", "ulip", "health insurance",
        "life insurance", "renewal",
    ),
    "healthcare": (
        "patient", "doctor", "appointment", "clinic", "hospital", "treatment",
        "diagnosis", "consultation", "health checkup", "lab test", "prescription",
    ),
    "edtech": (
        "course", "student", "admission", "batch", "enroll", "scholarship",
        "syllabus", "demo class", "tuition", "exam", "training", "certification",
    ),
    "automotive": (
        "car", "vehicle", "test drive", "showroom", "model", "ex-showroom",
        "emi", "service", "mileage", "variant",
    ),
    "fintech": (
        "loan", "credit card", "emi", "interest rate", "kyc", "account",
        "investment", "mutual fund", "sip", "wallet", "upi",
    ),
    "ecommerce": (
        "order", "delivery", "cart", "product", "shipping", "return",
        "discount code", "checkout", "out of stock",
    ),
    "support_services": (
        "ticket", "support agent", "service request", "sla", "resolution",
        "callback", "helpdesk", "customer care",
    ),
}

# Capability signals — does the campaign need booking / human handoff / WhatsApp.
_BOOKING_SIGNALS = (
    "book", "appointment", "schedule", "site visit", "slot", "reserve",
    "meeting", "consultation", "demo", "visit",
)
_HANDOFF_SIGNALS = (
    "transfer", "human agent", "talk to a person", "escalate", "sales team",
    "relationship manager", "connect to", "handover", "handoff", "senior",
    "supervisor", "specialist", "expert will call",
)
_WHATSAPP_SIGNALS = (
    "whatsapp", "wa", "send details", "share brochure", "send link",
    "send on chat", "message you the", "share on whatsapp", "send the location",
)


@dataclass(frozen=True)
class CampaignUnderstanding:
    """The EDITABLE classification result. Every field is a suggestion the
    vendor can override in the Script Studio (an explicit `fields` value wins —
    see `classify`)."""

    use_case: UseCase = UseCase.SALES
    industry: str = ""
    objective: str = ""
    needs_booking: bool = False
    needs_handoff: bool = False
    needs_whatsapp: bool = False
    # provenance/debug: the winning scores, so the UI can show WHY + how confident
    use_case_scores: dict = field(default_factory=dict)
    industry_scores: dict = field(default_factory=dict)
    confidence: float = 0.0
    source: str = "inferred"  # "inferred" | "vendor_override" | "mixed"

    def with_overrides(self, **kw) -> "CampaignUnderstanding":
        """Return a copy with vendor edits applied (marks source=vendor_override).
        Used by the Script Studio save path when the vendor edits the suggestion.
        """
        applied = {k: v for k, v in kw.items() if v not in (None, "")}
        if not applied:
            return self
        return replace(self, source="mixed" if self.source == "inferred" else self.source, **applied)


def _count_hits(haystack: str, signals: tuple[str, ...]) -> int:
    """Count how many signal tokens appear in the (lowercased) brief. Multi-word
    signals are matched as substrings; single words as whole-ish tokens."""
    n = 0
    for sig in signals:
        if sig in haystack:
            n += haystack.count(sig)
    return n


def _objective_for(use_case: UseCase, industry: str) -> str:
    """A generic, vertical-aware one-line objective for L1. NOT campaign content —
    a behavioural goal the brain pack would otherwise supply."""
    base = {
        UseCase.SALES: "qualify the lead and move them toward the next commitment (visit / demo / purchase)",
        UseCase.SUPPORT: "understand and resolve the customer's issue, or route it to the right team",
        UseCase.BOOKING: "confirm interest and book a concrete slot (date + time)",
        UseCase.REMINDER: "remind the customer of the pending action and confirm they will act",
        UseCase.FEEDBACK: "collect honest feedback and a rating without leading the answer",
        UseCase.RENEWAL: "secure the renewal before expiry and clear any blocker",
        UseCase.COMPLAINT: "de-escalate, acknowledge, and route the complaint to resolution",
        UseCase.ONBOARDING: "activate the customer and get them to the first successful action",
    }.get(use_case, "have a useful, human conversation toward the campaign goal")
    return base


def classify(brief: str, fields: dict | None = None) -> CampaignUnderstanding:
    """Infer the campaign understanding from the FULL brief text (+ optional
    structured fields). PURE + SYNC. Vendor-supplied explicit fields ALWAYS win
    over inference (the result is editable, never a lock).

    `fields` may carry explicit overrides under any of:
      use_case, industry, goal/objective, needs_booking, needs_handoff,
      needs_whatsapp.
    """
    f = dict(fields or {})
    hay = (brief or "").lower()
    # fold any structured field text into the haystack so a sparse brief still
    # classifies from the discrete fields the vendor filled.
    for k in ("product_summary", "goal", "talking_points", "usps", "objections"):
        v = f.get(k)
        if isinstance(v, str):
            hay += " " + v.lower()
        elif isinstance(v, (list, tuple)):
            hay += " " + " ".join(str(x).lower() for x in v)

    # -- use_case ------------------------------------------------------------
    uc_scores = {uc: _count_hits(hay, sigs) for uc, sigs in _USE_CASE_SIGNALS.items()}
    best_uc = max(uc_scores, key=lambda k: uc_scores[k]) if any(uc_scores.values()) else UseCase.SALES
    # vendor explicit override wins
    uc_override = _coerce_use_case(f.get("use_case"))
    use_case = uc_override or best_uc

    # -- industry ------------------------------------------------------------
    ind_scores = {ind: _count_hits(hay, sigs) for ind, sigs in _INDUSTRY_SIGNALS.items()}
    best_ind = max(ind_scores, key=lambda k: ind_scores[k]) if any(ind_scores.values()) else ""
    industry = str(f.get("industry", "")).strip() or best_ind

    # -- capabilities --------------------------------------------------------
    needs_booking = _as_bool(f.get("needs_booking")) if "needs_booking" in f else (
        _count_hits(hay, _BOOKING_SIGNALS) > 0 or use_case == UseCase.BOOKING
    )
    needs_handoff = _as_bool(f.get("needs_handoff")) if "needs_handoff" in f else (
        _count_hits(hay, _HANDOFF_SIGNALS) > 0
    )
    needs_whatsapp = _as_bool(f.get("needs_whatsapp")) if "needs_whatsapp" in f else (
        _count_hits(hay, _WHATSAPP_SIGNALS) > 0
    )

    # -- objective -----------------------------------------------------------
    objective = str(f.get("objective", "") or f.get("goal", "")).strip() or _objective_for(use_case, industry)

    # -- confidence (top score relative to total signal) ---------------------
    total = sum(uc_scores.values()) or 1
    confidence = round(uc_scores.get(best_uc, 0) / total, 3)

    source = "vendor_override" if (uc_override or f.get("industry")) else "inferred"

    return CampaignUnderstanding(
        use_case=use_case,
        industry=industry,
        objective=objective,
        needs_booking=bool(needs_booking),
        needs_handoff=bool(needs_handoff),
        needs_whatsapp=bool(needs_whatsapp),
        use_case_scores={uc.value: s for uc, s in uc_scores.items() if s},
        industry_scores={ind: s for ind, s in ind_scores.items() if s},
        confidence=confidence,
        source=source,
    )


def _coerce_use_case(v) -> UseCase | None:
    if not v:
        return None
    if isinstance(v, UseCase):
        return v
    try:
        return UseCase(str(v).strip().lower())
    except ValueError:
        return None


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")
