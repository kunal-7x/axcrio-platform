"""ads_engine.guardrails — the FAIL-CLOSED disposition chain (W3).

optimization.py PROPOSES; this DISPOSES. Every proposed move and every spend-mutating
request passes `evaluate(...)` -> Verdict before any connector can spend. When in doubt
the move is BLOCKED + audited, never run. Nothing here calls a connector or spends; it
returns a Verdict that the caller (W5 tick/endpoints) uses to decide whether to mutate.

EXPLICIT PRECEDENCE (REDTEAM C4 — the safety pauses must NOT be muzzled by the learning
lock). The chain is evaluated TOP-DOWN; the FIRST deny short-circuits. Ordering:

  SAFETY TIER (exempt from + ordered ABOVE the learning/edit lock):
    1. conversion-tracking gate  -> blocked_no_conversion_tracking   (REDTEAM M4)
    2. hard spend caps           -> blocked_cap_exceeded             (un-bypassable)
    3. CPL loss circuit-breaker  -> blocked_cpl_breach
    4. insufficient funds        -> blocked_insufficient_funds
  LEARNING TIER (only reached if the move is NOT a safety pause):
    5. learning-phase lock       -> blocked_learning_locked  (blocks kill/scale on noise)
  APPROVAL TIER:
    6. anomaly (drafts a pause for spend-side spikes; cold-start warm-up, REDTEAM M1)
    7. only-decreasing auto-applies (REDTEAM C5): any non-decreasing move -> draft/approve
    8. op sub-budget (REDTEAM M5): a self-applied move consumes a per-tenant daily op quota

KEY RULE (REDTEAM C4): safety pauses (cap breach, CPL breaker, insufficient funds,
no-tracking) are themselves the ACTIONS the safety tier WANTS — they are spend-decreasing
pauses and are EXEMPT from the learning lock. A cap-breach pause overrides an active
learning lock. The learning lock only ever blocks *discretionary* kill/scale moves.

REDTEAM C5: only spend-DECREASING moves (pause, kill_loser) auto-apply. Any move with
spend_delta_sign >= 0 (scale_winner, alloc-raising reallocate, cap raise) is forced to
draft -> approve -> step-up.

Concurrency (REDTEAM C2): `spend_lock(tenant_id, account_id)` returns a per-key asyncio
lock; the caller holds it across read->evaluate->spend->writeback. The store's `cas_row`
is the optimistic-concurrency backstop.

Every decision yields a DecisionRow (plain-language `explanation`) the caller appends to
the immutable decision_log via store.append_decision.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Status vocabulary (sole owner — mirrors _lib.ts blocked_* AdsStatus).
# ---------------------------------------------------------------------------
BLOCKED_NO_TRACKING = "blocked_no_conversion_tracking"
BLOCKED_CAP = "blocked_cap_exceeded"
BLOCKED_CPL = "blocked_cpl_breach"
BLOCKED_FUNDS = "blocked_insufficient_funds"
BLOCKED_LEARNING = "blocked_learning_locked"
BLOCKED_NOT_APPROVED = "blocked_not_approved"
BLOCKED_OP_BUDGET = "blocked_op_budget_exhausted"

# Moves that are inherently safety pauses — spend-decreasing and EXEMPT from the
# learning lock (REDTEAM C4). These can always run to stop the bleeding.
SAFETY_PAUSE_MOVES = {"pause", "auto_pause", "kill_campaign"}
# Discretionary learning-phase-gated moves.
LEARNING_GATED_MOVES = {"kill_loser", "scale_winner"}

# Defaults (overridable via the guardrail_state row / config).
DEFAULT_CPL_BREAKER_FACTOR = 3.0
DEFAULT_CPL_BREAKER_MIN_SPEND_MINOR = 150000
DEFAULT_ANOMALY_Z = 3.0
# Anomaly cold-start warm-up (REDTEAM M1).
ANOMALY_WARMUP_MIN_N = 20
ANOMALY_STD_FLOOR_MINOR = 1.0
DEFAULT_OP_BUDGET_PER_DAY = 50


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
class Verdict:
    """The disposition of a single move through the chain."""

    __slots__ = ("allow", "auto_apply", "outcome", "blocked_by", "status",
                 "reason", "guard_chain", "spend_delta_sign")

    def __init__(self, allow: bool, *, auto_apply: bool, outcome: str,
                 blocked_by: Optional[str], status: Optional[str], reason: str,
                 guard_chain: list, spend_delta_sign: int = 0) -> None:
        self.allow = allow                  # may the move proceed at all?
        self.auto_apply = auto_apply        # proceed WITHOUT human approval?
        self.outcome = outcome              # applied|blocked|deferred_pending_approval|dry_run
        self.blocked_by = blocked_by        # a blocked_* status when blocked
        self.status = status                # campaign status to set (blocked_* / active)
        self.reason = reason                # plain-language explanation
        self.guard_chain = guard_chain      # ordered list of "<gate>:<verdict>"
        self.spend_delta_sign = int(spend_delta_sign)

    def to_dict(self) -> dict:
        return {
            "allow": self.allow,
            "auto_apply": self.auto_apply,
            "outcome": self.outcome,
            "blocked_by": self.blocked_by,
            "status": self.status,
            "reason": self.reason,
            "guard_chain": list(self.guard_chain),
            "spend_delta_sign": self.spend_delta_sign,
        }


def _spend_delta_sign(move: dict) -> int:
    try:
        return int(move.get("spend_delta_sign", 0))
    except Exception:  # noqa: BLE001
        return 0


def _is_safety_pause(move: dict) -> bool:
    return str(move.get("move", "")) in SAFETY_PAUSE_MOVES


# ---------------------------------------------------------------------------
# Individual gates — each returns (deny: bool, status, reason). Pure functions.
# ---------------------------------------------------------------------------
def gate_tracking(gstate: dict, move: dict) -> tuple[bool, Optional[str], str]:
    """REDTEAM M4: block any SCALE/increase when conversion tracking is zero/broken.
    Spend-decreasing moves are allowed (you can always pause/kill with no tracking)."""
    if _spend_delta_sign(move) < 0 or _is_safety_pause(move):
        return (False, None, "tracking gate n/a for spend-decreasing move")
    tracking_ok = bool(gstate.get("conversion_tracking_ok", False))
    conv_seen = float(gstate.get("conversions_observed", 0) or 0)
    if not tracking_ok or conv_seen <= 0:
        return (True, BLOCKED_NO_TRACKING,
                "conversion tracking is zero/broken — cannot scale on an unmeasured objective")
    return (False, None, "conversion tracking healthy")


def gate_caps(gstate: dict, move: dict) -> tuple[bool, Optional[str], str]:
    """Un-bypassable hard caps. A spend-INCREASING move that would exceed a cap is
    denied; a campaign already at/over a cap denies any non-pause move."""
    spend_today = int(gstate.get("spend_today_minor", 0) or 0)
    spend_life = int(gstate.get("spend_life_minor", 0) or 0)
    daily_cap = int(gstate.get("daily_cap_minor", 0) or 0)
    life_cap = int(gstate.get("lifetime_cap_minor", 0) or 0)
    delta = int(move.get("spend_delta_minor", 0) or 0)
    if _is_safety_pause(move) or _spend_delta_sign(move) < 0:
        return (False, None, "caps n/a for spend-decreasing/pause move")
    if daily_cap > 0 and spend_today + max(delta, 0) > daily_cap:
        return (True, BLOCKED_CAP,
                f"daily cap would be exceeded: {spend_today}+{max(delta,0)} > {daily_cap} paise")
    if life_cap > 0 and spend_life + max(delta, 0) > life_cap:
        return (True, BLOCKED_CAP,
                f"lifetime cap would be exceeded: {spend_life}+{max(delta,0)} > {life_cap} paise")
    return (False, None, "within hard caps")


def gate_cpl_breaker(gstate: dict, move: dict) -> tuple[bool, Optional[str], str]:
    """Loss circuit-breaker. After min spend, if CPL > factor*target, the breaker is
    tripped: block any spend-increasing move (the campaign must be paused, not scaled).
    The actual auto-pause is the SAFETY move the caller emits; this gate denies scale."""
    if _is_safety_pause(move) or _spend_delta_sign(move) < 0:
        return (False, None, "breaker n/a for spend-decreasing/pause move")
    spend_today = int(gstate.get("spend_today_minor", 0) or 0)
    min_spend = int(gstate.get("cpl_breaker_min_spend_minor",
                               DEFAULT_CPL_BREAKER_MIN_SPEND_MINOR) or 0)
    factor = float(gstate.get("cpl_breaker_factor", DEFAULT_CPL_BREAKER_FACTOR) or 0)
    target = int(gstate.get("cpl_target_minor", 0) or 0)
    last_cpl = int(gstate.get("last_cpl_minor", 0) or 0)
    if spend_today >= min_spend and target > 0 and factor > 0 \
            and last_cpl > factor * target:
        return (True, BLOCKED_CPL,
                f"CPL breaker: CPL {last_cpl} > {factor:g}x target {target} after {spend_today} spend")
    return (False, None, "CPL within breaker band")


def gate_funds(gstate: dict, move: dict) -> tuple[bool, Optional[str], str]:
    """Insufficient-funds: a spend-increasing move with no ledger headroom is denied."""
    if _is_safety_pause(move) or _spend_delta_sign(move) < 0:
        return (False, None, "funds n/a for spend-decreasing/pause move")
    balance = gstate.get("ledger_balance_minor", None)
    if balance is None:
        return (False, None, "no ledger balance supplied — funds gate skipped")
    delta = int(move.get("spend_delta_minor", 0) or 0)
    if int(balance) < max(delta, 0):
        return (True, BLOCKED_FUNDS,
                f"insufficient funds: balance {int(balance)} < required {max(delta,0)} paise")
    return (False, None, "sufficient funds")


def gate_learning_lock(gstate: dict, move: dict) -> tuple[bool, Optional[str], str]:
    """Learning-phase lock — blocks DISCRETIONARY kill/scale on noise. EXEMPT for
    safety pauses (handled before this gate is ever reached, REDTEAM C4)."""
    if str(move.get("move", "")) not in LEARNING_GATED_MOVES:
        return (False, None, "move not learning-gated")
    locked = bool(gstate.get("learning_lock", False))
    if locked:
        conv = gstate.get("conv_7d", "?")
        minc = gstate.get("min_conv", 50)
        return (True, BLOCKED_LEARNING,
                f"learning phase active ({conv}/{minc} conv/7d) — kill/scale deferred until signal")
    return (False, None, "learning phase exited")


def _zscore(observed: float, baseline: dict) -> tuple[float, bool]:
    """(|z|, warmed_up). REDTEAM M1: needs min-n samples AND a std above the floor,
    else returns warmed_up=False (no false trip during the cold-start window)."""
    n = int(baseline.get("n", 0) or 0)
    std = float(baseline.get("std", 0.0) or 0.0)
    mean = float(baseline.get("mean", 0.0) or 0.0)
    if n < ANOMALY_WARMUP_MIN_N or std < ANOMALY_STD_FLOOR_MINOR:
        return (0.0, False)
    return (abs(float(observed) - mean) / std, True)


def detect_anomaly(gstate: dict, z_threshold: float = DEFAULT_ANOMALY_Z) -> dict:
    """Z-score CPM/CPL/frequency vs EWMA baselines, cold-start-suppressed (REDTEAM M1).
    Returns {flag, kind, metric, z, warmed_up}. A flagged spend-side spike DRAFTS a
    pause for approval rather than auto-killing (anomaly != certainty)."""
    baselines = gstate.get("baselines", {})
    checks = [
        ("cpm_minor", gstate.get("last_cpm_minor", 0)),
        ("cpl_minor", gstate.get("last_cpl_minor", 0)),
        ("frequency", gstate.get("last_frequency", 0)),
    ]
    worst = {"flag": False, "kind": "", "metric": "", "z": 0.0, "warmed_up": False}
    for metric, observed in checks:
        bl = baselines.get(metric, {})
        z, warmed = _zscore(float(observed or 0.0), bl)
        if warmed and z > z_threshold and z > worst["z"]:
            worst = {"flag": True, "kind": "spike", "metric": metric,
                     "z": float(z), "warmed_up": True}
        elif warmed and not worst["flag"]:
            worst["warmed_up"] = True
    return worst


# ---------------------------------------------------------------------------
# The ordered chain.
# ---------------------------------------------------------------------------
def evaluate(gstate: dict, move: dict, *,
             op_budget_ok: Optional[bool] = None,
             anomaly_z: float = DEFAULT_ANOMALY_Z) -> Verdict:
    """Run `move` through the ordered, fail-closed chain. Returns a Verdict.

    `op_budget_ok`: when a self-applied move would consume the per-tenant daily op
    sub-budget (REDTEAM M5), the caller reserves it via store.try_consume_op and passes
    the result here (None = not checked / not an auto-apply). False -> blocked.
    """
    chain: list[str] = []
    sign = _spend_delta_sign(move)
    is_pause = _is_safety_pause(move)

    # ---- SAFETY TIER (exempt from + above the learning lock, REDTEAM C4) ----
    # Safety pauses themselves skip the deny-gates (they ARE the remedy) but still
    # record the chain so the audit shows why they ran.
    for name, fn in (("tracking", gate_tracking), ("daily_cap", gate_caps),
                     ("cpl_breaker", gate_cpl_breaker), ("funds", gate_funds)):
        deny, status, reason = fn(gstate, move)
        if deny:
            chain.append(f"{name}:deny")
            return Verdict(False, auto_apply=False, outcome="blocked",
                           blocked_by=status, status=status, reason=reason,
                           guard_chain=chain, spend_delta_sign=sign)
        chain.append(f"{name}:pass")

    # ---- LEARNING TIER (only discretionary moves reach here) ----
    deny, status, reason = gate_learning_lock(gstate, move)
    if deny:
        chain.append("learning_lock:deny")
        return Verdict(False, auto_apply=False, outcome="blocked",
                       blocked_by=status, status=status, reason=reason,
                       guard_chain=chain, spend_delta_sign=sign)
    chain.append("learning_lock:pass")

    # ---- APPROVAL TIER ----
    # Anomaly: a warmed-up spend-side spike DRAFTS a pause for approval.
    anom = detect_anomaly(gstate, anomaly_z)
    if anom["flag"] and sign >= 0 and not is_pause:
        chain.append(f"anomaly:{anom['metric']}_z{anom['z']:.1f}_draft")
        return Verdict(True, auto_apply=False, outcome="deferred_pending_approval",
                       blocked_by=BLOCKED_NOT_APPROVED, status=BLOCKED_NOT_APPROVED,
                       reason=(f"anomaly on {anom['metric']} (z={anom['z']:.1f}) — "
                               "spend move drafted for approval, not auto-applied"),
                       guard_chain=chain, spend_delta_sign=sign)
    chain.append("anomaly:pass")

    # REDTEAM C5: only spend-DECREASING moves auto-apply. Anything non-decreasing
    # (scale_winner, alloc-raising reallocate, cap raise) -> draft/approve + step-up.
    if sign >= 0 and not is_pause:
        chain.append("auto_apply_gate:needs_approval")
        return Verdict(True, auto_apply=False, outcome="deferred_pending_approval",
                       blocked_by=BLOCKED_NOT_APPROVED, status=BLOCKED_NOT_APPROVED,
                       reason="non-decreasing-spend move requires draft -> approve -> step-up",
                       guard_chain=chain, spend_delta_sign=sign)
    chain.append("auto_apply_gate:auto")

    # REDTEAM M5: a self-applied move consumes a per-tenant daily op quota.
    if op_budget_ok is False:
        chain.append("op_budget:exhausted")
        return Verdict(False, auto_apply=False, outcome="blocked",
                       blocked_by=BLOCKED_OP_BUDGET, status=BLOCKED_OP_BUDGET,
                       reason="per-tenant daily op sub-budget exhausted — auto-apply deferred",
                       guard_chain=chain, spend_delta_sign=sign)
    if op_budget_ok is True:
        chain.append("op_budget:consumed")

    # All gates passed: a spend-decreasing/pause move auto-applies.
    return Verdict(True, auto_apply=True, outcome="applied",
                   blocked_by=None, status="active",
                   reason="spend-decreasing move auto-applied (all guards passed)",
                   guard_chain=chain, spend_delta_sign=sign)


# ---------------------------------------------------------------------------
# DecisionRow builder (the caller appends to store.decision_log).
# ---------------------------------------------------------------------------
def build_decision_row(tenant_id: str, move: dict, verdict: Verdict, *,
                       inputs: dict | None = None, ts: int | None = None,
                       actor: str = "system") -> dict:
    """An immutable DecisionRow capturing the move, the ordered guard verdicts, and a
    plain-language explanation (PROVE-DON'T-OBEY: the measured numbers go in `inputs`)."""
    return {
        "id": "dec_" + uuid.uuid4().hex[:10],
        "tenant_id": tenant_id,
        "ts": int(ts if ts is not None else time.time()),
        "kind": _kind_for_move(move),
        "campaign_id": move.get("plan_id") or move.get("campaign_id"),
        "account_id": move.get("account_id"),
        "decision": move.get("move"),
        "target": {"variant_id": move.get("variant_id"), "channel": move.get("channel")},
        "inputs": dict(inputs or {}),
        "guard_chain": list(verdict.guard_chain),
        "outcome": verdict.outcome,
        "blocked_by": verdict.blocked_by,
        "explanation": move.get("reason", "") + (
            f" | guard: {verdict.reason}" if verdict.reason else ""),
        "actor": actor,
        "reversible": str(move.get("move", "")) in (
            LEARNING_GATED_MOVES | SAFETY_PAUSE_MOVES | {"reallocate"}),
    }


def _kind_for_move(move: dict) -> str:
    m = str(move.get("move", ""))
    if m in ("scale_winner", "kill_loser", "hold"):
        return "bandit_move"
    if m == "reallocate":
        return "allocation"
    if m in SAFETY_PAUSE_MOVES:
        return "safety_pause"
    return "manual"


# ---------------------------------------------------------------------------
# Concurrency (REDTEAM C2): per-tenant(+account) async lock registry.
# ---------------------------------------------------------------------------
_LOCKS: dict[str, "asyncio.Lock"] = {}


def spend_lock(tenant_id: str, account_id: str = "") -> "asyncio.Lock":
    """Return the asyncio.Lock for this (tenant, account) key. The caller holds it
    across read -> evaluate -> (proposed) spend -> writeback so two writers can't blow
    a cap by interleaving (REDTEAM C2). Combined with store.cas_row as the backstop."""
    key = f"{tenant_id}::{account_id}"
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock
