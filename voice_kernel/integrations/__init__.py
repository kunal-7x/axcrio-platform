"""voice_kernel.integrations — the agent-facing integration façades.

This package holds the TRACKED, git-revertable BULK of every flag-gated agent
integration. The live voice agents (gitignored, box-only) gain only a few
flag-guarded call sites; ALL the wiring (build_kernel + every W2–W7 impl
construction + the per-hook glue) lives here so an integration can be reverted
with a single `git revert` of one tracked module.

`inbound` — the INBOUND (`aim_voice_agent.py`) façade. KERNEL_INBOUND default
OFF ⇒ every function returns the legacy-equivalent and the agent is byte-identical
to today. See design/W-INT-INBOUND-PLAN.md + design/W-INT-INBOUND-PATCH.md.

IMPORT ISOLATION: importing this package (and `voice_kernel.integrations.inbound`)
pulls ZERO droplet_work modules at module load. Every droplet/heavy import is
LAZY (inside a function, guarded by the flag), so the OFF path imports nothing.
"""
from __future__ import annotations

__all__ = ["inbound"]
