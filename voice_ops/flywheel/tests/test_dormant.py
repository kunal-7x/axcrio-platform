"""Tests for the DORMANT-SAFE design law of voice_ops.flywheel.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_dormant
The resting state of the package (FLYWHEEL_ENABLED unset / no ClickHouse / no OPENROUTER) must
be byte-identical to a deployment that never heard of the Flywheel:
  * config.active() is False;
  * store.insert_trajectories([...]) is a clean no-op that returns False and never raises;
  * the schema dataclasses still round-trip through to_row() (the wire contract is always live);
  * trajectory.capture_finalized(..., transcript=[...]) returns 0 and writes nothing without
    raising into the (dormant) finalize path.
This test ENFORCES dormancy: it clears the relevant env vars before asserting.
NO network, NO ClickHouse — pure synthetic inputs.
"""
from __future__ import annotations

import os

from voice_ops.flywheel import config as _cfg
from voice_ops.flywheel import store as _st
from voice_ops.flywheel import trajectory
from voice_ops.flywheel.schema import (
    ArmPosterior, Challenger, HumanLabel, MonitorPoint, MovePRMRow,
    PreferencePair, RewardComponents, TrajectoryRow,
)


# Env vars that could accidentally activate the package; clear them so the test asserts the
# true dormant resting state regardless of the developer's shell.
_ACTIVATION_ENV = (
    "FLYWHEEL_ENABLED",
    "FLYWHEEL_CLICKHOUSE_URL",
    "CLICKHOUSE_URL",
    "CLICKHOUSE_WRITE_URL",
)


def _force_dormant():
    for k in _ACTIVATION_ENV:
        os.environ.pop(k, None)


def test_config_active_is_false_when_unset():
    _force_dormant()
    assert _cfg.active() is False
    cfg = _cfg.load()
    assert cfg.enabled is False
    # status() is a plain dict that never raises and reports dormancy.
    st = cfg.status()
    assert isinstance(st, dict)


def test_insert_trajectories_is_a_noop_returning_false():
    _force_dormant()
    rows = [TrajectoryRow(tenant_id="t", call_id="c", turn_num=0, ts_iso="2026-06-25T10:00:00.000Z")]
    assert _st.insert_trajectories(rows) is False
    # every sync writer is dormant-safe + returns False (no-op), never raises.
    assert _st.insert_preferences([PreferencePair(tenant_id="t")]) is False
    assert _st.insert_posteriors([ArmPosterior(tenant_id="t", arm_id="A")]) is False
    assert _st.insert_move_prm([MovePRMRow(tenant_id="t")]) is False
    assert _st.insert_challengers([Challenger(tenant_id="t")]) is False
    assert _st.insert_human_labels([HumanLabel(tenant_id="t")]) is False
    assert _st.insert_monitors([MonitorPoint(tenant_id="t")]) is False
    # an empty list is also a clean no-op (never raises).
    assert _st.insert_trajectories([]) is False


def test_schema_dataclasses_still_round_trip_to_row():
    """The wire contract is ALWAYS live even when dormant — every dataclass serialises."""
    rc = RewardComponents(terminal_credit=0.8, affect_delta=0.2, judge_score=0.3)
    assert isinstance(rc.to_json(), str)
    assert isinstance(rc.fused(), float)

    rows = [
        TrajectoryRow(tenant_id="t", call_id="c", turn_num=1, ts_iso="2026-06-25T10:00:00.000Z",
                      low_conf=True),
        PreferencePair(tenant_id="t", pair_id="p1", chosen_text="a", rejected_text="b",
                       compliant=True, outcome_anchored=True),
        ArmPosterior(tenant_id="t", arm_id="A", alpha=2.0, beta=3.0, plays=5),
        MovePRMRow(tenant_id="t", move_type="cta_push", n_samples=10),
        Challenger(tenant_id="t", challenger_id="ch1", gates_passed=True),
        HumanLabel(tenant_id="t", call_id="c", turn_num=2, used_for_calibration=False),
        MonitorPoint(tenant_id="t", metric="optout_rate", value=0.03, threshold_breached=False),
    ]
    for obj in rows:
        row = obj.to_row()
        assert isinstance(row, dict) and row, (type(obj).__name__, row)
        # bools must be coerced to UInt8 (0/1), never python bools, in the wire row.
        for v in row.values():
            assert not isinstance(v, bool), (type(obj).__name__, row)


def test_capture_finalized_writes_nothing_and_never_raises_when_dormant():
    """The finalize hook is SYNC and must NEVER raise into the droplet's call-finalize path.
    When dormant it still BUILDS the seed rows (so the count is real) but the INSERT is a no-op."""
    _force_dormant()
    transcript = [
        {"speaker": "agent", "text": "Namaste, main Riya bol rahi hoon Prestige ki taraf se"},
        {"speaker": "caller", "text": "haan boliye"},
        {"speaker": "agent", "text": "Aapka budget kitna hai is project ke liye?"},
    ]
    rec = {"campaign_id": "camp_demo", "outcome": "site_visit_booked", "deal_value": 8_500_000.0}
    n = trajectory.capture_finalized("tenant_demo", "call_demo", rec, transcript)
    # two agent turns -> two seed rows built (the INSERT itself was a dormant no-op).
    assert n == 2, n

    # a totally empty record + no transcript still never raises; coarse fallback row.
    n2 = trajectory.capture_finalized("t", "c2", {}, None)
    assert isinstance(n2, int) and n2 >= 0, n2

    # garbage inputs (None rec, junk non-list transcript) must be swallowed and degrade to a
    # coarse seed (never a raise); the call still returns a clean non-negative int count.
    n3 = trajectory.capture_finalized("", "", None, "not-a-list")  # type: ignore[arg-type]
    assert isinstance(n3, int) and n3 >= 0, n3


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_dormant OK")


if __name__ == "__main__":
    _run_all()
