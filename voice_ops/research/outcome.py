"""voice_ops.research.outcome — sequence-to-outcome conversion-risk head (Phase 2, Upgrade #4).

Replaces the brittle `arousal_trend = last - first` rollup with a PREDICTIVE, calibrated per-turn
conversion-RISK CURVE over the full affect/dynamics/intent trajectory — so the dashboard shows when
risk spiked, whether it recovered, and a measurable-AUC score on YOUR calls (not a descriptive delta).

Honest framing (kept everywhere): this is PREDICTIVE / descriptive, contaminated by confounding and
selection bias — NOT a causal claim. It is a discrete-time hazard: at each turn we score the risk of
a non-conversion outcome from the trajectory SO FAR (cumulative features), giving a monotone-ish risk
curve. A transparent logistic over engineered trajectory features ships with documented DEFAULT WEIGHTS
(works cold, no training data) and an optional `.fit()` that learns from the converted/lost labels we
already store in ResearchSummary. Inference is pure-Python (runs in the realtime worker, no numpy).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


# Documented default logit weights (sign-sensible, hand-set so risk works with ZERO training data).
# Feature scale notes keep each term ~O(1). Risk = P(non-conversion).
_DEFAULT_W: Dict[str, float] = {
    "bias": -0.4,
    "friction_peak": 0.9,      # (friction_peak_so_far - 50)/15
    "friction_now": 0.5,       # (friction_now - 50)/15
    "friction_trend": 0.6,     # friction_trend / 6
    "objection_density": 1.1,  # share of turns flagged objecting/price-resistant
    "latency": 0.4,            # mean response latency, normalised /1500ms, capped
    "engagement": -0.8,        # (engagement_now - 50)/15
    "buying_intent": -1.0,     # max buying_intent seen so far, 0..1
    "arousal_warm": -0.3,      # arousal_trend / 6 (warming reduces risk a little)
}


@dataclass
class OutcomeModel:
    weights: Dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_W))

    # -- cumulative trajectory features up to turn t (a ResearchTurn-like dict list) ----- #
    @staticmethod
    def _features(turns: List[dict], t: int) -> Dict[str, float]:
        seq = turns[: t + 1]
        fr = [float(x.get("friction", 50) or 50) for x in seq]
        ar = [float(x.get("arousal", 50) or 50) for x in seq]
        eng = [float(x.get("engagement", 50) or 50) for x in seq]
        lat = [float(x.get("turn_latency_ms", 0) or 0) for x in seq]
        intents = [(x.get("intent") or "") for x in seq]
        obj_n = sum(1 for s in intents if s in ("objecting", "price-resistant", "annoyed", "hesitant"))
        buy = [float(x.get("buying_intent") or 0) for x in seq if x.get("buying_intent") is not None]
        fr_trend = (fr[-1] - fr[0]) if len(fr) > 1 else 0.0
        ar_trend = (ar[-1] - ar[0]) if len(ar) > 1 else 0.0
        return {
            "friction_peak": (max(fr) - 50.0) / 15.0,
            "friction_now": (fr[-1] - 50.0) / 15.0,
            "friction_trend": fr_trend / 6.0,
            "objection_density": obj_n / max(1, len(seq)),
            "latency": min(2.0, (sum(lat) / max(1, len(lat))) / 1500.0),
            "engagement": (eng[-1] - 50.0) / 15.0,
            "buying_intent": max(buy) if buy else 0.0,
            "arousal_warm": ar_trend / 6.0,
        }

    def _score(self, feats: Dict[str, float]) -> float:
        z = self.weights.get("bias", 0.0) + sum(self.weights.get(k, 0.0) * v for k, v in feats.items())
        return _sigmoid(z)

    def risk_curve(self, turns: List[dict]) -> List[float]:
        """Per-turn conversion-risk in 0..100 (cumulative through each turn)."""
        return [round(100.0 * self._score(self._features(turns, t)), 1) for t in range(len(turns))]

    def final_risk(self, turns: List[dict]) -> float:
        c = self.risk_curve(turns)
        return c[-1] if c else 0.0

    # -- optional offline fit on real labels (numpy if available; else pure-Python GD) --- #
    def fit(self, calls: List[tuple], *, epochs: int = 300, lr: float = 0.1, l2: float = 1e-3) -> "OutcomeModel":
        """calls: list of (turns:list[dict], converted:bool). Trains on the LAST-turn features
        (call-level non-conversion label). Best-effort: returns self unchanged on any failure."""
        try:
            X, y = [], []
            keys = [k for k in _DEFAULT_W if k != "bias"]
            for turns, conv in calls:
                if not turns:
                    continue
                f = self._features(turns, len(turns) - 1)
                X.append([f[k] for k in keys])
                y.append(0.0 if conv else 1.0)        # label = non-conversion (risk)
            if len(X) < 8:
                return self                            # too little data → keep defaults
            w = [self.weights.get(k, 0.0) for k in keys]
            b = self.weights.get("bias", 0.0)
            n = len(X)
            for _ in range(epochs):
                gb = 0.0
                gw = [0.0] * len(keys)
                for xi, yi in zip(X, y):
                    p = _sigmoid(b + sum(w[j] * xi[j] for j in range(len(keys))))
                    e = p - yi
                    gb += e
                    for j in range(len(keys)):
                        gw[j] += e * xi[j]
                b -= lr * gb / n
                for j in range(len(keys)):
                    w[j] -= lr * (gw[j] / n + l2 * w[j])
            self.weights = {"bias": b, **{keys[j]: w[j] for j in range(len(keys))}}
        except Exception:  # noqa: BLE001
            pass
        return self
