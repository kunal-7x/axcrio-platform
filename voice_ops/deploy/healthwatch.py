"""voice_ops.deploy.healthwatch — post-deploy HEALTH WATCH + AUTO-ROLLBACK.

After a flag flip / restart, watch the newly-deployed unit for a settle window.
If health degrades (the /health probe goes non-200 for `fail_threshold`
consecutive polls) OR the held synthetic canary fails, FIRE the auto-rollback:
restore the backup + force the flag OFF + restart, then verify the earner is
back to golden md5. Healthy for the whole window => the deploy is accepted.

The watcher takes:
  * a health probe callable (transport -> bool healthy),
  * an optional canary (canary.SyntheticCanary) run ONCE up-front (the held
    canary on the standby/drained worker), and
  * a RollbackGenerator it triggers on failure.

All timing is injected (clock + sleep) so tests run instantly + deterministically.
NO box, NO PSTN: the probe + canary are driven by the FakeTransport in tests.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .canary import CanaryVerdict, SyntheticCanary
from .rollback import RollbackGenerator
from .transport import ExecTransport


HealthProbe = Callable[[ExecTransport], bool]


def http_health_probe(url: str = "http://127.0.0.1:8209/health?deep=0") -> HealthProbe:
    """A health probe that is True iff the URL returns HTTP 200."""

    def _probe(t: ExecTransport) -> bool:
        code = t.run(f'curl -s -o /dev/null -w "%{{http_code}}" {url}').stdout.strip()
        return code == "200"

    return _probe


@dataclass(frozen=True)
class WatchOutcome:
    healthy: bool
    rolled_back: bool
    reason: str
    polls: int
    canary: CanaryVerdict | None = None
    restored_md5: str | None = None

    def render(self) -> str:
        verdict = "ACCEPTED (healthy)" if self.healthy else "REJECTED"
        tail = ""
        if self.rolled_back:
            tail = f" -> AUTO-ROLLBACK fired (restored md5={self.restored_md5})"
        return f"healthwatch: {verdict} after {self.polls} poll(s): {self.reason}{tail}"


@dataclass
class HealthWatcher:
    transport: ExecTransport
    rollback: RollbackGenerator
    health_probe: HealthProbe = field(default_factory=http_health_probe)
    canary: SyntheticCanary | None = None
    fail_threshold: int = 2          # consecutive non-200 polls => unhealthy
    settle_polls: int = 6            # number of healthy polls required to ACCEPT
    poll_seconds: float = 5.0
    _sleep: Callable[[float], None] = field(default=lambda s: None)
    golden_md5: str | None = None    # if set, restored md5 is asserted == this

    def _auto_rollback(self, reason: str, *, canary: CanaryVerdict | None) -> WatchOutcome:
        restored = self.rollback.execute(self.transport)
        if self.golden_md5 is not None and restored != self.golden_md5:
            # rollback itself did not restore golden — surface loudly
            reason = (
                f"{reason}; AUTO-ROLLBACK INCOMPLETE: restored md5 {restored} "
                f"!= golden {self.golden_md5}"
            )
        return WatchOutcome(
            healthy=False,
            rolled_back=True,
            reason=reason,
            polls=0,
            canary=canary,
            restored_md5=restored,
        )

    def watch(self) -> WatchOutcome:
        """Run the canary (if any) THEN watch health for `settle_polls`. Fire
        auto-rollback on canary FAIL or on `fail_threshold` consecutive non-200s.
        Returns the WatchOutcome (accepted or rolled-back)."""
        # 1. held synthetic canary first — fail-closed gate before we trust health
        canary_verdict: CanaryVerdict | None = None
        if self.canary is not None:
            canary_verdict = self.canary.run()
            if not canary_verdict.passed:
                return self._auto_rollback(
                    f"canary FAILED: {[c.name for c in canary_verdict.failures]}",
                    canary=canary_verdict,
                )

        # 2. settle window
        consecutive_bad = 0
        for i in range(self.settle_polls):
            healthy = self.health_probe(self.transport)
            if healthy:
                consecutive_bad = 0
            else:
                consecutive_bad += 1
                if consecutive_bad >= self.fail_threshold:
                    return self._auto_rollback(
                        f"health non-200 for {consecutive_bad} consecutive polls",
                        canary=canary_verdict,
                    )
            if i < self.settle_polls - 1:
                self._sleep(self.poll_seconds)

        return WatchOutcome(
            healthy=True,
            rolled_back=False,
            reason=f"healthy through {self.settle_polls} settle poll(s)"
            + (" + canary PASS" if canary_verdict else ""),
            polls=self.settle_polls,
            canary=canary_verdict,
        )
