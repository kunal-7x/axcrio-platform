"""Offline W3 smoke for ads_engine — bandit + allocator + guardrails + store. No app
boot, no .env, no network, no connector, no caller. Deterministic (seeded RNG).

Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w3 as s; s.main()"

Asserts (all from the W3 prompt's OFFLINE TESTS list):
  * bandit allocates more to the genuinely-better arm over rounds
  * best-arm confidence rises for a clear winner
  * guard precedence: a cap-breach overrides an active learning lock
  * only spend-decreasing auto-applies; scale needs approval
  * caps cannot be exceeded (spend-increasing over cap -> blocked)
  * reconciliation_factor is clamped to its band + denom floored
  * anomaly warm-up suppresses early false positives
  * per-tenant lock serializes (asyncio.Lock identity per key)
  * bandit_state is tenant-isolated via the store
  * op sub-budget exhausts and then fail-closes
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path


def _t_reconciliation_clamp():
    from ads_engine import optimization as opt
    # crm 100, platform 0 -> denom floored to 1, factor would be 100 -> clamped to MAX.
    f1 = opt.clamp_reconciliation(platform_reported=0.0, crm_true=100.0)
    # crm 1000, platform 1 -> 1000 -> clamped to MAX.
    f2 = opt.clamp_reconciliation(platform_reported=1.0, crm_true=1000.0)
    # crm 0, platform 100 -> 0 -> clamped to MIN.
    f3 = opt.clamp_reconciliation(platform_reported=100.0, crm_true=0.0)
    # in-band passes through.
    f4 = opt.clamp_reconciliation(platform_reported=100.0, crm_true=84.0)
    ok = (f1 == opt.RECON_FACTOR_MAX and f2 == opt.RECON_FACTOR_MAX
          and f3 == opt.RECON_FACTOR_MIN and abs(f4 - 0.84) < 1e-9)
    return (f"reconciliation_factor clamped+floored (f1={f1},f2={f2},f3={f3},f4={f4})", ok)


def _t_bandit_prefers_better_arm():
    from ads_engine import optimization as opt
    import numpy as np
    rng = np.random.default_rng(12345)
    st = opt.new_bandit_state("cmp_x", "t_demo")
    # Two arms: A truly better (CVR 0.20) vs B worse (CVR 0.04). Feed proxy=pcvr signal.
    for _ in range(400):
        # Arm A
        a_rew = 1.0 if rng.random() < 0.20 else 0.0
        opt.update_arm(st, "A", pcvr_calibrated=a_rew, observed_conv=a_rew,
                       expected_observed_fraction=1.0, crm_true_conv=a_rew,
                       platform_reported_conv=a_rew, impressions=1)
        # Arm B
        b_rew = 1.0 if rng.random() < 0.04 else 0.0
        opt.update_arm(st, "B", pcvr_calibrated=b_rew, observed_conv=b_rew,
                       expected_observed_fraction=1.0, crm_true_conv=b_rew,
                       platform_reported_conv=b_rew, impressions=1)
    best_id, conf = opt.best_arm_confidence(st, rng=rng)
    mean_a = st["arms"]["A"]["alpha"] / (st["arms"]["A"]["alpha"] + st["arms"]["A"]["beta"])
    mean_b = st["arms"]["B"]["alpha"] / (st["arms"]["B"]["alpha"] + st["arms"]["B"]["beta"])
    # TTTS selection over many draws should pick A more often.
    picks = [opt.select_arm(st, rng=rng) for _ in range(500)]
    a_share = picks.count("A") / len(picks)
    ok = (best_id == "A" and conf > 0.95 and mean_a > mean_b and a_share > 0.55)
    return (f"bandit prefers better arm (best={best_id}, conf={conf:.3f}, "
            f"meanA={mean_a:.3f}>meanB={mean_b:.3f}, A_share={a_share:.2f})", ok)


def _t_bandit_warmup_suppresses_early_kill():
    from ads_engine import optimization as opt
    import numpy as np
    rng = np.random.default_rng(7)
    st = opt.new_bandit_state("cmp_y", "t_demo")
    # Very few observations -> not warmed up -> propose must be HOLD only (no kill/scale).
    for _ in range(5):
        opt.update_arm(st, "A", pcvr_calibrated=1.0, observed_conv=1.0, impressions=1,
                       crm_true_conv=1.0, platform_reported_conv=1.0)
        opt.update_arm(st, "B", pcvr_calibrated=0.0, observed_conv=0.0, impressions=1)
    moves = opt.propose_bandit_moves(st, rng=rng)
    kinds = {m["move"] for m in moves}
    ok = kinds == {"hold"}
    return (f"warm-up suppresses early kill/scale (moves={sorted(kinds)})", ok)


def _t_guard_caps_cannot_be_exceeded():
    from ads_engine import guardrails as gr
    gstate = {
        "spend_today_minor": 280000, "daily_cap_minor": 300000,
        "conversion_tracking_ok": True, "conversions_observed": 10,
        "learning_lock": False,
    }
    # A scale move that would add 50000 -> 330000 > 300000 -> blocked_cap.
    move = {"plan_id": "cmp_x", "move": "scale_winner", "spend_delta_sign": +1,
            "spend_delta_minor": 50000}
    v = gr.evaluate(gstate, move)
    ok = (not v.allow) and v.blocked_by == gr.BLOCKED_CAP
    return (f"caps cannot be exceeded (blocked_by={v.blocked_by})", ok)


def _t_guard_precedence_cap_over_learning():
    from ads_engine import guardrails as gr
    # Learning lock ACTIVE *and* a cap breach. The cap (safety tier) must win,
    # and a safety PAUSE must run despite the learning lock (REDTEAM C4).
    gstate = {
        "learning_lock": True, "conv_7d": 3, "min_conv": 50,
        "spend_today_minor": 320000, "daily_cap_minor": 300000,
        "conversion_tracking_ok": True, "conversions_observed": 5,
    }
    # 1) A discretionary scale during a cap breach -> blocked by CAP (not learning).
    scale = {"plan_id": "c", "move": "scale_winner", "spend_delta_sign": +1,
             "spend_delta_minor": 1}
    v_scale = gr.evaluate(gstate, scale)
    cap_wins = (not v_scale.allow) and v_scale.blocked_by == gr.BLOCKED_CAP \
        and "daily_cap:deny" in v_scale.guard_chain
    # 2) The safety auto-pause runs EVEN with the learning lock active + cap over.
    pause = {"plan_id": "c", "move": "auto_pause", "spend_delta_sign": -1}
    v_pause = gr.evaluate(pause and gstate, pause)
    pause_runs = v_pause.allow and v_pause.auto_apply and v_pause.blocked_by is None
    ok = cap_wins and pause_runs
    return (f"cap-breach overrides learning lock; safety pause exempt "
            f"(cap_wins={cap_wins}, pause_runs={pause_runs})", ok)


def _t_only_decreasing_auto_applies():
    from ads_engine import guardrails as gr
    gstate = {"learning_lock": False, "daily_cap_minor": 0,
              "conversion_tracking_ok": True, "conversions_observed": 100}
    # kill_loser (spend-decreasing) auto-applies.
    kill = {"plan_id": "c", "move": "kill_loser", "spend_delta_sign": -1}
    v_kill = gr.evaluate(gstate, kill, op_budget_ok=True)
    # scale_winner (spend-increasing) needs approval.
    scale = {"plan_id": "c", "move": "scale_winner", "spend_delta_sign": +1,
             "spend_delta_minor": 1000}
    v_scale = gr.evaluate(gstate, scale)
    ok = (v_kill.allow and v_kill.auto_apply
          and v_scale.allow and not v_scale.auto_apply
          and v_scale.outcome == "deferred_pending_approval")
    return (f"only-decreasing auto-applies; scale needs approval "
            f"(kill_auto={v_kill.auto_apply}, scale_auto={v_scale.auto_apply})", ok)


def _t_learning_lock_blocks_discretionary():
    from ads_engine import guardrails as gr
    gstate = {"learning_lock": True, "conv_7d": 10, "min_conv": 50,
              "daily_cap_minor": 0, "conversion_tracking_ok": True,
              "conversions_observed": 10}
    kill = {"plan_id": "c", "move": "kill_loser", "spend_delta_sign": -1}
    v = gr.evaluate(gstate, kill)
    ok = (not v.allow) and v.blocked_by == gr.BLOCKED_LEARNING
    return (f"learning lock blocks discretionary kill (blocked_by={v.blocked_by})", ok)


def _t_tracking_gate_blocks_scale():
    from ads_engine import guardrails as gr
    gstate = {"learning_lock": False, "daily_cap_minor": 0,
              "conversion_tracking_ok": False, "conversions_observed": 0}
    scale = {"plan_id": "c", "move": "scale_winner", "spend_delta_sign": +1,
             "spend_delta_minor": 100}
    v = gr.evaluate(gstate, scale)
    ok = (not v.allow) and v.blocked_by == gr.BLOCKED_NO_TRACKING
    return (f"no-tracking blocks scale (blocked_by={v.blocked_by})", ok)


def _t_anomaly_warmup_suppresses():
    from ads_engine import guardrails as gr
    # Cold start: n small / std below floor -> NO anomaly flag despite a big observed value.
    cold = {"baselines": {"cpm_minor": {"mean": 20000, "std": 0.0, "n": 2}},
            "last_cpm_minor": 99999}
    a_cold = gr.detect_anomaly(cold)
    # Warmed: real baseline + a 5-sigma spike -> flag.
    warm = {"baselines": {"cpm_minor": {"mean": 20000, "std": 3000, "n": 50}},
            "last_cpm_minor": 50000}
    a_warm = gr.detect_anomaly(warm)
    ok = (a_cold["flag"] is False and a_warm["flag"] is True
          and a_warm["metric"] == "cpm_minor")
    return (f"anomaly warm-up suppresses early FP (cold={a_cold['flag']}, "
            f"warm={a_warm['flag']})", ok)


def _t_allocator_sum_within_budget():
    from ads_engine import optimization as opt
    alloc_state = {
        "account_id": "acct_1", "total_budget_minor": 1000000, "step_minor": 100000,
        "channels": {
            "meta:c1": {"history": [[100000, 2.0], [300000, 9.0], [500000, 11.0]],
                        "theta": 0.6, "alloc_minor": 200000},
            "meta:c2": {"history": [[100000, 1.0], [300000, 2.0], [500000, 2.5]],
                        "theta": 0.5, "alloc_minor": 200000},
        },
    }
    res = opt.propose_allocation(alloc_state, rng=42)
    total = sum(res["allocation"].values())
    # c1 has a much better response curve -> should get >= c2.
    a1 = res["allocation"]["meta:c1"]; a2 = res["allocation"]["meta:c2"]
    ok = total <= 1000000 and a1 >= a2 and res["solver"] == "gp_ucb_knapsack"
    return (f"allocator sum<=B and favors better channel (a1={a1}>=a2={a2}, tot={total})", ok)


def _t_knapsack_honors_min_bounds():
    from ads_engine import optimization as opt
    # c2 has a weak curve but a min bound; the allocator must still fund c2 >= its min,
    # never skip it below the floor (and total stays within budget).
    channels = ["c1", "c2"]
    levels = {
        "c1": [(0, 0.0), (100, 1.0), (200, 9.0), (300, 9.5)],
        "c2": [(0, 0.0), (100, 0.5), (200, 0.6), (300, 0.7)],
    }
    alloc = opt.knapsack_allocate(channels, levels, total_budget=400, step=100,
                                  min_bounds={"c2": 100}, max_bounds=None)
    total = sum(alloc.values())
    ok = alloc["c2"] >= 100 and total <= 400
    return (f"knapsack honors min bounds (c2={alloc['c2']}>=100, tot={total})", ok)


def _t_changepoint_resets():
    from ads_engine import optimization as opt
    # Stable then a big regime shift -> change-point trips.
    stable = [[1, 5.0], [2, 5.1], [3, 4.9], [4, 5.0]]
    shifted = [[1, 5.0], [2, 5.0], [3, 5.0], [4, 5.0], [5, 50.0], [6, 52.0], [7, 48.0], [8, 51.0]]
    ok = (opt.detect_change_point(stable) is False
          and opt.detect_change_point(shifted) is True)
    return (f"change-point detects regime shift (stable=False, shifted=True)", ok)


def _t_store_isolation_and_oplock(tmp: Path):
    import ads_engine as pkg
    import ads_engine.store as store

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _awj(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    pkg.wire(_read=_read, _write=lambda p, d: _awj(p, d),
             _atomic_write_json=_awj, var_dir=tmp)

    # bandit_state tenant isolation
    store.put_bandit_state("t_A", "cmp_1", {"campaign_id": "cmp_1", "secret": "A"})
    store.put_bandit_state("t_B", "cmp_1", {"campaign_id": "cmp_1", "secret": "B"})
    a = store.get_bandit_state("t_A", "cmp_1")
    b = store.get_bandit_state("t_B", "cmp_1")
    iso = (a["secret"] == "A" and b["secret"] == "B"
           and store.get_bandit_state("t_A", "nope") is None)

    # CAS rejects on stale version.
    row = store.get_bandit_state("t_A", "cmp_1")
    v = int(row.get("version", 0))
    cas_ok = False
    try:
        store.put_bandit_state("t_A", "cmp_1", {"campaign_id": "cmp_1", "x": 1},
                               expected_version=v + 99)  # wrong version
    except store.VersionConflict:
        cas_ok = True

    # decision_log append + newest-first read.
    store.append_decision("t_A", {"id": "d1", "campaign_id": "cmp_1", "decision": "hold"})
    store.append_decision("t_A", {"id": "d2", "campaign_id": "cmp_1", "decision": "kill_loser"})
    decs = store.get_decisions("t_A", limit=10)
    log_ok = len(decs) == 2 and decs[0]["id"] == "d2"  # newest first

    # op sub-budget: consume up to the limit, then fail-closed.
    consumed = sum(1 for _ in range(5)
                   if store.try_consume_op("t_A", "20260625", default_limit=3))
    op_ok = consumed == 3  # only 3 of 5 succeed

    ok = iso and cas_ok and log_ok and op_ok
    return (f"store tenant-iso + CAS + decision_log + op-budget "
            f"(iso={iso}, cas={cas_ok}, log={log_ok}, op={op_ok})", ok)


def _t_spend_lock_serializes():
    from ads_engine import guardrails as gr

    # Same key -> same lock object; different key -> different. And the lock actually
    # serializes a read-modify-write across awaits (no interleave -> final == N).
    l1 = gr.spend_lock("t_A", "acct_1")
    l2 = gr.spend_lock("t_A", "acct_1")
    l3 = gr.spend_lock("t_A", "acct_2")
    identity_ok = (l1 is l2) and (l1 is not l3)

    shared = {"n": 0}

    async def worker(lock):
        async with lock:
            cur = shared["n"]
            await asyncio.sleep(0)  # yield -> would interleave if unlocked
            shared["n"] = cur + 1

    async def run():
        lock = gr.spend_lock("t_X", "acct")
        await asyncio.gather(*[worker(lock) for _ in range(50)])

    asyncio.run(run())
    serial_ok = shared["n"] == 50
    ok = identity_ok and serial_ok
    return (f"per-tenant lock serializes (identity={identity_ok}, final={shared['n']}/50)", ok)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ads_w3_"))
    checks = [
        _t_reconciliation_clamp(),
        _t_bandit_prefers_better_arm(),
        _t_bandit_warmup_suppresses_early_kill(),
        _t_guard_caps_cannot_be_exceeded(),
        _t_guard_precedence_cap_over_learning(),
        _t_only_decreasing_auto_applies(),
        _t_learning_lock_blocks_discretionary(),
        _t_tracking_gate_blocks_scale(),
        _t_anomaly_warmup_suppresses(),
        _t_allocator_sum_within_budget(),
        _t_knapsack_honors_min_bounds(),
        _t_changepoint_resets(),
        _t_store_isolation_and_oplock(tmp),
        _t_spend_lock_serializes(),
    ]
    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and ok
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
