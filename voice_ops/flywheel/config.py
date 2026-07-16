"""voice_ops.flywheel.config — all Flywheel knobs in one frozen, side-effect-free place.

Mirrors voice_ops/research env reads + grow/config.py. Pure data: importing this never
touches the network or a file. `active()` is the master dormancy predicate — when it is
False every public entrypoint in the package is a cheap no-op (the resting state is
byte-identical to a deployment that never heard of the Flywheel).

ClickHouse reuses the SAME env chain as research_analytics / voice_analytics so an operator
who already runs Famit Research gets the Flywheel warehouse for free.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except Exception:  # noqa: BLE001
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, "") or default))
    except Exception:  # noqa: BLE001
        return default


def _ch_write_url() -> str:
    return (os.getenv("FLYWHEEL_CLICKHOUSE_URL")
            or os.getenv("CLICKHOUSE_WRITE_URL") or os.getenv("CLICKHOUSE_URL") or "").strip().rstrip("/")


def _ch_read_url() -> str:
    return (os.getenv("FLYWHEEL_CLICKHOUSE_URL")
            or os.getenv("CLICKHOUSE_URL") or os.getenv("CLICKHOUSE_WRITE_URL") or "").strip().rstrip("/")


@dataclass(frozen=True)
class FlywheelConfig:
    # --- master gate ------------------------------------------------------- #
    enabled: bool = False
    ch_write_url: str = ""
    ch_read_url: str = ""

    # --- reward shaping (anti-Goodhart caps; outcome term dominates) ------- #
    reward_cap: float = 2.0           # clip the outcome reward — removes the heavy tail
    deal_scale: float = 5_000_000.0   # ₹ scale for the concave tanh deal multiplier
    deal_cap: float = 1.5             # max deal multiplier
    w_outcome: float = 1.0
    w_affect: float = 0.15            # PBRS affect-delta weight (bounded shaping)
    w_judge: float = 0.10             # RLAIF judge weight (bounded shaping)
    gamma_sparse: float = 0.95        # discount for MC returns
    credit_alpha: float = 0.6         # MT-GRPO intermediate/outcome blend

    # --- RLAIF judge ------------------------------------------------------- #
    judge_enabled: bool = False
    judge_model: str = "anthropic/claude-3.5-sonnet"   # cross-family (NEVER Llama grading Llama)
    judge_sample_rate: float = 0.0    # outcome-stratified sampling (1.0 = always; hot always-on)
    judge_panel_size: int = 1         # 2-3 disjoint families only for high-stakes pref labels
    rubric_version: str = "v1"        # snapshotted into every reward row; a bump re-gates

    # --- bandit ------------------------------------------------------------ #
    bandit_enabled: bool = False
    bandit_epsilon: float = 0.08      # forced-exploration floor (precondition for honest OPE)
    bandit_explore_cap: float = 0.15  # max challenger-arm traffic per campaign
    bandit_discount: float = 0.98     # posterior discount per update (non-stationarity)

    # --- optimizer / promotion -------------------------------------------- #
    optimizer_enabled: bool = False
    auto_promote: bool = False        # MUST stay False — promotion needs a human click
    holdout_pct: int = 5              # frozen holdout never optimized on (Goodhart canary)

    # --- worker ------------------------------------------------------------ #
    worker_interval_s: int = 3600

    # --- power-up tier (B1–B7) — every flag default OFF ⇒ the tier is dormant ------------ #
    ensemble_enabled: bool = False        # B1 reward ensemble + pessimistic LCB
    ensemble_lambda: float = 0.5          # variance penalty weight
    ensemble_kappa: float = 1.0           # uncertainty (u) penalty weight
    sequential_enabled: bool = False      # B2 always-valid promotion test
    seq_alpha: float = 0.05               # anytime-valid significance level
    seq_practical_delta: float = 0.01     # minimum practical lift to bother promoting
    conformal_alpha: float = 0.1          # conformal miscoverage
    conformal_min_calib: int = 50         # min calibration rows per bucket (else parent fallback)
    critic_enabled: bool = False          # B3 learned V(state)→P(book)
    critic_model: str = "logistic"        # logistic | gbt | mlp (heavier lazy)
    critic_min_rows: int = 5000           # don't train a critic on too little data
    critic_eta: float = 0.3               # BSRS-bounded PBRS potential scale
    causal_enabled: bool = False          # B4 DR X-learner CATE
    causal_k_folds: int = 5
    causal_min_overlap: float = 0.02      # propensity-overlap floor (below ⇒ untrustworthy cell)
    causal_estimator: str = "dr_xlearner"
    simulator_enabled: bool = False       # B5 caller world model (filter-only, never promotes)
    sim_usi_ece_max: float = 0.15         # self-disable the sim above this calibration error
    sim_k_rollouts: int = 4
    sim_max_archetypes: int = 12
    contextual_policy_enabled: bool = False  # B6 LinTS per-state rebuttal selector
    policy_epsilon: float = 0.08
    policy_discount: float = 0.98
    policy_logsmooth_lambda: float = 0.1
    distill_enabled: bool = False         # B7 KTO/SimPO export + self-hosted shadow challenger
    distill_base_model: str = ""
    distill_method: str = "kto"
    distill_min_desirable: int = 200

    @classmethod
    def from_env(cls) -> "FlywheelConfig":
        return cls(
            enabled=_truthy(os.getenv("FLYWHEEL_ENABLED", "0")),
            ch_write_url=_ch_write_url(),
            ch_read_url=_ch_read_url(),
            reward_cap=_f("FLYWHEEL_REWARD_CAP", 2.0),
            deal_scale=_f("FLYWHEEL_DEAL_SCALE", 5_000_000.0),
            deal_cap=_f("FLYWHEEL_DEAL_CAP", 1.5),
            w_outcome=_f("FLYWHEEL_W_OUTCOME", 1.0),
            w_affect=_f("FLYWHEEL_W_AFFECT", 0.15),
            w_judge=_f("FLYWHEEL_W_JUDGE", 0.10),
            gamma_sparse=_f("FLYWHEEL_GAMMA_SPARSE", 0.95),
            credit_alpha=_f("FLYWHEEL_CREDIT_ALPHA", 0.6),
            judge_enabled=_truthy(os.getenv("FLYWHEEL_JUDGE_ENABLED", "0")),
            judge_model=(os.getenv("FLYWHEEL_JUDGE_MODEL") or "anthropic/claude-3.5-sonnet").strip(),
            judge_sample_rate=_f("FLYWHEEL_JUDGE_SAMPLE_RATE", 0.0),
            judge_panel_size=_i("FLYWHEEL_JUDGE_PANEL_SIZE", 1),
            rubric_version=(os.getenv("FLYWHEEL_RUBRIC_VERSION") or "v1").strip(),
            bandit_enabled=_truthy(os.getenv("FLYWHEEL_BANDIT_ENABLED", "0")),
            bandit_epsilon=_f("FLYWHEEL_BANDIT_EPSILON", 0.08),
            bandit_explore_cap=_f("FLYWHEEL_BANDIT_EXPLORE_CAP", 0.15),
            bandit_discount=_f("FLYWHEEL_BANDIT_DISCOUNT", 0.98),
            optimizer_enabled=_truthy(os.getenv("FLYWHEEL_OPTIMIZER_ENABLED", "0")),
            auto_promote=_truthy(os.getenv("FLYWHEEL_AUTO_PROMOTE", "0")),
            holdout_pct=_i("FLYWHEEL_HOLDOUT_PCT", 5),
            worker_interval_s=_i("FLYWHEEL_WORKER_INTERVAL_S", 3600),
            ensemble_enabled=_truthy(os.getenv("FLYWHEEL_ENSEMBLE_ENABLED", "0")),
            ensemble_lambda=_f("FLYWHEEL_ENSEMBLE_LAMBDA", 0.5),
            ensemble_kappa=_f("FLYWHEEL_ENSEMBLE_KAPPA", 1.0),
            sequential_enabled=_truthy(os.getenv("FLYWHEEL_SEQUENTIAL_ENABLED", "0")),
            seq_alpha=_f("FLYWHEEL_SEQ_ALPHA", 0.05),
            seq_practical_delta=_f("FLYWHEEL_SEQ_PRACTICAL_DELTA", 0.01),
            conformal_alpha=_f("FLYWHEEL_CONFORMAL_ALPHA", 0.1),
            conformal_min_calib=_i("FLYWHEEL_CONFORMAL_MIN_CALIB", 50),
            critic_enabled=_truthy(os.getenv("FLYWHEEL_CRITIC_ENABLED", "0")),
            critic_model=(os.getenv("FLYWHEEL_CRITIC_MODEL") or "logistic").strip(),
            critic_min_rows=_i("FLYWHEEL_CRITIC_MIN_ROWS", 5000),
            critic_eta=_f("FLYWHEEL_CRITIC_ETA", 0.3),
            causal_enabled=_truthy(os.getenv("FLYWHEEL_CAUSAL_ENABLED", "0")),
            causal_k_folds=_i("FLYWHEEL_CAUSAL_K_FOLDS", 5),
            causal_min_overlap=_f("FLYWHEEL_CAUSAL_MIN_OVERLAP", 0.02),
            causal_estimator=(os.getenv("FLYWHEEL_CAUSAL_ESTIMATOR") or "dr_xlearner").strip(),
            simulator_enabled=_truthy(os.getenv("FLYWHEEL_SIMULATOR_ENABLED", "0")),
            sim_usi_ece_max=_f("FLYWHEEL_SIM_USI_ECE_MAX", 0.15),
            sim_k_rollouts=_i("FLYWHEEL_SIM_K_ROLLOUTS", 4),
            sim_max_archetypes=_i("FLYWHEEL_SIM_MAX_ARCHETYPES", 12),
            contextual_policy_enabled=_truthy(os.getenv("FLYWHEEL_CONTEXTUAL_POLICY_ENABLED", "0")),
            policy_epsilon=_f("FLYWHEEL_POLICY_EPSILON", 0.08),
            policy_discount=_f("FLYWHEEL_POLICY_DISCOUNT", 0.98),
            policy_logsmooth_lambda=_f("FLYWHEEL_POLICY_LOGSMOOTH_LAMBDA", 0.1),
            distill_enabled=_truthy(os.getenv("FLYWHEEL_DISTILL_ENABLED", "0")),
            distill_base_model=(os.getenv("FLYWHEEL_DISTILL_BASE_MODEL") or "").strip(),
            distill_method=(os.getenv("FLYWHEEL_DISTILL_METHOD") or "kto").strip(),
            distill_min_desirable=_i("FLYWHEEL_DISTILL_MIN_DESIRABLE", 200),
        )

    # -- predicates --------------------------------------------------------- #
    def active(self) -> bool:
        """Master dormancy gate: capture/persist only when enabled AND a CH url exists."""
        return bool(self.enabled and self.ch_write_url)

    def read_active(self) -> bool:
        """Reads can work even when WRITING is off (the console shows demo otherwise)."""
        return bool(self.ch_read_url)

    def judge_active(self) -> bool:
        return bool(self.active() and self.judge_enabled and os.getenv("OPENROUTER_API_KEY"))

    def bandit_active(self) -> bool:
        return bool(self.active() and self.bandit_enabled)

    def optimizer_active(self) -> bool:
        return bool(self.active() and self.optimizer_enabled)

    # -- power-up predicates (each requires the master gate + its own flag) -- #
    def ensemble_active(self) -> bool:
        return bool(self.active() and self.ensemble_enabled)

    def sequential_active(self) -> bool:
        return bool(self.active() and self.sequential_enabled)

    def critic_active(self) -> bool:
        return bool(self.active() and self.critic_enabled)

    def causal_active(self) -> bool:
        return bool(self.active() and self.causal_enabled)

    def simulator_active(self) -> bool:
        # the sim makes cross-family LLM calls ⇒ also needs an OpenRouter key (like the judge)
        return bool(self.active() and self.simulator_enabled and os.getenv("OPENROUTER_API_KEY"))

    def policy_active(self) -> bool:
        return bool(self.active() and self.contextual_policy_enabled)

    def distill_active(self) -> bool:
        return bool(self.active() and self.distill_enabled)

    def in_holdout(self, call_id: str) -> bool:
        """Deterministic frozen-holdout membership (never optimized on; the ground-truth
        canary). Hash the call_id so the slice is stable across re-runs."""
        if self.holdout_pct <= 0:
            return False
        import hashlib
        h = int(hashlib.sha1((call_id or "").encode("utf-8")).hexdigest(), 16) % 100
        return h < self.holdout_pct

    def status(self) -> Dict:
        """No secrets — safe to serve on /flywheel/health."""
        return {
            "enabled": self.enabled,
            "store_configured": bool(self.ch_write_url),
            "read_configured": bool(self.ch_read_url),
            "judge_enabled": self.judge_enabled,
            "judge_model": self.judge_model,
            "judge_sample_rate": self.judge_sample_rate,
            "bandit_enabled": self.bandit_enabled,
            "bandit_epsilon": self.bandit_epsilon,
            "optimizer_enabled": self.optimizer_enabled,
            "auto_promote": self.auto_promote,
            "rubric_version": self.rubric_version,
            "holdout_pct": self.holdout_pct,
            "worker_interval_s": self.worker_interval_s,
            "active": self.active(),
            # power-up tier (B1–B7)
            "ensemble_enabled": self.ensemble_enabled,
            "sequential_enabled": self.sequential_enabled,
            "critic_enabled": self.critic_enabled,
            "causal_enabled": self.causal_enabled,
            "simulator_enabled": self.simulator_enabled,
            "contextual_policy_enabled": self.contextual_policy_enabled,
            "distill_enabled": self.distill_enabled,
            "causal_estimator": self.causal_estimator,
            "critic_model": self.critic_model,
            "distill_method": self.distill_method,
        }


# Cheap module-level accessor (re-reads env each call so a runtime flag flip is honoured,
# mirroring research_analytics._enabled()).
def load() -> FlywheelConfig:
    return FlywheelConfig.from_env()


def active() -> bool:
    return load().active()


def status() -> Dict:
    return load().status()
