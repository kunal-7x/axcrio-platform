"""voice_ops.reporting.aggregate — the pure aggregation engine (W14).

All functions here are PURE: (list[FactCall], DateRange, filters) -> plain dicts.
No I/O, no clock — the service supplies the already-scanned rows + the resolved
range, this layer does the math. That makes the founder's "every metric
recalculated per range" trivially testable: feed the same rows with a different
range and the numbers change; feed a drill-down filter and only matching rows
count.

Funnel math (the 8 stages uploaded->...->converted): a call's `funnel_stage` is
the FURTHEST stage it reached, so the funnel count at stage S = number of calls
whose furthest stage index >= S (a monotone “reached at least this stage” funnel).
Conversion% between consecutive stages is derived from those counts.

Pure stdlib + sibling model/daterange. No droplet import.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from voice_kernel.events.timeutil import vendor_date

from .daterange import DateRange
from .model import (
    FUNNEL_STAGES,
    BookingStatus,
    CallStatus,
    FactCall,
    LeadStatus,
    funnel_index,
)

# The drill-down dimensions the founder asked for, each -> the FactCall attribute.
DRILL_DIMS = {
    "campaign": "campaign_id",
    "lead_status": "lead_status",
    "source": "source",
    "agent": "agent",
    "call_status": "call_status",
    "booking_status": "booking_status",
}


def _val(fact: FactCall, attr: str) -> str:
    v = getattr(fact, attr, "")
    # enums -> their value so a filter string like "hot" matches LeadStatus.HOT.
    return getattr(v, "value", v) if v is not None else ""


def drill(rows: Iterable[FactCall], filters: Optional[dict] = None) -> list[FactCall]:
    """Return the subset of `rows` matching every (dimension -> value) in
    `filters`. Unknown dimension keys are ignored (forward-compatible). An empty
    or None filter returns all rows. Matching is on the canonical string value so
    callers pass plain strings ('hot', 'connected', campaign id)."""
    if not filters:
        return list(rows)
    norm = {DRILL_DIMS[k]: str(v).lower() for k, v in filters.items() if k in DRILL_DIMS and v not in (None, "")}
    if not norm:
        return list(rows)
    out = []
    for f in rows:
        if all(_val(f, attr).lower() == want for attr, want in norm.items()):
            out.append(f)
    return out


def in_range(rows: Iterable[FactCall], rng: DateRange) -> list[FactCall]:
    """Rows whose ts falls in the half-open [start, end) window."""
    return [f for f in rows if rng.contains(f.ts_iso)]


def totals(rows: list[FactCall]) -> dict:
    """Top-line counts for a (range+drill) row set."""
    t = {
        "calls": len(rows),
        "dialed": 0,
        "connected": 0,
        "interested": 0,
        "booked": 0,
        "converted": 0,
        "handoff": 0,
        "whatsapp_sent": 0,
        "callbacks": 0,
        "no_answer": 0,
        "voicemail": 0,
        "failed": 0,
        "opted_out": 0,
        "hot": 0,
        "warm": 0,
        "cold": 0,
        "dead": 0,
        "talk_time_s": 0,
    }
    for f in rows:
        if funnel_index(f.funnel_stage) >= funnel_index("dialed"):
            t["dialed"] += 1
        if f.connected:
            t["connected"] += 1
        if f.interested:
            t["interested"] += 1
        if f.booked:
            t["booked"] += 1
        if f.converted:
            t["converted"] += 1
        if f.handoff:
            t["handoff"] += 1
        if f.whatsapp_sent:
            t["whatsapp_sent"] += 1
        if f.callback_scheduled:
            t["callbacks"] += 1
        t["talk_time_s"] += int(f.duration_s or 0)
        cs = getattr(f.call_status, "value", f.call_status)
        if cs == CallStatus.NO_ANSWER.value:
            t["no_answer"] += 1
        elif cs == CallStatus.VOICEMAIL.value:
            t["voicemail"] += 1
        elif cs == CallStatus.FAILED.value:
            t["failed"] += 1
        elif cs == CallStatus.OPTED_OUT.value:
            t["opted_out"] += 1
        ls = getattr(f.lead_status, "value", f.lead_status)
        if ls in ("hot", "warm", "cold", "dead"):
            t[ls] += 1
    t["connect_rate"] = _rate(t["connected"], t["dialed"])
    t["book_rate"] = _rate(t["booked"], t["connected"])
    t["conversion_rate"] = _rate(t["converted"], t["dialed"])
    t["avg_talk_time_s"] = round(t["talk_time_s"] / t["connected"], 1) if t["connected"] else 0.0
    return t


def build_funnel(rows: list[FactCall]) -> list[dict]:
    """The 8-stage funnel. count[S] = #calls whose furthest stage >= S.
    `pct_of_top` = stage count / uploaded count; `step_conv` = stage / prev
    stage (the drop-off between adjacent stages)."""
    counts = [0] * len(FUNNEL_STAGES)
    for f in rows:
        reached = funnel_index(f.funnel_stage)
        for i in range(reached + 1):
            counts[i] += 1
    top = counts[0] or 0
    out = []
    for i, stage in enumerate(FUNNEL_STAGES):
        prev = counts[i - 1] if i > 0 else counts[i]
        out.append({
            "stage": stage,
            "count": counts[i],
            "pct_of_top": _rate(counts[i], top),
            "step_conv": _rate(counts[i], prev) if i > 0 else 100.0,
        })
    return out


def _breakdown(rows: list[FactCall], attr: str) -> list[dict]:
    """Per-value rollup for one dimension (count + connected + booked + converted),
    sorted by count desc. Powers source/campaign/agent analytics tables."""
    agg: dict[str, dict] = defaultdict(lambda: {"calls": 0, "connected": 0, "booked": 0,
                                                 "converted": 0, "talk_time_s": 0})
    for f in rows:
        key = _val(f, attr) or "(none)"
        a = agg[key]
        a["calls"] += 1
        a["connected"] += 1 if f.connected else 0
        a["booked"] += 1 if f.booked else 0
        a["converted"] += 1 if f.converted else 0
        a["talk_time_s"] += int(f.duration_s or 0)
    out = []
    for key, a in agg.items():
        out.append({
            "key": key,
            **a,
            "connect_rate": _rate(a["connected"], a["calls"]),
            "book_rate": _rate(a["booked"], a["connected"]),
        })
    out.sort(key=lambda r: r["calls"], reverse=True)
    return out


def agent_performance(rows: list[FactCall]) -> list[dict]:
    """Per-agent analytics (founder pain #3: agent perf)."""
    return _breakdown(rows, "agent")


def source_analytics(rows: list[FactCall]) -> list[dict]:
    return _breakdown(rows, "source")


def campaign_analytics(rows: list[FactCall]) -> list[dict]:
    return _breakdown(rows, "campaign_id")


def followup_analytics(rows: list[FactCall]) -> dict:
    """Follow-up analytics: callbacks scheduled, whatsapp follow-ups, handoffs —
    the post-call action layer the founder wants visibility into."""
    callbacks = sum(1 for f in rows if f.callback_scheduled)
    wa = sum(1 for f in rows if f.whatsapp_sent)
    handoffs = sum(1 for f in rows if f.handoff)
    pending = sum(1 for f in rows if f.callback_scheduled and not f.booked and not f.converted)
    return {
        "callbacks_scheduled": callbacks,
        "whatsapp_followups": wa,
        "handoffs": handoffs,
        "pending_followups": pending,
    }


def daily_timeline(rows: list[FactCall], rng: DateRange) -> list[dict]:
    """Per-vendor-day activity series across the range (founder pain #3: daily
    activity timeline). Every day in the window appears (zero-filled), grouped on
    the VENDOR-local calendar date (timeutil.vendor_date) so a 00:30 IST call is
    on the right day — the off-by-one fix."""
    buckets: dict[str, dict] = {
        d: {"date": d, "calls": 0, "connected": 0, "booked": 0, "converted": 0}
        for d in rng.vendor_dates()
    }
    for f in rows:
        try:
            d = vendor_date(f.ts_iso, rng.tz_name)
        except Exception:
            continue
        b = buckets.get(d)
        if b is None:
            continue
        b["calls"] += 1
        b["connected"] += 1 if f.connected else 0
        b["booked"] += 1 if f.booked else 0
        b["converted"] += 1 if f.converted else 0
    return [buckets[d] for d in rng.vendor_dates()]


def status_breakdowns(rows: list[FactCall]) -> dict:
    """Counts grouped by lead_status / call_status / booking_status — the
    drill-down chips' badge counts."""
    lead = defaultdict(int)
    call = defaultdict(int)
    book = defaultdict(int)
    for f in rows:
        lead[getattr(f.lead_status, "value", f.lead_status)] += 1
        call[getattr(f.call_status, "value", f.call_status)] += 1
        book[getattr(f.booking_status, "value", f.booking_status)] += 1
    return {
        "lead_status": dict(lead),
        "call_status": dict(call),
        "booking_status": dict(book),
    }


def aggregate(rows: list[FactCall], rng: DateRange, filters: Optional[dict] = None) -> dict:
    """The full report for a range + optional drill-down. The single entry the
    service calls: range-filter -> drill -> compute every section. Recalculated
    entirely from the supplied rows, so any range/filter combination is correct by
    construction."""
    scoped = drill(in_range(rows, rng), filters)
    return {
        "range": {
            "preset": rng.preset,
            "from": rng.start_iso,
            "to": rng.end_iso,
            "tz": rng.tz_name,
        },
        "filters": dict(filters or {}),
        "totals": totals(scoped),
        "funnel": build_funnel(scoped),
        "by_status": status_breakdowns(scoped),
        "agents": agent_performance(scoped),
        "sources": source_analytics(scoped),
        "campaigns": campaign_analytics(scoped),
        "followups": followup_analytics(scoped),
        "timeline": daily_timeline(scoped, rng),
    }


def _rate(num: int, den: int) -> float:
    """Percentage (0..100, 1dp). 0/0 -> 0.0 (never a ZeroDivisionError)."""
    if not den:
        return 0.0
    return round(100.0 * num / den, 1)
