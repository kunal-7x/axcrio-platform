"""voice_ops.ai_manager_live.commands — the deterministic NL command parser (W14).

The founder's WhatsApp command center: "send today's report", "show hot leads",
"campaign X performance", "yesterday's numbers", "how many calls this week". A
DETERMINISTIC parser handles the common verbs (cheap, drift-free, testable); the
long tail can be routed to an LLM later. The parser NEVER raises — an unrecognized
message returns CommandKind.UNKNOWN so the manager can fall back gracefully.

Output is a structured `Command` carrying:
  * kind     — the verb (send_report / hot_leads / campaign_perf / metric / unknown)
  * preset   — the resolved date range preset (today/yesterday/7d/30d/...)
  * target   — a campaign id/name for campaign_perf (raw text, resolved upstream)
  * metric   — the metric key for a metric query (calls/connected/booked/...)
  * filters  — drill-down dict ({"lead_status":"hot"}, {"source":"meta"}, ...)
  * deliver  — True when the user asked to SEND/WhatsApp the result somewhere

Pure stdlib (regex). No droplet, no LLM, no I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CommandKind(str, Enum):
    SEND_REPORT = "send_report"      # "send today's report"
    HOT_LEADS = "hot_leads"          # "show hot leads"
    CAMPAIGN_PERF = "campaign_perf"  # "campaign X performance"
    METRIC = "metric"                # "how many calls today" / "connect rate this week"
    FUNNEL = "funnel"                # "show the funnel"
    UNKNOWN = "unknown"


@dataclass
class Command:
    kind: CommandKind
    preset: str = "today"
    target: str = ""                       # campaign id/name (raw)
    metric: str = ""                       # metric key for METRIC
    filters: dict = field(default_factory=dict)
    deliver: bool = False                  # send/whatsapp the result
    raw: str = ""


# Range phrases -> preset. Longer phrases first so "this month" beats "month".
_RANGE_PATTERNS = [
    (r"\bprev(?:ious)?[ -]?month\b|\blast month\b", "prev-month"),
    (r"\bthis month\b|\bmonth to date\b|\bmtd\b", "this-month"),
    (r"\blast 30 days\b|\bpast 30 days\b|\b30 ?d\b|\blast month'?s\b", "30d"),
    (r"\blast 7 days\b|\bpast 7 days\b|\b7 ?d\b|\bthis week\b|\bweek\b", "7d"),
    (r"\byesterday\b|\byday\b", "yesterday"),
    (r"\btoday\b|\btoday'?s\b|\bso far\b", "today"),
]

# Metric synonyms -> the totals key the reporting layer exposes.
_METRIC_PATTERNS = [
    (r"\bconnect(?:ion)? rate\b", "connect_rate"),
    (r"\bconversion rate\b", "conversion_rate"),
    (r"\bbook(?:ing)? rate\b", "book_rate"),
    (r"\bconnected\b|\banswered\b|\bpicked up\b", "connected"),
    (r"\bbook(?:ed|ings?)\b|\bappointments?\b|\bsite visits?\b", "booked"),
    (r"\bconvert(?:ed|sions?)\b|\bsales?\b|\bdeals?\b", "converted"),
    (r"\bhandoffs?\b|\btransfers?\b", "handoff"),
    (r"\bcallbacks?\b|\bfollow ?ups?\b", "callbacks"),
    (r"\bwhats ?app(?:s)?\b|\bwa msgs?\b", "whatsapp_sent"),
    (r"\bno[ -]?answer(?:s)?\b|\bunanswered\b", "no_answer"),
    (r"\bcalls?\b|\bdial(?:ed|s)?\b", "calls"),
]

_LEAD_STATUS = ("hot", "warm", "cold", "dead")
_SOURCE_HINTS = ("meta", "facebook", "google", "instagram", "whatsapp", "csv", "manual", "website")

_DELIVER_RE = re.compile(r"\b(send|share|whats ?app|wa|deliver|text|message|push|forward)\b", re.I)
_HOTLEAD_RE = re.compile(r"\b(hot|warm|cold|dead)\b.*\bleads?\b|\bleads?\b.*\b(hot|warm|cold|dead)\b", re.I)
_FUNNEL_RE = re.compile(r"\bfunnel\b|\bpipeline\b|\bdrop ?off\b", re.I)
_CAMPAIGN_RE = re.compile(
    r"\bcampaign\s+(?:called\s+|named\s+|\"|')?([a-z0-9][a-z0-9 _\-]{0,48}?)(?:[\"']?)\s*"
    r"(?:performance|perf|report|stats?|numbers?|results?|breakdown|analytics)?\s*$",
    re.I,
)
_REPORT_RE = re.compile(r"\breport\b|\bsummary\b|\boverview\b|\bnumbers?\b|\bstats?\b|\brecap\b|\bdigest\b", re.I)


def _detect_preset(text: str, default: str) -> str:
    for pat, preset in _RANGE_PATTERNS:
        if re.search(pat, text, re.I):
            return preset
    return default


def _detect_filters(text: str) -> dict:
    filters: dict = {}
    for s in _LEAD_STATUS:
        if re.search(rf"\b{s}\b", text, re.I):
            filters["lead_status"] = s
            break
    for src in _SOURCE_HINTS:
        if re.search(rf"\b{src}\b", text, re.I):
            filters["source"] = "facebook" if src in ("facebook",) else src
            break
    return filters


def parse_command(message: str, *, default_preset: str = "today") -> Command:
    """Parse a free-text manager command into a structured Command. Never raises;
    unknown -> CommandKind.UNKNOWN. Deterministic + order-sensitive (most specific
    intent wins): campaign-perf > hot-leads > funnel > report > metric."""
    raw = (message or "").strip()
    text = raw.lower()
    if not text:
        return Command(kind=CommandKind.UNKNOWN, raw=raw, preset=default_preset)

    preset = _detect_preset(text, default_preset)
    deliver = bool(_DELIVER_RE.search(text))
    filters = _detect_filters(text)

    # 1) campaign performance — "campaign <name> performance"
    m = _CAMPAIGN_RE.search(raw)
    if m and re.search(r"\bcampaign\b", text):
        target = m.group(1).strip()
        # strip a trailing range word that the greedy name capture may have eaten
        target = re.sub(r"\b(today|yesterday|this|last|week|month|days?)\b.*$", "", target, flags=re.I).strip()
        if target:
            return Command(kind=CommandKind.CAMPAIGN_PERF, preset=preset, target=target,
                           filters=filters, deliver=deliver, raw=raw)

    # 2) hot/warm/cold/dead leads — "show hot leads" / "list warm leads"
    if _HOTLEAD_RE.search(text) or (re.search(r"\bleads?\b", text) and filters.get("lead_status")):
        status = filters.get("lead_status", "hot")
        return Command(kind=CommandKind.HOT_LEADS, preset=preset,
                       filters={"lead_status": status}, deliver=deliver, raw=raw)

    # 3) funnel / pipeline
    if _FUNNEL_RE.search(text):
        return Command(kind=CommandKind.FUNNEL, preset=preset, filters=filters,
                       deliver=deliver, raw=raw)

    # 4) full report / summary — "send today's report", "give me a summary"
    if _REPORT_RE.search(text):
        return Command(kind=CommandKind.SEND_REPORT, preset=preset, filters=filters,
                       deliver=deliver, raw=raw)

    # 5) a specific metric — "how many calls today", "connect rate this week"
    for pat, key in _METRIC_PATTERNS:
        if re.search(pat, text):
            return Command(kind=CommandKind.METRIC, preset=preset, metric=key,
                           filters=filters, deliver=deliver, raw=raw)

    return Command(kind=CommandKind.UNKNOWN, preset=preset, filters=filters,
                   deliver=deliver, raw=raw)
