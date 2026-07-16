"""voice_ops.research.demo — scientifically-consistent synthetic calls.

So the Famit Research dashboard is ALIVE and demonstrable before live telephony + ClickHouse
exist (and so `next dev` alone tells the whole story). These are NOT hard-coded chart numbers:
we script plausible per-turn PROSODY driver curves for a handful of call archetypes, then run
them through the SAME real AffectTracker the production pipeline uses. The arousal/friction
traces, uncertainty bands and regime flags you see are the genuine filter output — only the
input features are synthetic. Every row is stamped source='demo' so the UI labels it honestly.

Deterministic per call_id (seeded RNG) so the dashboard is stable across reloads.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from .affect_filter import AffectConfig, AffectTracker
from .conformal import ConformalTrigger
from .extractor import _apply_risk
from .outcome import OutcomeModel
from .schema import ResearchSummary, ResearchTurn

# archetype → (label, outcome, converted, deal_value, arousal keyframes, friction keyframes,
#              base prosody). Keyframes are (progress 0..1, z-drive) pairs, linearly interpolated.
_ARCHETYPES: Dict[str, Dict] = {
    "smooth_close": {
        "label": "Smooth close", "outcome": "hot", "converted": True, "deal": 85000,
        "arousal": [(0, -0.2), (0.4, 0.3), (1.0, 1.3)],
        "friction": [(0, -0.2), (1.0, -0.6)],
    },
    "objection_recovered": {
        "label": "Objection recovered → won", "outcome": "hot", "converted": True, "deal": 120000,
        "arousal": [(0, 0.0), (0.5, 1.3), (0.7, 0.7), (1.0, 0.9)],
        "friction": [(0, -0.1), (0.45, 0.1), (0.6, 1.9), (0.8, 0.5), (1.0, -0.4)],
    },
    "objection_lost": {
        "label": "Price objection → lost", "outcome": "warm", "converted": False, "deal": 0,
        "arousal": [(0, 0.1), (0.5, 1.1), (1.0, 0.5)],
        "friction": [(0, -0.1), (0.45, 0.1), (0.6, 1.5), (1.0, 2.6)],
    },
    "disengaged": {
        "label": "Disengaged → cold", "outcome": "cold", "converted": False, "deal": 0,
        "arousal": [(0, 0.4), (0.45, 0.3), (0.6, -0.6), (1.0, -2.2)],
        "friction": [(0, 0.0), (0.5, 0.2), (0.7, 1.0), (1.0, 1.6)],
    },
}

_BASE = {"f0": 168.0, "loudness": -26.0, "rate": 4.2, "pause": 0.18}


def _rng(seed: str) -> random.Random:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16)
    return random.Random(h)


def _interp(keys: List[Tuple[float, float]], p: float) -> float:
    if p <= keys[0][0]:
        return keys[0][1]
    if p >= keys[-1][0]:
        return keys[-1][1]
    for (x0, y0), (x1, y1) in zip(keys, keys[1:]):
        if x0 <= p <= x1:
            f = (p - x0) / (x1 - x0) if x1 > x0 else 0.0
            return y0 + f * (y1 - y0)
    return keys[-1][1]


def synthetic_call(
    tenant_id: str, call_id: str, archetype: str = "objection_recovered",
    *, turns: int = 0, started_iso: str = "",
) -> Tuple[List[ResearchTurn], ResearchSummary]:
    spec = _ARCHETYPES.get(archetype, _ARCHETYPES["objection_recovered"])
    rng = _rng(call_id + archetype)
    n = turns or rng.randint(9, 15)
    base = datetime.fromisoformat(started_iso.replace("Z", "+00:00")) if started_iso else datetime.now(timezone.utc)
    tracker = AffectTracker(AffectConfig())
    rows: List[ResearchTurn] = []
    t_cursor = 0.0
    for i in range(n):
        p = i / max(n - 1, 1)
        a_drive = _interp(spec["arousal"], p) + rng.gauss(0, 0.12)
        f_drive = _interp(spec["friction"], p) + rng.gauss(0, 0.12)
        e_drive = -0.55 * f_drive + 0.30 * a_drive + rng.gauss(0, 0.1)   # engaged when warming, not frictional
        latency_ms = round(max(180, 520 + 320 * f_drive - 80 * e_drive + rng.gauss(0, 80)), 1)
        # map drivers → plausible telephone-band prosody + the multimodal channels (LLM friction,
        # dynamics engagement) the real pipeline feeds — z-scored internally by the tracker.
        feats = {
            "f0_mean_hz": _BASE["f0"] + 22.0 * a_drive + rng.gauss(0, 4),
            "loudness_db": _BASE["loudness"] + 4.0 * a_drive + rng.gauss(0, 0.8),
            "speech_rate_sps": max(1.5, _BASE["rate"] + 0.9 * a_drive - 0.55 * f_drive + rng.gauss(0, 0.2)),
            "pause_ratio": min(0.85, max(0.02, _BASE["pause"] + 0.12 * f_drive + rng.gauss(0, 0.02))),
            "valence_hint": max(-1, min(1, -0.45 * f_drive + 0.2 * a_drive + rng.gauss(0, 0.1))),
            "confidence": round(min(0.88, max(0.45, 0.72 + rng.gauss(0, 0.06))), 3),
            "llm_friction_z": round(max(-4, min(4, f_drive * 1.55 + rng.gauss(0, 0.15))), 3),
            "llm_conf": 0.7,
            "engagement_obs": round(e_drive, 3), "engagement_conf": 0.7,
        }
        st = tracker.update(feats)
        intent = ("price-resistant" if f_drive > 1.1 else "objecting" if f_drive > 0.6
                  else "hesitant" if f_drive > 0.25 else "interested" if a_drive > 0.4 and f_drive < 0 else "neutral")
        buy = round(max(0.0, min(1.0, -0.4 * f_drive + 0.35 * a_drive + 0.1)), 3)
        dur = max(1.2, 3.4 + rng.gauss(0, 1.0))
        ts = base + timedelta(seconds=t_cursor)
        rows.append(ResearchTurn(
            tenant_id=tenant_id, call_id=call_id, turn_num=i + 1,
            ts_iso=ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", t_sec=round(t_cursor, 1),
            f0_mean_hz=round(feats["f0_mean_hz"], 1),
            f0_range_hz=round(28 + 14 * abs(a_drive) + rng.uniform(0, 8), 1),
            f0_slope_hz_s=round(8 * a_drive + rng.gauss(0, 3), 2),
            f0_var_hz=round(12 + 6 * abs(a_drive), 1),
            loudness_db=round(feats["loudness_db"], 2),
            speech_rate_sps=round(feats["speech_rate_sps"], 2),
            pause_ratio=round(feats["pause_ratio"], 3),
            turn_latency_ms=latency_ms,
            voiced_sec=round(dur * (1 - feats["pause_ratio"]), 2),
            arousal=st.arousal, arousal_var=st.arousal_var,
            friction=st.friction, friction_var=st.friction_var,
            engagement=st.engagement, engagement_var=st.engagement_var,
            valence_hint=round(feats["valence_hint"], 3),
            llm_valence=round(max(-1, min(1, buy - 0.5 * max(0, f_drive))), 3), intent=intent,
            objection=round(max(0, min(1, f_drive * 0.5)), 3), buying_intent=buy,
            talk_share=round(max(0.2, min(0.75, 0.5 - 0.06 * f_drive + rng.gauss(0, 0.04))), 3),
            backchannel_rate=round(max(0.0, min(1.0, 0.25 + 0.12 * e_drive)), 3),
            entrainment=round(max(0.0, min(1.0, 0.6 + 0.15 * e_drive + rng.gauss(0, 0.05))), 3),
            confidence=st.confidence, source="demo", regime=st.regime,
            low_conf=True,
            transcript=_DEMO_LINES.get(archetype, _DEMO_LINES["objection_recovered"])[i % 6],
        ))
        t_cursor += dur
    _apply_risk(rows, OutcomeModel(), ConformalTrigger())
    summ = ResearchSummary(
        tenant_id=tenant_id, call_id=call_id,
        started_iso=started_iso or (rows[0].ts_iso if rows else ""),
        turns=len(rows), duration_s=round(t_cursor, 1),
        arousal_mean=round(sum(r.arousal for r in rows) / len(rows), 1),
        arousal_peak=round(max(r.arousal for r in rows), 1),
        friction_mean=round(sum(r.friction for r in rows) / len(rows), 1),
        friction_peak=round(max(r.friction for r in rows), 1),
        arousal_trend=round(rows[-1].arousal - rows[0].arousal, 1),
        friction_trend=round(rows[-1].friction - rows[0].friction, 1),
        engagement_mean=round(sum(r.engagement for r in rows) / len(rows), 1),
        engagement_peak=round(max(r.engagement for r in rows), 1),
        engagement_trend=round(rows[-1].engagement - rows[0].engagement, 1),
        conversion_risk=round(rows[-1].conversion_risk or 0.0, 1),
        intervene=any(r.intervene for r in rows),
        top_intent=Counter(r.intent for r in rows if r.intent).most_common(1)[0][0] if any(r.intent for r in rows) else "",
        f0_mean_hz=round(sum(r.f0_mean_hz for r in rows) / len(rows), 1),
        speech_rate_sps=round(sum(r.speech_rate_sps for r in rows) / len(rows), 2),
        pause_ratio=round(sum(r.pause_ratio for r in rows) / len(rows), 3),
        confidence=round(sum(r.confidence for r in rows) / len(rows), 3),
        source="demo",
        regimes=[r for i, r in enumerate([x.regime for x in rows]) if r != "steady"
                 and (i == 0 or [x.regime for x in rows][i - 1] != r)],
        outcome=spec["outcome"], converted=spec["converted"], deal_value=float(spec["deal"]),
    )
    return rows, summ


_DEMO_LINES = {
    "smooth_close": ["Haan ji, tell me", "Okay that sounds good", "Yes I'm interested",
                     "What's the price?", "Theek hai, sounds fair", "Let's do it"],
    "objection_recovered": ["Hello, who is this?", "Hmm, go on", "That's quite expensive",
                            "I'm not sure about the cost", "Oh, the EMI helps actually", "Okay, let's proceed"],
    "objection_lost": ["Yes?", "It's too costly for me", "No, that's way over budget",
                       "I said it's expensive", "Maybe later", "Not now, thanks"],
    "disengaged": ["Hi", "Mm-hmm", "I'm a bit busy", "...okay", "Can you call later",
                   "I have to go"],
}

_DEMO_CALLS = [
    ("demo-call-7741", "objection_recovered"), ("demo-call-7740", "smooth_close"),
    ("demo-call-7739", "objection_lost"), ("demo-call-7738", "disengaged"),
    ("demo-call-7737", "objection_recovered"), ("demo-call-7736", "smooth_close"),
    ("demo-call-7735", "disengaged"), ("demo-call-7734", "objection_lost"),
]


def demo_calls(tenant_id: str = "demo") -> List[Tuple[List[ResearchTurn], ResearchSummary]]:
    base = datetime.now(timezone.utc) - timedelta(hours=6)
    out = []
    for i, (cid, arch) in enumerate(_DEMO_CALLS):
        started = (base + timedelta(minutes=37 * i)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        out.append(synthetic_call(tenant_id, cid, arch, started_iso=started))
    return out


def archetype_label(name: str) -> str:
    return _ARCHETYPES.get(name, {}).get("label", name)
