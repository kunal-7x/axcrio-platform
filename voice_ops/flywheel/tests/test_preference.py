"""Tests for voice_ops.flywheel.preference — the (chosen, rejected) MOAT mining.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_preference
Validates the PROPERTIES that keep the preference dataset honest:
  * state_bucket is stable + deterministic (same state -> same 16-char key across re-runs),
    and falls back cleanly on junk coordinates instead of fragmenting buckets;
  * mine_matched_state pairs an OUTCOME-ANCHORED, compliant winning move (chosen) against a
    non-anchored / negative move (rejected) in the SAME state bucket (anti-survivorship);
  * coverage_grid returns the {objection: {temperature: count}} density map shape.
NO network, NO ClickHouse, NO OPENROUTER — pure synthetic inputs.
"""
from __future__ import annotations

from voice_ops.flywheel.preference import (
    _MIN_MATCHED_MARGIN, coverage_grid, mine_matched_state, mine_within_call,
    state_bucket,
)


def test_state_bucket_is_deterministic_and_stable():
    b1 = state_bucket("price", "hot", "spike")
    b2 = state_bucket("price", "hot", "spike")
    assert b1 == b2, (b1, b2)
    assert len(b1) == 16, b1
    # different coordinates -> different bucket.
    assert state_bucket("loan", "hot", "spike") != b1


def test_state_bucket_junk_coordinates_fall_back_cleanly():
    """Unknown / empty coordinates fall back to the canonical enum defaults rather than
    fragmenting the bucket space, but still yield a stable 16-char key."""
    b = state_bucket("___bad___", "___bad___", "steady")
    assert len(b) == 16, b
    # a junk objection/temperature collapses to ('none','unknown',...) — same as passing those.
    assert b == state_bucket("none", "unknown", "steady")


def test_mine_matched_state_pairs_anchored_chosen_vs_nonanchored_rejected():
    """The cross-call moat: in ONE state bucket, an outcome-anchored compliant winning move is
    the `chosen`; a non-anchored / losing move is the `rejected`. The pair must be flagged as
    outcome_anchored + compliant, with a margin above the matched-state threshold."""
    bkey = state_bucket("loan", "warm", "steady")
    grouped = {
        bkey: [
            {"text": "Loan ke liye hum pre-approved bank tie-up provide karte hain.",
             "reward": 1.2, "outcome_anchored": True, "compliant": True, "move_id": "callA:3",
             "campaign_id": "c1", "regime": "steady", "objection_type": "loan",
             "lead_temperature": "warm", "tenant_id": "t_demo"},
            {"text": "Loan aapka problem hai, mujhe kya.",
             "reward": -0.7, "outcome_anchored": False, "compliant": True, "move_id": "callB:5",
             "campaign_id": "c1", "regime": "steady", "objection_type": "loan",
             "lead_temperature": "warm", "tenant_id": "t_demo"},
        ]
    }
    pairs = mine_matched_state(grouped)
    assert len(pairs) == 1, pairs
    p = pairs[0]
    assert p.source == "matched_state"
    assert p.outcome_anchored is True and p.compliant is True
    assert p.margin > _MIN_MATCHED_MARGIN, p.margin
    # the anchored winner is chosen; the losing/non-anchored move is rejected.
    assert "pre-approved" in p.chosen_text
    assert "problem hai" in p.rejected_text
    assert p.chosen_move_id == "callA:3" and p.rejected_move_id == "callB:5"


def test_mine_matched_state_needs_both_pools():
    """No outcome-anchored chosen OR no rejected candidate -> no pair (we never fabricate one)."""
    bkey = state_bucket("trust", "cold", "steady")
    only_anchored = {
        bkey: [
            {"text": "Hum RERA registered hain, verified docs bhej deta hoon.", "reward": 1.0,
             "outcome_anchored": True, "compliant": True, "move_id": "x:1", "objection_type": "trust",
             "lead_temperature": "cold", "tenant_id": "t"},
            {"text": "RERA number aapko WhatsApp pe bhej rahi hoon.", "reward": 0.9,
             "outcome_anchored": True, "compliant": True, "move_id": "x:2", "objection_type": "trust",
             "lead_temperature": "cold", "tenant_id": "t"},
        ]
    }
    assert mine_matched_state(only_anchored) == []


def test_coverage_grid_shape():
    """coverage_grid -> {objection_type: {lead_temperature: count}} over a list of pairs."""
    meta = {"tenant_id": "t", "campaign_id": "c1", "call_id": "call_42",
            "vertical": "real_estate", "lead_temperature": "hot", "outcome_anchored": True}
    within = mine_within_call([
        {"turn_num": 1, "agent_text": "Sir, RERA-registered project hai, verified docs bhej deta hoon.",
         "objection_type": "rera", "lead_temperature": "hot", "state_regime": "steady",
         "credit_advantage": 0.9, "compliant": True},
        {"turn_num": 2, "agent_text": "Arre bas haan bol do, last unit hai, abhi nahi to gaya!",
         "objection_type": "rera", "lead_temperature": "hot", "state_regime": "steady",
         "credit_advantage": -0.4, "compliant": False},
    ], meta)
    grid = coverage_grid(within)
    assert isinstance(grid, dict)
    assert grid.get("rera", {}).get("hot") == 1, grid
    # empty input -> empty grid (never raises).
    assert coverage_grid([]) == {}


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_preference OK")


if __name__ == "__main__":
    _run_all()
