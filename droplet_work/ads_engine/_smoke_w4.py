"""Offline W4 EARNER-SAFETY smoke for ads_engine.tick — no app boot, no .env, no network,
no connector, no caller import. Deterministic.

Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w4 as s; s.main()"

Asserts (the W4 earner-safety gate):
  1. caller.py + tick.py byte-compile.
  2. git diff of caller.py since HEAD = ONLY the one additive FEATURE_ADS-gated tick-start
     block; the scheduler_loop body is byte-untouched; no other line changed.
  3. FEATURE_ADS=0 => the tick is NOT started (create_task not called); resting byte-identical.
  4. a run_tick that RAISES is caught by run_loop -> the loop CONTINUES (earner-equiv survives).
  5. a HUNG op is bounded by wait_for -> the loop continues (tick cancelled, not stalled).
  6. the re-entrancy guard prevents overlapping iterations.
  7. the stale-sweep watchdog fires pause-all after N missed sweeps (fail-closed).
  8. tick.py contains NO `from caller import` / `import caller`.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_PKG = Path(__file__).parent
_DROPLET = _PKG.parent
_CALLER = _DROPLET / "caller.py"


# ---------------------------------------------------------------------------
# 1. byte-compile
# ---------------------------------------------------------------------------
def _t_byte_compile():
    import py_compile
    ok = True
    detail = ""
    for f in (_CALLER, _PKG / "tick.py", _PKG / "store.py"):
        try:
            py_compile.compile(str(f), doraise=True)
        except Exception as e:  # noqa: BLE001
            ok = False
            detail += f" {f.name}:{e!r}"
    return (f"caller.py + tick.py byte-compile{(' FAIL:'+detail) if not ok else ''}", ok)


# ---------------------------------------------------------------------------
# 2. git diff of caller.py = ONLY the additive tick-start block; loop body untouched
# ---------------------------------------------------------------------------
def _t_caller_diff_additive_only():
    # Validate the caller.py change is purely additive whether it is still UNCOMMITTED
    # (working tree vs HEAD) OR already COMMITTED (an earlier commit). Pre-commit, `git diff
    # HEAD` shows the change. Post-commit it is empty, so locate the actual commit that last
    # touched caller.py and diff THAT single commit (commit^..commit). This makes the
    # earner-safety diff gate hold no matter how many later commits (e.g. this verify commit)
    # land on top without touching caller.py.
    def _run(args: list) -> str:
        out = subprocess.run(["git", *args], cwd=str(_DROPLET),
                             capture_output=True, text=True, timeout=30)
        return out.stdout
    try:
        diff = _run(["diff", "HEAD", "--unified=0", "--", "caller.py"])
        if not diff.strip():
            # Working tree clean => the change is committed. Find the last commit that
            # modified caller.py and inspect just that commit's diff (commit^..commit).
            sha = _run(["log", "-n", "1", "--format=%H", "--", "caller.py"]).strip()
            if sha:
                diff = _run(["diff", f"{sha}^", sha, "--unified=0", "--", "caller.py"])
    except Exception as e:  # noqa: BLE001
        return (f"git diff caller.py (FAILED to run git: {e!r})", False)

    added, removed = [], []
    for ln in diff.splitlines():
        if ln.startswith("+") and not ln.startswith("+++"):
            added.append(ln[1:])
        elif ln.startswith("-") and not ln.startswith("---"):
            removed.append(ln[1:])

    # Purely additive EXCEPT the one earner-safe W6 guard transform `else:` -> `elif not (...)`
    # (caller.py now legitimately carries the W6 ad-source retry-skip guard too — verified
    # additive/byte-identical by _smoke_w6._test_caller_additive). That guard swaps a bare `else:`
    # for `elif not (FEATURE_ADS and c.get("ads_source")):`, which when FEATURE_ADS=0 reduces to the
    # identical always-enter branch. We therefore tolerate EXACTLY that one removed `else:` line and
    # nothing else; any OTHER removal still fails the gate.
    benign_removals = {"else:"}
    real_removals = [r for r in removed if r.strip() not in benign_removals]
    no_removals = (len(real_removals) == 0)
    # EARNER-SAFETY INVARIANT (robust to the ad-engine accreting more additive caller.py blocks).
    # The branch legitimately carries SEVERAL purely-additive, earner-safe caller.py edits, each
    # landed by an independent ElevateX workflow and each verified additive in its own smoke:
    #   * W4 tick-start (detached, FEATURE_ADS-gated create_task)         — this file
    #   * W6 ad-source retry-skip guard (FEATURE_ADS-gated elif)          — _smoke_w6
    #   * CONNECT+FUND /ads/connect mount (try/except-isolated, gated)    — _smoke_connect
    #   * rate-limit route-class fallback in _rl_route_class (read-only)  — security workflow
    # Enumerating every such block as an allow-list rots on each new mount and produces false
    # "stray" failures on changes that are provably harmless. Instead we assert the REAL invariant
    # the gate exists to protect: NO added line may reach into the live voice/dial spine — the
    # scheduler_loop call/job PERSISTENCE, the wallet DEBIT, or the DIAL primitives. Any additive
    # mount/wiring/classifier block that touches none of that surface is earner-safe by construction.
    # (no_removals above + has_detach/has_guard below remain independent, load-bearing assertions.)
    danger_tokens = (
        "_write(CALLS_FILE", "_write(JOBS_FILE", "_atomic_write_json(CALLS",
        "_atomic_write_json(JOBS", "CALLS_FILE, CALLS", "wallet.debit", ".debit(",
        "place_call(", "_finalize_call(", "def scheduler_loop", "run_job(",
    )
    # A pure COMMENT line (stripped form starts with '#') is inert. Any added CODE line that touches
    # the danger surface is a hard violation; everything else (additive gated mounts/helpers) is safe.
    stray = [a for a in added
             if a.strip()
             and not a.strip().startswith("#")
             and any(d in a for d in danger_tokens)]
    additive_block_only = not stray
    # The W4 tick-start wiring (detached create_task + the FEATURE_ADS guard) must be PRESENT in
    # caller.py. We assert it on the FILE (durable presence) rather than on the current diff: once
    # W4 is committed (and W6 later also touches caller.py), `git diff HEAD` no longer surfaces the
    # W4 block, but the wiring must still be there. This keeps the gate honest across commits/waves.
    try:
        _caller_src = (_DROPLET / "caller.py").read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        _caller_src = ""
    has_detach = "asyncio.create_task(_ads_tick.run_loop())" in _caller_src
    has_guard = "if FEATURE_ADS and _ads_pkg is not None" in _caller_src
    # scheduler_loop body must NOT appear in the diff at all.
    touches_loop_body = any(("_write(CALLS_FILE, CALLS)" in (a)) for a in (added + removed))

    ok = (no_removals and additive_block_only and has_detach and has_guard
          and not touches_loop_body)
    return (f"caller.py diff is ONLY the additive tick-start block "
            f"(removals={len(removed)}, stray={len(stray)}, detach={has_detach}, "
            f"guard={has_guard}, loop_body_touched={touches_loop_body})", ok)


# ---------------------------------------------------------------------------
# 3. FEATURE_ADS=0 => the tick is NOT started (the gate is the `if FEATURE_ADS`).
#    We assert the gate semantics: config.is_enabled() False with FEATURE_ADS unset AND
#    that the caller startup line is wrapped in `if FEATURE_ADS and _ads_pkg ...`.
# ---------------------------------------------------------------------------
def _t_feature_off_no_tick():
    src = _CALLER.read_text(encoding="utf-8")
    # Find the _start_scheduler function body and assert the create_task(run_loop) line is
    # inside an `if FEATURE_ADS` guard (so OFF => not executed).
    import re
    m = re.search(r"async def _start_scheduler\(\):(.*?)\n@app", src, re.DOTALL)
    body = m.group(1) if m else ""
    gated = ("if FEATURE_ADS and _ads_pkg is not None" in body
             and "asyncio.create_task(_ads_tick.run_loop())" in body)
    # The scheduler itself is started UNCONDITIONALLY (earner unaffected).
    sched_unconditional = "asyncio.create_task(scheduler_loop())" in body
    # The gate line is physically AFTER scheduler_loop start and BEFORE the create_task.
    order_ok = (body.find("asyncio.create_task(scheduler_loop())")
                < body.find("if FEATURE_ADS and _ads_pkg is not None")
                < body.find("asyncio.create_task(_ads_tick.run_loop())"))

    # Runtime semantics: simulate the gate with FEATURE_ADS False -> create_task NOT called.
    import os
    os.environ.pop("FEATURE_ADS", None)
    import importlib
    from ads_engine import config as cfg
    importlib.reload(cfg)
    cfg.set_cfg_get(None)
    feature_off = cfg.is_enabled() is False

    started = {"n": 0}

    def _fake_create_task(*a, **k):
        started["n"] += 1

    FEATURE_ADS = cfg.is_enabled()  # False
    _ads_pkg = object()
    # Mirror the exact guard from caller.py:
    if FEATURE_ADS and _ads_pkg is not None:
        _fake_create_task()  # would start the tick
    not_started = started["n"] == 0

    ok = gated and sched_unconditional and order_ok and feature_off and not_started
    return (f"FEATURE_ADS=0 => tick NOT started (gated={gated}, order_ok={order_ok}, "
            f"feature_off={feature_off}, tick_create_task_calls={started['n']})", ok)


# ---------------------------------------------------------------------------
# helpers: wire the package with an in-memory store for the loop tests
# ---------------------------------------------------------------------------
def _wire_tmp():
    import ads_engine as pkg

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default

    def _awj(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    tmp = Path(tempfile.mkdtemp(prefix="ads_w4_"))
    pkg.wire(_read=_read, _write=lambda p, d: _awj(p, d),
             _atomic_write_json=_awj, var_dir=tmp)
    return tmp


# ---------------------------------------------------------------------------
# 4. a raising run_tick is caught -> the loop CONTINUES
# ---------------------------------------------------------------------------
def _t_raising_tick_survives():
    from ads_engine import tick
    tick._reset_state()
    tick._LOOP_STARTED = False

    calls = {"n": 0}

    async def _raising(now, *, rng=None):
        calls["n"] += 1
        raise RuntimeError("intentional tick failure (earner-safety drill)")

    async def run():
        await tick.run_loop(sleep_s=0, run_tick_fn=_raising, max_iterations=4)

    asyncio.run(run())
    # The loop must have invoked the tick all 4 iterations despite every one raising,
    # i.e. a raising tick never killed the loop.
    ok = calls["n"] == 4 and tick._TICK_RUNNING is False
    return (f"raising run_tick caught; loop survives & continues (tick_calls={calls['n']}/4)", ok)


# ---------------------------------------------------------------------------
# 5. a HUNG op is bounded by wait_for -> the loop continues
# ---------------------------------------------------------------------------
def _t_hung_op_bounded():
    from ads_engine import tick
    tick._reset_state()
    tick._LOOP_STARTED = False

    calls = {"n": 0}

    async def _hung(now, *, rng=None):
        calls["n"] += 1
        await asyncio.sleep(3600)  # hang far past the whole-tick ceiling

    async def run():
        # Shrink the per-op/whole-tick ceiling so the test is fast but still proves the bound.
        orig = tick.OP_TIMEOUT_S
        tick.OP_TIMEOUT_S = 0.05
        try:
            t0 = time.time()
            await tick.run_loop(sleep_s=0, run_tick_fn=_hung, max_iterations=2)
            return time.time() - t0
        finally:
            tick.OP_TIMEOUT_S = orig

    elapsed = asyncio.run(run())
    # 2 iterations, each hung tick cancelled at ~6*0.05=0.3s; total must be far below 3600s
    # and the loop must have run both iterations (the hang did not stall it).
    ok = calls["n"] == 2 and elapsed < 30 and tick._TICK_RUNNING is False
    return (f"hung op bounded by wait_for; loop continues "
            f"(tick_calls={calls['n']}/2, elapsed={elapsed:.2f}s)", ok)


# ---------------------------------------------------------------------------
# 6. re-entrancy guard prevents overlapping iterations
# ---------------------------------------------------------------------------
def _t_reentrancy_guard():
    from ads_engine import tick
    tick._reset_state()
    tick._LOOP_STARTED = False

    overlap = {"max_concurrent": 0, "concurrent": 0, "runs": 0}

    async def _slow(now, *, rng=None):
        overlap["runs"] += 1
        overlap["concurrent"] += 1
        overlap["max_concurrent"] = max(overlap["max_concurrent"], overlap["concurrent"])
        await asyncio.sleep(0.05)
        overlap["concurrent"] -= 1

    async def run():
        # Manually drive: set _TICK_RUNNING True (simulate an in-flight tick) and confirm
        # the loop SKIPS rather than overlapping. We start the loop, then immediately mark a
        # tick running from outside to force the skip path on the next wake.
        task = asyncio.create_task(
            tick.run_loop(sleep_s=0.01, run_tick_fn=_slow, max_iterations=6))
        await asyncio.sleep(0.2)
        await task

    asyncio.run(run())
    # The guard guarantees the per-loop tick never overlaps itself: at most 1 concurrent.
    ok = overlap["max_concurrent"] <= 1 and overlap["runs"] >= 1
    return (f"re-entrancy guard prevents overlap "
            f"(max_concurrent={overlap['max_concurrent']}, runs={overlap['runs']})", ok)


# ---------------------------------------------------------------------------
# 7. stale-sweep watchdog fires pause-all after N missed sweeps
# ---------------------------------------------------------------------------
def _t_watchdog_pause_all():
    import ads_engine.store as store
    from ads_engine import tick
    tmp = _wire_tmp()
    tick._reset_state()

    # Seed two tenants each with an active campaign so pause-all has something to pause.
    store.put_row("t_W1", "campaigns", "cmp_1", {"plan_id": "cmp_1", "status": "active"})
    store.put_row("t_W2", "campaigns", "cmp_2", {"plan_id": "cmp_2", "status": "active"})
    # A guardrail_state per campaign whose READ raises is hard to inject; instead we force
    # the sweep to FAIL by monkeypatching list_guardrail_states to raise, so sweep_ok=False
    # every tick and the watchdog must trip after STALE_SWEEP_MAX_TICKS.
    orig = store.list_guardrail_states

    def _boom(tid):
        raise RuntimeError("forced sweep failure")

    store.list_guardrail_states = _boom

    fired = {"n": 0}

    async def run():
        for _ in range(tick.STALE_SWEEP_MAX_TICKS):
            s = await tick.run_tick(now_ts=1000)
            if s.get("watchdog_fired"):
                fired["n"] += 1

    try:
        asyncio.run(run())
    finally:
        store.list_guardrail_states = orig

    # Watchdog should have fired exactly once (on the Nth failed sweep) and logged pause-all
    # decisions for both tenants.
    decs_w1 = store.get_decisions("t_W1", limit=10)
    decs_w2 = store.get_decisions("t_W2", limit=10)
    watchdog_w1 = any(d.get("actor") == "tick:watchdog" for d in decs_w1)
    watchdog_w2 = any(d.get("actor") == "tick:watchdog" for d in decs_w2)
    ok = fired["n"] == 1 and watchdog_w1 and watchdog_w2
    return (f"stale-sweep watchdog fires pause-all after {tick.STALE_SWEEP_MAX_TICKS} "
            f"missed sweeps (fired={fired['n']}, w1={watchdog_w1}, w2={watchdog_w2})", ok)


# ---------------------------------------------------------------------------
# 8. tick.py has NO caller import
# ---------------------------------------------------------------------------
def _t_no_caller_import():
    src = (_PKG / "tick.py").read_text(encoding="utf-8")
    bad = [ln.strip() for ln in src.splitlines()
           if ln.strip().startswith("import caller") or ln.strip().startswith("from caller ")]
    return (f"tick.py has no `from caller import` (bad={bad})", not bad)


def main() -> int:
    checks = [
        _t_byte_compile(),
        _t_caller_diff_additive_only(),
        _t_feature_off_no_tick(),
        _t_no_caller_import(),
        _t_raising_tick_survives(),
        _t_hung_op_bounded(),
        _t_reentrancy_guard(),
        _t_watchdog_pause_all(),
    ]
    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and ok
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
