"""grow.optimizer — the Draft / Trash / Promote brain (GROWTH-OS §12).

The platforms (Advantage+/PMax) already do targeting + bidding ML — we don't rebuild that.
Our edge is deciding *which creative to risk, when to kill it, and when to scale it* against
the TRUTH signal (qualified leads, value-weighted), with a plain-language "why" for every
move (trust is the adoption bottleneck for autonomous spend). Reward = qualified leads;
posterior = Gamma–Poisson on the qualified-lead rate per ₹ (conjugate, cheap, interpretable).

Guardrails fire FIRST (G1–G6), statistics second. Every decision emits an Explanation
(what / evidence / expected effect / confidence / reversible / undo). Pure, deterministic,
offline-testable (uses math.erf for the posterior tail, no RNG). Live "execute" is an
injected connector seam (founder-gated on Ads OAuth)."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("grow.optimizer")


@dataclass
class Arm:
    """A creative × audience-cell × destination (an ad). Stats from the 4h insights snapshot
    joined with our qualified-lead truth."""
    id: str
    name: str = ""
    spend_minor: int = 0
    qualified_leads: int = 0
    leads: int = 0
    junk_leads: int = 0
    impressions: int = 0
    clicks: int = 0
    days_running: int = 0
    frequency_7d: float = 0.0
    ctr_now: float = 0.0
    ctr_peak_7d: float = 0.0
    ctr_declining_days: int = 0
    delivery_error: bool = False

    @property
    def spend_rupees(self) -> float:
        return self.spend_minor / 100.0

    @property
    def cpql_minor(self) -> int:
        """Cost per qualified lead (minor units). 0 qualified -> 0 sentinel (= infinite)."""
        return int(self.spend_minor / self.qualified_leads) if self.qualified_leads else 0


@dataclass
class Explanation:
    summary_en: str
    evidence: list = field(default_factory=list)     # [{metric,value}]
    expected_effect: str = ""
    confidence: str = "medium"                       # high | medium | low
    reversible: bool = True
    undo_plan: str = ""

    def public(self) -> dict:
        return {"summary_en": self.summary_en, "evidence": list(self.evidence),
                "expected_effect": self.expected_effect, "confidence": self.confidence,
                "reversible": self.reversible, "undo_plan": self.undo_plan}


@dataclass
class Decision:
    arm_id: str
    decision: str                # pause_now | trash | pause_adset | promote | rotate | quarantine | hold
    rule: str                    # G1..G6 | promote | hold
    scope: str = "ad"            # ad | adset
    explanation: Optional[Explanation] = None

    def public(self) -> dict:
        return {"arm_id": self.arm_id, "decision": self.decision, "rule": self.rule,
                "scope": self.scope,
                "explanation": self.explanation.public() if self.explanation else None}


class Optimizer:
    """Construct once. `evaluate(arm, target_cpql_minor, daily_share_minor)` -> Decision;
    `allocate(arms, target)` -> {arm_id: budget_share}."""

    # promote/kill constants (GROWTH-OS §12.3-12.4)
    G2_ZEROQ_X = 2.5             # spend ≥ 2.5× target & q=0 -> trash
    G3_SETFAIL_X = 4.0          # spend ≥ 4× target & P(cpql>target)>0.85 -> pause adset
    G3_PROB = 0.85
    G4_JUNK_MIN_LEADS = 8
    G4_JUNK_RATE = 0.60
    G5_FREQ = 2.5
    G5_CTR_DROP = 0.7           # ctr ≤ 0.7× peak ...
    G5_CTR_DAYS = 3             # ... for 3 consecutive days
    G1_RUNAWAY_X = 3.0
    PROMOTE_MIN_Q = 5
    PROMOTE_CPQL_X = 0.8        # cpql ≤ 0.8× target
    PROMOTE_MIN_DAYS = 3
    SCALE_STEP = 0.20           # +20% per 48-72h
    MIN_EXPLORE = 0.10          # always keep exploring
    MAX_ARM = 0.40              # never all-in on one arm

    # Gamma prior on qualified-rate per ₹ (prior mean = 1/beta0 -> cpql ≈ ₹beta0)
    ALPHA0 = 1.0
    BETA0 = 2000.0

    # ----------------------------------------------------- posterior #
    def posterior(self, arm: Arm) -> "tuple[float, float]":
        return self.ALPHA0 + arm.qualified_leads, self.BETA0 + arm.spend_rupees

    def p_cpql_exceeds_target(self, arm: Arm, target_cpql_minor: int) -> float:
        """P(CPqL > target | posterior) = P(rate < 1/target_rupees). Normal approx of the
        Gamma posterior (math.erf), deterministic — no RNG."""
        target_rupees = target_cpql_minor / 100.0
        if target_rupees <= 0:
            return 0.0
        a, b = self.posterior(arm)
        mean = a / b
        sd = math.sqrt(a) / b or 1e-9
        target_rate = 1.0 / target_rupees
        z = (target_rate - mean) / sd
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    # ----------------------------------------------------- evaluate #
    def evaluate(self, arm: Arm, target_cpql_minor: int, *, daily_share_minor: int = 0) -> Decision:
        try:
            return self._evaluate(arm, target_cpql_minor, daily_share_minor)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.optimizer.evaluate failed (-> hold): %r", exc)
            return Decision(arm.id, "hold", "error",
                            explanation=Explanation(f"evaluation error: {exc!r}"[:160],
                                                    confidence="low"))

    def _evaluate(self, arm: Arm, target: int, daily_share: int) -> Decision:
        t_rupees = target / 100.0

        # G6 policy first (a rejected/erroring ad can't be judged on stats)
        if arm.delivery_error:
            return self._d(arm, "quarantine", "G6", "ad",
                           "Delivery error / policy rejection — quarantined for compliance review.",
                           [{"metric": "delivery_error", "value": True}],
                           "creative held; compliance ticket opened", undo="re-submit after fix")

        # G1 runaway (any time, even in learning)
        if daily_share and arm.spend_today_runaway(daily_share):
            return self._d(arm, "pause_now", "G1", "ad",
                           f"Runaway spend: ₹{arm.spend_rupees:,.0f} today is past 3× the daily share.",
                           [{"metric": "spend", "value": arm.spend_minor}],
                           "paused immediately; budget protected", undo="resume from approval inbox",
                           conf="high")

        # G2 zero-qualified
        if arm.qualified_leads == 0 and arm.spend_minor >= self.G2_ZEROQ_X * target and target > 0:
            return self._d(arm, "trash", "G2", "ad",
                           f"Paused '{arm.name or arm.id}': spent ₹{arm.spend_rupees:,.0f} "
                           f"({arm.spend_minor / max(1, target):.1f}× your ₹{t_rupees:,.0f} target per "
                           f"qualified lead) with 0 qualified leads.",
                           [{"metric": "spend", "value": arm.spend_minor},
                            {"metric": "qualified_leads", "value": 0}],
                           "budget reallocated to a winning arm", undo="unpause the ad",
                           conf="high")

        # G3 ad-set failing (statistical)
        if arm.spend_minor >= self.G3_SETFAIL_X * target and target > 0:
            p = self.p_cpql_exceeds_target(arm, target)
            if p > self.G3_PROB:
                return self._d(arm, "pause_adset", "G3", "adset",
                               f"Ad set very likely above target ({p * 100:.0f}% confident CPqL > "
                               f"₹{t_rupees:,.0f}) after ₹{arm.spend_rupees:,.0f}.",
                               [{"metric": "P(cpql>target)", "value": round(p, 3)},
                                {"metric": "spend", "value": arm.spend_minor}],
                               "ad set paused; budget freed", undo="resume the ad set", conf="high")

        # G4 junk trap (cheap leads ≠ good leads)
        if arm.leads >= self.G4_JUNK_MIN_LEADS and arm.leads:
            junk_rate = arm.junk_leads / arm.leads
            if junk_rate > self.G4_JUNK_RATE:
                return self._d(arm, "trash", "G4", "ad",
                               f"Lead-quality trap: {junk_rate * 100:.0f}% of {arm.leads} leads scored "
                               f"junk — cheap leads, no real buyers.",
                               [{"metric": "junk_rate", "value": round(junk_rate, 2)},
                                {"metric": "leads", "value": arm.leads}],
                               "stop scaling junk; reallocate", undo="unpause the ad", conf="high")

        # G5 fatigue
        if arm.frequency_7d > self.G5_FREQ or (
                arm.ctr_peak_7d > 0 and arm.ctr_now <= self.G5_CTR_DROP * arm.ctr_peak_7d
                and arm.ctr_declining_days >= self.G5_CTR_DAYS):
            return self._d(arm, "rotate", "G5", "ad",
                           f"Creative fatigue (frequency {arm.frequency_7d:.1f} / CTR sliding) — "
                           "rotate in fresh siblings, retire this ad.",
                           [{"metric": "frequency_7d", "value": round(arm.frequency_7d, 2)},
                            {"metric": "ctr_now", "value": arm.ctr_now}],
                           "request 3 DNA-sibling creatives", undo="keep ad live", conf="medium")

        # PROMOTE (scale a proven winner)
        if (arm.qualified_leads >= self.PROMOTE_MIN_Q and target > 0
                and arm.cpql_minor and arm.cpql_minor <= self.PROMOTE_CPQL_X * target
                and arm.days_running >= self.PROMOTE_MIN_DAYS):
            return self._d(arm, "promote", "promote", "ad",
                           f"Scaling '{arm.name or arm.id}' +20%: {arm.qualified_leads} qualified at "
                           f"₹{arm.cpql_minor / 100:,.0f} CPqL (under your ₹{t_rupees:,.0f} target), "
                           f"stable {arm.days_running} days.",
                           [{"metric": "qualified_leads", "value": arm.qualified_leads},
                            {"metric": "cpql_minor", "value": arm.cpql_minor}],
                           "budget +20% over 48-72h while marginal CPqL holds",
                           undo="revert budget", conf="high")

        return self._d(arm, "hold", "hold", "ad",
                       "Holding — not enough signal to act yet.",
                       [{"metric": "spend", "value": arm.spend_minor},
                        {"metric": "qualified_leads", "value": arm.qualified_leads}],
                       "keep gathering data", undo="", conf="low")

    # ----------------------------------------------------- allocate #
    def allocate(self, arms: list, target_cpql_minor: int) -> dict:
        """Budget split across arms = posterior-mean-proportional (a deterministic Thompson
        proxy), bounded by min_explore (always exploring) and max_arm (never all-in).
        Production swaps in posterior SAMPLING; the bounds + interface are identical."""
        live = [a for a in arms if not a.delivery_error]
        if not live:
            return {}
        means = {a.id: (self.posterior(a)[0] / self.posterior(a)[1]) for a in live}
        total = sum(means.values()) or 1.0
        raw = {aid: m / total for aid, m in means.items()}
        # clamp to [min_explore, max_arm] then renormalize
        n = len(live)
        floor = self.MIN_EXPLORE if n > 1 else 0.0
        clamped = {aid: max(floor, min(self.MAX_ARM, sh)) for aid, sh in raw.items()}
        s = sum(clamped.values()) or 1.0
        return {aid: round(sh / s, 4) for aid, sh in clamped.items()}

    # ----------------------------------------------------- helper #
    def _d(self, arm: Arm, decision: str, rule: str, scope: str, summary: str,
           evidence: list, effect: str, undo: str = "", conf: str = "medium") -> Decision:
        return Decision(arm.id, decision, rule, scope,
                        Explanation(summary, evidence, effect, conf, True, undo))


# small helper bolted onto Arm for the G1 check (kept here to avoid widening the dataclass API)
def _spend_today_runaway(self: Arm, daily_share_minor: int) -> bool:
    return bool(daily_share_minor) and self.spend_minor > Optimizer.G1_RUNAWAY_X * daily_share_minor


Arm.spend_today_runaway = _spend_today_runaway  # type: ignore[attr-defined]
