"""voice_kernel.config — KernelConfig, the flag reader. Default OFF, always.

Flag pattern is the codebase-native one (agent.py:451 OPENER_ALREADY_SAID):
    os.getenv("NAME", "0") in ("1", "true", "True")
No new config framework.

Three scoped flags so inbound can be enabled WITHOUT touching the earner:
  - KERNEL_ENABLED          master switch (default OFF)
  - KERNEL_INBOUND          enable on aim_voice_agent.py only (default OFF)
  - KERNEL_OUTBOUND_SHADOW  outbound shadow-compute only, never replaces the
                            string (default OFF)

LEARNINGS §2 (banked): inbound flags placed in the SHARED `.env` leak to the
outbound earner on its next restart. Therefore KERNEL_INBOUND must be set via
the systemd drop-in `Environment=` on aim-voice-agent.service.d (shipped as a
tracked template in voice_kernel/systemd/), NOT in the shared .env. This config
object does not enforce that placement (it can't read systemd), but the README +
the shipped drop-in template make the safe path the obvious one, and the
integration wave verifies via /proc/<pid>/environ.

`enabled_for(direction)` is the single gate the adapter calls. With NO env set,
EVERY direction returns False (proven in test_flags.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import ConfigError

_TRUE = ("1", "true", "True")


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) in _TRUE


@dataclass(frozen=True)
class KernelConfig:
    """Immutable snapshot of the kernel flags + budget knobs.

    Build with `KernelConfig.from_env()` in production; construct directly in
    tests for determinism (no env dependence).
    """

    enabled: bool = False  # KERNEL_ENABLED — master switch
    inbound: bool = False  # KERNEL_INBOUND
    outbound_shadow: bool = False  # KERNEL_OUTBOUND_SHADOW
    max_total_tokens: int = 2800

    @classmethod
    def from_env(cls) -> "KernelConfig":
        cfg = cls(
            enabled=_flag("KERNEL_ENABLED"),
            inbound=_flag("KERNEL_INBOUND"),
            outbound_shadow=_flag("KERNEL_OUTBOUND_SHADOW"),
            max_total_tokens=int(os.getenv("KERNEL_MAX_TOTAL_TOKENS", "2800")),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.max_total_tokens <= 0:
            raise ConfigError(f"max_total_tokens must be > 0, got {self.max_total_tokens}")

    def enabled_for(self, direction: str) -> bool:
        """The single gate. Returns True ONLY when the kernel should REPLACE the
        legacy string for this direction.

        - outbound: requires the master switch AND is NEVER replaced by shadow
          mode (shadow only computes-and-logs, never substitutes). So outbound
          live replacement is gated purely on `KERNEL_ENABLED` — which the build
          wave keeps OFF; the live cutover is the human-gated G3 step.
        - inbound: master switch OR the inbound-scoped flag.

        With no env set, every branch is False.
        """
        d = (direction or "outbound").lower()
        if d == "inbound":
            return self.enabled or self.inbound
        # outbound (default): master only. Shadow does NOT enable replacement.
        return self.enabled

    def shadow_active(self) -> bool:
        """True when the outbound shadow sidecar should compute+log the diff.
        This NEVER substitutes the live string."""
        return self.outbound_shadow
