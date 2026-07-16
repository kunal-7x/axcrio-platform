"""grow.budget — the Budget Governor (money safety as architecture, GROWTH-OS §13).

Money is sacred (P4): no code path may increase spend without a Governor stamp. This is the
guardrail that makes autonomous spend safe — hard daily caps, an anomaly sentinel that
auto-pauses on a runaway, month-end forecast throttle, and a kill-switch. Pure logic on
INTEGER minor units (paise — never floats for money); offline-testable; never raises.
The live "apply pause/resume" is an injected connector seam (founder-gated on Ads OAuth).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("grow.budget")


@dataclass(frozen=True)
class BudgetTree:
    """The spend tree: workspace_monthly → campaign_lifetime → daily_cap → per-adset.
    All minor units (paise). 0 = unset/unbounded for that level."""
    workspace_monthly_minor: int = 0
    campaign_lifetime_minor: int = 0
    daily_cap_minor: int = 0
    adsets: int = 1                     # split the daily cap across N ad sets

    @property
    def per_adset_daily_minor(self) -> int:
        return self.daily_cap_minor // max(1, self.adsets) if self.daily_cap_minor else 0


@dataclass
class GovernorVerdict:
    allow: bool
    reason: str
    headroom_minor: int = 0            # how much more spend the cap allows today
    stamp: str = ""                    # the Governor stamp an ActionPlan must carry


@dataclass
class AnomalyVerdict:
    anomaly: bool
    reasons: list = field(default_factory=list)
    severity: str = "none"            # none | yellow | red


class BudgetGovernor:
    """Construct with a BudgetTree. All checks are pure; `apply_pause` is an injected seam."""

    # anomaly thresholds (GROWTH-OS §13.2)
    VELOCITY_X = 3.0                   # spend velocity > 3× trailing-7d hourly norm
    CPM_X = 4.0                        # CPM > 4× norm
    CTR_LOW_X = 0.2                    # CTR < 0.2× norm with spend
    RUNAWAY_X = 3.0                    # spend_today > 3× daily share -> pause NOW

    def __init__(self, tree: Optional[BudgetTree] = None):
        self.tree = tree or BudgetTree()

    # ----------------------------------------------------- admission #
    def admit_spend(self, *, spent_today_minor: int, proposed_minor: int,
                    spent_month_minor: int = 0) -> GovernorVerdict:
        """May this spend increase be signed? Sum of daily budgets must stay ≤ the daily
        cap (reconciled against ACTUAL spend), and the month cap must hold. Fail-closed."""
        cap = self.tree.daily_cap_minor
        if cap and (spent_today_minor + proposed_minor) > cap:
            return GovernorVerdict(False, "daily_cap_exceeded",
                                   headroom_minor=max(0, cap - spent_today_minor))
        mcap = self.tree.workspace_monthly_minor
        if mcap and (spent_month_minor + proposed_minor) > mcap:
            return GovernorVerdict(False, "monthly_cap_exceeded",
                                   headroom_minor=max(0, mcap - spent_month_minor))
        headroom = (cap - spent_today_minor - proposed_minor) if cap else proposed_minor
        # a deterministic stamp proving this passed the Governor (carried on the ActionPlan)
        stamp = f"gov:ok:d{spent_today_minor + proposed_minor}/{cap or 'inf'}"
        return GovernorVerdict(True, "within_caps", headroom_minor=max(0, headroom), stamp=stamp)

    # ----------------------------------------------------- runaway / sentinel #
    def is_runaway(self, *, spent_today_minor: int) -> bool:
        """Spend today already blew past 3× the daily share => pause immediately (any time,
        even during learning)."""
        share = self.tree.per_adset_daily_minor or self.tree.daily_cap_minor
        return bool(share) and spent_today_minor > self.RUNAWAY_X * share

    def detect_anomaly(self, *, spend_velocity: float, velocity_norm: float,
                       cpm: float = 0.0, cpm_norm: float = 0.0,
                       ctr: float = -1.0, ctr_norm: float = 0.0,
                       emq_collapsed: bool = False) -> AnomalyVerdict:
        """The Spend Sentinel: any of velocity/CPM/CTR/EMQ anomalies => auto-pause signal."""
        reasons = []
        if velocity_norm > 0 and spend_velocity > self.VELOCITY_X * velocity_norm:
            reasons.append(f"spend_velocity_{spend_velocity:.0f}>3x_norm_{velocity_norm:.0f}")
        if cpm_norm > 0 and cpm > self.CPM_X * cpm_norm:
            reasons.append(f"cpm_{cpm:.0f}>4x_norm")
        if ctr_norm > 0 and 0 <= ctr < self.CTR_LOW_X * ctr_norm:
            reasons.append("ctr_collapse")
        if emq_collapsed:
            reasons.append("emq_collapse")
        sev = "red" if len(reasons) >= 2 or any("velocity" in r for r in reasons) else \
              ("yellow" if reasons else "none")
        return AnomalyVerdict(anomaly=bool(reasons), reasons=reasons, severity=sev)

    # ----------------------------------------------------- forecast #
    def month_forecast(self, *, spent_month_minor: int, day_of_month: int,
                       days_in_month: int = 30) -> dict:
        """Projected month spend at the current run-rate; flags a graduated throttle
        (never a mid-learning cliff stop) if it would blow the monthly cap."""
        d = max(1, day_of_month)
        projected = int(spent_month_minor / d * days_in_month)
        cap = self.tree.workspace_monthly_minor
        over = bool(cap and projected > cap)
        throttle = round(cap / projected, 3) if (over and projected) else 1.0
        return {"projected_minor": projected, "cap_minor": cap, "over_cap": over,
                "suggested_throttle": throttle}

    def kill_switch(self, reason: str = "manual") -> dict:
        """The emergency pause-all directive (the live executor applies it via the connector)."""
        return {"action": "pause_all", "reason": reason, "reversible": True,
                "undo_plan": "resume campaigns from the approval inbox"}
