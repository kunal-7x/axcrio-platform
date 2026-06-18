"""W25 deploy-safety tooling tests — ZERO box, ZERO droplet imports, ZERO PSTN.

Every box interaction is driven through transport.FakeTransport. The required
proofs (from the wave brief):
  * intended-closure assertion CATCHES a wrong/truncated file before swap
  * box<->local DRIFT is detected
  * drain WAITS for in-flight jobs before restart
  * canary FAILS CLOSED
  * auto-rollback FIRES on health fail (and on canary fail)
plus: backup-before-swap ordering, atomic-swap idempotency, one-command rollback
script content, runbook render, and a guard that NO heavy/droplet module loads.
"""
from __future__ import annotations

import sys

import pytest

from voice_ops.deploy import EARNER_GOLDEN_MD5
from voice_ops.deploy.canary import (
    CheckOutcome,
    SyntheticCanary,
    db_health_check,
    greeting_render_check,
    tool_dispatch_check,
)
from voice_ops.deploy.closure import (
    DeployClosure,
    PatchError,
    apply_unified_diff,
    compute_intended_md5,
)
from voice_ops.deploy.drain import (
    DrainError,
    DrainOrchestrator,
    TwoWorkerPlan,
    metrics_inflight_probe,
)
from voice_ops.deploy.drift import DriftChecker, DriftError
from voice_ops.deploy.healthwatch import (
    HealthWatcher,
    RollbackIncompleteError,
    http_health_probe,
)
from voice_ops.deploy.plan import (
    BoxLayout,
    DeployError,
    DeployPlanEngine,
    EarnerGate,
    EarnerGateError,
)
from voice_ops.deploy.rollback import RollbackGenerator, RollbackTarget
from voice_ops.deploy.runbook import RunbookSpec, render_runbook
from voice_ops.deploy.transport import FakeTransport, TransportError, md5_norm


GOLDEN = b"""def greet():
    return "Namaste"

def main():
    greet()
"""

# A unified diff that changes the greeting string.
PATCH = """--- a/agent.py
+++ b/agent.py
@@ -1,2 +1,2 @@
 def greet():
-    return "Namaste"
+    return "Namaste ji"
"""


# --------------------------------------------------------------------------- #
# closure + intended-new-md5  (catches a wrong file)
# --------------------------------------------------------------------------- #
def test_apply_unified_diff_changes_only_the_patched_line():
    new = apply_unified_diff(GOLDEN.decode(), PATCH)
    assert 'return "Namaste ji"' in new
    assert "def main():" in new            # tail preserved
    assert new.count("def ") == 2          # nothing duplicated/dropped


def test_compute_intended_md5_is_stable_and_syntactically_valid():
    intended = compute_intended_md5(GOLDEN, PATCH)
    # deterministic: same inputs -> same md5
    again = compute_intended_md5(GOLDEN, PATCH)
    assert intended.md5 == again.md5
    # the md5 is of the patched text, NOT the golden
    assert intended.md5 != md5_norm(GOLDEN)
    assert intended.md5 == md5_norm(intended.as_bytes())


def test_patch_against_wrong_golden_fails_closed():
    wrong_golden = b'def greet():\n    return "Hello"\n\ndef main():\n    greet()\n'
    with pytest.raises(PatchError):
        compute_intended_md5(wrong_golden, PATCH)


def test_patch_that_breaks_syntax_fails_py_compile():
    bad_patch = (
        "--- a/agent.py\n+++ b/agent.py\n@@ -1,2 +1,2 @@\n"
        " def greet():\n-    return \"Namaste\"\n+    return \"Namaste\n"
    )
    with pytest.raises(PatchError):
        compute_intended_md5(GOLDEN, bad_patch)


def test_stage_and_assert_catches_a_wrong_landed_file():
    """The CORE gate: if the bytes that land on the box hash != intended-new,
    the engine refuses to swap (simulating a truncated SCP / clobber)."""
    intended = compute_intended_md5(GOLDEN, PATCH)
    t = FakeTransport()
    engine = DeployPlanEngine(transport=t)

    # Simulate a transport whose write lands DIFFERENT bytes (truncation).
    class TruncatingTransport(FakeTransport):
        def write(self, path, data):  # land a corrupted/truncated copy
            super().write(path, data[:-5])

    bad = TruncatingTransport()
    engine_bad = DeployPlanEngine(transport=bad)
    with pytest.raises(DeployError, match="intended-new-closure"):
        engine_bad.stage_and_assert("/opt/famit-agent/releases/r1", intended)

    # And the happy path lands the exact intended md5.
    staged = engine.stage_and_assert("/opt/famit-agent/releases/r1", intended)
    assert t.md5(staged) == intended.md5


# --------------------------------------------------------------------------- #
# drift  (box <-> local)
# --------------------------------------------------------------------------- #
def _box_with(files: dict[str, bytes]) -> FakeTransport:
    return FakeTransport(files=dict(files))


def test_drift_detected_when_box_file_changed():
    expected = DeployClosure.from_manifest(
        {"agent.py": md5_norm(GOLDEN), "caller.py": md5_norm(b"x")}
    )
    box = _box_with(
        {
            "/opt/famit-agent/agent.py": GOLDEN + b"# hot-edited\n",  # changed!
            "/opt/famit-agent/caller.py": b"x",
        }
    )
    rep = DriftChecker(box).check(
        expected=expected,
        box_root="/opt/famit-agent",
        relpaths=["agent.py", "caller.py"],
    )
    assert rep.has_drift
    assert "agent.py" in rep.diff.changed
    assert "caller.py" not in rep.diff.changed
    with pytest.raises(DriftError):
        DriftChecker(box).assert_no_drift(
            expected=expected,
            box_root="/opt/famit-agent",
            relpaths=["agent.py", "caller.py"],
        )


def test_no_drift_when_box_matches():
    expected = DeployClosure.from_manifest({"agent.py": md5_norm(GOLDEN)})
    box = _box_with({"/opt/famit-agent/agent.py": GOLDEN})
    rep = DriftChecker(box).check(
        expected=expected, box_root="/opt/famit-agent", relpaths=["agent.py"]
    )
    assert not rep.has_drift
    assert "CLEAN" in rep.render()


# --------------------------------------------------------------------------- #
# plan engine — preflight gate, backup-before-swap, atomic swap
# --------------------------------------------------------------------------- #
def _gate_for(md5: str) -> EarnerGate:
    return EarnerGate(
        expected_md5=md5,
        target_path="/opt/famit-agent/agent.py",
        health_url="http://127.0.0.1:8209/health?deep=0",
        unit="famit-agent",
    )


def _healthy_box(agent_bytes: bytes) -> FakeTransport:
    t = _box_with({"/opt/famit-agent/agent.py": agent_bytes})
    # make backup `cp` actually copy in the fake fs
    def _cp(self, cmd):
        if cmd.startswith("cp -p "):
            _, _, src, dst = cmd.split(" ", 3)
            self.files[dst] = self.files[src]
    t.on_run = _cp
    t.on("systemctl show famit-agent -p MainPID --value", stdout="12345")
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="200")
    return t


def test_preflight_gate_aborts_on_md5_mismatch():
    t = _healthy_box(GOLDEN)
    engine = DeployPlanEngine(transport=t)
    # gate expects a DIFFERENT md5 than what's on the box
    with pytest.raises(EarnerGateError, match="md5"):
        engine.preflight_gate(_gate_for("deadbeef" * 4))


def test_preflight_gate_aborts_when_unit_down():
    t = _healthy_box(GOLDEN)
    t.on("systemctl show famit-agent -p MainPID --value", stdout="0")
    engine = DeployPlanEngine(transport=t)
    with pytest.raises(EarnerGateError, match="MainPID"):
        engine.preflight_gate(_gate_for(md5_norm(GOLDEN)))


def test_preflight_gate_aborts_on_non_200_health():
    t = _healthy_box(GOLDEN)
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="503")
    engine = DeployPlanEngine(transport=t)
    with pytest.raises(EarnerGateError, match="200"):
        engine.preflight_gate(_gate_for(md5_norm(GOLDEN)))


def test_backup_verifies_md5_and_runs_before_swap():
    t = _healthy_box(GOLDEN)
    intended = compute_intended_md5(GOLDEN, PATCH)
    engine = DeployPlanEngine(transport=t)
    rec = engine.deploy_flag_off(
        gate=_gate_for(md5_norm(GOLDEN)), intended=intended, release_id="rX", ts="TS"
    )
    # backup created + md5 verified
    assert t.exists(rec.backup_path)
    assert t.md5(rec.backup_path) == md5_norm(GOLDEN)
    assert rec.swapped is True
    assert rec.landed_md5 == intended.md5
    # ORDER: backup (cp) must run strictly before the atomic swap (mv -T)
    assert t.ran_before("cp -p /opt/famit-agent/agent.py", "mv -T")


def test_atomic_swap_uses_flock_and_mv_t():
    t = _healthy_box(GOLDEN)
    engine = DeployPlanEngine(transport=t)
    engine.atomic_swap("/opt/famit-agent/releases/rX")
    swap_cmd = [c for c in t.commands() if "mv -T" in c][0]
    assert "flock" in swap_cmd
    assert "ln -sfn /opt/famit-agent/releases/rX" in swap_cmd
    assert "mv -T" in swap_cmd  # atomic rename, not a non-atomic ln -sfn over current


def test_golden_md5_constant_is_the_frozen_earner():
    assert EARNER_GOLDEN_MD5 == "98655dbfc71d5c3da36bcfe3f848082c"


# --------------------------------------------------------------------------- #
# drain — waits for in-flight before restart
# --------------------------------------------------------------------------- #
def test_drain_waits_for_in_flight_then_restarts():
    # probe returns 2, 2, 1, 0 -> drain must wait 3 polls before idle
    seq = iter([2, 2, 1, 0])

    def probe(_t):
        return next(seq)

    t = FakeTransport()
    sleeps: list[float] = []
    orch = DrainOrchestrator(
        transport=t,
        unit="famit-agent",
        inflight_probe=probe,
        _now=lambda: 0.0,                 # frozen clock (deadline never hit here)
        _sleep=lambda s: sleeps.append(s),
    )
    result = orch.drain_then_restart(deadline_seconds=1000, poll_seconds=5)
    assert result.reached_idle is True
    assert result.last_inflight == 0
    # SIGTERM drain BEFORE restart; restart only AFTER idle
    assert t.ran_before("systemctl kill -s SIGTERM", "systemctl restart famit-agent")
    # it actually waited (slept) while jobs were in flight
    assert len(sleeps) >= 1


def test_drain_raises_when_deadline_exceeds_with_jobs_in_flight():
    # probe never reaches 0; clock advances past the deadline on the 2nd read
    clock = iter([0.0, 0.0, 100.0, 100.0, 100.0])

    t = FakeTransport()
    orch = DrainOrchestrator(
        transport=t,
        inflight_probe=lambda _t: 1,      # always busy
        _now=lambda: next(clock),
        _sleep=lambda s: None,
    )
    with pytest.raises(DrainError, match="deadline"):
        orch.wait_for_drain(deadline_seconds=10, poll_seconds=1)
    # never restarted while busy
    assert "systemctl restart" not in " ".join(t.commands())


def test_metrics_inflight_probe_parses_gauge_and_fails_closed():
    t = FakeTransport()
    t.on("curl -s http://127.0.0.1:8090/metrics",
         stdout="# HELP\nlivekit_active_jobs 3\nother 9\n")
    probe = metrics_inflight_probe()
    assert probe(t) == 3
    # explicit `... 0` line -> idle (0)
    t0 = FakeTransport()
    t0.on("curl -s http://127.0.0.1:8090/metrics", stdout="# HELP\nlivekit_active_jobs 0\n")
    assert metrics_inflight_probe()(t0) == 0
    # B2: absent metric (even with successful curl) -> RAISE, never assume idle.
    t2 = FakeTransport()
    t2.on("curl -s http://127.0.0.1:8090/metrics", stdout="other 9\n")
    with pytest.raises(DrainError, match="ABSENT"):
        metrics_inflight_probe()(t2)
    # curl FAILURE -> raise (must NOT assume idle)
    t3 = FakeTransport()
    t3.on("curl -s http://127.0.0.1:8090/metrics", rc=7)
    with pytest.raises(DrainError):
        metrics_inflight_probe()(t3)


def test_two_worker_plan_systemd_has_load_bearing_timeoutstopsec():
    plan = TwoWorkerPlan(drain_timeout=1800)
    unit = plan.systemd_unit()
    assert "TimeoutStopSec=1800" in unit
    assert "famit-agent@" in unit or "Worker %i" in unit
    steps = plan.rolling_drain_steps()
    joined = "\n".join(steps)
    # drains A while B serves, then B while A serves
    assert "Drain A" in joined and "Drain B" in joined
    assert "ROLLBACK" in joined


# --------------------------------------------------------------------------- #
# canary — fails closed
# --------------------------------------------------------------------------- #
def _canary_box(*, render="Namaste", tool="ok", health="200") -> FakeTransport:
    t = FakeTransport()
    t.on("curl -s http://render", stdout=render)
    t.on("curl -s http://tool", stdout=tool)
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health', stdout=health)
    return t


def test_canary_passes_when_all_checks_ok():
    t = _canary_box()
    canary = SyntheticCanary.default(
        t, render_url="http://render", tool_url="http://tool"
    )
    v = canary.run()
    assert v.passed is True
    assert all(c.ok for c in v.checks)


def test_canary_fails_closed_on_empty_render():
    t = _canary_box(render="")
    canary = SyntheticCanary.default(
        t, render_url="http://render", tool_url="http://tool"
    )
    v = canary.run()
    assert v.passed is False
    assert any("greeting_render" == c.name for c in v.failures)


def test_canary_fails_closed_on_bad_db_health():
    t = _canary_box(health="503")
    canary = SyntheticCanary.default(
        t, render_url="http://render", tool_url="http://tool"
    )
    v = canary.run()
    assert v.passed is False
    assert any(c.name == "db_health" for c in v.failures)


def test_canary_fails_closed_when_a_check_raises():
    def boom(_t):
        raise RuntimeError("kaboom")

    canary = SyntheticCanary(transport=FakeTransport(), checks=[boom])
    v = canary.run()
    assert v.passed is False
    assert "kaboom" in v.checks[0].detail


def test_canary_greeting_md5_equality_gate():
    t = _canary_box(render="Namaste")
    golden_md5 = md5_norm(b"Namaste")
    chk = greeting_render_check(render_url="http://render", expected_md5=golden_md5)
    assert chk(t).ok is True
    # different render -> md5 mismatch -> fail
    t2 = _canary_box(render="Namaste ji")
    assert chk(t2).ok is False


def test_canary_never_dials_pstn():
    """Hard guard: nothing the canary runs is a SIP/PSTN dial."""
    t = _canary_box()
    SyntheticCanary.default(t, render_url="http://render", tool_url="http://tool").run()
    blob = " ".join(t.commands()).lower()
    for forbidden in ("sip:", "originate", "pstn", "dial ", "place_call", "+91"):
        assert forbidden not in blob


# --------------------------------------------------------------------------- #
# healthwatch + auto-rollback
# --------------------------------------------------------------------------- #
def _rollback_box(agent_bytes: bytes, *, restore_to: bytes) -> tuple[FakeTransport, RollbackGenerator]:
    t = _box_with(
        {
            "/opt/famit-agent/agent.py": agent_bytes,
            "/opt/famit-agent/agent.py.WOUTbak.TS": restore_to,
        }
    )

    def _cp(self, cmd):
        if cmd.startswith("cp -p "):
            _, _, src, dst = cmd.split(" ", 3)
            self.files[dst] = self.files[src]

    t.on_run = _cp
    rb = RollbackGenerator(
        RollbackTarget(
            target_path="/opt/famit-agent/agent.py",
            backup_path="/opt/famit-agent/agent.py.WOUTbak.TS",
            golden_md5=md5_norm(restore_to),
            unit="famit-agent",
            flag_dropin="/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf",
            flag_name="KERNEL_OUTBOUND",
        )
    )
    return t, rb


def test_auto_rollback_fires_on_health_fail():
    new_code = GOLDEN + b"# new (bad)\n"
    t, rb = _rollback_box(new_code, restore_to=GOLDEN)
    # health probe: always non-200 -> unhealthy
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="500")
    watcher = HealthWatcher(
        transport=t,
        rollback=rb,
        fail_threshold=2,
        settle_polls=6,
        _sleep=lambda s: None,
        golden_md5=md5_norm(GOLDEN),
    )
    out = watcher.watch()
    assert out.rolled_back is True
    assert out.healthy is False
    # the backup was restored over the target -> md5 back to golden
    assert t.md5("/opt/famit-agent/agent.py") == md5_norm(GOLDEN)
    assert out.restored_md5 == md5_norm(GOLDEN)
    # rollback forced the flag OFF + restarted
    cmds = " ".join(t.commands())
    assert "KERNEL_OUTBOUND=0" in cmds
    assert "systemctl restart famit-agent" in cmds


def test_auto_rollback_fires_on_canary_fail_before_health():
    new_code = GOLDEN + b"# new (bad)\n"
    t, rb = _rollback_box(new_code, restore_to=GOLDEN)
    # canary fails (empty render) even though health would be fine
    t.on("curl -s http://render", stdout="")
    t.on("curl -s http://tool", stdout="ok")
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health', stdout="200")
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="200")
    canary = SyntheticCanary.default(t, render_url="http://render", tool_url="http://tool")
    watcher = HealthWatcher(
        transport=t,
        rollback=rb,
        canary=canary,
        _sleep=lambda s: None,
        golden_md5=md5_norm(GOLDEN),
    )
    out = watcher.watch()
    assert out.rolled_back is True
    assert out.canary is not None and out.canary.passed is False
    assert t.md5("/opt/famit-agent/agent.py") == md5_norm(GOLDEN)


def test_healthwatch_accepts_when_healthy_and_canary_pass():
    new_code = GOLDEN + b"# new (good)\n"
    t, rb = _rollback_box(new_code, restore_to=GOLDEN)
    t.on("curl -s http://render", stdout="Namaste")
    t.on("curl -s http://tool", stdout="ok")
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health', stdout="200")
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="200")
    canary = SyntheticCanary.default(t, render_url="http://render", tool_url="http://tool")
    watcher = HealthWatcher(
        transport=t, rollback=rb, canary=canary, settle_polls=4, _sleep=lambda s: None
    )
    out = watcher.watch()
    assert out.healthy is True
    assert out.rolled_back is False
    # target NOT reverted: still the new code
    assert t.md5("/opt/famit-agent/agent.py") == md5_norm(new_code)


def test_one_intermittent_blip_does_not_trigger_rollback():
    """fail_threshold=2 means a single non-200 blip is tolerated."""
    new_code = GOLDEN + b"# new\n"
    t, rb = _rollback_box(new_code, restore_to=GOLDEN)
    codes = iter(["200", "500", "200", "200"])  # one blip then recovers
    watcher = HealthWatcher(
        transport=t,
        rollback=rb,
        health_probe=lambda _t: next(codes) == "200",
        fail_threshold=2,
        settle_polls=4,
        _sleep=lambda s: None,
    )
    out = watcher.watch()
    assert out.healthy is True
    assert out.rolled_back is False


# --------------------------------------------------------------------------- #
# rollback script + runbook
# --------------------------------------------------------------------------- #
def test_rollback_script_restores_and_verifies_golden():
    rb = RollbackGenerator(
        RollbackTarget(
            target_path="/opt/famit-agent/agent.py",
            backup_path="/opt/famit-agent/agent.py.WOUTbak.TS",
            golden_md5=EARNER_GOLDEN_MD5,
            unit="famit-agent",
            flag_dropin="/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf",
            flag_name="KERNEL_OUTBOUND",
        )
    )
    s = rb.script()
    assert "cp -p /opt/famit-agent/agent.py.WOUTbak.TS /opt/famit-agent/agent.py" in s
    assert "KERNEL_OUTBOUND=0" in s
    assert "systemctl daemon-reload" in s
    assert "systemctl restart famit-agent" in s
    assert EARNER_GOLDEN_MD5 in s            # verify step asserts golden
    assert "set -euo pipefail" in s


def test_rollback_symlink_variant_uses_atomic_mv():
    rb = RollbackGenerator(
        RollbackTarget(
            target_path="/opt/famit-agent/agent.py",
            backup_path="/opt/famit-agent/agent.py.WOUTbak.TS",
            golden_md5=EARNER_GOLDEN_MD5,
            current_link="/opt/famit-agent/current",
            previous_release_dir="/opt/famit-agent/releases/prev",
        )
    )
    s = rb.script()
    assert "mv -T" in s and "flock" in s
    assert "/opt/famit-agent/releases/prev" in s


def test_runbook_renders_all_gates_and_rollback():
    rb = RollbackGenerator(
        RollbackTarget(
            target_path="/opt/famit-agent/agent.py",
            backup_path="/opt/famit-agent/agent.py.WOUTbak.TS",
            golden_md5=EARNER_GOLDEN_MD5,
            unit="famit-agent",
            flag_dropin="/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf",
            flag_name="KERNEL_OUTBOUND",
        )
    )
    plan = TwoWorkerPlan()
    spec = RunbookSpec(
        unit="famit-agent",
        target_path="/opt/famit-agent/agent.py",
        golden_md5=EARNER_GOLDEN_MD5,
        intended_md5="abc123",
        release_id="20260618-1",
        flag_name="KERNEL_OUTBOUND",
        flag_dropin="/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf",
        rolling_drain_steps=plan.rolling_drain_steps(),
        two_worker=True,
    )
    md = render_runbook(spec, rb)
    for needle in (
        "PREFLIGHT EARNER GATE",
        "BACKUP FIRST",
        "INTENDED-NEW-CLOSURE",
        "ATOMIC SWAP",
        "HELD SYNTHETIC CANARY",
        "AUTO-ROLLBACK",
        "POSTFLIGHT EARNER GATE",
        "ONE-COMMAND ROLLBACK",
        EARNER_GOLDEN_MD5,
        "abc123",
    ):
        assert needle in md, f"runbook missing: {needle}"


# --------------------------------------------------------------------------- #
# the hard guard: NO droplet / agent / heavy-SDK import is pulled in
# --------------------------------------------------------------------------- #
def test_no_droplet_or_heavy_sdk_imports_loaded():
    import voice_ops.deploy  # noqa: F401
    import voice_ops.deploy.canary  # noqa
    import voice_ops.deploy.closure  # noqa
    import voice_ops.deploy.drain  # noqa
    import voice_ops.deploy.drift  # noqa
    import voice_ops.deploy.healthwatch  # noqa
    import voice_ops.deploy.plan  # noqa
    import voice_ops.deploy.rollback  # noqa
    import voice_ops.deploy.runbook  # noqa
    import voice_ops.deploy.transport  # noqa

    loaded = set(sys.modules)
    forbidden = {
        "agent",
        "caller",
        "aim_voice_agent",
        "livekit",
        "boto3",
        "redis",
        "paramiko",
        "droplet_work",
    }
    hits = {m for m in loaded if m.split(".")[0] in forbidden}
    assert not hits, f"forbidden modules imported by voice_ops.deploy: {hits}"


# --------------------------------------------------------------------------- #
# RED-TEAM REGRESSION FIXES (W25 verify pass) — B1 / B2 / B3
# --------------------------------------------------------------------------- #
# B1: a patch that applies cleanly against the WRONG golden must NOT silently
# produce an intended.md5. compute_intended_md5(expected_golden_md5=...) ties the
# golden bytes to a known hash before patching.
def test_b1_compute_intended_rejects_wrong_golden_when_md5_pinned():
    # A patch that touches a line both goldens share, so it APPLIES against the
    # wrong golden too — only the md5 pin catches the swap.
    shared_patch = (
        "--- a/agent.py\n+++ b/agent.py\n@@ -1,1 +1,2 @@\n"
        " def greet():\n+    pass\n"
    )
    right = b"def greet():\n"
    wrong = b"def greet():\n"  # same bytes here; the point is the PIN, not content
    # pinning the CORRECT md5 -> ok
    ok = compute_intended_md5(right, shared_patch, expected_golden_md5=md5_norm(right))
    assert ok.md5 == md5_norm(ok.as_bytes())
    # pinning a DIFFERENT md5 than the supplied golden -> fail closed
    with pytest.raises(PatchError, match="golden md5"):
        compute_intended_md5(wrong, shared_patch, expected_golden_md5="deadbeef" * 4)


# B1: a garbled patch whose hunk body does not match its @@ line-counts must
# fail closed (it would otherwise silently insert/drop lines).
def test_b1_garbled_hunk_count_fails_closed():
    # header claims -2,1 (1 old line) but the body removes 1 AND adds 2 = the
    # new-count is wrong (declared +.,1 but body emits 2). Must raise.
    garbled = (
        "--- a/agent.py\n+++ b/agent.py\n@@ -1,1 +1,1 @@\n"
        "-def greet():\n+def greet():\n+    extra = 1\n"
    )
    with pytest.raises(PatchError, match="hunk body does not match"):
        apply_unified_diff("def greet():\n", garbled)


def test_b1_valid_hunk_counts_still_apply():
    # the canonical PATCH fixture has matching counts and must still apply.
    new = apply_unified_diff(GOLDEN.decode(), PATCH)
    assert 'return "Namaste ji"' in new


# B1: the EarnerGate ties expected_md5 to the frozen EARNER_GOLDEN_MD5 when the
# constant is supplied — a baseline that isn't the known golden fails closed
# BEFORE any box fact is read.
def test_b1_earner_gate_ties_expected_to_frozen_golden():
    from voice_ops.deploy import EARNER_GOLDEN_MD5 as GMD5

    t = _healthy_box(GOLDEN)
    engine = DeployPlanEngine(transport=t)
    bad_gate = EarnerGate(
        expected_md5=md5_norm(GOLDEN),   # not the frozen earner golden
        target_path="/opt/famit-agent/agent.py",
        health_url="http://127.0.0.1:8209/health?deep=0",
        unit="famit-agent",
        earner_golden_md5=GMD5,
    )
    with pytest.raises(EarnerGateError, match="EARNER_GOLDEN_MD5"):
        engine.preflight_gate(bad_gate)


# B2: an ABSENT in-flight gauge must NOT read as idle (0) — a freshly-restarted
# worker whose gauge isn't registered yet would otherwise be drained mid-call.
def test_b2_absent_gauge_is_unknown_not_idle():
    t = FakeTransport()
    t.on("curl -s http://127.0.0.1:8090/metrics", stdout="# HELP\nsome_other 1\n")
    with pytest.raises(DrainError, match="ABSENT"):
        metrics_inflight_probe()(t)


def test_b2_drain_does_not_restart_when_gauge_absent():
    """End-to-end: with the real metrics probe and an absent gauge, the drain
    orchestrator raises and NEVER issues a restart (no live call cut)."""
    t = FakeTransport()
    t.on("curl -s http://127.0.0.1:8090/metrics", stdout="other 9\n")
    orch = DrainOrchestrator(
        transport=t,
        unit="famit-agent",
        inflight_probe=metrics_inflight_probe(),
        _now=lambda: 0.0,
        _sleep=lambda s: None,
    )
    with pytest.raises(DrainError):
        orch.drain_then_restart(deadline_seconds=1000, poll_seconds=5)
    assert "systemctl restart" not in " ".join(t.commands())


# B3: an INCOMPLETE auto-rollback (restored md5 != golden) must ESCALATE, not be
# silently reported as rolled_back=True/success.
def test_b3_incomplete_rollback_escalates():
    new_code = GOLDEN + b"# new (bad)\n"
    # restore_to is DELIBERATELY not golden: the backup is corrupt, so the
    # restored md5 will not equal the golden we assert against.
    corrupt_backup = b"def greet():\n    return 'corrupted backup'\n"
    t, rb = _rollback_box(new_code, restore_to=corrupt_backup)
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="500")
    watcher = HealthWatcher(
        transport=t,
        rollback=rb,
        fail_threshold=2,
        settle_polls=6,
        _sleep=lambda s: None,
        golden_md5=md5_norm(GOLDEN),     # backup will NOT match this
    )
    with pytest.raises(RollbackIncompleteError, match="INCOMPLETE"):
        watcher.watch()


# B3: a SUCCESSFUL auto-rollback exposes rollback_verified=True so a caller can
# trust the earner is provably back (not just `rolled_back`).
def test_b3_verified_rollback_sets_flag_true():
    new_code = GOLDEN + b"# new (bad)\n"
    t, rb = _rollback_box(new_code, restore_to=GOLDEN)
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="500")
    watcher = HealthWatcher(
        transport=t,
        rollback=rb,
        fail_threshold=2,
        settle_polls=6,
        _sleep=lambda s: None,
        golden_md5=md5_norm(GOLDEN),
    )
    out = watcher.watch()
    assert out.rolled_back is True
    assert out.rollback_verified is True
    assert "VERIFIED" in out.render()


# B3: with NO golden supplied, rollback_verified is None (cannot prove) — and
# the render makes the un-provability explicit rather than implying success.
def test_b3_rollback_without_golden_is_unverified_not_success():
    new_code = GOLDEN + b"# new (bad)\n"
    t, rb = _rollback_box(new_code, restore_to=GOLDEN)
    t.on('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8209/health?deep=0', stdout="500")
    watcher = HealthWatcher(
        transport=t,
        rollback=rb,
        fail_threshold=2,
        settle_polls=6,
        _sleep=lambda s: None,
        golden_md5=None,                 # nothing to verify against
    )
    out = watcher.watch()
    assert out.rolled_back is True
    assert out.rollback_verified is None
    assert "UNVERIFIED" in out.render()
