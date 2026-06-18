"""voice_kernel.errors — the KernelError hierarchy.

LEARNINGS §1: NEVER silently fail. Every failure path either raises one of these
typed errors OR logs a warning and falls back to the legacy string. We never
`pass` on an exception and we never return a silently-wrong packet.

These are pure-stdlib, import-safe (no third-party deps), so the kernel core can
be imported by `aim_voice_agent.py` without dragging in Redis/PG/Qdrant.
"""
from __future__ import annotations


class KernelError(Exception):
    """Base class for every voice_kernel failure."""


class BudgetExceededError(KernelError):
    """The assembled packet exceeds its hard token budget AFTER clamping.

    Raised only when even the most aggressive clamp (drop L5, trim L4) cannot
    bring the packet under `budget.max_total_tokens` — i.e. L0..L3 alone are
    oversized, which is a campaign-config bug the operator must fix. We raise
    rather than silently send an over-budget prompt.
    """


class ClampError(KernelError):
    """A clamp helper was handed a value it cannot safely truncate."""


class ContractViolationError(KernelError):
    """A dependency-injected service does not conform to its Protocol, or
    returned a value of the wrong shape. Surfaced loudly at wiring time."""


class ConfigError(KernelError):
    """KernelConfig was constructed with contradictory / invalid flags."""
