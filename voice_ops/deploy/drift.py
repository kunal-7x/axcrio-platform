"""voice_ops.deploy.drift — box <-> local DRIFT check.

Before any deploy you must know whether the box's live files match the local
closure you THINK is deployed. If they don't, someone hot-edited the box (or a
prior deploy was partial), and deploying on top would silently clobber that. The
DriftChecker builds a closure from the box via the transport, compares it to the
expected local closure, and reports added/removed/changed files with md5s.

Pure comparison — no mutation. Reuses DeployClosure so the same md5 truth drives
drift detection AND the post-deploy 'landed == intended' assertion.
"""
from __future__ import annotations

from dataclasses import dataclass

from .closure import ClosureDiff, DeployClosure
from .transport import ExecTransport


@dataclass(frozen=True)
class DriftReport:
    diff: ClosureDiff
    box_root: str
    relpaths: tuple[str, ...]

    @property
    def has_drift(self) -> bool:
        return not self.diff.clean

    def render(self) -> str:
        head = f"drift check {self.box_root} ({len(self.relpaths)} files): "
        return head + ("CLEAN" if not self.has_drift else "\n" + self.diff.summary())


@dataclass
class DriftChecker:
    transport: ExecTransport

    def check(
        self, *, expected: DeployClosure, box_root: str, relpaths: list[str]
    ) -> DriftReport:
        """Compare the box's current closure against `expected` (the local truth).
        `expected.diff(actual)` => what changed ON THE BOX relative to expected."""
        actual = DeployClosure.from_transport(self.transport, box_root, relpaths)
        diff = expected.diff(actual)
        return DriftReport(diff=diff, box_root=box_root, relpaths=tuple(relpaths))

    def assert_no_drift(
        self, *, expected: DeployClosure, box_root: str, relpaths: list[str]
    ) -> DriftReport:
        """Like check() but raises DriftError when the box has drifted — use this
        as a hard pre-deploy gate when you require the box to be pristine."""
        rep = self.check(expected=expected, box_root=box_root, relpaths=relpaths)
        if rep.has_drift:
            raise DriftError(rep.render())
        return rep


class DriftError(RuntimeError):
    """The box drifted from the expected closure — refuse to deploy on top."""
