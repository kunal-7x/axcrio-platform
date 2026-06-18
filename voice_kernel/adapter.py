"""voice_kernel.adapter — instructions_provider, the OFF-is-identity seam.

This is the ONE seam the voice agents call. The earner-safety guarantee:

  When the kernel is OFF for this direction, the adapter returns the EXACT
  legacy string (the agent's own build_system_prompt / _build_sales_instructions
  output), so the call is BYTE-FOR-BYTE identical to today.

`legacy_render` is a zero-arg callable the AGENT passes that produces today's
string. So the kernel never imports the agent, and the agent never changes its
own logic — it just routes its existing output through this seam. The build wave
ships this WITHOUT wiring it into any agent (that is the integration wave); this
module + its test ARE the unit-level earner gate.

LEARNINGS §1: never silently fail. If the kernel raises while ON, we log a
WARNING and fall back to the legacy string (== today's behaviour) — we never
emit a broken prompt and we never swallow the error silently.
"""
from __future__ import annotations

import logging
from typing import Callable

from .config import KernelConfig
from .contracts import CallContext
from .kernel import build_kernel

log = logging.getLogger("voice_kernel.adapter")


def instructions_provider(
    legacy_render: Callable[[], str],
    ctx: CallContext,
    *,
    cfg: KernelConfig,
) -> str:
    """Return the instructions string for this call.

    OFF (default): byte-identical to `legacy_render()`.
    ON: the kernel packet prefix, with a safe fallback to legacy on any error.
    """
    if not cfg.enabled_for(ctx.meta.direction):
        return legacy_render()  # <- OFF: identical to today, no kernel code runs
    try:
        return build_kernel(cfg).assemble_prefix(ctx)
    except Exception as exc:  # never silently fail (LEARNINGS §1)
        log.warning("kernel assemble failed, falling back to legacy: %r", exc)
        return legacy_render()  # safe fallback == today's behaviour
