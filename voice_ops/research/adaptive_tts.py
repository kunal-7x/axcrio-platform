"""voice_ops.research.adaptive_tts — close the loop: affect state → TTS prosody (Phase 4, Upgrade #7).

Turns Famit Research from a post-call DASHBOARD into an in-call BEHAVIOR. When friction rises /
engagement drops, nudge the agent's delivery — slower & steadier to de-escalate, a touch livelier to
re-engage — applied at the START of the next agent turn via tts.update_options (the cache-safe,
"takes effect next utterance" path proven for language switching; ~0 ms added IF the WS is pre-warmed).

HARD evidence-based constraint (Benus et al., Speech Prosody 2018): entrain INTENSITY/RATE — it RAISES
user trust — but NEVER entrain PITCH (it LOWERS trust). So we only ever touch speed + stability, never
pitch. Speed clamped to a safe [0.85, 1.15] band.

Gated by FAMIT_RESEARCH_ADAPTIVE_TTS (default OFF) with a kill-switch. The decision logic is pure +
unit-tested; the agent supplies the `update_options` callable so the live wiring stays one guarded step.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("research.adaptive_tts")

SPEED_MIN, SPEED_MAX = 0.85, 1.15


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _truthy(os.getenv("FAMIT_RESEARCH_ADAPTIVE_TTS", "0"))


def decide(regime: str, friction: float, engagement: float, conversion_risk: float) -> Optional[dict]:
    """Map the live affect state → {speed, stability, reason}, or None for "no change". NEVER pitch."""
    fr = float(friction or 50.0)
    eng = float(engagement or 50.0)
    risk = float(conversion_risk or 0.0)
    if risk >= 65 or regime == "rising_friction" or fr >= 64:
        return {"speed": 0.92, "stability": 0.78,
                "reason": "de-escalate: slower + steadier (rising friction / high risk)"}
    if regime == "disengaging" or eng <= 42:
        return {"speed": 1.06, "stability": 0.45,
                "reason": "re-engage: a touch livelier (engagement dropping)"}
    if regime in ("warming", "resolving"):
        return {"speed": 1.02, "stability": 0.55,
                "reason": "match positive momentum"}
    return None


def _clamp_speed(s: float) -> float:
    return max(SPEED_MIN, min(SPEED_MAX, float(s)))


@dataclass
class AdaptiveTtsController:
    """Stateful per-call controller. `step` decides + applies via the agent-supplied callable, skipping
    redundant updates (same-value no-op = cache-safe, mirrors the language-switch pattern)."""
    kill: bool = False
    _last: Optional[tuple] = None

    def step(self, state, apply_fn: Optional[Callable[[float, float], None]] = None) -> Optional[dict]:
        """state: an AffectState-like object (or dict) with regime/friction/engagement/conversion_risk.
        apply_fn(speed, stability): the agent's tts.update_options wrapper. Returns the decision (for
        logging/telemetry) or None. Never raises into the agent."""
        if self.kill or not enabled():
            return None
        try:
            g = (lambda k, d=0.0: getattr(state, k, d)) if not isinstance(state, dict) else (lambda k, d=0.0: state.get(k, d))
            d = decide(str(g("regime", "steady")), g("friction", 50.0), g("engagement", 50.0),
                       g("conversion_risk", 0.0) or 0.0)
            if d is None:
                return None
            speed = _clamp_speed(d["speed"])
            key = (round(speed, 2), round(d["stability"], 2))
            if key == self._last:                       # no-op when unchanged (cache-safe)
                return None
            self._last = key
            if apply_fn is not None:
                apply_fn(speed, float(d["stability"]))   # NEVER pass pitch
            logger.info("adaptive_tts → speed=%.2f stability=%.2f (%s)", speed, d["stability"], d["reason"])
            return {"speed": speed, "stability": d["stability"], "reason": d["reason"]}
        except Exception as exc:  # noqa: BLE001
            logger.warning("adaptive_tts step failed (no-op): %r", exc)
            return None
