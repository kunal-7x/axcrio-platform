"""voice_ops.deploy.canary — HELD SYNTHETIC canary. Proves the freshly-deployed
code is alive end-to-end WITHOUT ever placing a real PSTN call (no carrier burn,
no real customer dialed).

A synthetic canary exercises the parts of the pipeline that a deploy could break,
each as an isolated, offline-driveable check:

  1. GREETING RENDER — render the opener/greeting from a golden campaign prompt
     against the deployed code's render endpoint (or a render shim). Assert the
     output is non-empty and (optionally) byte-identical to a golden md5 — this
     is the "flag-OFF render-equality" gate, run against the live process.
  2. TOOL DISPATCH — invoke one safe, idempotent tool (e.g. a no-op `ping`/
     `book_site_visit` dry-run) and assert it returns OK. Catches a broken tool
     registry / import error in the new code.
  3. DB CHECK — a cheap read (e.g. deep /health that touches the DB) returns 200.
     Catches a new code path that can't reach Postgres.

ALL THREE are HARD by default and the canary FAILS CLOSED: if any check raises,
errors, or returns a non-OK code, the canary verdict is FAIL — which the
health-watcher turns into an auto-rollback. The canary NEVER dials out: there is
no SIP/telephony call anywhere in this module, by construction. Each check is an
injected callable (a function of the transport) so tests drive them with a fake
and assert the fail-closed behaviour with zero box and zero PSTN.

On a single worker the canary necessarily occupies the only worker, so a TRULY
"held" canary (held while real traffic continues) requires the 2nd worker from
drain.TwoWorkerPlan — the canary runs on the drained/standby worker B while A
serves real dispatches. This module runs the checks; WHERE it runs (which worker)
is the orchestrator's choice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .transport import ExecTransport, md5_norm


CanaryCheck = Callable[[ExecTransport], "CheckOutcome"]


@dataclass(frozen=True)
class CheckOutcome:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class CanaryVerdict:
    passed: bool
    checks: tuple[CheckOutcome, ...]

    def render(self) -> str:
        lines = [f"canary {'PASS' if self.passed else 'FAIL'}:"]
        for c in self.checks:
            lines.append(f"  [{'ok ' if c.ok else 'FAIL'}] {c.name}: {c.detail}")
        return "\n".join(lines)

    @property
    def failures(self) -> list[CheckOutcome]:
        return [c for c in self.checks if not c.ok]


# --------------------------------------------------------------------------- #
# Built-in check factories (each returns a CanaryCheck closure)
# --------------------------------------------------------------------------- #
def greeting_render_check(
    *,
    render_url: str,
    expected_md5: str | None = None,
    name: str = "greeting_render",
) -> CanaryCheck:
    """Render the deployed greeting and assert non-empty (and md5-equal if a
    golden md5 is given). Fails closed on curl error / empty / md5 mismatch."""

    def _check(t: ExecTransport) -> CheckOutcome:
        res = t.run(f"curl -s {render_url}")
        if not res.ok:
            return CheckOutcome(name, False, f"render curl rc={res.rc}")
        body = res.stdout.strip()
        if not body:
            return CheckOutcome(name, False, "empty render output")
        if expected_md5 is not None:
            got = md5_norm(body.encode())
            if got != expected_md5:
                return CheckOutcome(
                    name, False, f"render md5 {got} != golden {expected_md5}"
                )
            return CheckOutcome(name, True, f"render md5-identical {got}")
        return CheckOutcome(name, True, f"rendered {len(body)} bytes")

    return _check


def tool_dispatch_check(
    *,
    tool_url: str,
    expect_substr: str = "ok",
    name: str = "tool_dispatch",
) -> CanaryCheck:
    """Invoke one safe idempotent tool (dry-run) and assert the response carries
    `expect_substr`. Catches a broken tool registry in the new code."""

    def _check(t: ExecTransport) -> CheckOutcome:
        res = t.run(f"curl -s {tool_url}")
        if not res.ok:
            return CheckOutcome(name, False, f"tool curl rc={res.rc}")
        if expect_substr not in res.stdout:
            return CheckOutcome(
                name, False, f"missing {expect_substr!r} in tool response"
            )
        return CheckOutcome(name, True, "tool dry-run OK")

    return _check


def db_health_check(
    *,
    health_url: str = "http://127.0.0.1:8209/health",
    name: str = "db_health",
) -> CanaryCheck:
    """A cheap DB-touching read (deep /health returns 200 iff Postgres reachable).
    Fails closed on any non-200 / curl error."""

    def _check(t: ExecTransport) -> CheckOutcome:
        code = t.run(
            f'curl -s -o /dev/null -w "%{{http_code}}" {health_url}'
        ).stdout.strip()
        if code != "200":
            return CheckOutcome(name, False, f"deep /health {code} != 200")
        return CheckOutcome(name, True, "db reachable (deep /health 200)")

    return _check


@dataclass
class SyntheticCanary:
    """Runs the held synthetic checks. NEVER dials PSTN. Fails closed."""

    transport: ExecTransport
    checks: list[CanaryCheck] = field(default_factory=list)

    def run(self) -> CanaryVerdict:
        outcomes: list[CheckOutcome] = []
        for chk in self.checks:
            try:
                outcomes.append(chk(self.transport))
            except Exception as e:  # fail-closed: an exception is a FAILED check
                outcomes.append(
                    CheckOutcome(
                        getattr(chk, "__name__", "check"),
                        False,
                        f"raised {type(e).__name__}: {e}",
                    )
                )
        passed = bool(outcomes) and all(o.ok for o in outcomes)
        return CanaryVerdict(passed=passed, checks=tuple(outcomes))

    @classmethod
    def default(
        cls,
        transport: ExecTransport,
        *,
        render_url: str,
        tool_url: str,
        health_url: str = "http://127.0.0.1:8209/health",
        greeting_md5: str | None = None,
    ) -> "SyntheticCanary":
        """The standard 3-check held canary: greeting render + tool + DB."""
        return cls(
            transport=transport,
            checks=[
                greeting_render_check(render_url=render_url, expected_md5=greeting_md5),
                tool_dispatch_check(tool_url=tool_url),
                db_health_check(health_url=health_url),
            ],
        )
