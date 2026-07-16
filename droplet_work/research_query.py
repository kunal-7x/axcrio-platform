"""research_query — read-only, tenant-scoped ClickHouse analytics for Famit Research.

Mirrors obs_query.py: ALL queries are READ-ONLY (readonly=2 at the session level) and the
tenant is bound as a ClickHouse HTTP param ({tid:String}) on EVERY query — ClickHouse has no
row-level security, so this Python-side WHERE tenant_id = {tid:String} IS the tenant boundary
(the top security invariant: a missing filter would leak cross-tenant data to a super-admin).
Every function degrades to a clean {"error": ...} / demo payload and NEVER raises.

DEMO FALLBACK: when ClickHouse is absent/empty (the common pre-rollout state), we synthesise a
scientifically-consistent dataset by running the SAME real AffectTracker over scripted archetype
calls (voice_ops.research.demo) and stamp `demo: true` so the panel badges it. This guarantees the
premium dashboard is alive on day one instead of an all-zeros dead page — without ever faking a
real tenant's numbers (the demo set is clearly labelled and tenant-namespaced).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import httpx

TURNS = "famit_research_turns"
CALLS = "famit_research_calls"


def _read_url() -> str:
    return (os.getenv("FAMIT_RESEARCH_CLICKHOUSE_URL")
            or os.getenv("CLICKHOUSE_URL") or "").strip().rstrip("/")


def _clamp(v, lo, hi, default) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except Exception:  # noqa: BLE001
        return default


async def _ch(sql: str, params: Optional[dict] = None) -> dict:
    base = _read_url()
    if not base:
        return {"error": "metrics backend not configured", "rows": []}
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(base + "/", content=sql.encode("utf-8"),
                             params={**(params or {}), "default_format": "JSONEachRow",
                                     "readonly": "2", "max_execution_time": "30",
                                     "max_result_rows": "200000", "result_overflow_mode": "break"})
        if r.status_code != 200:
            return {"error": (r.text or "")[:300].strip(), "rows": []}
        import json
        rows = []
        for ln in r.text.splitlines():
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
        return {"rows": rows}
    except Exception:  # noqa: BLE001
        return {"error": "metrics backend unreachable", "rows": []}


# --------------------------------------------------------------------------- #
# Aggregation helpers (pure-Python over the fetched/demo rows).
# --------------------------------------------------------------------------- #
def _avg(xs: List[float], d=0.0) -> float:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else d


def _build_dashboard(calls: List[dict], *, demo: bool, minutes: int) -> dict:
    n = len(calls)
    # Outcome buckets + conversion rate use ONLY calls whose outcome is actually known. has_outcome=0
    # means "not resolved yet" — and it is persisted as converted=0, so counting it would silently
    # defame the 'lost' arm and deflate conversion. Demo rows have no has_outcome key → default 1.
    labelled = [c for c in calls if c.get("has_outcome", 1)]
    rn = len(labelled)
    converted = sum(1 for c in labelled if c.get("converted"))
    regime_counts: Dict[str, int] = {}
    for c in calls:
        regs = c.get("regimes")
        regs = regs.split(",") if isinstance(regs, str) else (regs or [])
        for r in regs:
            r = (r or "").strip()
            if r:
                regime_counts[r] = regime_counts.get(r, 0) + 1
    won = [c for c in labelled if c.get("converted")]
    lost = [c for c in labelled if not c.get("converted")]
    return {
        "demo": demo,
        "range": {"minutes": minutes},
        "summary": {
            "calls": n,
            "resolved": rn,
            "unknown_outcome": n - rn,
            "turns": sum(int(c.get("turns", 0) or 0) for c in calls),
            "avg_arousal": _avg([c.get("arousal_mean", 50) for c in calls], 50.0),
            "avg_friction": _avg([c.get("friction_mean", 50) for c in calls], 50.0),
            "peak_friction": round(max([c.get("friction_peak", 50) for c in calls], default=50.0), 1),
            "avg_engagement": _avg([c.get("engagement_mean", 50) for c in calls], 50.0),
            "avg_conversion_risk": _avg([c.get("conversion_risk", 0) for c in calls]),
            "intervened": sum(1 for c in calls if c.get("intervene")),
            "avg_speech_rate": _avg([c.get("speech_rate_sps", 0) for c in calls]),
            "confidence": _avg([c.get("confidence", 0) for c in calls]),
            "converted": converted,
            "conversion_rate": round(100.0 * converted / rn, 1) if rn else 0.0,
        },
        # closed-loop OUTCOMES LAB: does the friction/arousal trajectory SHAPE correlate with the
        # outcome? Honest, descriptive (effect sizes on real held-out calls, not an auto-mutator).
        "outcomes": {
            "won": {"n": len(won),
                    "avg_friction_peak": _avg([c.get("friction_peak", 50) for c in won], 50.0),
                    "avg_arousal_trend": _avg([c.get("arousal_trend", 0) for c in won]),
                    "avg_friction_trend": _avg([c.get("friction_trend", 0) for c in won])},
            "lost": {"n": len(lost),
                     "avg_friction_peak": _avg([c.get("friction_peak", 50) for c in lost], 50.0),
                     "avg_arousal_trend": _avg([c.get("arousal_trend", 0) for c in lost]),
                     "avg_friction_trend": _avg([c.get("friction_trend", 0) for c in lost])},
        },
        "regime_counts": regime_counts,
        "calls": sorted(calls, key=lambda c: c.get("ts", ""), reverse=True),
    }


# --------------------------------------------------------------------------- #
# Public API (tenant-scoped). demo_if_empty controls the fallback.
# --------------------------------------------------------------------------- #
async def dashboard(tenant_id: str, minutes: int = 1440, *, demo_if_empty: bool = True) -> dict:
    m = _clamp(minutes, 1, 43200, 1440)
    res = await _ch(
        f"SELECT call_id, toString(ts) AS ts, turns, duration_s, arousal_mean, arousal_peak, "
        f"friction_mean, friction_peak, arousal_trend, friction_trend, "
        f"engagement_mean, engagement_peak, engagement_trend, conversion_risk, intervene, top_intent, "
        f"speech_rate_sps, pause_ratio, confidence, source, regimes, outcome, converted, has_outcome, deal_value "
        f"FROM {CALLS} WHERE tenant_id = {{tid:String}} AND ts > now() - INTERVAL {m} MINUTE "
        f"ORDER BY ts DESC LIMIT 500",
        {"tid": tenant_id},
    )
    rows = res.get("rows") or []
    if not rows and demo_if_empty:
        return _demo_dashboard(tenant_id, minutes=m)
    return _build_dashboard(rows, demo=False, minutes=m)


async def call_detail(tenant_id: str, call_id: str, *, demo_if_empty: bool = True) -> dict:
    res = await _ch(
        f"SELECT turn_num, t_sec, toString(ts) AS ts, arousal, arousal_var, friction, friction_var, "
        f"engagement, engagement_var, conversion_risk, intervene, intent, llm_valence, objection, buying_intent, "
        f"talk_share, backchannel_rate, entrainment, ssl_arousal, "
        f"f0_mean_hz, f0_range_hz, f0_slope_hz_s, f0_var_hz, loudness_db, speech_rate_sps, pause_ratio, "
        f"turn_latency_ms, voiced_sec, valence_hint, confidence, source, regime, low_conf, transcript "
        f"FROM {TURNS} WHERE tenant_id = {{tid:String}} AND call_id = {{cid:String}} "
        f"ORDER BY turn_num ASC LIMIT 2000",
        {"tid": tenant_id, "cid": call_id},
    )
    rows = res.get("rows") or []
    if not rows and demo_if_empty:
        return _demo_call_detail(tenant_id, call_id)
    hdr = await _ch(
        f"SELECT * FROM {CALLS} WHERE tenant_id = {{tid:String}} AND call_id = {{cid:String}} LIMIT 1",
        {"tid": tenant_id, "cid": call_id},
    )
    return {"demo": False, "call": (hdr.get("rows") or [{}])[0], "turns": rows}


# --------------------------------------------------------------------------- #
# Demo builders — REAL filter output over scripted archetypes (voice_ops.research.demo).
# --------------------------------------------------------------------------- #
def _demo_dashboard(tenant_id: str, minutes: int) -> dict:
    try:
        from voice_ops.research.demo import demo_calls
        calls = []
        for _, summ in demo_calls(tenant_id):
            d = summ.to_dict()
            d["ts"] = ""           # demo headers sort by insertion order
            calls.append(d)
        out = _build_dashboard(calls, demo=True, minutes=minutes)
        # demo calls have no real ts → keep generation order (newest first by call_id suffix)
        out["calls"] = sorted(calls, key=lambda c: c.get("call_id", ""), reverse=True)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"demo": True, "error": f"demo unavailable: {exc}", "summary": {}, "calls": []}


def _demo_call_detail(tenant_id: str, call_id: str) -> dict:
    try:
        from voice_ops.research.demo import _DEMO_CALLS, synthetic_call
        arch = dict(_DEMO_CALLS).get(call_id, "objection_recovered")
        rows, summ = synthetic_call(tenant_id, call_id, arch)
        return {"demo": True, "call": summ.to_dict(),
                "turns": [r.to_row() for r in rows]}
    except Exception as exc:  # noqa: BLE001
        return {"demo": True, "error": f"demo unavailable: {exc}", "call": {}, "turns": []}
