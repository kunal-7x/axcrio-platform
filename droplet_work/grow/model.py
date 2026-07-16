"""grow.model — canonical records, enums, event taxonomy + PII hashing for Haptica Grow.

Haptica Grow = the autonomous Ad → Lead → AI-call/WhatsApp-qualify → SCORE →
conversion-signal-back-to-Meta/Google loop (the "ElevateX / Growth-OS" vision,
GROWTH-OS-BUILD-SPEC §11 flagship). This module is the SHARED contract every other
grow.* module binds to (scoring, signals, store, loop, endpoints) — keep field names
canonical; downstream code + the FORCE-RLS DDL (grow/db/ddl_grow.sql) mirror them.

POSTURE (house rules, mirrors voice_ops): stdlib-only at import; dataclasses with a
`.copy()`; enums with `.coerce()`; never log raw PII; money/score are INTEGER.

TWO DISTINCT HASHES — do not conflate:
  * `capi_hash(value)`     — UNSALTED SHA-256 of a NORMALIZED identifier. This is what
                             Meta CAPI / Google Enhanced-Conversions require so THEIR
                             hashed graph can match ours. Used ONLY for outbound match
                             keys. (GROWTH-OS §5.4 / §11.3.)
  * `principal_ref(salt,)` — SALTED SHA-256, for OUR at-rest identity key (PII-min, so a
                             DB leak cannot be matched back). Mirrors the compliance
                             ConsentLedger.data_principal_ref. NEVER sent to a platform.
Raw phone/email never live at rest in grow tables — only these hashes + a masked tail.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
from dataclasses import dataclass, field, replace
from typing import Optional


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


# =========================================================================== #
# PII normalization + hashing
# =========================================================================== #
def normalize_phone(raw: str) -> str:
    """E.164-ish normalize for hashing: strip everything non-digit; default India CC.
    Returns digits WITHOUT the leading '+' (Meta hashes the country-code-prefixed number
    with no '+'), e.g. '+91 98765-43210' -> '919876543210'. Empty -> ''."""
    if not raw:
        return ""
    # E.164 numbers never start with 0 — strip any trunk/leading zeros first.
    digits = re.sub(r"\D+", "", str(raw)).lstrip("0")
    if not digits:
        return ""
    # bare 10-digit Indian mobile -> prefix the country code; already-CC'd -> keep.
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def normalize_name(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip().lower())


def capi_hash(value: str) -> str:
    """UNSALTED SHA-256 hex of an ALREADY-NORMALIZED value (for platform match keys).
    Empty input -> '' (so callers can drop absent keys, never send a hash of '')."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def principal_ref(salt: str, phone: str = "", *, lead_id: str = "") -> str:
    """SALTED SHA-256 hex — OUR PII-min at-rest identity key. Prefer the normalized phone
    (E.164 is king in India for identity, §8.3); fall back to lead_id so a number-less
    lead still gets a stable ref. Returns '' only if both are empty."""
    norm = normalize_phone(phone)
    basis = norm or (lead_id or "").strip()
    if not basis:
        return ""
    return hashlib.sha256(f"{salt}|{basis}".encode("utf-8")).hexdigest()


def mask_phone(raw: str) -> str:
    """Display-safe masked tail, e.g. '+91 98765 43210' -> '••••• 43210'."""
    d = re.sub(r"\D+", "", str(raw or ""))
    if len(d) < 4:
        return "•" * len(d)
    return "•" * (len(d) - 4) + " " + d[-4:]


# =========================================================================== #
# Event taxonomy (subset of GROWTH-OS §6.2 — extend, never mutate)
# =========================================================================== #
EVT_LEAD_CAPTURED = "lead.captured"
EVT_LEAD_SCORED = "lead.scored"
EVT_LEAD_QUALIFIED = "lead.qualified"
EVT_LEAD_DISQUALIFIED = "lead.disqualified"
EVT_CALL_COMPLETED = "call.completed"
EVT_CALL_OUTCOME = "call.outcome"
EVT_WA_RECEIVED = "wa.message.received"
EVT_BOOKING_CREATED = "booking.created"
EVT_BOOKING_ATTENDED = "booking.attended"
EVT_SALE_RECORDED = "sale.recorded"
EVT_SIGNAL_DISPATCHED = "signal.dispatched"


# =========================================================================== #
# Lead tier (L5) — the "Hot / Warm / Investor / End-user / Junk" the deck promises
# =========================================================================== #
class LeadTier:
    HOT = "hot"
    WARM = "warm"
    INVESTOR = "investor"
    END_USER = "end_user"
    JUNK = "junk"

    _ALL = ("hot", "warm", "investor", "end_user", "junk")

    @classmethod
    def coerce(cls, v: str) -> str:
        s = (v or "").strip().lower().replace("-", "_")
        return s if s in cls._ALL else cls.JUNK

    @classmethod
    def is_sales_ready(cls, tier: str) -> bool:
        """Tiers that route to the builder's sales team in real time (L6)."""
        return cls.coerce(tier) in (cls.HOT, cls.INVESTOR)


# =========================================================================== #
# The CAPI event ladder (GROWTH-OS §11.1) — deepest event with volume wins
# =========================================================================== #
class Ladder:
    LEAD = "Lead"                 # on capture
    QUALIFIED = "QualifiedLead"   # lead_score >= T_hot OR call_outcome == qualified (custom)
    SCHEDULE = "Schedule"         # booking.created
    ATTENDED = "Attended"         # booking.attended (custom)
    PURCHASE = "Purchase"         # sale.recorded {value: order_value}

    _STEP = {"Lead": 1, "QualifiedLead": 2, "Schedule": 3, "Attended": 4, "Purchase": 5}

    @classmethod
    def step(cls, name: str) -> int:
        return cls._STEP.get(name, 0)


# =========================================================================== #
# Records
# =========================================================================== #
@dataclass
class ScoringInput:
    """Everything the L5 scorer reads about one lead, joined across the journey.
    All fields optional/defaulted so a partial signal still scores (re-score on each
    new journey event — §9.5). Raw phone is accepted only to derive masked/hash; it is
    NEVER persisted by the scorer."""
    tenant_id: str = ""
    lead_id: str = ""
    journey_id: str = ""
    phone: str = ""                     # raw, transient (hashed/masked downstream)
    name: str = ""
    source_platform: str = ""           # meta | google | whatsapp | manual | import
    # --- form / capture validity ---
    phone_valid: bool = True
    disposable_email: bool = False
    # --- voice call outcome (from agent.py finalize → caller _finalize_call) ---
    call_answered: bool = False
    call_duration_s: int = 0
    interest_score: int = 0             # 0-100 the live agent already extracts
    budget_mentioned: bool = False
    timeline_mentioned: bool = False    # "ready in 3 months" etc.
    decision_authority: bool = False    # speaking to the actual buyer/decision-maker
    site_visit_ready: bool = False
    booking_made: bool = False
    investor_intent: bool = False       # "looking to invest / rental yield / portfolio"
    end_user_intent: bool = False       # "for my family to live in"
    last_outcome: str = ""              # interested|callback|not_interested|dnc|...
    # --- whatsapp behavior (async qualification) ---
    wa_replied: bool = False
    wa_reply_latency_s: int = 0
    wa_depth: int = 0                   # # of inbound turns
    extra: dict = field(default_factory=dict)

    def copy(self) -> "ScoringInput":
        return replace(self, extra=dict(self.extra))


@dataclass
class ScoredLead:
    """Output of L5 scoring + the row persisted to grow_lead_scores."""
    tenant_id: str
    lead_id: str
    journey_id: str = ""
    principal_ref: str = ""             # salted hash (PII-min identity key)
    phone_masked: str = ""
    score: int = 0                      # 0-100
    tier: str = LeadTier.JUNK
    confidence: float = 0.0            # 0..1
    reasons: list = field(default_factory=list)   # the human-readable "why"
    features: dict = field(default_factory=dict)  # stored WITH the score (training data, §9.5)
    model: str = "heuristic_v1"
    source_platform: str = ""
    scored_at: Optional[_dt.datetime] = None

    def __post_init__(self):
        if self.scored_at is None:
            self.scored_at = _now()
        self.tier = LeadTier.coerce(self.tier)

    @property
    def sales_ready(self) -> bool:
        return LeadTier.is_sales_ready(self.tier)

    def copy(self) -> "ScoredLead":
        return replace(self, reasons=list(self.reasons), features=dict(self.features))

    def public(self) -> dict:
        """PII-safe dict for API responses (no principal_ref leak; masked phone only)."""
        return {
            "lead_id": self.lead_id, "journey_id": self.journey_id,
            "phone_masked": self.phone_masked, "score": self.score, "tier": self.tier,
            "confidence": round(self.confidence, 3), "reasons": list(self.reasons),
            "sales_ready": self.sales_ready, "model": self.model,
            "source_platform": self.source_platform,
            "scored_at": self.scored_at.isoformat() if self.scored_at else None,
        }


class SignalStatus:
    SHADOW = "shadow"        # would-send logged; no creds / shadow mode (default)
    QUEUED = "queued"
    SENT = "sent"
    ACKED = "acked"
    FAILED = "failed"
    DEDUPED = "deduped"      # event_id already dispatched → skipped (idempotent)


@dataclass
class SignalEvent:
    """One row of the dispatch ledger (grow_signals_log). The OUTBOUND CAPI/EC truth.
    We persist match-key TYPES + a redacted view — never the raw hashed PII values —
    so the ledger itself stays clean even though the live payload carries the hashes."""
    tenant_id: str
    event_id: str                      # sha256(journey_id + ladder_step) — dedup key
    journey_id: str = ""
    lead_id: str = ""
    platform: str = "meta"             # meta | google
    endpoint: str = "capi"             # capi | enhanced_conversions
    event_name: str = Ladder.LEAD
    value: int = 0                     # value=lead_score (Lead) or order_value (Purchase)
    currency: str = "INR"
    match_keys: list = field(default_factory=list)   # ["ph","em","fbc","ctwa_clid",...]
    status: str = SignalStatus.SHADOW
    emq_estimate: float = 0.0          # match-quality proxy 0..10 (key-coverage based)
    reason: str = ""                   # why shadow/failed
    dispatched_at: Optional[_dt.datetime] = None

    def __post_init__(self):
        if self.dispatched_at is None:
            self.dispatched_at = _now()

    def copy(self) -> "SignalEvent":
        return replace(self, match_keys=list(self.match_keys))

    def public(self) -> dict:
        return {
            "event_id": self.event_id, "journey_id": self.journey_id, "lead_id": self.lead_id,
            "platform": self.platform, "endpoint": self.endpoint, "event_name": self.event_name,
            "value": self.value, "currency": self.currency, "match_keys": list(self.match_keys),
            "status": self.status, "emq_estimate": round(self.emq_estimate, 2),
            "reason": self.reason,
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
        }


@dataclass
class Journey:
    """One person's journey (GROWTH-OS §6.3) — correlation spine for deterministic ROI.
    `correlation_id`/journey_id minted at first touch, propagated through every event."""
    tenant_id: str
    journey_id: str
    principal_ref: str = ""
    phone_masked: str = ""
    source_platform: str = ""          # meta | google | whatsapp | manual
    source_ad_id: str = ""
    ctwa_clid: str = ""                # click-to-WhatsApp click id (keys business-msg CAPI)
    fbclid: str = ""
    gclid: str = ""
    status: str = "open"               # open | qualified | booked | won | lost
    first_touch_at: Optional[_dt.datetime] = None
    updated_at: Optional[_dt.datetime] = None

    def __post_init__(self):
        now = _now()
        if self.first_touch_at is None:
            self.first_touch_at = now
        if self.updated_at is None:
            self.updated_at = now

    def copy(self) -> "Journey":
        return replace(self)

    def public(self) -> dict:
        return {
            "journey_id": self.journey_id, "phone_masked": self.phone_masked,
            "source_platform": self.source_platform, "source_ad_id": self.source_ad_id,
            "has_ctwa": bool(self.ctwa_clid), "has_click_id": bool(self.fbclid or self.gclid),
            "status": self.status,
            "first_touch_at": self.first_touch_at.isoformat() if self.first_touch_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =========================================================================== #
# L3 — Speed-to-lead orchestration records (W2)
# =========================================================================== #
@dataclass
class CapturedLead:
    """A consent-clean lead the instant it raises its hand (Meta/Google leadgen form,
    CTWA, or a landing-page form). The input to the <60s speed-to-lead orchestration.
    Raw phone/email are transient (hashed/masked downstream, never stored raw)."""
    tenant_id: str
    lead_id: str
    phone: str = ""
    name: str = ""
    email: str = ""
    source_platform: str = ""          # meta | google | whatsapp | landing | manual
    source_ad_id: str = ""
    ctwa_clid: str = ""
    fbclid: str = ""
    gclid: str = ""
    campaign_id: str = ""
    consent_basis: str = "explicit"    # explicit (lead-form opt-in) | inferred | legitimate_use
    consent_channel: str = "web_form"  # web_form | whatsapp | ivr_dtmf | import
    captured_at: Optional[_dt.datetime] = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.captured_at is None:
            self.captured_at = _now()

    def copy(self) -> "CapturedLead":
        return replace(self, extra=dict(self.extra))


class ChannelStatus:
    FIRED = "fired"                    # action handed off to the channel
    SKIPPED_NO_CONFIG = "skipped_no_config"   # dormant-safe: channel not wired
    BLOCKED = "blocked"               # compliance gate said no
    FAILED = "failed"
    SUPPRESSED = "suppressed"         # DND / opted-out


@dataclass
class ChannelResult:
    channel: str                       # whatsapp | voice
    status: str = ChannelStatus.SKIPPED_NO_CONFIG
    ref: str = ""                      # message_id / call_id
    reason: str = ""

    def public(self) -> dict:
        return {"channel": self.channel, "status": self.status, "ref": self.ref,
                "reason": self.reason}


class OrchStatus:
    DONE = "done"                      # at least one channel fired
    BLOCKED = "blocked"               # compliance blocked all outreach
    NO_CHANNELS = "no_channels"       # nothing wired (dormant) — recorded, not an error
    ERROR = "error"


@dataclass
class Orchestration:
    """The record of one speed-to-lead run: capture → compliance gate → fire channels,
    journey-threaded, with the capture→fire latency + whether the <60s SLA held."""
    tenant_id: str
    journey_id: str
    lead_id: str = ""
    status: str = OrchStatus.DONE
    compliance_decision: str = "allow"   # allow | block | soft | unenforced
    compliance_reasons: list = field(default_factory=list)
    channels: list = field(default_factory=list)   # list[ChannelResult]
    latency_ms: int = 0                  # capture → fire
    sla_seconds: int = 60
    sla_met: bool = True
    captured_at: Optional[_dt.datetime] = None
    completed_at: Optional[_dt.datetime] = None

    def __post_init__(self):
        if self.completed_at is None:
            self.completed_at = _now()

    @property
    def fired(self) -> list:
        return [c for c in self.channels if getattr(c, "status", "") == ChannelStatus.FIRED]

    def copy(self) -> "Orchestration":
        return replace(self, compliance_reasons=list(self.compliance_reasons),
                       channels=[replace(c) for c in self.channels])

    def public(self) -> dict:
        return {
            "journey_id": self.journey_id, "lead_id": self.lead_id, "status": self.status,
            "compliance_decision": self.compliance_decision,
            "compliance_reasons": list(self.compliance_reasons),
            "channels": [c.public() for c in self.channels],
            "fired": [c.channel for c in self.fired],
            "latency_ms": self.latency_ms, "sla_seconds": self.sla_seconds,
            "sla_met": self.sla_met,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
