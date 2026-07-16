"""Tests for voice_ops.flywheel.reward — the Layer-B reward FUSION + anti-Goodhart caps.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_reward
Validates the PROPERTIES that keep the reward HONEST and Goodhart-safe — not magic numbers:
  * a whale deal can NEVER push the terminal reward over reward_cap (saturation);
  * a WhatsApp opt-out maps to a strong negative terminal (revoked permission to contact);
  * affect shaping is sign-correct (friction DOWN -> positive), bounded to [-1, 1], and a
    low-confidence telephony turn shapes ~nothing (confidence gate);
  * fuse() always returns a provenance-carrying RewardComponents, never a bare float.
NO network, NO ClickHouse, NO OPENROUTER — pure synthetic inputs.
"""
from __future__ import annotations

from voice_ops.flywheel import config as _cfg
from voice_ops.flywheel.reward import (
    REWARD_TABLE, affect_delta_shaping, fuse, outcome_from_rec, terminal_reward,
)
from voice_ops.flywheel.schema import RewardComponents


def test_terminal_reward_whale_deal_cannot_exceed_cap():
    """The whole anti-Goodhart point: a fat-tailed deal value saturates (tanh + deal_cap)
    and is hard-clipped, so a single ₹-crore whale can never swamp the gradient."""
    cfg = _cfg.load()
    # A normal booking with a deal still amplifies the +1.0 base above 1.0 ...
    raw, capped = terminal_reward("site_visit_booked", 7_500_000, cfg)
    assert raw > 1.0, raw
    assert capped <= cfg.reward_cap, capped
    # ... but an absurd deal saturates: raw never exceeds the deal-multiplier cap, and the
    # capped value never exceeds reward_cap no matter how large the deal.
    big_raw, big_capped = terminal_reward("site_visit_booked", 10 ** 12, cfg)
    assert big_raw <= cfg.deal_cap + 1e-6, big_raw
    assert big_capped <= cfg.reward_cap, big_capped


def test_terminal_reward_negative_outcome_ignores_deal_and_floors_at_minus_one():
    """A big LOST deal must not read as 'extra bad' (which would teach the agent to avoid
    high-value leads). The deal multiplier only amplifies positives; negatives floor at -1."""
    cfg = _cfg.load()
    neg_raw, neg_capped = terminal_reward("lead_dead", 9_000_000, cfg)
    assert neg_capped == -1.0, neg_capped
    # raw equals the bare table value (no deal multiplier on a negative base).
    assert neg_raw == REWARD_TABLE["lead_dead"], neg_raw


def test_opt_out_maps_to_strong_negative():
    """A WhatsApp opt-out = the caller revoking permission to contact: the one terminal a
    growth-optimised agent must never be incentivised to risk. It is maximally negative."""
    o, _dv = outcome_from_rec({"outcome": "opt_out"})
    assert o == "whatsapp_opted_out", o
    assert REWARD_TABLE["whatsapp_opted_out"] == -1.0
    _raw, capped = terminal_reward("whatsapp_opted_out", 0.0)
    assert capped == -1.0, capped
    # it must be the (joint) most-negative entry in the whole table.
    assert REWARD_TABLE["whatsapp_opted_out"] == min(REWARD_TABLE.values())


def test_terminal_reward_unknown_outcome_is_zero():
    assert terminal_reward("???")[1] == 0.0
    assert terminal_reward("")[1] == 0.0


def test_affect_shaping_sign_friction_down_is_positive():
    """PBRS on caller friction: friction going DOWN over a turn (the caller relaxing) is a
    POSITIVE shaping signal; friction going UP is negative."""
    cfg = _cfg.load()
    down = affect_delta_shaping(70.0, 40.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    up = affect_delta_shaping(40.0, 70.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    assert down > 0, down
    assert up < 0, up


def test_affect_shaping_is_bounded_to_unit_interval():
    """A single turn's shaping can never dominate the bounded w_affect channel — it is
    clamped to [-1, 1] even on an extreme friction swing."""
    cfg = _cfg.load()
    extreme_down = affect_delta_shaping(100.0, 0.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    extreme_up = affect_delta_shaping(0.0, 100.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    assert -1.0 <= extreme_down <= 1.0, extreme_down
    assert -1.0 <= extreme_up <= 1.0, extreme_up


def test_affect_shaping_low_confidence_shapes_almost_nothing():
    """Confidence gate: a low-confidence (noisy telephony) turn with the SAME friction drop
    must shape MUCH less than a high-confidence one — we never shape on noise."""
    cfg = _cfg.load()
    high = affect_delta_shaping(70.0, 40.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    low = affect_delta_shaping(70.0, 40.0, confidence=0.05, friction_var=0.0, cfg=cfg)
    assert abs(low) < abs(high), (low, high)
    assert abs(low) < 0.05, low  # ~0 at near-zero confidence


def test_affect_shaping_high_variance_shapes_almost_nothing():
    """A wide uncertainty band (high friction_var) also attenuates the shaping toward 0."""
    cfg = _cfg.load()
    tight = affect_delta_shaping(70.0, 40.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    wide = affect_delta_shaping(70.0, 40.0, confidence=1.0, friction_var=50.0, cfg=cfg)
    assert abs(wide) < abs(tight), (wide, tight)


def test_affect_shaping_never_raises_on_junk():
    """Junk inputs (NaN friction, None, a non-numeric confidence) must be swallowed and
    coerced to safe defaults — the result is always a finite, bounded float, never a raise."""
    out = affect_delta_shaping(float("nan"), None, confidence="x")
    assert isinstance(out, float)
    assert -1.0 <= out <= 1.0, out


def test_fuse_returns_reward_components_with_provenance_fields():
    """fuse() must NEVER return a bare float — it returns a RewardComponents carrying the
    weights, the judge model id, the rubric version, the confidence and the disagreement flag
    so the console can always show *why* a turn scored what it did (honest science)."""
    cfg = _cfg.load()
    rc = fuse(0.8, affect_delta=0.3, judge_score=0.4,
              confidence=0.7, judge_model_id="anthropic/claude-3.5-sonnet",
              rubric_version="v1", disagreement=True, cfg=cfg)
    assert isinstance(rc, RewardComponents)
    # provenance fields present + populated.
    assert rc.terminal_credit == 0.8
    assert rc.affect_delta == 0.3
    assert rc.judge_score == 0.4
    assert rc.judge_model_id == "anthropic/claude-3.5-sonnet"
    assert rc.rubric_version == "v1"
    assert rc.confidence == 0.7
    assert rc.disagreement is True
    # weights carried from cfg.
    assert rc.w_outcome == cfg.w_outcome
    assert rc.w_affect == cfg.w_affect
    assert rc.w_judge == cfg.w_judge
    # fused == weighted sum of the three channels (provenance stays attached).
    expect = round(rc.w_outcome * 0.8 + rc.w_affect * 0.3 + rc.w_judge * 0.4, 5)
    assert abs(rc.fused() - expect) < 1e-9, (rc.fused(), expect)


def test_fuse_never_raises_on_junk_input():
    rc = fuse(float("nan"), affect_delta=None, judge_score="x")
    assert isinstance(rc, RewardComponents)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_reward OK")


if __name__ == "__main__":
    _run_all()
