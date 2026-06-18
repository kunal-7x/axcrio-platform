"""voice_ops.deploy.plan — the deploy-plan ENGINE. Codifies §5 of the manual
cutover as ordered, idempotent steps that run through the injected transport.

The invariant order (any failure aborts and leaves the box untouched):

  1. PREFLIGHT EARNER GATE   assert box agent.py md5 == expected golden, the
                             earner PID is unchanged, /health is 200. Hard abort
                             on ANY mismatch. (Nothing is mutated before this.)
  2. BACKUP FIRST            cp <target> <target>.<bak-suffix>.<ts>; verify the
                             backup md5 == the current target md5.
  3. UPLOAD (FLAG-OFF)       write the new bytes to a STAGED temp path under the
                             release dir; assert its landed md5 == intended-new
                             closure md5 (the number computed locally up-front).
  4. ATOMIC SWAP             flock a deploy lock, then `ln -sfn <release> current`
                             swapped via a temp symlink + `mv -T` (atomic rename
                             on one fs). The release dir is immutable once swapped.
  5. (caller then runs drain/restart, flag-flip, post-gate via the other modules)

This engine ONLY does the parts that must be atomic + asserted. Restart, drain,
canary, health-watch and rollback are separate modules so each is independently
testable and the engine never has to know about LiveKit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .closure import IntendedClosure
from .transport import ExecTransport, TransportError


class EarnerGateError(RuntimeError):
    """A preflight/postflight earner-gate assertion failed — abort, do not deploy."""


class DeployError(RuntimeError):
    """A deploy step failed an assertion (e.g. landed md5 != intended)."""


@dataclass
class BoxLayout:
    """Where things live on the box (matches the W-INT-OUTBOUND picture)."""

    app_root: str = "/opt/famit-agent"
    releases_dir: str = "/opt/famit-agent/releases"
    current_link: str = "/opt/famit-agent/current"
    target_rel: str = "agent.py"          # the file inside a release
    legacy_target: str = "/opt/famit-agent/agent.py"  # the in-place legacy path
    health_url: str = "http://127.0.0.1:8209/health?deep=0"
    lock_path: str = "/opt/famit-agent/.deploy.lock"
    unit: str = "famit-agent"


@dataclass
class EarnerGate:
    """The frozen-golden assertion target for the preflight/postflight gate.

    When `earner_golden_md5` is set (callers deploying the real earner MUST set
    it to deploy.EARNER_GOLDEN_MD5), `expected_md5` is asserted == it at gate
    time — so the caller-supplied baseline, the box file, and the frozen-golden
    constant are all tied together (B1/B3). A mismatch fails closed before any
    box fact is read."""

    expected_md5: str
    target_path: str
    health_url: str
    unit: str
    earner_golden_md5: str | None = None

    def assert_ok(self, t: ExecTransport, *, phase: str) -> dict:
        """Assert md5 + PID-present + /health 200. Returns the observed facts.
        Raises EarnerGateError on any mismatch (fail-closed)."""
        facts: dict = {"phase": phase}
        # 0. (B1/B3) tie the caller-supplied baseline to the frozen-golden const.
        if self.earner_golden_md5 is not None and self.expected_md5 != self.earner_golden_md5:
            raise EarnerGateError(
                f"[{phase}] gate expected_md5 {self.expected_md5} != frozen "
                f"EARNER_GOLDEN_MD5 {self.earner_golden_md5} — refusing to gate "
                f"against a baseline that is not the known earner golden"
            )
        # 1. md5 of the live target
        got = t.md5(self.target_path)
        facts["md5"] = got
        if got != self.expected_md5:
            raise EarnerGateError(
                f"[{phase}] {self.target_path} md5 {got} != expected {self.expected_md5}"
            )
        # 2. earner PID present
        pid = t.run(f"systemctl show {self.unit} -p MainPID --value").stdout.strip()
        facts["pid"] = pid
        if not pid or pid == "0":
            raise EarnerGateError(f"[{phase}] unit {self.unit} has no MainPID (down?)")
        # 3. /health 200
        code = t.run(
            f'curl -s -o /dev/null -w "%{{http_code}}" {self.health_url}'
        ).stdout.strip()
        facts["health"] = code
        if code != "200":
            raise EarnerGateError(f"[{phase}] {self.health_url} returned {code} != 200")
        return facts


@dataclass
class DeployRecord:
    """Durable record of one deploy attempt — the rollback generator reads this."""

    release_id: str
    target_path: str
    backup_path: str
    pre_md5: str
    intended_md5: str
    landed_md5: str | None = None
    preflight: dict | None = None
    postflight: dict | None = None
    swapped: bool = False
    steps: list[str] = field(default_factory=list)

    def note(self, s: str) -> None:
        self.steps.append(s)


@dataclass
class DeployPlanEngine:
    transport: ExecTransport
    layout: BoxLayout = field(default_factory=BoxLayout)
    backup_suffix: str = "WOUTbak"

    # -- step 1 ------------------------------------------------------------ #
    def preflight_gate(self, gate: EarnerGate) -> dict:
        return gate.assert_ok(self.transport, phase="preflight")

    # -- step 2 ------------------------------------------------------------ #
    def backup(self, target_path: str, *, ts: str | None = None) -> tuple[str, str]:
        """cp the target aside and verify the backup md5 == the target md5.
        Returns (backup_path, pre_md5). Idempotent for a given ts."""
        t = self.transport
        ts = ts or time.strftime("%Y%m%d-%H%M%S")
        backup_path = f"{target_path}.{self.backup_suffix}.{ts}"
        pre_md5 = t.md5(target_path)
        t.run(f"cp -p {target_path} {backup_path}", check=True)
        if not t.exists(backup_path):
            raise DeployError(f"backup not created: {backup_path}")
        if t.md5(backup_path) != pre_md5:
            raise DeployError(
                f"backup md5 mismatch: {backup_path} != source {target_path}"
            )
        return backup_path, pre_md5

    # -- step 3 ------------------------------------------------------------ #
    def stage_and_assert(
        self, release_dir: str, intended: IntendedClosure, *, rel: str | None = None
    ) -> str:
        """Write the intended bytes to a STAGED path in the release dir, then
        assert the landed md5 == the intended-new-closure md5. Returns the staged
        path. The assertion is the gate that catches a wrong file / truncated SCP."""
        t = self.transport
        rel = rel or self.layout.target_rel
        t.run(f"mkdir -p {release_dir}", check=True)
        staged = f"{release_dir.rstrip('/')}/{rel}"
        t.write(staged, intended.as_bytes())
        landed = t.md5(staged)
        if landed != intended.md5:
            raise DeployError(
                f"landed md5 {landed} != intended-new-closure {intended.md5} "
                f"(file {staged}) — refusing to swap"
            )
        return staged

    # -- step 4 ------------------------------------------------------------ #
    def atomic_swap(self, release_dir: str) -> None:
        """Atomically repoint `current` -> release_dir under a flock.

        `ln -sfn` is NOT atomic (it unlinks then symlinks). We create the new
        link at a temp name then `mv -T` it over `current` — `rename(2)` is
        atomic on one filesystem, so `current` is never absent/partial. The whole
        thing runs under flock so two concurrent deploys can't race the symlink."""
        t = self.transport
        link = self.layout.current_link
        tmp = f"{link}.tmp.$$"
        lock = self.layout.lock_path
        cmd = (
            f"flock -w 30 {lock} -c "
            f"'ln -sfn {release_dir} {tmp} && mv -T {tmp} {link}'"
        )
        res = t.run(cmd)
        if not res.ok:
            raise DeployError(f"atomic swap failed rc={res.rc}: {res.stderr}")

    # -- step 5: postflight ------------------------------------------------ #
    def postflight_gate(self, gate: EarnerGate) -> dict:
        return gate.assert_ok(self.transport, phase="postflight")

    # -- orchestration: the full flag-OFF deploy up to the swap ------------ #
    def deploy_flag_off(
        self,
        *,
        gate: EarnerGate,
        intended: IntendedClosure,
        release_id: str | None = None,
        ts: str | None = None,
    ) -> DeployRecord:
        """Run steps 1-4 (preflight -> backup -> stage+assert -> atomic swap)
        WITH the feature flag OFF. The flag flip + restart are deliberately the
        caller's next move (so the flag-off smoke can happen in between). Returns
        the DeployRecord the rollback generator needs."""
        ts = ts or time.strftime("%Y%m%d-%H%M%S")
        release_id = release_id or ts
        release_dir = f"{self.layout.releases_dir.rstrip('/')}/{release_id}"

        pre = self.preflight_gate(gate)  # aborts on mismatch
        backup_path, pre_md5 = self.backup(gate.target_path, ts=ts)
        rec = DeployRecord(
            release_id=release_id,
            target_path=gate.target_path,
            backup_path=backup_path,
            pre_md5=pre_md5,
            intended_md5=intended.md5,
            preflight=pre,
        )
        rec.note(f"preflight OK md5={pre_md5}")
        rec.note(f"backup -> {backup_path}")

        staged = self.stage_and_assert(release_dir, intended)
        rec.landed_md5 = intended.md5
        rec.note(f"staged+asserted {staged} md5={intended.md5}")

        self.atomic_swap(release_dir)
        rec.swapped = True
        rec.note(f"atomic-swap current -> {release_dir}")
        return rec
