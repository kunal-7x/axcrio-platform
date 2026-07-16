"""voice_ops.flywheel.schema — the Haptica Flywheel wire contract.

ONE dataclass per ClickHouse table + the embedded RewardComponents provenance record.
These dataclasses are the SINGLE SOURCE OF TRUTH for:
  * the ClickHouse table columns (voice_ops/flywheel/db/ddl_flywheel.sql),
  * the JSON the backend serves the panel (router.py via store.py),
  * the TypeScript types in famit-panel/lib/api.ts (mirror these verbatim).
Keep all three in lockstep.

DESIGN LAWS (mirror voice_ops/research/schema.py):
  * Pure-python, zero heavy deps — imports safely even when ClickHouse / OpenRouter
    are unconfigured (the package must be dormant-safe).
  * `to_row()` returns a ClickHouse JSONEachRow dict: None-valued optionals dropped,
    bools coerced to UInt8 (0/1), lists comma-joined, nested dicts JSON-encoded.
  * HONEST SCIENCE: a fused reward NEVER travels without its components. Every
    TrajectoryRow carries a RewardComponents (raw vs capped outcome, affect_delta,
    judge_score, the weights, judge_model_id, rubric_version, confidence) so the
    console can always show *why* a turn scored what it did.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


# --------------------------------------------------------------------------- #
# Canonical vocabularies (closed enums kept here so every module agrees).
# --------------------------------------------------------------------------- #
# A turn's MOVE — what the agent *did* this turn. The founder's "which move is
# positive/negative" question is answered per-move (see credit.py move PRM).
MOVE_TYPES = (
    "opening",            # greeting / who-am-I / why-calling
    "probe",              # discovery / qualifying question
    "empathize",          # acknowledge / rapport / mirror
    "inform",             # product fact / USP / answer
    "price_reveal",       # state price / budget framing
    "objection_rebuttal", # handle a "no / too costly / busy / not interested"
    "cta_push",           # ask for the next step (site visit / callback)
    "handoff_offer",      # offer a human / senior callback
    "close",              # confirm appointment / wrap
    "other",
)

# OBJECTION sub-types (real-estate Hinglish) — tag for matched-state preference mining.
OBJECTION_TYPES = (
    "price", "loan", "location", "timing", "rera", "possession",
    "trust", "spouse_decision", "already_bought", "not_interested", "none",
)

# Lead temperature buckets — the cohort axis credit assignment controls for.
LEAD_TEMPERATURES = ("hot", "warm", "cold", "dead", "unknown")

# Bandit knobs — each is its OWN factored hierarchical-TS dimension (not a joint arm).
KNOBS = ("model", "voice", "variant", "opening", "rebuttal")

# Preference-pair provenance.  sim_self_play = minted by the caller simulator (down-weighted vs
# real outcome-anchored rows — a synthetic pair is a hypothesis, not ground truth).
PREF_SOURCES = ("within_call", "matched_state", "rubric_pairwise", "sim_self_play")

# Challenger lifecycle.
CHALLENGER_STATES = ("proposed", "gated", "approved", "promoted", "rejected", "reverted")
CHALLENGER_KINDS = ("bandit_arm", "prompt", "rebuttal", "variant")

# Human-label triggers (the ~1-5% of calls worth a human look — the RLHF spend).
LABEL_TRIGGERS = (
    "judge_affect_disagreement", "high_value_lost",
    "champ_chall_divergence", "low_conf_pivotal",
)

# Goodhart-canary monitor metrics (+ the power-up tier's calibration canaries — a model whose
# calibration (ECE) decays silently is the first sign a learned component is going stale/gaming).
MONITOR_METRICS = (
    "judge_vs_outcome_corr", "optout_rate", "friction_trend",
    "psi_drift", "rm_human_kappa",
    "sim_outcome_ece", "sim_behavior_kl", "sim_usi",
    "critic_ece", "critic_auc", "cate_overlap", "ensemble_disagreement",
)


# --------------------------------------------------------------------------- #
# Small shared helpers (used across the whole package).
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    """Canonical UTC, Z-suffixed (matches voice_kernel.events.timeutil)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def ch_ts(iso: str = "") -> str:
    """ISO8601 → ClickHouse DateTime64(3) literal 'YYYY-MM-DD HH:MM:SS.mmm' (UTC).
    Mirrors research_analytics._ch_ts so both pipelines stamp identically."""
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def new_id(prefix: str = "") -> str:
    """Opaque unique id (challengers, pairs that have no natural key)."""
    return f"{prefix}{uuid.uuid4().hex[:16]}" if prefix else uuid.uuid4().hex[:16]


def digest_id(*parts: object) -> str:
    """Deterministic id from its parts — so a re-run produces the SAME id and the
    MergeTree dedupes instead of double-counting (idempotency over re-processing)."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return h[:16]


def _u8(v) -> int:
    return 1 if v else 0


def _f(v, d: float = 0.0) -> float:
    try:
        f = float(v)
        return d if (f != f) else f          # NaN guard
    except Exception:  # noqa: BLE001
        return d


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------- #
# RewardComponents — the honest-science provenance carried by every turn.
# --------------------------------------------------------------------------- #
@dataclass
class RewardComponents:
    """Every part that produced a turn's fused reward — never a bare scalar.

    `terminal_credit` is the credit-assigned share of the call's terminal outcome
    attributed to THIS turn (credit.py); `affect_delta`/`judge_score` are the dense
    process channels; the weights show how they were fused; `disagreement` flags an
    affect-vs-judge conflict (→ a human-label trigger)."""
    raw_outcome: float = 0.0          # tier-2 base outcome (uncapped, pre deal-mult)
    capped_outcome: float = 0.0       # after tanh deal-mult + clip(-1, +cap)
    terminal_credit: float = 0.0      # this turn's share of capped_outcome (credit assignment)
    affect_delta: float = 0.0         # tier-3 PBRS friction-shaping (confidence-gated)
    judge_score: float = 0.0          # tier-3 RLAIF rubric scalar (sampled; 0 if unjudged)
    w_outcome: float = 1.0
    w_affect: float = 0.15
    w_judge: float = 0.10
    judge_model_id: str = ""          # pinned cross-family judge id (provenance)
    rubric_version: str = ""          # snapshotted; a bump re-triggers the gate
    confidence: float = 0.0           # fused confidence (affect conf × judge conf)
    disagreement: bool = False        # affect channel vs judge channel conflict
    # --- power-up tier (B1 ensemble): a 4th head + epistemic uncertainty + pessimistic LCB ---
    value_head: float = 0.0           # learned V(state)→P(book) critic head (B3), centred
    ensemble_mean: float = 0.0        # mean of the z-normalized heads (B1)
    ensemble_var: float = 0.0         # head disagreement = epistemic uncertainty (B1)
    lcb_reward: float = 0.0           # pessimistic lower-confidence-bound reward (B1) — what the
                                      # optimizer/bandit consume so they can't exploit one bad head
    ensemble_computed: bool = False   # True once B1 has filled the ensemble fields

    def fused(self) -> float:
        """The PROVENANCE number (point estimate). Always available; what the console shows."""
        return round(
            self.w_outcome * self.terminal_credit
            + self.w_affect * self.affect_delta
            + self.w_judge * self.judge_score,
            5,
        )

    def optimized(self) -> float:
        """The number the OPTIMIZER + BANDIT consume — the pessimistic LCB when the ensemble has
        run (anti-Goodhart: point-estimate maximization can't overfit a single mis-specified head),
        else the plain fused point estimate (dormant-safe). This .fused()→.optimized() flip is the
        whole anti-over-optimization guard (Gao scaling laws / WARM / UWO)."""
        return round(self.lcb_reward, 5) if self.ensemble_computed else self.fused()

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# --------------------------------------------------------------------------- #
# TrajectoryRow — one row per agent turn: the RL (state, action, reward) unit.
# --------------------------------------------------------------------------- #
@dataclass
class TrajectoryRow:
    # identity / routing
    tenant_id: str = ""
    call_id: str = ""
    turn_num: int = 0
    ts_iso: str = ""
    campaign_id: str = ""
    vertical: str = "real_estate"
    lead_temperature: str = "unknown"
    # action (the move + the arm that produced it)
    move_type: str = "other"
    objection_type: str = "none"
    arm_model: str = ""
    arm_voice: str = ""
    arm_variant: str = ""
    propensity: float = 1.0           # P(this arm | policy) at decision time — load-bearing for OPE
    # state (from famit_research_turns; z-scored to the caller's own baseline)
    state_friction: float = 50.0
    state_arousal: float = 50.0
    state_regime: str = "steady"
    # reward (dense channels + credit-assigned terminal + provenance)
    affect_delta: float = 0.0
    judge_score: float = 0.0
    rubric_json: str = ""             # per-dimension judge breakdown (JSON)
    credit_advantage: float = 0.0     # credit.py per-turn advantage (the +/- signal)
    reward_raw: float = 0.0
    reward_capped: float = 0.0
    reward_components_json: str = ""  # RewardComponents.to_json()
    confidence: float = 0.0
    low_conf: bool = False
    judge_model_id: str = ""
    rubric_version: str = ""
    # context (PII-light; matches famit_research_turns transcript clip)
    agent_text: str = ""              # what Riya said this turn (the action text)
    caller_text: str = ""             # the caller turn that prompted it
    # --- power-up tier enrichments (all default-0 ⇒ back-compatible / dormant) ---
    v_state: float = 0.0              # B3 critic V(state) = P(book | state) at this turn
    v_momentum: float = 0.0           # B3 ΔV vs previous turn (live "are we winning?" signal)
    ensemble_mean: float = 0.0        # B1 ensemble point estimate
    ensemble_var: float = 0.0         # B1 head disagreement (epistemic uncertainty)
    lcb_reward: float = 0.0           # B1 pessimistic reward
    value_head: float = 0.0           # B1 value head contribution
    counterfactual_delta: float = 0.0 # B5 sim counterfactual credit (advisory; PRM-gated)
    counterfactual_n: int = 0         # B5 number of counterfactual rollouts behind it
    list_source: str = ""             # B4 lead-list quality confounder (causal adjustment)
    play_template_id: str = ""        # B6 the contextual-policy rebuttal arm chosen (if any)
    state_feature_json: str = ""      # B6 the exact feature vector (so OPE reconstructs identically)

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso),
            "tenant_id": str(self.tenant_id)[:120],
            "call_id": str(self.call_id)[:120],
            "turn_num": int(self.turn_num or 0),
            "campaign_id": str(self.campaign_id)[:120],
            "vertical": str(self.vertical or "real_estate")[:40],
            "lead_temperature": str(self.lead_temperature or "unknown")[:16],
            "move_type": str(self.move_type or "other")[:32],
            "objection_type": str(self.objection_type or "none")[:32],
            "arm_model": str(self.arm_model or "")[:80],
            "arm_voice": str(self.arm_voice or "")[:80],
            "arm_variant": str(self.arm_variant or "")[:80],
            "propensity": _f(self.propensity, 1.0),
            "state_friction": _f(self.state_friction, 50.0),
            "state_arousal": _f(self.state_arousal, 50.0),
            "state_regime": str(self.state_regime or "steady")[:24],
            "affect_delta": _f(self.affect_delta),
            "judge_score": _f(self.judge_score),
            "rubric_json": (self.rubric_json or "")[:2000],
            "credit_advantage": _f(self.credit_advantage),
            "reward_raw": _f(self.reward_raw),
            "reward_capped": _f(self.reward_capped),
            "reward_components_json": (self.reward_components_json or "")[:2000],
            "confidence": _f(self.confidence),
            "low_conf": _u8(self.low_conf),
            "judge_model_id": str(self.judge_model_id or "")[:60],
            "rubric_version": str(self.rubric_version or "")[:24],
            "agent_text": (self.agent_text or "")[:400],
            "caller_text": (self.caller_text or "")[:400],
            "v_state": _f(self.v_state),
            "v_momentum": _f(self.v_momentum),
            "ensemble_mean": _f(self.ensemble_mean),
            "ensemble_var": _f(self.ensemble_var),
            "lcb_reward": _f(self.lcb_reward),
            "value_head": _f(self.value_head),
            "counterfactual_delta": _f(self.counterfactual_delta),
            "counterfactual_n": int(self.counterfactual_n or 0),
            "list_source": str(self.list_source or "")[:40],
            "play_template_id": str(self.play_template_id or "")[:60],
            "state_feature_json": (self.state_feature_json or "")[:1000],
        })


# --------------------------------------------------------------------------- #
# PreferencePair — the proprietary (chosen, rejected) moat.
# --------------------------------------------------------------------------- #
@dataclass
class PreferencePair:
    tenant_id: str = ""
    pair_id: str = ""
    ts_iso: str = ""
    state_embedding_id: str = ""      # bucket key for matched-state dedup
    objection_type: str = "none"
    lead_temperature: str = "unknown"
    regime: str = "steady"
    vertical: str = "real_estate"
    chosen_text: str = ""
    rejected_text: str = ""
    chosen_move_id: str = ""          # call_id:turn_num of the chosen move
    rejected_move_id: str = ""
    margin: float = 0.0               # reward(chosen) - reward(rejected)
    source: str = "within_call"       # PREF_SOURCES
    survived_swap: bool = True        # pairwise judge agreed under A/B swap (position-bias check)
    confidence: float = 0.0
    compliant: bool = True            # chosen passed the Tier-1 hard gate
    outcome_anchored: bool = False    # chosen sits on a real converted call
    campaign_id: str = ""

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso),
            "tenant_id": str(self.tenant_id)[:120],
            "pair_id": str(self.pair_id or new_id("pair_"))[:40],
            "state_embedding_id": str(self.state_embedding_id or "")[:40],
            "objection_type": str(self.objection_type or "none")[:32],
            "lead_temperature": str(self.lead_temperature or "unknown")[:16],
            "regime": str(self.regime or "steady")[:24],
            "vertical": str(self.vertical or "real_estate")[:40],
            "chosen_text": (self.chosen_text or "")[:600],
            "rejected_text": (self.rejected_text or "")[:600],
            "chosen_move_id": str(self.chosen_move_id or "")[:80],
            "rejected_move_id": str(self.rejected_move_id or "")[:80],
            "margin": _f(self.margin),
            "source": str(self.source or "within_call")[:24],
            "survived_swap": _u8(self.survived_swap),
            "confidence": _f(self.confidence),
            "compliant": _u8(self.compliant),
            "outcome_anchored": _u8(self.outcome_anchored),
            "campaign_id": str(self.campaign_id or "")[:120],
        })

    def _state_preamble(self) -> str:
        """A rendered state prompt so an exported completion is conditioned on WHERE it was said."""
        return (f"[caller objection={self.objection_type}; temperature={self.lead_temperature}; "
                f"regime={self.regime}; vertical={self.vertical}] respond as the agent:")

    def to_export(self) -> dict:
        """JSONL row for a PAIRED DPO/SimPO export (chosen/rejected on the same prompt)."""
        return {"prompt": self._state_preamble(), "chosen": self.chosen_text,
                "rejected": self.rejected_text, "objection": self.objection_type,
                "temperature": self.lead_temperature, "vertical": self.vertical,
                "source": self.source, "confidence": self.confidence}

    def to_kto_rows(self) -> list:
        """UNPAIRED {prompt, completion, label} rows for a KTO export (B7) — the moat is natively
        unpaired/binary, so KTO keeps BOTH sides as separate signals (DPO would force-pair and throw
        most data away + amplify length bias). A non-compliant chosen is NEVER exported as desirable.
        Synthetic (sim_self_play) / rubric_pairwise rows carry low confidence so training can
        down-weight them vs real outcome-anchored rows."""
        rows = []
        pre = self._state_preamble()
        meta = {"tenant_id": self.tenant_id, "vertical": self.vertical,
                "objection": self.objection_type, "temperature": self.lead_temperature,
                "source": self.source, "confidence": self.confidence,
                "outcome_anchored": self.outcome_anchored}
        if self.chosen_text and self.compliant:           # desirable (skip a non-compliant 'chosen')
            rows.append({"prompt": pre, "completion": self.chosen_text, "label": True, **meta})
        if self.rejected_text:                             # undesirable
            rows.append({"prompt": pre, "completion": self.rejected_text, "label": False, **meta})
        return rows


# --------------------------------------------------------------------------- #
# ArmPosterior — hierarchical Thompson-sampling bandit state (per knob, per arm).
# --------------------------------------------------------------------------- #
@dataclass
class ArmPosterior:
    tenant_id: str = ""
    campaign_id: str = ""
    vertical: str = "real_estate"
    knob: str = "variant"             # KNOBS
    arm_id: str = ""
    context_bucket: str = "all"       # e.g. lead_temperature bucket
    ts_iso: str = ""
    alpha: float = 1.0                # Beta(alpha, beta) success pseudo-count
    beta: float = 1.0                 # failure pseudo-count
    plays: int = 0
    reward_sum: float = 0.0
    last_reward_ts: str = ""
    discounted: float = 0.0           # discounted reward mass (non-stationarity)
    guardrail_optout_rate: float = 0.0
    guardrail_cost_per_booking: float = 0.0

    def mean(self) -> float:
        tot = self.alpha + self.beta
        return round(self.alpha / tot, 4) if tot > 0 else 0.0

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso),
            "tenant_id": str(self.tenant_id)[:120],
            "campaign_id": str(self.campaign_id or "")[:120],
            "vertical": str(self.vertical or "real_estate")[:40],
            "knob": str(self.knob or "variant")[:24],
            "arm_id": str(self.arm_id or "")[:120],
            "context_bucket": str(self.context_bucket or "all")[:40],
            "alpha": _f(self.alpha, 1.0),
            "beta": _f(self.beta, 1.0),
            "plays": int(self.plays or 0),
            "reward_sum": _f(self.reward_sum),
            "last_reward_ts": ch_ts(self.last_reward_ts) if self.last_reward_ts else ch_ts(self.ts_iso),
            "discounted": _f(self.discounted),
            "guardrail_optout_rate": _f(self.guardrail_optout_rate),
            "guardrail_cost_per_booking": _f(self.guardrail_cost_per_booking),
        })


# --------------------------------------------------------------------------- #
# MovePRMRow — per-move process reward model P(book | move at state).
# --------------------------------------------------------------------------- #
@dataclass
class MovePRMRow:
    tenant_id: str = ""
    vertical: str = "real_estate"
    move_type: str = "other"
    objection_type: str = "none"
    regime: str = "steady"
    lead_temperature: str = "unknown"
    ts_iso: str = ""
    book_rate: float = 0.0            # P(book | this move at this state)
    baseline_rate: float = 0.0       # cohort base rate
    lift: float = 0.0                # book_rate - baseline_rate (the +/- signal)
    n_samples: int = 0
    ci_low: float = 0.0
    ci_high: float = 0.0

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso),
            "tenant_id": str(self.tenant_id)[:120],
            "vertical": str(self.vertical or "real_estate")[:40],
            "move_type": str(self.move_type or "other")[:32],
            "objection_type": str(self.objection_type or "none")[:32],
            "regime": str(self.regime or "steady")[:24],
            "lead_temperature": str(self.lead_temperature or "unknown")[:16],
            "book_rate": _f(self.book_rate),
            "baseline_rate": _f(self.baseline_rate),
            "lift": _f(self.lift),
            "n_samples": int(self.n_samples or 0),
            "ci_low": _f(self.ci_low),
            "ci_high": _f(self.ci_high),
        })


# --------------------------------------------------------------------------- #
# Challenger — a gated policy-change proposal (the only path to a new champion).
# --------------------------------------------------------------------------- #
@dataclass
class Challenger:
    tenant_id: str = ""
    challenger_id: str = ""
    ts_iso: str = ""
    kind: str = "variant"             # CHALLENGER_KINDS
    campaign_id: str = ""
    proposed_config_json: str = ""    # the candidate variant/prompt config
    rationale: str = ""               # human-readable "why this should win"
    ope_snips_value: float = 0.0      # off-policy estimate from logged calls
    gates_passed: bool = False        # run_all_gates().passed
    replay_delta: float = 0.0         # cost-per-appointment delta vs champion
    shadow_ok: bool = False
    status: str = "proposed"          # CHALLENGER_STATES
    approved_by: str = ""
    reward_lift: float = 0.0          # estimated reward lift vs champion
    ttft_ms: int = 0                  # latency budget check (voice cares about TTFT)
    cost_per_appointment: float = 0.0
    # --- power-up tier ---
    sim_reward_lift: float = 0.0      # B5 simulator pre-eval lift (advisory gate step 0)
    sim_preeval_json: str = ""        # B5 per-archetype sim scorecard
    ope_cs_lower: float = 0.0         # B2 anytime-valid OPE confidence-sequence bounds
    ope_cs_upper: float = 0.0
    reward_cs_lower: float = 0.0      # B2 reward CS lower bound (must clear champion's upper)
    optout_cs_upper: float = 0.0      # B2 opt-out CS upper (must stay under the ceiling)
    seq_significant: bool = False     # B2 always-valid separation reached (safe-to-promote signal)
    practical_sig: bool = False       # B2 lift exceeds the minimum practical delta
    # --- B7 distill (a self-hosted shadow challenger, NEVER the live hosted model) ---
    adapter_uri: str = ""             # QLoRA adapter artifact location
    base_model: str = ""              # the open base it was trained on
    method: str = ""                  # kto | simpo | dpo
    serving_endpoint: str = ""        # self-hosted vLLM shadow endpoint
    is_shadow: bool = False           # MUST be True for a distilled model (frozen-live-LLM law)

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso),
            "tenant_id": str(self.tenant_id)[:120],
            "challenger_id": str(self.challenger_id or new_id("ch_"))[:40],
            "kind": str(self.kind or "variant")[:24],
            "campaign_id": str(self.campaign_id or "")[:120],
            "proposed_config_json": (self.proposed_config_json or "")[:4000],
            "rationale": (self.rationale or "")[:600],
            "ope_snips_value": _f(self.ope_snips_value),
            "gates_passed": _u8(self.gates_passed),
            "replay_delta": _f(self.replay_delta),
            "shadow_ok": _u8(self.shadow_ok),
            "status": str(self.status or "proposed")[:24],
            "approved_by": str(self.approved_by or "")[:120],
            "reward_lift": _f(self.reward_lift),
            "ttft_ms": int(self.ttft_ms or 0),
            "cost_per_appointment": _f(self.cost_per_appointment),
            "sim_reward_lift": _f(self.sim_reward_lift),
            "sim_preeval_json": (self.sim_preeval_json or "")[:2000],
            "ope_cs_lower": _f(self.ope_cs_lower),
            "ope_cs_upper": _f(self.ope_cs_upper),
            "reward_cs_lower": _f(self.reward_cs_lower),
            "optout_cs_upper": _f(self.optout_cs_upper),
            "seq_significant": _u8(self.seq_significant),
            "practical_sig": _u8(self.practical_sig),
            "adapter_uri": str(self.adapter_uri or "")[:300],
            "base_model": str(self.base_model or "")[:80],
            "method": str(self.method or "")[:24],
            "serving_endpoint": str(self.serving_endpoint or "")[:200],
            "is_shadow": _u8(self.is_shadow),
        })


# --------------------------------------------------------------------------- #
# HumanLabel — the triggered RLHF human-label queue.
# --------------------------------------------------------------------------- #
@dataclass
class HumanLabel:
    tenant_id: str = ""
    call_id: str = ""
    turn_num: int = 0
    ts_iso: str = ""
    trigger: str = "low_conf_pivotal"  # LABEL_TRIGGERS
    label: str = ""                   # human verdict (good/bad/specific tag); blank = unlabeled
    labeler: str = ""
    rationale: str = ""
    used_for_calibration: bool = False

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso),
            "tenant_id": str(self.tenant_id)[:120],
            "call_id": str(self.call_id)[:120],
            "turn_num": int(self.turn_num or 0),
            "trigger": str(self.trigger or "low_conf_pivotal")[:40],
            "label": str(self.label or "")[:40],
            "labeler": str(self.labeler or "")[:120],
            "rationale": (self.rationale or "")[:600],
            "used_for_calibration": _u8(self.used_for_calibration),
        })


# --------------------------------------------------------------------------- #
# MonitorPoint — the degrading-flywheel (Goodhart canary) detectors.
# --------------------------------------------------------------------------- #
@dataclass
class MonitorPoint:
    tenant_id: str = ""
    ts_iso: str = ""
    metric: str = ""                  # MONITOR_METRICS
    value: float = 0.0
    arm_id: str = ""
    threshold_breached: bool = False

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso),
            "tenant_id": str(self.tenant_id)[:120],
            "metric": str(self.metric or "")[:40],
            "value": _f(self.value),
            "arm_id": str(self.arm_id or "")[:120],
            "threshold_breached": _u8(self.threshold_breached),
        })


# =========================================================================== #
# POWER-UP TIER dataclasses (B1–B7). Each mirrors a new flywheel_* table; to_row() drops None.
# =========================================================================== #
@dataclass
class MoveCATERow:
    """B4 — doubly-robust X-learner CATE per (move, state): the booking lift CAUSED by playing a
    move above its segment base rate, with an honest CI. Stored beside the correlational raw_lift."""
    tenant_id: str = ""
    vertical: str = "real_estate"
    move_type: str = "other"
    objection_type: str = "none"
    regime: str = "steady"
    lead_temperature: str = "unknown"
    ts_iso: str = ""
    cate: float = 0.0                 # causal effect (DR X-learner)
    cate_se: float = 0.0
    cate_lower: float = 0.0           # the PESSIMISTIC promotion signal: act only when cate_lower>0
    cate_upper: float = 0.0
    raw_lift: float = 0.0             # the old correlational PRM lift (side-by-side for the console)
    n_treated: int = 0
    n_control: int = 0
    overlap_min: float = 0.0          # min logged propensity in the cell (<0.02 ⇒ untrustworthy)
    estimator: str = "dr_xlearner"
    sign_agree: bool = True           # DR-X and R-learner agree on the sign (else not robust)

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "vertical": str(self.vertical or "real_estate")[:40], "move_type": str(self.move_type)[:32],
            "objection_type": str(self.objection_type)[:32], "regime": str(self.regime)[:24],
            "lead_temperature": str(self.lead_temperature)[:16],
            "cate": _f(self.cate), "cate_se": _f(self.cate_se), "cate_lower": _f(self.cate_lower),
            "cate_upper": _f(self.cate_upper), "raw_lift": _f(self.raw_lift),
            "n_treated": int(self.n_treated or 0), "n_control": int(self.n_control or 0),
            "overlap_min": _f(self.overlap_min), "estimator": str(self.estimator)[:24],
            "sign_agree": _u8(self.sign_agree),
        })


@dataclass
class CriticModel:
    """B3 — a trained V(state)→P(book) critic (coefficients + Platt calibration), latest per tenant."""
    tenant_id: str = ""
    vertical: str = "real_estate"
    ts_iso: str = ""
    model_type: str = "logistic"
    coef_json: str = ""               # serialized weights / feature spec
    platt_a: float = 1.0
    platt_b: float = 0.0
    auc: float = 0.0
    ece: float = 1.0                  # expected calibration error (auto-disables on breach)
    n_rows: int = 0
    active: bool = False              # only a calibrated model (low ECE, AUC>0.55) is used live

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "vertical": str(self.vertical or "real_estate")[:40], "model_type": str(self.model_type)[:24],
            "coef_json": (self.coef_json or "")[:8000], "platt_a": _f(self.platt_a, 1.0),
            "platt_b": _f(self.platt_b), "auc": _f(self.auc), "ece": _f(self.ece, 1.0),
            "n_rows": int(self.n_rows or 0), "active": _u8(self.active),
        })


@dataclass
class PolicyModel:
    """B6 — a contextual LinTS per-state selector (per-arm sufficient stats + OPE), latest per tenant."""
    tenant_id: str = ""
    campaign_id: str = ""
    vertical: str = "real_estate"
    ts_iso: str = ""
    knob: str = "rebuttal"
    n_features: int = 0
    arms_json: str = ""               # {template_id: {A_flat, b_vec, plays}}
    ope_snips: float = 0.0
    ope_fqe: float = 0.0
    ope_magic: float = 0.0
    ope_lower: float = 0.0            # pessimistic min over the 3-leg OPE (gate reads this)
    active: bool = False

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "campaign_id": str(self.campaign_id or "")[:120], "vertical": str(self.vertical)[:40],
            "knob": str(self.knob or "rebuttal")[:24], "n_features": int(self.n_features or 0),
            "arms_json": (self.arms_json or "")[:60000], "ope_snips": _f(self.ope_snips),
            "ope_fqe": _f(self.ope_fqe), "ope_magic": _f(self.ope_magic), "ope_lower": _f(self.ope_lower),
            "active": _u8(self.active),
        })


@dataclass
class PlayTemplate:
    """B6 — the data-defined per-tenant rebuttal/play action space the contextual policy selects over."""
    tenant_id: str = ""
    template_id: str = ""
    ts_iso: str = ""
    objection_type: str = "none"
    text: str = ""
    label: str = ""
    active: bool = True

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "template_id": str(self.template_id or new_id("tpl_"))[:60],
            "objection_type": str(self.objection_type)[:32], "text": (self.text or "")[:600],
            "label": str(self.label or "")[:80], "active": _u8(self.active),
        })


@dataclass
class ArchetypeRow:
    """B5 — a mined caller archetype (intent + affect template + temperament) the simulator role-plays."""
    tenant_id: str = ""
    archetype_id: str = ""
    ts_iso: str = ""
    label: str = ""
    objection_hist_json: str = ""
    affect_template_json: str = ""
    temperament: str = ""
    base_book_rate: float = 0.0
    weight: float = 1.0               # coverage up-weight for HARD archetypes (anti-Goodhart)
    n_calls: int = 0

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "archetype_id": str(self.archetype_id or new_id("arc_"))[:60], "label": str(self.label)[:80],
            "objection_hist_json": (self.objection_hist_json or "")[:2000],
            "affect_template_json": (self.affect_template_json or "")[:2000],
            "temperament": str(self.temperament)[:40], "base_book_rate": _f(self.base_book_rate),
            "weight": _f(self.weight, 1.0), "n_calls": int(self.n_calls or 0),
        })


@dataclass
class SimRolloutRow:
    """B5 — one simulated rollout (audit). Sim is FILTER-ONLY: never promotes, only proposes/removes."""
    tenant_id: str = ""
    ts_iso: str = ""
    archetype_id: str = ""
    challenger_id: str = ""
    policy_label: str = ""
    sim_outcome: str = ""
    sim_reward: float = 0.0
    turns: int = 0
    usi: float = 0.0                  # user-simulator informativeness
    ece: float = 1.0                  # calibration of the sim vs real outcomes (self-disable gate)
    notes: str = ""

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "archetype_id": str(self.archetype_id)[:60], "challenger_id": str(self.challenger_id)[:40],
            "policy_label": str(self.policy_label)[:80], "sim_outcome": str(self.sim_outcome)[:40],
            "sim_reward": _f(self.sim_reward), "turns": int(self.turns or 0), "usi": _f(self.usi),
            "ece": _f(self.ece, 1.0), "notes": (self.notes or "")[:400],
        })


@dataclass
class DistillRun:
    """B7 — a KTO/SimPO QLoRA training run (audit). The adapter ships ONLY as a shadow challenger."""
    tenant_id: str = ""
    run_id: str = ""
    ts_iso: str = ""
    method: str = "kto"
    base_model: str = ""
    n_desirable: int = 0
    n_undesirable: int = 0
    status: str = "exported"          # exported | training | trained | failed
    adapter_uri: str = ""
    metrics_json: str = ""

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "run_id": str(self.run_id or new_id("run_"))[:40], "method": str(self.method)[:24],
            "base_model": str(self.base_model)[:80], "n_desirable": int(self.n_desirable or 0),
            "n_undesirable": int(self.n_undesirable or 0), "status": str(self.status)[:24],
            "adapter_uri": (self.adapter_uri or "")[:300], "metrics_json": (self.metrics_json or "")[:2000],
        })


@dataclass
class SequentialState:
    """B2 — persisted running sufficient stats for the anytime-valid promotion test (survives the
    worker restarting between daily peeks; latest per (tenant, challenger, metric))."""
    tenant_id: str = ""
    challenger_id: str = ""
    ts_iso: str = ""
    metric: str = "reward"            # reward | ope | optout
    n: int = 0
    running_mean: float = 0.0
    running_var: float = 0.0
    cs_lower: float = 0.0
    cs_upper: float = 0.0
    significant: bool = False

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "challenger_id": str(self.challenger_id)[:40], "metric": str(self.metric)[:24],
            "n": int(self.n or 0), "running_mean": _f(self.running_mean), "running_var": _f(self.running_var),
            "cs_lower": _f(self.cs_lower), "cs_upper": _f(self.cs_upper), "significant": _u8(self.significant),
        })


@dataclass
class ConformalCalib:
    """B2 — a Mondrian (group-conditional) split-conformal q_hat per cohort bucket; latest per key."""
    tenant_id: str = ""
    model_key: str = ""               # 'judge' | 'critic' | ...
    bucket: str = "all"               # (campaign, lead_temperature, vertical) composite
    ts_iso: str = ""
    q_hat: float = 0.0
    alpha: float = 0.1
    n_calib: int = 0

    def to_row(self) -> dict:
        return _drop_none({
            "ts": ch_ts(self.ts_iso), "tenant_id": str(self.tenant_id)[:120],
            "model_key": str(self.model_key)[:40], "bucket": str(self.bucket)[:120],
            "q_hat": _f(self.q_hat), "alpha": _f(self.alpha, 0.1), "n_calib": int(self.n_calib or 0),
        })


__all__ = [
    "MOVE_TYPES", "OBJECTION_TYPES", "LEAD_TEMPERATURES", "KNOBS", "PREF_SOURCES",
    "CHALLENGER_STATES", "CHALLENGER_KINDS", "LABEL_TRIGGERS", "MONITOR_METRICS",
    "now_iso", "ch_ts", "new_id", "digest_id",
    "RewardComponents", "TrajectoryRow", "PreferencePair", "ArmPosterior",
    "MovePRMRow", "Challenger", "HumanLabel", "MonitorPoint",
    "MoveCATERow", "CriticModel", "PolicyModel", "PlayTemplate", "ArchetypeRow",
    "SimRolloutRow", "DistillRun", "SequentialState", "ConformalCalib",
]
