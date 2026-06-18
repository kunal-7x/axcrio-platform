"""voice_ops.deploy — TRACKED, droplet-free deploy-SAFETY tooling for the live
voice box (the OUTBOUND earner `agent.py`, the INBOUND `aim_voice_agent.py`, and
`caller.py`). W18/C6/NEW-W25.

WHY THIS EXISTS
---------------
The deploy primitive today is `systemctl restart <unit>` — a hard KILL, not a
drain. A restart cuts any live LiveKit call mid-sentence and lands the new code
directly on the carrier with no staging/canary isolation. On a single registered
worker there is no way to drain (finish in-flight calls) or to hold a synthetic
canary without occupying the only worker. The manual cutover this session proved
the RIGHT discipline:

    preflight earner-gate (assert frozen md5 + PID + /health)
      -> backup first (verify backup md5)
      -> compute the INTENDED-NEW-CLOSURE md5 locally (golden + patch, py_compile)
      -> upload flag-OFF -> assert landed md5 == intended-new-closure
      -> render-equality gate (flag-off output byte-identical to backup)
      -> flag-OFF smoke -> flag-ON flip -> earner-gate AFTER
      -> one-command rollback always staged.

This package CODIFIES that discipline as repeatable, idempotent, *tested*
primitives a later drain/canary layer can call.

HARD RULES (match the rest of voice_ops)
----------------------------------------
- This package is git-tracked (NOT inside the gitignored `droplet_work/`).
- It imports ZERO droplet_work modules and ZERO `agent.py` / `caller.py` /
  `aim_voice_agent.py`. It NEVER edits the earner.
- ZERO heavy SDK imports at module load (no livekit / boto3 / redis / paramiko).
  Every side-effecting interaction with the box goes through an INJECTED
  `ExecTransport` (see transport.py). Tests inject a fake => no SSH, no real box,
  no real PSTN dial ever runs in the suite.
- The OUTBOUND earner frozen-golden md5 is `98655dbfc71d5c3da36bcfe3f848082c`
  (KERNEL_OUTBOUND=0, rolled back). The preflight gate asserts against the
  caller-supplied expected md5; this default is recorded in EARNER_GOLDEN_MD5.

PUBLIC SURFACE
--------------
    closure.DeployClosure        — md5 manifest of a deploy closure (set of files)
    closure.compute_intended_md5 — golden + unified-diff patch -> intended-new md5
    transport.ExecTransport      — the injected box interface (run/read/write/exists)
    transport.FakeTransport      — in-memory fake fs + scripted command results (tests)
    plan.DeployPlanEngine        — preflight gate, backup, assert-landed, atomic swap
    drift.DriftChecker           — box<->local md5-manifest drift
    drain.DrainOrchestrator      — graceful in-flight drain + 2nd-worker plan
    canary.SyntheticCanary       — held synthetic canary (NO real PSTN dial)
    healthwatch.HealthWatcher    — post-deploy health watch + auto-rollback trigger
    rollback.RollbackGenerator   — one-command rollback script generator
    runbook.render_runbook       — the human RUNBOOK template assembler
"""
from __future__ import annotations

# The frozen-golden md5 of the live OUTBOUND earner agent.py (KERNEL_OUTBOUND=0,
# rolled back). The preflight earner-gate asserts the box file matches the
# caller-supplied expected hash; this is the documented default.
EARNER_GOLDEN_MD5 = "98655dbfc71d5c3da36bcfe3f848082c"

__all__ = ["EARNER_GOLDEN_MD5"]
