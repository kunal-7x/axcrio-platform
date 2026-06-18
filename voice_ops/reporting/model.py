"""voice_ops.reporting.model — the canonical read-model row + taxonomies (W14).

A `FactCall` is ONE row per call: the denormalized, latest-wins projection that
the SinkConsumer materializes from the W8 event stream and the query API
aggregates. It is deliberately flat + cheap so an aggregate over a date range is a
single pass, never an O(n) JSON walk + joins like the live flat-file path.

Reuses the W7 lead Lifecycle values for `lead_status` (hot/warm/cold/dead/new) —
reporting NEVER re-classifies; it records what the memory FSM derived. Timestamps
are canonical UTC 'Z' ISO strings (timeutil contract).

Pure stdlib. No droplet import.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


class LeadStatus(str, Enum):
    """Mirrors voice_kernel.packet.Lifecycle so the dashboard badges line up.
    Kept as its own enum so reporting stays importable WITHOUT pulling packet at
    module load; `from_lifecycle` bridges the two."""

    NEW = "new"
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    DEAD = "dead"

    @classmethod
    def coerce(cls, value) -> "LeadStatus":
        try:
            return cls((value or "new").lower())
        except Exception:
            return cls.NEW


class CallStatus(str, Enum):
    """The outcome of a dial attempt — the drill-down dimension for call-status."""

    PENDING = "pending"          # uploaded, not yet dialed
    DIALING = "dialing"          # originate sent, ringing
    CONNECTED = "connected"      # media established / answered
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    VOICEMAIL = "voicemail"
    FAILED = "failed"            # SIP error / crashed
    COMPLETED = "completed"      # normal hangup after a real conversation
    OPTED_OUT = "opted_out"


class BookingStatus(str, Enum):
    NONE = "none"
    BOOKED = "booked"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


# The 8 funnel stages the founder asked for, in order. A call's `funnel_stage` is
# the FURTHEST stage it reached. Aggregation counts, per stage S, the calls whose
# furthest stage is >= S (a cumulative/“reached this stage” funnel).
FUNNEL_STAGES = (
    "uploaded",
    "dialed",
    "connected",
    "interested",
    "warm",
    "hot",
    "booked",
    "converted",
)

_FUNNEL_INDEX = {s: i for i, s in enumerate(FUNNEL_STAGES)}


def funnel_index(stage: str) -> int:
    """Ordinal of a funnel stage (0..7); unknown -> 0 (uploaded floor)."""
    return _FUNNEL_INDEX.get((stage or "uploaded").lower(), 0)


@dataclass
class FactCall:
    """One denormalized call row (latest-wins on call_id within a tenant).

    All the drill-down dimensions live here so a filter is a field compare, and
    the funnel is derived from `funnel_stage`. Mutable on purpose: the consumer
    upserts the same row as later events for the same call arrive (call_started ->
    call_connected -> summary_ready -> site_visit_booked all refine one row)."""

    tenant_id: str
    call_id: str
    # when the call happened (canonical UTC 'Z' ISO) — the range-filter key.
    ts_iso: str

    # drill-down dimensions
    campaign_id: str = ""
    source: str = ""                       # lead source (csv/meta/google/manual/...)
    agent: str = ""                        # the (AI persona / human) handling agent id
    lead_status: LeadStatus = LeadStatus.NEW
    call_status: CallStatus = CallStatus.PENDING
    booking_status: BookingStatus = BookingStatus.NONE

    # furthest funnel stage reached (drives the funnel math)
    funnel_stage: str = "uploaded"

    # measures
    duration_s: int = 0
    connected: bool = False
    interested: bool = False
    booked: bool = False
    converted: bool = False
    handoff: bool = False
    whatsapp_sent: bool = False
    callback_scheduled: bool = False
    has_recording: bool = False
    has_transcript: bool = False

    # lead identity for hot-lead naming in summaries (PII-light: name + masked phone)
    lead_name: str = ""
    lead_phone_masked: str = ""

    # the short AI summary + suggested next action (founder pain #4)
    ai_summary: str = ""
    next_action: str = ""
    conversion_prob: int = 0

    def bump_stage(self, stage: str) -> None:
        """Advance `funnel_stage` to `stage` only if it is FURTHER than the
        current one (the funnel is monotone — a call never goes backwards)."""
        if funnel_index(stage) > funnel_index(self.funnel_stage):
            self.funnel_stage = stage

    def copy(self) -> "FactCall":
        return replace(self)


def lead_status_to_funnel(status: LeadStatus) -> Optional[str]:
    """Map a lead lifecycle to its funnel stage contribution (None for new/dead)."""
    return {
        LeadStatus.WARM: "warm",
        LeadStatus.HOT: "hot",
    }.get(status)
