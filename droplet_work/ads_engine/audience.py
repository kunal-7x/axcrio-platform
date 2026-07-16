"""ads_engine.audience — AUTONOMOUS AUDIENCE EXPANSION (V2-W3 parity loop).

On Meta/Google the configured audience is a HINT, not a wall: Andromeda/Smart Bidding seed off it and
then expand to whatever higher-converting segment they discover (research/comp-autonomy.md §"manual
audiences become hints, not walls" + gap #5). Our campaigns deliver only to the exact audience the vendor
typed. This module closes that: it treats the configured audience as a SEED (a floor), mines the live
ad_events for new segments that convert at/above the seed, and surfaces them as PROPOSAL-ONLY, guardrailed
expansion candidates under a SOFT CEILING (bounded count + bounded budget share) — never a hard wall that
drops the seed, never auto-spend.

EARNER-SAFE: pure discovery over the conversion-signal spine; the emitted `audience_expand` move is
spend-INCREASING (sign +1) so guardrails forces draft -> approve -> step-up before any rupee moves. No
auto audience change, no network, no caller import. Deterministic + offline-testable. Never raises.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from . import ad_events as _ev

_log = logging.getLogger("ads_engine.audience")

# ---------------------------------------------------------------------------
# SOFT-CEILING tunables — expansion is bounded, never unbounded (and never replaces the seed).
# ---------------------------------------------------------------------------
MAX_EXPANSION_SEGMENTS = 5       # PMax discovers ~3-5 new profitable segments; cap proposals here
MIN_SEGMENT_CONVERSIONS = 3      # a candidate segment needs real conversion signal, not one fluke
MIN_LIFT = 1.0                   # candidate conv-rate must be >= seed conv-rate (>1 = strictly better)
EXPANSION_BUDGET_SHARE = 0.15    # SOFT ceiling: each new segment may take up to 15% of budget (bounded)


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _segment_key(ev: dict) -> str:
    """Resolve a segment label from an event. Prefers an explicit `segment` label, else a canonical
    join of `attributes` (geo/age/interest...). Empty => the event is not segment-attributable."""
    seg = _norm(ev.get("segment") or ev.get("audience_segment"))
    if seg:
        return seg
    attrs = ev.get("attributes")
    if isinstance(attrs, dict) and attrs:
        return ",".join(f"{_norm(k)}={_norm(v)}" for k, v in sorted(attrs.items()))
    return ""


_QUALITY_RUNGS = frozenset({_ev.EV_LEAD_QUALIFIED, _ev.EV_HOT,
                            _ev.EV_SITE_VISIT_BOOKED, _ev.EV_BOOKING})


def aggregate_segments(events: list, *, campaign_id: Optional[str] = None) -> dict:
    """Per-segment {reach, leads, conversions, conv_rate} over the events. reach = views/clicks proxy
    denominator; conversions = QUALITY rungs (real buyers). Pure, deterministic."""
    segs: dict = {}
    for e in events or []:
        if campaign_id is not None and str(e.get("campaign_id") or e.get("source_campaign_id")) != str(campaign_id):
            continue
        key = _segment_key(e)
        if not key:
            continue
        s = segs.setdefault(key, {"segment": key, "reach": 0, "leads": 0, "conversions": 0})
        etype = _norm(e.get("type"))
        if etype in (_ev.EV_PAGE_VIEW, _ev.EV_VIEW_CONTENT, _ev.EV_CLICK, _ev.EV_CALL_CONNECTED):
            s["reach"] += 1
        if etype == _ev.EV_LEAD_SUBMITTED:
            s["leads"] += 1
        if etype in _QUALITY_RUNGS:
            s["conversions"] += 1
    for s in segs.values():
        denom = max(s["reach"], s["leads"], s["conversions"], 1)
        s["conv_rate"] = s["conversions"] / denom
    return segs


def discover_segments(events: list, seed_segments: list, *,
                      campaign_id: Optional[str] = None) -> dict:
    """Find converting segments OUTSIDE the seed. Returns {seed_conv_rate, candidates:[...]} where each
    candidate carries conv_rate + lift vs the seed, ranked best-first and capped at MAX_EXPANSION_SEGMENTS
    (the soft ceiling). A candidate must clear MIN_SEGMENT_CONVERSIONS and MIN_LIFT vs the seed."""
    seeds = {_norm(s) for s in (seed_segments or [])}
    segs = aggregate_segments(events, campaign_id=campaign_id)
    # Seed baseline conv-rate: the configured audience's own measured rate (floor to beat). If the seed
    # has no measured rate yet, fall back to the median of all observed segments (conservative).
    seed_rates = [s["conv_rate"] for k, s in segs.items() if k in seeds and (s["reach"] or s["leads"])]
    if seed_rates:
        seed_rate = sum(seed_rates) / len(seed_rates)
    else:
        rates = sorted(s["conv_rate"] for s in segs.values())
        seed_rate = rates[len(rates) // 2] if rates else 0.0
    candidates = []
    for key, s in segs.items():
        if key in seeds:
            continue
        if s["conversions"] < MIN_SEGMENT_CONVERSIONS:
            continue
        lift = (s["conv_rate"] / seed_rate) if seed_rate > 0 else (s["conv_rate"] and float("inf") or 0.0)
        if seed_rate > 0 and lift < MIN_LIFT:
            continue
        candidates.append({"segment": key, "conv_rate": s["conv_rate"], "conversions": s["conversions"],
                           "reach": s["reach"], "lift": (lift if lift != float("inf") else None)})
    # Best converters first; cap at the soft ceiling.
    candidates.sort(key=lambda c: (c["conv_rate"], c["conversions"]), reverse=True)
    candidates = candidates[:MAX_EXPANSION_SEGMENTS]
    return {"seed_conv_rate": seed_rate, "candidates": candidates}


def propose_expansion(discovery: dict, *, campaign_id: str = "",
                      budget_daily_minor: int = 0) -> list:
    """Turn discovered candidates into propose-only `audience_expand` moves. Each carries a BOUNDED
    `expand_budget_minor` (<= EXPANSION_BUDGET_SHARE of the daily budget — the soft ceiling) and is
    spend-INCREASING (sign +1), so guardrails forces draft -> approve before any spend. The seed audience
    is never removed (floor preserved)."""
    moves = []
    cap = int(int(budget_daily_minor or 0) * EXPANSION_BUDGET_SHARE)
    for c in (discovery or {}).get("candidates", []):
        moves.append({
            "plan_id": campaign_id, "campaign_id": campaign_id,
            "move": "audience_expand", "segment": c["segment"],
            "spend_delta_sign": +1,                 # new spend on a new segment => human-gated
            "spend_delta_minor": cap,               # bounded by the soft ceiling
            "expand_budget_minor": cap,
            "reason": (f"audience expansion: segment '{c['segment']}' converts at "
                       f"{c['conv_rate']:.1%}"
                       + (f" ({c['lift']:.1f}x the seed)" if c.get('lift') else "")
                       + f"; propose up to {cap} paise/day (soft ceiling, seed preserved)"),
            "candidate": c,
        })
    return moves


def build_state(campaign_id: str, seed_segments: list, discovery: dict, moves: list, *,
                now_ts: Optional[float] = None) -> dict:
    """A UI-facing audience_state row: the seed (floor), the discovered candidates, the proposals."""
    return {
        "campaign_id": campaign_id,
        "seed_segments": list(seed_segments or []),
        "seed_conv_rate": (discovery or {}).get("seed_conv_rate", 0.0),
        "candidates": (discovery or {}).get("candidates", []),
        "expansion_proposals": moves or [],
        "soft_ceiling": {"max_segments": MAX_EXPANSION_SEGMENTS,
                         "budget_share": EXPANSION_BUDGET_SHARE},
        "updated_ts": float(now_ts if now_ts is not None else time.time()),
    }


__all__ = ["aggregate_segments", "discover_segments", "propose_expansion", "build_state",
           "MAX_EXPANSION_SEGMENTS", "EXPANSION_BUDGET_SHARE"]
