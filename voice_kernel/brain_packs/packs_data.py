"""voice_kernel.brain_packs.packs_data — the default brain-pack CONTENT (W6 §C).

The 11 use-case packs (one per `UseCase` enum member) + the seed industry packs,
encoded as DATA. Every string here is BEHAVIOR (goal/stance/opening/data-to-
collect/push-stop-handoff in the abstract). NOTHING is campaign content — no
product name, no price, no project, no slot, no canned sentence. The campaign +
lead data fill every dynamic value at runtime (the provider layers `fields`).

Cross-vertical proof: vertical vocabulary lives ONLY in the IndustryPack list
below, NEVER in a UseCasePack. So a SUPPORT call, or an insurance call, can never
inherit real-estate words.

Pure stdlib. Imports ZERO droplet_work modules.
"""
from __future__ import annotations

from ..packet import Stage, UseCase
from .model import IndustryPack, Stance, UseCasePack

# --------------------------------------------------------------------------- #
# Stances (the behavioral postures). pushes_sale is load-bearing.
# --------------------------------------------------------------------------- #
_ADVANCE = Stance("advance", "Advance the lead to a concrete revenue next step; push hard but never pushy.", pushes_sale=True)
_RESOLVE = Stance("resolve", "Understand and resolve (or route) the problem; empathy-first, NO selling.", pushes_sale=False, empathy_first=True)
_SERVE = Stance("serve", "Service first; surface issues; any upsell is a light, permission-based mention only if happy.", pushes_sale=False)
_CONFIRM = Stance("confirm", "Drive a single clean scheduling decision; low-friction, slot-driven.", pushes_sale=False)
_NUDGE = Stance("nudge", "One calm reminder; confirm-or-reschedule; zero pressure.", pushes_sale=False)
_LISTEN = Stance("neutral_listen", "Neutrally capture honest feedback; never defensive, never selling.", pushes_sale=False, empathy_first=True)
_DEESCALATE = Stance("de_escalate", "De-escalate, take ownership, resolve/route fast; maximum empathy, no defensiveness.", pushes_sale=False, empathy_first=True)
_RETAIN = Stance("retain", "Retain for the next term; lead with value already realized; push value+ease, not pressure.", pushes_sale=True)
_ONBOARD = Stance("onboard", "Get the new customer successfully started; service-first, ensure first value.", pushes_sale=False)
_RECEPTION = Stance("serve_route", "They called us — identify intent fast, help, and route to the right mode.", pushes_sale=False)
_ACT = Stance("execute", "Execute the operator's business action with firewall/PIN/audit; confirm and report.", pushes_sale=False)


# --------------------------------------------------------------------------- #
# The 11 use-case packs. id == "<use_case>.v1".
# --------------------------------------------------------------------------- #
_USE_CASE_PACKS: tuple[UseCasePack, ...] = (
    UseCasePack(
        id="sales.v1", use_case=UseCase.SALES, stance=_ADVANCE,
        objective_template="Move a cold/warm lead toward a booked next step (site-visit/demo/purchase intent); create a real booking or a scheduled callback.",
        success_criteria="A booked next step with date+time persisted, OR a scheduled callback with a concrete time + captured reason, OR a clean qualified status change.",
        opening_style="Full greet->confirm->intro->reason->permission skeleton. Pattern-interrupt only for warm/known leads.",
        data_to_collect=("need/use-case", "budget band", "timeline/urgency", "decision-makers", "specific interest", "best callback time"),
        push_stop_handoff="PUSH on buy-signals (asks price/visit) -> shortcut to close. STOP on DND/opt-out or a hard repeated no. HANDOFF when the lead asks for a human or is hot+stuck on a human-only concession.",
        memory_fields=("lead_temp", "interest", "budget_band", "objections", "commitments", "next_action", "next_call_at", "last_stage"),
        behavior_pack_ids=("discovery", "objection", "closing", "push-without-pushy"),
    ),
    UseCasePack(
        id="support.v1", use_case=UseCase.SUPPORT, stance=_RESOLVE,
        objective_template="Understand and resolve (or correctly route) the customer's problem; leave them feeling heard.",
        success_criteria="Issue resolved + confirmed by the customer, OR correctly escalated with a ticket + a promised follow-up time; a satisfaction check done (NOT a sales close).",
        opening_style="Warm greet + identity + 'how can I help' (inbound) / 'calling about your issue with X' (outbound). NO permission-to-pitch, NO selling.",
        data_to_collect=("issue description", "product/order/ticket id", "when it started", "what they tried", "severity/impact", "preferred resolution + callback"),
        push_stop_handoff="NEVER push — drive to resolution. STOP pitching entirely. HANDOFF to L2/supervisor on anything outside known resolution or a frustrated/escalating customer.",
        memory_fields=("ticket_id", "issue_type", "severity", "steps_tried", "resolution_state", "escalated_to", "follow_up_at", "csat"),
        stage_skips=frozenset({Stage.PERMISSION, Stage.BOOKING}),
        behavior_pack_ids=("support-mode",),
    ),
    UseCasePack(
        id="after_sales.v1", use_case=UseCase.AFTER_SALES, stance=_SERVE,
        objective_template="Confirm delivery/install went well, ensure the customer is benefiting, surface issues early, capture satisfaction; tee up renewal/upsell SOFTLY only if they're happy.",
        success_criteria="Confirmed healthy usage + captured satisfaction, OR a logged issue routed to support, OR (only if happy) a warm next-step for renewal/add-on.",
        opening_style="Warm recognition of the recent purchase ('checking in on your X'). Continuity from the purchase context.",
        data_to_collect=("delivery/install status", "usage/experience", "any problems", "satisfaction (NPS-style)", "add-on/renewal interest (only if happy)"),
        push_stop_handoff="PUSH never on service. A satisfaction dip -> switch fully to support/complaint mode + log. Upsell only if CSAT high AND they invite it. HANDOFF unresolved service issues.",
        memory_fields=("purchase_ref", "delivery_state", "usage_health", "csat", "issues", "upsell_interest", "renewal_due_at"),
        stage_skips=frozenset({Stage.PERMISSION, Stage.OBJECTION}),
        behavior_pack_ids=("aftersales-feedback-nps",),
    ),
    UseCasePack(
        id="booking.v1", use_case=UseCase.BOOKING, stance=_CONFIRM,
        objective_template="Create, confirm, or reschedule a real appointment and write the booking record (+ calendar).",
        success_criteria="A persisted appointment with date+time + status Scheduled/Confirmed, reflected on the booking page + connected calendar; reschedule/cancel handled cleanly with status update.",
        opening_style="Greet + identity + state the booking purpose directly. Distinguish inquiry (wants to book) vs confirmation (already booked).",
        data_to_collect=("desired service/visit type", "preferred date+time (offer 2 slots)", "location/mode", "contact for reminders", "constraints"),
        push_stop_handoff="Gently steer to a concrete slot; offer alternatives if taken. STOP forcing if they want to think. HANDOFF only for special requests outside the calendar.",
        memory_fields=("appt_id", "appt_type", "slot_datetime", "location_mode", "status", "reminder_channel"),
        stage_skips=frozenset({Stage.OBJECTION}),
        behavior_pack_ids=("closing-booking",),
    ),
    UseCasePack(
        id="reminder.v1", use_case=UseCase.REMINDER, stance=_NUDGE,
        objective_template="Ensure the customer remembers + confirms an upcoming commitment; reduce no-shows / late payments.",
        success_criteria="Confirmed attendance/payment OR a clean reschedule with updated status; no annoyance.",
        opening_style="Greet + identity + the reminder in ONE calm line. Short by design.",
        data_to_collect=("confirm attend/pay", "or capture reschedule/decline", "update status"),
        push_stop_handoff="Light confirm-or-reschedule only; NEVER hard-sell. STOP after the reminder lands + a response is captured. HANDOFF if they raise an issue (-> support/booking). Cadence sensible, not spam; 2-3 retries max.",
        memory_fields=("reminder_for", "due_datetime", "confirmation_state", "reschedule_to", "attempts"),
        stage_skips=frozenset({Stage.QUALIFY, Stage.OBJECTION}),
        behavior_pack_ids=("reminder-renewal-payment", "callback-followup-cadence"),
    ),
    UseCasePack(
        id="feedback.v1", use_case=UseCase.FEEDBACK, stance=_LISTEN,
        objective_template="Capture honest satisfaction + the reason behind it; route detractors to recovery, promoters to advocacy.",
        success_criteria="A captured score + a usable reason; detractor recovery logged; promoter optionally invited to refer/review.",
        opening_style="Greet + identity + a one-line ask for 'two minutes of honest feedback'. Make it feel low-stakes.",
        data_to_collect=("rating/NPS", "the why", "specific praise/pain points", "permission to follow up"),
        push_stop_handoff="NEVER push back on criticism — thank and probe. STOP at the rating + reason. HANDOFF a detractor's concrete problem to support/complaint with a recovery promise.",
        memory_fields=("nps_score", "reason", "theme", "detractor_recovery", "consent_followup"),
        stage_skips=frozenset({Stage.PERMISSION, Stage.OBJECTION, Stage.BOOKING}),
        behavior_pack_ids=("aftersales-feedback-nps",),
    ),
    UseCasePack(
        id="complaint.v1", use_case=UseCase.COMPLAINT, stance=_DEESCALATE,
        objective_template="De-escalate, take ownership, resolve or route fast, and rebuild trust.",
        success_criteria="Customer feels heard + has a concrete next step (resolution or escalation) with a committed timeline; trust visibly steadied.",
        opening_style="Acknowledge the issue FIRST and apologize sincerely before anything else; identity comes with the apology. Slow, validating pace.",
        data_to_collect=("full grievance", "impact on them", "what resolution they want", "ticket/order ref", "urgency", "callback contact"),
        push_stop_handoff="NEVER push back. Validate -> own -> act. STOP any sales/upsell entirely. HANDOFF to supervisor on a serious/repeat/legal complaint or churn threat, carrying full context.",
        memory_fields=("complaint_id", "grievance", "severity", "desired_resolution", "escalated_to", "recovery_promised_at", "churn_risk"),
        stage_skips=frozenset({Stage.PERMISSION, Stage.BOOKING}),
        behavior_pack_ids=("support-mode",),
    ),
    UseCasePack(
        id="renewal.v1", use_case=UseCase.RENEWAL, stance=_RETAIN,
        objective_template="Retain the customer for the next term; surface and remove the friction that would cause churn.",
        success_criteria="Renewed (record + payment path set) OR a captured, specific churn reason + a scheduled win-back, OR routed to support if blocked by an issue.",
        opening_style="Warm recognition as an existing customer + the renewal context. Continuity from their usage history.",
        data_to_collect=("satisfaction with current term", "usage/value realized", "hesitations/competitor temptation", "renewal decision + preferred plan", "payment readiness"),
        push_stop_handoff="Push VALUE and EASE, not pressure; address the specific churn reason from full context. STOP if they firmly decline (capture reason for win-back). HANDOFF pricing concessions to a human; HANDOFF an unhappy customer to support first.",
        memory_fields=("subscription_ref", "renewal_due_at", "usage_value", "churn_reason", "decision", "new_plan", "winback_at"),
        behavior_pack_ids=("reminder-renewal-payment", "objection"),
    ),
    UseCasePack(
        id="onboarding.v1", use_case=UseCase.ONBOARDING, stance=_ONBOARD,
        objective_template="Get the new customer successfully started — confirm setup, walk the first value, capture any blocker early.",
        success_criteria="Confirmed first successful use OR a logged setup blocker routed to support with a follow-up time.",
        opening_style="Warm welcome as a brand-new customer + the onboarding purpose. Patient, service-first.",
        data_to_collect=("setup status", "first-use experience", "blockers", "what they need to get value", "preferred follow-up"),
        push_stop_handoff="NEVER sell — ensure activation. STOP forcing if they need time. HANDOFF setup blockers to support.",
        memory_fields=("onboarding_ref", "setup_state", "first_value_reached", "blockers", "follow_up_at"),
        stage_skips=frozenset({Stage.OBJECTION}),
        behavior_pack_ids=("support-mode",),
    ),
    UseCasePack(
        id="inbound.v1", use_case=UseCase.INBOUND, stance=_RECEPTION,
        objective_template="Identify why they called, help fast, and route to the right mode (sales/support/booking/complaint).",
        success_criteria="Intent correctly identified + served or routed in one call; lead/record updated; any commitment (booking/callback) persisted.",
        opening_style="INVERTED — time-of-day greet + warm company identity + 'how can I help you today?'. NO permission-to-talk, NO cold pattern-interrupt; move straight to listening.",
        data_to_collect=("intent/reason for calling", "who they are (confirm if known)", "what they need", "contact-back details"),
        push_stop_handoff="Match their intent — buying -> flip to sales; problem -> support/complaint; booking -> booking. STOP forcing any single track. HANDOFF when they want a human or it's beyond scope.",
        memory_fields=("inbound_intent", "caller_known", "routed_mode", "outcome", "next_action"),
        stage_skips=frozenset({Stage.PERMISSION}),
        behavior_pack_ids=("inbound-receptionist",),
    ),
    UseCasePack(
        id="ai_manager.v1", use_case=UseCase.AI_MANAGER, stance=_ACT,
        objective_template="Execute the operator's spoken business action safely (PIN/firewall/audit-gated), confirm what was done, and report the result.",
        success_criteria="The requested action executed (or correctly refused/stepped-up) with an audit record; a clear spoken confirmation of the outcome.",
        opening_style="Operator-facing: brief, capable, action-oriented; confirm risky actions before executing.",
        data_to_collect=("the requested action", "target/entity", "parameters", "confirmation/PIN for risky actions"),
        push_stop_handoff="NEVER sell. Gate destructive/spend actions behind the firewall (PIN step-up). STOP and confirm on ambiguity. HANDOFF anything outside the allowed action set.",
        memory_fields=("last_action", "action_target", "outcome", "audit_ref"),
        stage_skips=frozenset({Stage.PERMISSION, Stage.QUALIFY, Stage.OBJECTION, Stage.BOOKING}),
        behavior_pack_ids=(),
    ),
)

_USE_CASE_INDEX: dict[UseCase, UseCasePack] = {p.use_case: p for p in _USE_CASE_PACKS}


def get_use_case_pack(use_case: UseCase) -> UseCasePack:
    """Resolve the default pack for a use-case, defaulting to SALES (richest path)."""
    return _USE_CASE_INDEX.get(use_case, _USE_CASE_INDEX[UseCase.SALES])


def all_use_case_packs() -> tuple[UseCasePack, ...]:
    return _USE_CASE_PACKS


# --------------------------------------------------------------------------- #
# Seed INDUSTRY packs (L2 vocabulary). Vertical terms ONLY — no campaign content.
# `match` keywords resolve a campaign's fields to the pack. Vendors/tenants add
# more via the registry (these are the shipped defaults).
# --------------------------------------------------------------------------- #
_INDUSTRY_PACKS: tuple[IndustryPack, ...] = (
    IndustryPack(
        id="real_estate.v1", label="Real Estate",
        match=("real estate", "realty", "property", "properties", "builder", "flat", "apartment", "plot", "villa", "bhk", "project"),
        vertical_terms=("site visit", "possession", "carpet area", "BHK", "lakh/crore", "RERA", "booking amount", "loan/EMI", "end-use vs investment"),
        norm_nudges=("frame end-use vs investment; speak prices as 'pachaasi lakh' not digits; never invent possession dates — retrieve them",),
        compliance_ref="RERA",
    ),
    IndustryPack(
        id="insurance.v1", label="Insurance",
        match=("insurance", "policy", "premium", "term plan", "life cover", "health cover", "mediclaim"),
        vertical_terms=("premium", "sum assured", "grace period", "rider", "claim", "policy term", "nominee", "maturity"),
        norm_nudges=("never mis-state policy clauses — retrieve them; be precise on grace period and claim process",),
        compliance_ref="IRDAI",
    ),
    IndustryPack(
        id="clinic.v1", label="Clinic / Healthcare",
        match=("clinic", "hospital", "doctor", "dental", "consultation", "diagnostic", "healthcare", "appointment"),
        vertical_terms=("consultation", "appointment slot", "follow-up visit", "report", "specialist", "OPD"),
        norm_nudges=("never give medical advice; route clinical questions to the doctor; be gentle and patient",),
        compliance_ref="",
    ),
    IndustryPack(
        id="ecommerce.v1", label="E-commerce / Retail",
        match=("ecommerce", "e-commerce", "order", "shipment", "refund", "return", "replacement", "delivery", "shop", "store"),
        vertical_terms=("order id", "shipment", "refund", "replacement", "return window", "delivery slot", "COD"),
        norm_nudges=("be precise on refund/return timelines; never promise a delivery date you can't verify",),
        compliance_ref="",
    ),
    IndustryPack(
        id="edtech.v1", label="Education / EdTech",
        match=("edtech", "course", "coaching", "admission", "batch", "tuition", "training", "university", "college"),
        vertical_terms=("admission", "batch", "course fee", "scholarship", "demo class", "placement", "curriculum"),
        norm_nudges=("never over-promise outcomes/placements; be honest about fees and batch timing",),
        compliance_ref="",
    ),
    IndustryPack(
        id="finance.v1", label="Banking / Finance / Loans",
        match=("loan", "credit card", "mutual fund", "investment", "banking", "nbfc", "finance", "personal loan", "home loan"),
        vertical_terms=("EMI", "interest rate", "tenure", "eligibility", "processing fee", "credit score", "disbursal"),
        norm_nudges=("never mis-state rates/charges — retrieve them; be transparent on fees; defer approvals to the team",),
        compliance_ref="RBI",
    ),
)

_INDUSTRY_INDEX: dict[str, IndustryPack] = {p.id: p for p in _INDUSTRY_PACKS}


def all_industry_packs() -> tuple[IndustryPack, ...]:
    return _INDUSTRY_PACKS
