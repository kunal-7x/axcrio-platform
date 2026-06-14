"""Offline test for trunk_registry.concurrency (T2, NEW) — in-process counter + velocity throttle.

Spec acceptance (TELEPHONY-INDEPENDENCE-PLAN §2.4 + §3 red-team A1/A2/A3/A4/C-rel + §2.5 velocity):
  * per-trunk max_concurrency cap is NEVER oversold (atomic check-and-reserve under one lock — A2);
  * a channel NEVER leaks on a crash/raise (acquire/release paired in try/finally — A1);
  * the BOX-GLOBAL cap (A4) is enforced across trunks in this process;
  * GSM: a single SIM/DID carries at most ONE call (A3);
  * VELOCITY throttle (the stronger spam signal): per-DID min spacing + per-DID calls/hour ceiling.

Pure in-memory; a fake clock drives the velocity windows deterministically (no sleeping). The
box is uvicorn --workers 1, so this in-process counter is authoritative — NOT the fail-open
Redis :6380 (red-team C-rel).

Run: python -m trunk_registry.tests.test_concurrency_offline
"""
from __future__ import annotations

import os
import sys


def run() -> int:
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"UNEXPECTED {type(e).__name__}: {e}"))

    # Tight, deterministic knobs for the test (call-time env reads — config is never cached).
    os.environ["TRUNK_REGISTRY_ENABLED"] = "1"
    os.environ["TRUNK_BOX_GLOBAL_CONCURRENCY"] = "5"
    os.environ["TRUNK_VELOCITY_MIN_SPACING_S"] = "8"
    os.environ["TRUNK_VELOCITY_CALLS_PER_HOUR"] = "3"

    from trunk_registry import concurrency as cc

    A = "tenant-A"
    T1 = "trunk-1"
    T2 = "trunk-2"
    DID = "+918071583488"
    DID2 = "+918071583499"

    # A fake monotonic clock so velocity windows are deterministic.
    class Clock:
        def __init__(self):
            self.t = 1000.0

        def __call__(self):
            return self.t

    # ===================== per-trunk cap is never oversold (A2) =====================
    def t_trunk_cap_no_oversell():
        cc.reset_all()
        clk = Clock()
        leases = []
        # cap=3 on T1; fire 5 acquires spaced past the velocity gap on DISTINCT dids so velocity
        # never blocks — the ONLY limiter under test is the per-trunk cap.
        ok_count = 0
        for i in range(5):
            clk.t += 100  # well past spacing
            lease = cc.acquire(A, T1, f"+9180000000{i}", max_concurrency=3, now_fn=clk)
            leases.append(lease)
            if lease.ok:
                ok_count += 1
        assert ok_count == 3, f"per-trunk cap=3 must allow exactly 3, got {ok_count}"
        full = [l for l in leases if not l.ok]
        assert all(l.reason == "trunk_full" for l in full), [l.reason for l in full]
        for l in leases:
            cc.release(l)
        # after release, the trunk is free again
        snap = cc.snapshot(A, T1)
        assert snap["trunk_active"] == 0, snap
    check("per_trunk_cap_no_oversell", t_trunk_cap_no_oversell)

    # ===================== release frees a slot; no leak on try/finally (A1) =====================
    def t_release_no_leak():
        cc.reset_all()
        clk = Clock()
        lease = cc.acquire(A, T1, DID, max_concurrency=1, now_fn=clk)
        assert lease.ok
        # next acquire on same trunk (distinct DID, past spacing) is blocked (cap=1 full)
        clk.t += 100
        blocked = cc.acquire(A, T1, DID2, max_concurrency=1, now_fn=clk)
        assert not blocked.ok and blocked.reason == "trunk_full", blocked.reason
        # simulate a crash AFTER acquire -> the finally releases
        try:
            raise RuntimeError("boom mid-call")
        except RuntimeError:
            cc.release(lease)
        clk.t += 100
        # the slot is free now
        again = cc.acquire(A, T1, DID2, max_concurrency=1, now_fn=clk)
        assert again.ok, "after release a channel must be reusable (no leak)"
        cc.release(again)
    check("release_in_finally_no_channel_leak", t_release_no_leak)

    # ===================== double-release / None-release is a safe no-op =====================
    def t_double_release_safe():
        cc.reset_all()
        clk = Clock()
        lease = cc.acquire(A, T1, DID, max_concurrency=2, now_fn=clk)
        assert lease.ok
        cc.release(lease)
        cc.release(lease)   # double release -> no-op (must NOT drive the counter negative)
        cc.release(None)    # None -> no-op
        snap = cc.snapshot(A, T1)
        assert snap["trunk_active"] == 0 and snap["box_active"] == 0, snap
    check("double_release_is_safe_noop", t_double_release_safe)

    # ===================== box-global cap (A4) across trunks =====================
    def t_box_global_cap():
        cc.reset_all()
        clk = Clock()
        # box cap = 5. Spread acquires across two trunks with big per-trunk caps + distinct DIDs.
        held = []
        ok = 0
        for i in range(7):
            clk.t += 100
            trunk = T1 if i % 2 == 0 else T2
            lease = cc.acquire(A, trunk, f"+91999000{i:03d}", max_concurrency=50, now_fn=clk)
            held.append(lease)
            if lease.ok:
                ok += 1
        assert ok == 5, f"box-global cap=5 must allow exactly 5 across trunks, got {ok}"
        assert any(l.reason == "box_full" for l in held if not l.ok), \
            [l.reason for l in held if not l.ok]
        for l in held:
            cc.release(l)
        assert cc.snapshot()["box_active"] == 0
    check("box_global_cap_across_trunks", t_box_global_cap)

    # ===================== GSM: 1 SIM/DID = 1 call (A3) =====================
    def t_gsm_did_busy():
        cc.reset_all()
        clk = Clock()
        # a GSM trunk: even with max_concurrency=8, ONE DID can only carry ONE call.
        l1 = cc.acquire(A, T1, DID, max_concurrency=8, is_gsm=True, now_fn=clk)
        assert l1.ok
        clk.t += 100  # past spacing
        l2 = cc.acquire(A, T1, DID, max_concurrency=8, is_gsm=True, now_fn=clk)
        assert not l2.ok and l2.reason == "gsm_did_busy", l2.reason
        # a DIFFERENT DID on the same GSM trunk is fine (a 2nd SIM)
        clk.t += 100
        l3 = cc.acquire(A, T1, DID2, max_concurrency=8, is_gsm=True, now_fn=clk)
        assert l3.ok, "a second GSM SIM/DID may carry its own call"
        cc.release(l1); cc.release(l3)
    check("gsm_one_sim_one_call", t_gsm_did_busy)

    # ===================== velocity: per-DID min spacing =====================
    def t_velocity_spacing():
        cc.reset_all()
        clk = Clock()
        l1 = cc.acquire(A, T1, DID, max_concurrency=10, now_fn=clk)
        assert l1.ok
        cc.release(l1)  # release so the per-trunk cap is NOT the limiter
        # immediately try again on the SAME DID, < 8s spacing -> velocity_spacing
        clk.t += 3  # < 8s
        l2 = cc.acquire(A, T1, DID, max_concurrency=10, now_fn=clk)
        assert not l2.ok and l2.reason == "velocity_spacing", l2.reason
        # wait past the spacing -> allowed
        clk.t += 10  # now 13s since the first start
        l3 = cc.acquire(A, T1, DID, max_concurrency=10, now_fn=clk)
        assert l3.ok, "past the min spacing the same DID may dial again"
        cc.release(l3)
    check("velocity_per_did_spacing", t_velocity_spacing)

    # ===================== velocity: per-DID calls/hour ceiling =====================
    def t_velocity_hourly_cap():
        cc.reset_all()
        clk = Clock()
        # ceiling = 3 calls/hour for one DID. Space each past the 8s gap; the 4th is capped.
        ok = 0
        for i in range(5):
            clk.t += 20  # past spacing each time
            lease = cc.acquire(A, T1, DID, max_concurrency=10, now_fn=clk)
            if lease.ok:
                ok += 1
                cc.release(lease)  # release immediately so only velocity limits
            else:
                assert lease.reason == "velocity_hourly_cap", lease.reason
        assert ok == 3, f"per-DID hourly cap=3 must allow exactly 3, got {ok}"
        # after the rolling hour passes, the window resets
        clk.t += 3601
        lease = cc.acquire(A, T1, DID, max_concurrency=10, now_fn=clk)
        assert lease.ok, "after the hour window the DID may dial again"
        cc.release(lease)
    check("velocity_per_did_hourly_cap", t_velocity_hourly_cap)

    # ===================== flag-independent: counter works regardless (it is mechanical) =====
    def t_snapshot_shape():
        cc.reset_all()
        snap = cc.snapshot()
        assert snap["box_active"] == 0 and snap["box_cap"] == 5, snap
    check("snapshot_non_secret_shape", t_snapshot_shape)

    return _report("TRUNK-CONCURRENCY", results)


def _report(suite, results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        if not ok:
            print(f"[{suite}] FAIL {name}: {msg}")
    print(f"[{suite}] {passed}/{total} PASS")
    return 0 if passed == total else 1


def test_trunk_concurrency_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
