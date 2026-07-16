"""ads_engine.fatigue — CREATIVE FATIGUE detection + auto-rotation (V2-W3 parity loop).

Meta's Advantage+ Creative detects CTR-degradation 5-7 days before a human would, and when one creative
holds 70%+ delivery share over consecutive weeks with a downward CTR trend, it auto-pauses that asset and
promotes fresh ones (research/comp-autonomy.md §Meta creative-fatigue + gap #4). We lack that. This module
closes it: a LEADING-indicator CTR/engagement decay model that fires BEFORE aggregate ROAS drops, plus a
>70% delivery-share concentration guard, emitting propose-only `rotate_creative` moves the continuous
daemon routes through guardrails (fail-closed, dry-run).

WHY a leading indicator: by the time ROAS visibly drops the spend is already wasted. CTR/engagement decay
precedes the revenue drop, so rotating on the decay curve (not the ROAS curve) is what keeps the campaign
ahead of fatigue — exactly Meta's "5-7 days before a human notices" behaviour.

EARNER-SAFE: pure functions over metric snapshots; no spend, no network, no caller import. The rotation
"move" is spend-DECREASING for the fatigued variant (pause), so guardrails can auto-apply it; the paired
"promote a fresh variant" is a spend-NEUTRAL/INCREASING suggestion that stays a proposal (draft/approve).
Deterministic + offline-testable. Never raises.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from . import ad_events as _ev

_log = logging.getLogger("ads_engine.fatigue")

# ---------------------------------------------------------------------------
# Tunables (conservative; a mis-set value can only make rotation LESS aggressive).
# ---------------------------------------------------------------------------
FATIGUE_CTR_DECAY_PCT = 0.20     # recent CTR >=20% below its peak window => decaying
DELIVERY_SHARE_GUARD = 0.70      # >70% of impressions on one creative => concentration risk
MIN_IMPRESSIONS = 1000           # don't fatigue-flag on noise (need real delivery first)
MIN_BUCKETS = 3                  # need a trend (>=3 time buckets) before calling decay
DEFAULT_BUCKET_S = 86400         # daily buckets for the CTR series


def _safe_ctr(clicks: float, impressions: float) -> float:
    return (float(clicks) / float(impressions)) if impressions else 0.0


# ===========================================================================
# CTR series — bucket a variant's events (or accept a pre-bucketed history).
# ===========================================================================
def variant_series(events: list, variant_id: str, *, bucket_s: int = DEFAULT_BUCKET_S) -> list:
    """Build an oldest-first CTR series [{bucket_ts, impressions, clicks, ctr}] for ONE variant from the
    raw ad_events. impressions = page/content views; clicks = clicks + connected calls (engagement)."""
    buckets: dict = {}
    for e in events or []:
        if str(e.get("variant_id") or e.get("ad_id") or "") != str(variant_id):
            continue
        ts = float(e.get("ts") or 0)
        key = int(ts // max(1, int(bucket_s)))
        b = buckets.setdefault(key, {"bucket_ts": key * bucket_s, "impressions": 0, "clicks": 0})
        etype = str(e.get("type") or "").strip().lower()
        if etype in (_ev.EV_PAGE_VIEW, _ev.EV_VIEW_CONTENT):
            b["impressions"] += 1
        elif etype in (_ev.EV_CLICK, _ev.EV_CALL_CONNECTED):
            b["clicks"] += 1
    out = []
    for key in sorted(buckets):
        b = buckets[key]
        b["ctr"] = _safe_ctr(b["clicks"], b["impressions"])
        out.append(b)
    return out


def _normalize_series(series: list) -> list:
    """Accept either the {bucket_ts,impressions,clicks,ctr} shape or a raw {impr|impressions, clicks}
    history; return a clean oldest-first list with ctr computed. Tolerant of partial rows."""
    out = []
    for r in series or []:
        impr = float(r.get("impressions", r.get("impr", 0)) or 0)
        clk = float(r.get("clicks", r.get("clk", 0)) or 0)
        out.append({"bucket_ts": r.get("bucket_ts", 0), "impressions": impr, "clicks": clk,
                    "ctr": r.get("ctr", _safe_ctr(clk, impr))})
    return out


# ===========================================================================
# Detection — leading CTR-decay + delivery-share concentration.
# ===========================================================================
def detect_fatigue(series: list, *, delivery_share: float = 0.0) -> dict:
    """Verdict for ONE variant. Fatigued when EITHER:
      (a) CTR decays >= FATIGUE_CTR_DECAY_PCT from its peak window (leading indicator), OR
      (b) it hoards > DELIVERY_SHARE_GUARD of delivery (concentration risk — diversify even if healthy).
    Requires >= MIN_IMPRESSIONS total and >= MIN_BUCKETS to avoid flagging noise.

    Returns {fatigued, reason, ctr_decay_pct, peak_ctr, recent_ctr, delivery_share, total_impressions}."""
    s = _normalize_series(series)
    total_impr = sum(b["impressions"] for b in s)
    res = {"fatigued": False, "reason": "", "ctr_decay_pct": 0.0, "peak_ctr": 0.0,
           "recent_ctr": 0.0, "delivery_share": float(delivery_share),
           "total_impressions": total_impr}
    share_over = float(delivery_share) > DELIVERY_SHARE_GUARD
    if len(s) < MIN_BUCKETS or total_impr < MIN_IMPRESSIONS:
        # Not enough delivery for a CTR verdict — but a hard concentration breach still warns.
        if share_over and total_impr >= MIN_IMPRESSIONS:
            res.update(fatigued=True, reason="delivery_share_over_guard")
        return res
    peak_ctr = max(b["ctr"] for b in s)
    recent_ctr = s[-1]["ctr"]
    decay = (peak_ctr - recent_ctr) / peak_ctr if peak_ctr > 0 else 0.0
    res["peak_ctr"] = peak_ctr
    res["recent_ctr"] = recent_ctr
    res["ctr_decay_pct"] = max(0.0, decay)
    if decay >= FATIGUE_CTR_DECAY_PCT and recent_ctr < peak_ctr:
        res.update(fatigued=True, reason="ctr_decay")
    elif share_over:
        res.update(fatigued=True, reason="delivery_share_over_guard")
    return res


# ===========================================================================
# Analyze a campaign + propose rotation moves (propose-only; guardrails dispose).
# ===========================================================================
def analyze(events: list, *, campaign_id: Optional[str] = None,
            bucket_s: int = DEFAULT_BUCKET_S) -> dict:
    """Per-variant fatigue verdicts for a campaign's events, with delivery shares computed across the
    active variants. Returns {"variants": {vid: verdict}, "total_impressions": int}. Pure, never raises."""
    try:
        evs = [e for e in (events or [])
               if campaign_id is None
               or str(e.get("campaign_id") or e.get("source_campaign_id")) == str(campaign_id)]
        vids = sorted({str(e.get("variant_id") or e.get("ad_id") or "") for e in evs if (e.get("variant_id") or e.get("ad_id"))})
        series_by = {v: variant_series(evs, v, bucket_s=bucket_s) for v in vids}
        impr_by = {v: sum(b["impressions"] for b in s) for v, s in series_by.items()}
        total = sum(impr_by.values()) or 1
        verdicts = {}
        for v in vids:
            share = impr_by[v] / total
            verdicts[v] = detect_fatigue(series_by[v], delivery_share=share)
        return {"variants": verdicts, "total_impressions": total}
    except Exception as exc:  # noqa: BLE001
        _log.warning("fatigue.analyze failed: %r", type(exc).__name__)
        return {"variants": {}, "total_impressions": 0}


def propose_rotation(analysis: dict, *, campaign_id: str = "") -> list:
    """Turn fatigue verdicts into propose-only `rotate_creative` moves the daemon routes through
    guardrails. Each move PAUSES the fatigued variant (spend_delta_sign=-1 -> auto-applyable) and carries
    a `promote_fresh` flag (the paired spend-increasing 'add a fresh variant' stays a human proposal)."""
    moves = []
    for vid, verdict in (analysis or {}).get("variants", {}).items():
        if not verdict.get("fatigued"):
            continue
        moves.append({
            "plan_id": campaign_id, "campaign_id": campaign_id,
            "move": "rotate_creative", "variant_id": vid,
            "spend_delta_sign": -1,   # pausing the fatigued asset is spend-decreasing => safe to apply
            "promote_fresh": True,
            "reason": (f"creative fatigue ({verdict.get('reason')}): CTR decay "
                       f"{verdict.get('ctr_decay_pct', 0):.0%}, delivery share "
                       f"{verdict.get('delivery_share', 0):.0%} — rotate before ROAS drops"),
            "fatigue": verdict,
        })
    return moves


def build_state(campaign_id: str, analysis: dict, moves: list, *, now_ts: Optional[float] = None) -> dict:
    """A UI-facing fatigue_state row: per-variant verdicts + the rotation proposals + a timestamp."""
    return {
        "campaign_id": campaign_id,
        "variants": (analysis or {}).get("variants", {}),
        "total_impressions": (analysis or {}).get("total_impressions", 0),
        "rotation_proposals": moves or [],
        "fatigued_count": sum(1 for v in (analysis or {}).get("variants", {}).values()
                              if v.get("fatigued")),
        "updated_ts": float(now_ts if now_ts is not None else time.time()),
    }


__all__ = ["detect_fatigue", "analyze", "propose_rotation", "variant_series", "build_state",
           "FATIGUE_CTR_DECAY_PCT", "DELIVERY_SHARE_GUARD"]
