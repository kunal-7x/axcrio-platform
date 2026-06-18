"""voice_ops.deploy.drain — graceful DRAIN orchestration for the LiveKit worker.

THE PROBLEM
-----------
`systemctl restart` is a KILL: SIGTERM then SIGKILL after `TimeoutStopSec`
(systemd default 90s). A LiveKit worker that receives SIGTERM runs its own
`drain()` — it stops accepting NEW dispatches and lets in-flight calls finish —
but if `TimeoutStopSec` < the worker's `drain_timeout` (default 1800s), systemd
SIGKILLs the worker mid-drain and CUTS the live calls. So step one of a graceful
deploy is purely a systemd-config fact: `TimeoutStopSec` MUST be >= drain_timeout.

WHAT THIS MODULE DOES
---------------------
1. `wait_for_drain` — poll the worker until it reports ZERO in-flight jobs (or a
   deadline), so a restart only happens once the worker is idle. The "jobs in
   flight" probe is injected (a function of the transport) because the exact
   readout differs by box (LiveKit metrics endpoint, a caller.py /metrics gauge,
   or a log scrape). Default probe parses an active-jobs integer from a metrics
   line. This is the seam tests drive.

2. `DrainOrchestrator.drain_then_restart` — single-worker safe restart: flip the
   worker into drain, WAIT until idle, THEN restart. Never SIGKILLs a live call.
   On a single worker this still drops outbound CAPACITY while draining (there's
   no second worker to serve), which is why we also generate the 2nd-worker plan.

3. `TwoWorkerPlan` — the systemd/worker plan for a SECOND registered LiveKit
   worker (the real fix). With workers A and B both registered on the same
   dispatch rules: drain A while B serves -> A idle -> deploy to A -> un-drain A
   -> drain B while A serves -> deploy to B. No worker ever cuts a live call, and
   a held synthetic canary becomes possible (B holds the canary, A serves real).

NO LiveKit import anywhere — drain is driven through the transport + an injected
in-flight probe, so the whole thing tests offline.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

from .transport import ExecTransport


# in-flight probe: given the transport, return the count of jobs currently running
InFlightProbe = Callable[[ExecTransport], int]


def metrics_inflight_probe(
    metrics_url: str = "http://127.0.0.1:8090/metrics",
    metric_name: str = "livekit_active_jobs",
) -> InFlightProbe:
    """Build a probe that curls a Prometheus metrics endpoint and reads the
    active-jobs gauge. Falls back to 0 only if the metric line is ABSENT *and*
    the curl succeeded; a curl failure raises (fail-closed: we must not assume
    idle just because we couldn't read)."""

    def _probe(t: ExecTransport) -> int:
        res = t.run(f"curl -s {metrics_url}")
        if not res.ok:
            raise DrainError(f"metrics probe failed rc={res.rc}: {metrics_url}")
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith(metric_name):
                m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*$", line)
                if m:
                    return int(float(m.group(1)))
        return 0

    return _probe


class DrainError(RuntimeError):
    """Drain did not reach idle before the deadline, or a probe failed."""


@dataclass
class DrainResult:
    reached_idle: bool
    polls: int
    last_inflight: int
    waited_seconds: float


@dataclass
class DrainOrchestrator:
    transport: ExecTransport
    unit: str = "famit-agent"
    inflight_probe: InFlightProbe = field(default_factory=metrics_inflight_probe)
    # injected clock + sleep so tests are deterministic + instant
    _now: Callable[[], float] = field(default=time.monotonic)
    _sleep: Callable[[float], None] = field(default=lambda s: None)

    def begin_drain(self) -> None:
        """Ask the worker to enter drain mode WITHOUT killing it. systemd's
        `kill -s SIGTERM` to the main PID triggers the SDK drain loop; the worker
        stops taking new jobs but keeps live calls. (We send SIGTERM to the main
        pid, NOT `systemctl stop`, so systemd's TimeoutStopSec clock does not
        start — we control the wait ourselves.)"""
        self.transport.run(
            f"systemctl kill -s SIGTERM --kill-who=main {self.unit}", check=True
        )

    def wait_for_drain(
        self, *, deadline_seconds: float = 1800.0, poll_seconds: float = 5.0
    ) -> DrainResult:
        """Poll the in-flight probe until it reads 0 (idle) or the deadline.
        Returns DrainResult; raises DrainError if the deadline passes while jobs
        are still in flight (caller decides whether to force or abort)."""
        start = self._now()
        polls = 0
        last = self.inflight_probe(self.transport)
        polls += 1
        while last > 0:
            if self._now() - start >= deadline_seconds:
                raise DrainError(
                    f"drain deadline {deadline_seconds}s exceeded with "
                    f"{last} job(s) still in flight on {self.unit}"
                )
            self._sleep(poll_seconds)
            last = self.inflight_probe(self.transport)
            polls += 1
        return DrainResult(
            reached_idle=True,
            polls=polls,
            last_inflight=last,
            waited_seconds=self._now() - start,
        )

    def drain_then_restart(
        self, *, deadline_seconds: float = 1800.0, poll_seconds: float = 5.0
    ) -> DrainResult:
        """The single-worker safe deploy restart: drain -> wait idle -> restart.
        A live call is NEVER cut because the restart only fires once in-flight==0."""
        self.begin_drain()
        result = self.wait_for_drain(
            deadline_seconds=deadline_seconds, poll_seconds=poll_seconds
        )
        # now idle — safe to restart onto the new (already-swapped) code
        self.transport.run(f"systemctl restart {self.unit}", check=True)
        return result


# --------------------------------------------------------------------------- #
# Two-worker plan — the REAL fix (true drain + held canary)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TwoWorkerPlan:
    """Generates the systemd templated-unit + the rolling-drain runbook for a
    SECOND registered LiveKit worker on the same dispatch rules. This is the
    recommendation W18 calls out: a 2nd worker enables draining A while B serves
    (no capacity gap, no cut call) AND a held synthetic canary."""

    app_root: str = "/opt/famit-agent"
    venv_python: str = "/opt/capsy-agent/.venv/bin/python"
    agent_entry: str = "agent.py"
    base_port: int = 8090
    drain_timeout: int = 1800
    unit_template: str = "famit-agent@"

    def systemd_unit(self) -> str:
        """Templated unit `famit-agent@.service`. `%i` = instance (1->portA,
        2->portB). TimeoutStopSec == drain_timeout is the load-bearing line —
        without it systemd SIGKILLs mid-drain and cuts calls."""
        return f"""# {self.unit_template[:-1]}@.service — templated LiveKit worker (W25 drain plan).
# Instance %i selects the health port ({self.base_port}+%i) so worker A (%i=1)
# and worker B (%i=2) register independently on the SAME dispatch rules.
# TRACKED TEMPLATE — install is human-gated (see W25 runbook).
[Unit]
Description=Famit Voice Agent Worker %i
After=network.target

[Service]
Type=simple
User=famit
WorkingDirectory={self.app_root}/current
EnvironmentFile={self.app_root}/.env
# Per-worker health port; agent.py reads AGENT_HTTP_PORT (no agent.py edit needed
# beyond the already-present env read).
Environment=AGENT_HTTP_PORT={self.base_port}%i
ExecStart={self.venv_python} {self.agent_entry} start --drain-timeout {self.drain_timeout}
Restart=on-failure
RestartSec=5
KillMode=mixed
# LOAD-BEARING: must be >= the SDK drain_timeout or systemd SIGKILLs mid-drain
# and cuts live calls. This is the single most important line in the file.
TimeoutStopSec={self.drain_timeout}

[Install]
WantedBy=multi-user.target
"""

    def rolling_drain_steps(self, *, deploy_cmd: str = "<atomic-swap + flag flip>") -> list[str]:
        """The human-readable rolling-drain sequence (drain A while B serves)."""
        a = f"{self.unit_template}1"
        b = f"{self.unit_template}2"
        return [
            f"0. Precondition: BOTH {a} and {b} registered + healthy; new code already "
            f"atomic-swapped into {self.app_root}/current; flag still OFF.",
            f"1. Drain A:  systemctl kill -s SIGTERM --kill-who=main {a}  "
            f"(A stops taking new jobs; {b} now serves ALL new dispatches — no gap).",
            f"2. Wait until A in-flight == 0 (poll its metrics; deadline = drain_timeout).",
            f"3. Restart A onto new code:  systemctl restart {a}   ({deploy_cmd}).",
            f"4. Health-gate A (its /health 200) + optional HELD synthetic canary on A "
            f"while {b} keeps serving real traffic.",
            f"5. Drain B:  systemctl kill -s SIGTERM --kill-who=main {b}  "
            f"(now A serves all new dispatches).",
            f"6. Wait until B in-flight == 0; restart B onto new code; health-gate B.",
            f"7. Both workers now on new code; flip the feature flag ON; earner-gate after.",
            f"ROLLBACK at any step: re-point current -> previous release + flag OFF + "
            f"restart whichever worker(s) took the bad code; the still-good worker kept serving.",
        ]
