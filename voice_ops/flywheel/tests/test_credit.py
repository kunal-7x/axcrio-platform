"""Tests for voice_ops.flywheel.credit — sparse-terminal CREDIT ASSIGNMENT.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_credit
Validates the PROPERTIES that make the credit split honest:
  * assign() returns exactly one advantage per turn (len == n);
  * a BOOKED terminal makes the LATE (near-close) turns MORE positive than the same turns
    under a LOST terminal — terminal credit really does flow to the moves near the close;
  * cohort_baseline floors std at 0.1 so a zero-variance cohort can't blow the z-score up;
  * wilson_ci is monotonic in n at a fixed proportion and n==0 -> (0,0) (no evidence, no CI).
NO network, NO ClickHouse — pure synthetic inputs.
"""
from __future__ import annotations

from voice_ops.flywheel.credit import (
    assign, cohort_baseline, mt_grpo_blend, wilson_ci,
)


def _flat_turns(n: int) -> list:
    """n turns with zero intermediate signal, so the per-turn advantage is pure terminal
    credit — isolating the terminal-decay geometry we want to assert on."""
    return [{"affect_delta": 0.0, "judge_score": 0.0} for _ in range(n)]


def test_assign_returns_one_advantage_per_turn():
    turns = _flat_turns(5)
    adv = assign(turns, terminal_reward=1.0, cohort=(0.0, 1.0))
    assert len(adv) == len(turns) == 5
    assert all(isinstance(x, float) for x in adv)


def test_assign_empty_is_empty():
    assert assign([], 1.0) == []


def test_booked_terminal_lifts_late_turns_above_a_lost_one():
    """The load-bearing property: a positive (booked) terminal reward pushes the LATE turns
    (those nearest the close, which claim the most terminal credit) MORE positive than the
    same late turns under a negative (lost) terminal reward."""
    turns = _flat_turns(6)
    cohort = (0.0, 1.0)
    booked = assign(turns, terminal_reward=2.0, cohort=cohort)   # strong positive outcome
    lost = assign(turns, terminal_reward=-1.0, cohort=cohort)    # negative outcome
    assert len(booked) == len(lost) == 6
    # The closing turn (last) must be more positive on a booking than on a loss.
    assert booked[-1] > lost[-1], (booked[-1], lost[-1])
    # And the *near-close tail* as a whole is lifted by a booking.
    assert sum(booked[-3:]) > sum(lost[-3:]), (booked[-3:], lost[-3:])
    # With zero intermediate signal, terminal credit increases toward the close on a booking.
    assert booked[0] < booked[-1], booked


def test_assign_is_deterministic():
    turns = [
        {"affect_delta": -2.0, "judge_score": 0.0},
        {"affect_delta": 1.0, "judge_score": 1.0},
        {"affect_delta": 3.0, "judge_score": 1.0},
    ]
    cohort = cohort_baseline([0.0, 1.0, 2.0])
    a1 = assign(turns, 2.0, cohort)
    a2 = assign(turns, 2.0, cohort)
    assert a1 == a2


def test_cohort_baseline_std_floor():
    """A zero-variance cohort must NOT produce std 0 (that would explode the outcome z-score);
    the std is floored at 0.1. Empty cohort -> a neutral (0.0, 0.1) baseline."""
    mu, sd = cohort_baseline([1.0, 1.0, 1.0])
    assert mu == 1.0 and sd == 0.1, (mu, sd)
    mue, sde = cohort_baseline([])
    assert mue == 0.0 and sde == 0.1, (mue, sde)
    # a real-variance cohort keeps its computed (>= floor) std.
    mu2, sd2 = cohort_baseline([0.0, 2.0])
    assert mu2 == 1.0 and sd2 >= 0.1, (mu2, sd2)


def test_wilson_ci_zero_n_is_no_interval():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_narrows_monotonically_with_n():
    """At a fixed proportion (70%) more evidence must NARROW the interval — a real CI gets
    tighter with n. We check the half-width shrinks as n grows."""
    widths = []
    for n in (10, 50, 200, 1000):
        lo, hi = wilson_ci(int(round(0.7 * n)), n)
        assert 0.0 <= lo <= 0.7 <= hi <= 1.0, (n, lo, hi)
        widths.append(hi - lo)
    # strictly decreasing widths as n increases.
    assert all(widths[i] > widths[i + 1] for i in range(len(widths) - 1)), widths


def test_wilson_ci_clamps_k_to_n_and_stays_in_unit_interval():
    lo, hi = wilson_ci(15, 10)  # k > n -> clamped
    assert hi == 1.0
    assert 0.0 <= lo <= hi <= 1.0


def test_mt_grpo_blend_shape_and_terminal_decay():
    blended = mt_grpo_blend([0.0, 0.0, 0.0], outcome_adv=1.0, alpha=0.6)
    assert len(blended) == 3
    # terminal credit must increase toward the close with zero intermediate signal.
    assert blended[0] < blended[1] < blended[2], blended
    assert mt_grpo_blend([], 1.0) == []


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_credit OK")


if __name__ == "__main__":
    _run_all()
