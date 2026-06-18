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
