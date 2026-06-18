# W25 — Voice Deploy-Safety Tooling (`voice_ops/deploy/`)

Wave: **W18/C6/NEW-W25** — codify the manual-cutover deploy discipline into REAL, tested,
droplet-free tooling. Branch `fix/realtime-voice-kernel-v2`. EARNER LAW: builds TOOLING ONLY,
does NOT touch the box, NEVER imports/edits `agent.py`. Disjoint tracked code under
`voice_ops/deploy/` (new).

## Why (the gap)
Current deploy primitive = `systemctl restart <unit>` = a KILL not a drain: cuts live calls
mid-sentence + lands untested code on the carrier. Single worker => no real drain, no held
synthetic canary. This wave builds the seam: md5/closure gate + backup + atomic swap + drift +
drain + held canary + health-watch auto-rollback + one-cmd rollback + runbook. Plus the
2nd-LiveKit-worker recommendation (true drain: drain A while B serves).

## Deliverables (status)
- [x] `closure.py` — DeployClosure md5 manifest + intended-new-closure (golden+patch) + assert. DONE
- [x] `transport.py` — injectable exec transport (mock in tests; ZERO real box calls in tests). DONE
- [x] `plan.py` — deploy-plan engine: preflight earner gate, backup+record md5, assert landed==intended, atomic swap (release dir + symlink) with flock. DONE
- [x] `drift.py` — box<->local drift check (md5 manifest of the deploy closure). DONE
- [x] `drain.py` — graceful drain orchestration + 2nd-worker systemd/worker plan generator. DONE
- [x] `canary.py` — held SYNTHETIC canary runner (greeting render + tool + DB check; NEVER a real PSTN dial). DONE
- [x] `healthwatch.py` — post-deploy health watch + AUTO-ROLLBACK trigger. DONE
- [x] `rollback.py` — one-command rollback generator. DONE
- [x] `runbook.py` — RUNBOOK template assembler. DONE
- [x] `tests/` — pytest (mock ssh/fs): drift detected, intended-closure assertion catches wrong file, drain waits for in-flight, canary fails-closed, auto-rollback fires on health fail. 0 droplet/agent imports. DONE
- [x] `design/W25-DEPLOY-SAFETY-RUNBOOK.md` — incl. 2nd-LiveKit-worker recommendation. DONE

## Invariants honored
- 0 droplet_work imports, 0 agent.py import, 0 livekit/boto3/redis import at module load (all lazy/none).
- All box interaction goes through an INJECTED transport interface; tests inject a fake => no SSH/box in tests.
- Frozen golden outbound earner md5 = `98655dbfc71d5c3da36bcfe3f848082c` (KERNEL_OUTBOUND=0, rolled back).

## Result — DONE
- Built `voice_ops/deploy/`: `__init__.py`, `transport.py`, `closure.py`, `plan.py`,
  `drift.py`, `drain.py`, `canary.py`, `healthwatch.py`, `rollback.py`, `runbook.py`.
- Tests: `voice_ops/deploy/tests/test_deploy_safety.py` — **31 passed**. Proves all
  required scenarios (intended-closure catches wrong/truncated file, drift detected,
  drain waits for in-flight + raises on deadline, canary fails-closed, auto-rollback
  fires on health AND canary fail, backup-before-swap order, atomic-swap flock+mv -T,
  rollback script + runbook content, NO droplet/agent/heavy-SDK import guard).
- `pytest voice_ops/ voice_kernel/` = **717 passed** (baseline was 638; +new tests). 0 fail.
- Runbook: `design/W25-DEPLOY-SAFETY-RUNBOOK.md` (incl. the 2nd-LiveKit-worker
  recommendation + rolling-drain + atomic-swap layout + the TimeoutStopSec systemd fact).
- Invariants verified: 0 box mutation, 0 `agent.py` import, 0 livekit/boto3/redis/paramiko/
  droplet_work import at load (guarded by a test + an isolated-process check).
- Frozen golden constant `EARNER_GOLDEN_MD5 == 98655dbfc71d5c3da36bcfe3f848082c` (matches law).

## VERIFY+COMMIT pass (red-team fold) — B1/B2/B3 fixed
Red-team found the brief's five failure modes were documented-not-enforced. SHIP-WITH-FIXES.
Three blockers folded in (the tooling still mutates NOTHING on the box; fixes are deploy-time
correctness, scoped "before first real use"):
- **B1 — wrong-closure / undetected golden drift.** (a) `compute_intended_md5(...,
  expected_golden_md5=)` now asserts `md5_norm(golden_bytes) == expected` BEFORE patching, so a
  patch that applies against the WRONG golden fails closed; callers deploying the real earner
  pass `EARNER_GOLDEN_MD5`. (b) `EarnerGate(earner_golden_md5=)` ties `expected_md5` to the
  frozen constant at gate time (all three: caller baseline = box file = constant). (c)
  `apply_unified_diff` now validates each hunk BODY against its `@@` line-counts — a garbled
  patch that silently inserts/drops lines raises `PatchError`.
- **B2 — false-idle drain.** `metrics_inflight_probe` now treats an ABSENT gauge line as UNKNOWN
  and RAISES `DrainError` (was: `return 0` = "idle"). Only an explicit `<metric> 0` line concludes
  idle, so a freshly-restarted worker can't be drained mid-call.
- **B3 — unverified / incomplete rollback reported as success.** `WatchOutcome.rollback_verified:
  bool|None` added (True=proven golden, None=no golden to check, False→escalate). `_auto_rollback`
  now RAISES `RollbackIncompleteError` when `restored != golden_md5` instead of returning
  `rolled_back=True` with only a string note — a caller checking `.rolled_back` can no longer miss
  an earner left in an unknown state.
- Tests: +9 B1/B2/B3 regression tests. `voice_ops/deploy/` = **40 passed** (was 31).
  `pytest voice_ops/` = **412 passed**, `voice_kernel/` = **367 passed**. 0 fail.
- Changes confined to `voice_ops/deploy/{closure,drain,healthwatch,plan}.py` + its test file.
  Still 0 `agent.py`/`caller.py`/`aim_voice_agent.py` import, 0 box mutation, 0 PSTN dial.
