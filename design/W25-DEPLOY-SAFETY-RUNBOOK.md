# W25 — Voice Deploy-Safety Runbook + Tooling

**Wave:** W18 / C6 / NEW-W25.
**Branch:** `fix/realtime-voice-kernel-v2`.
**Scope:** TOOLING ONLY. This wave builds the deploy-safety primitives under
`voice_ops/deploy/` (new, tracked, droplet-free). It does **NOT** deploy, does NOT
touch the live box, and NEVER imports/edits `agent.py`. EARNER LAW honored: the
OUTBOUND earner live = `98655dbfc71d5c3da36bcfe3f848082c` (KERNEL_OUTBOUND=0,
rolled back).

---

## 1. The problem this fixes

The deploy primitive today is `systemctl restart <unit>` — a **hard kill**, not a
drain. SIGTERM is sent, then SIGKILL after `TimeoutStopSec` (systemd default 90s).
Consequences on the single live voice worker:

- It **cuts any live LiveKit call mid-sentence**.
- It **lands the new code directly on the carrier** with no staging/canary
  isolation.
- The held-synthetic-canary "never a real PSTN burn" is **undeliverable on a
  single worker** — the canary would occupy the only worker.

The manual cutover this session proved the right discipline. This wave **codifies**
that discipline into repeatable, tested tooling (no box calls in the tests — every
box interaction goes through an injected `ExecTransport`; tests inject a fake).

---

## 2. The tooling (`voice_ops/deploy/`)

| Module | Responsibility |
|---|---|
| `transport.py` | The ONE seam for box interaction. `ExecTransport` Protocol (run/read/write/exists/md5). Real impl = SSH (lazy, not imported at load). `FakeTransport` = in-memory fs + scripted command results + ordered command log. **All tests run through the fake → zero SSH, zero box, zero PSTN.** |
| `closure.py` | `DeployClosure` = `{relpath → md5}` manifest (CRLF-normalized, matches the box `_verifydeploy.py` idiom). `compute_intended_md5(golden, patch)` = apply a unified diff locally → `py_compile` gate → md5 = the **INTENDED-NEW-CLOSURE**. Fails closed on a wrong golden / stale patch / broken syntax. |
| `plan.py` | The deploy engine. `EarnerGate.assert_ok` (md5==golden + MainPID present + /health 200). `backup()` (cp aside + verify backup md5). `stage_and_assert()` (write to release dir, **assert landed md5 == intended-new-closure**, refuse to swap otherwise). `atomic_swap()` (`flock` + `ln -sfn …tmp && mv -T …tmp current` = atomic rename). `deploy_flag_off()` runs preflight→backup→stage→swap in the invariant order. |
| `drift.py` | `DriftChecker` builds the box's current closure and diffs it against the expected local closure → added/removed/changed with md5s. `assert_no_drift()` is a hard pre-deploy gate. |
| `drain.py` | `DrainOrchestrator.drain_then_restart()` = SIGTERM-to-main (enters SDK drain, NOT `systemctl stop`) → **poll in-flight until 0** (deadline-bounded) → restart. `metrics_inflight_probe` reads the active-jobs gauge and **fails closed on BOTH a curl error AND an ABSENT gauge** (B2): only an explicit `<metric> 0` line concludes idle — a freshly-restarted worker whose gauge isn't registered yet is treated as UNKNOWN, never idle, so its live call is never cut. `TwoWorkerPlan` generates the templated systemd unit + the rolling-drain runbook (see §5). |
| `canary.py` | `SyntheticCanary` = greeting render (+ optional md5-equality) + tool dry-run + DB deep-health. **Fails closed** (an exception or any non-OK check = FAIL). **NEVER dials PSTN** — there is no SIP/telephony call anywhere in the module, by construction. |
| `healthwatch.py` | `HealthWatcher.watch()` runs the held canary first, then watches health for a settle window. On canary FAIL or `fail_threshold` consecutive non-200s, **fires the auto-rollback** and verifies the earner is back to golden md5. A single intermittent blip is tolerated (`fail_threshold`). |
| `rollback.py` | `RollbackGenerator` → a single idempotent one-command bash script (restore backup/symlink + force flag OFF + daemon-reload + restart + re-assert golden md5 & /health 200). `execute()` runs it through the transport (the auto-rollback path). |
| `runbook.py` | `render_runbook()` assembles the human-readable runbook (every gate + the staged one-command rollback verbatim). |

Tests: `voice_ops/deploy/tests/test_deploy_safety.py` — 31 tests. Proves:
intended-closure assertion **catches a wrong/truncated file** before swap; box↔local
**drift detected**; drain **waits for in-flight** before restart (and raises on
deadline); canary **fails closed** (empty render / bad DB / raised exception);
auto-rollback **fires** on health fail AND on canary fail; backup runs **before**
swap; atomic swap uses `flock` + `mv -T`; rollback script + runbook content; and a
guard asserting **no droplet / agent / heavy-SDK module is imported**.

---

## 3. The invariant deploy order (what the engine enforces)

1. **PREFLIGHT EARNER GATE** — assert box `agent.py` md5 == frozen golden
   `98655dbfc71d5c3da36bcfe3f848082c`, `famit-agent` MainPID present, `/health`
   200. Hard abort on any mismatch (nothing mutated yet). **Construct the gate
   with `EarnerGate(..., earner_golden_md5=EARNER_GOLDEN_MD5)`** so `expected_md5`
   is itself asserted == the frozen constant (B1): the caller-supplied baseline,
   the box file, and the constant are all tied together — a baseline that isn't
   the known golden fails closed before any box fact is read.
2. **BACKUP FIRST** — `cp -p agent.py agent.py.WOUTbak.<ts>`; verify backup md5 ==
   current target md5.
3. **COMPUTE INTENDED-NEW-CLOSURE md5 LOCALLY** — golden + unified-diff patch →
   `py_compile` → md5. Done off-box, before any upload. **Pass
   `compute_intended_md5(golden_bytes, patch, expected_golden_md5=EARNER_GOLDEN_MD5)`**
   so the golden bytes are asserted == the frozen earner BEFORE patching (B1): a
   patch that applies cleanly against the WRONG golden can't produce a wrong
   intended md5. The diff applier also validates each hunk body against its `@@`
   line-counts, so a garbled patch that silently inserts/drops lines fails closed.
4. **UPLOAD FLAG-OFF** — stage into the release dir; **assert landed md5 ==
   intended-new-closure**. Refuse to swap on any mismatch (catches a wrong /
   truncated file).
5. **ATOMIC SWAP** — `flock` the deploy lock; `ln -sfn <release> current.tmp &&
   mv -T current.tmp current`. `current` is never partial (atomic rename).
6. **FLAG-OFF SMOKE** — restart only the target unit; `/health` 200; render the
   golden greeting and assert byte-identical to the backup (render-equality gate).
7. **GRACEFUL DRAIN + RESTART** — drain in-flight to 0, then restart onto the
   swapped code (single-worker) OR rolling-drain across two workers (§5).
8. **FLAG-ON FLIP** — set `KERNEL_OUTBOUND=1` in the systemd drop-in (NEVER the
   shared `.env`); `daemon-reload`; restart. Verify via `/proc/<pid>/environ` the
   flag is present on THIS unit and **absent** on the other unit.
9. **HELD SYNTHETIC CANARY** (no PSTN) — greeting render + tool dry-run + DB
   deep-health. Fail-closed → triggers auto-rollback.
10. **HEALTH WATCH + AUTO-ROLLBACK** — watch the unit for the settle window; on
    non-200 (≥ fail_threshold) OR canary fail, fire the staged rollback. Pass
    `HealthWatcher(..., golden_md5=EARNER_GOLDEN_MD5)`; the outcome's
    **`rollback_verified`** proves the restored md5 == golden. If the rollback is
    INCOMPLETE (`restored != golden`), the watcher **raises `RollbackIncompleteError`**
    (B3) — the earner is in an UNKNOWN state needing manual intervention; a caller
    must check `rollback_verified`, not just `rolled_back`, before trusting recovery.
11. **POSTFLIGHT EARNER GATE** — md5 on box == intended-new-closure, PIDs healthy,
    `/health` 200.
12. **ONE-COMMAND ROLLBACK** is staged **before** step 8 and always ready.

**Flags live in systemd drop-ins, never the shared `.env`** — a value in
`/opt/famit-agent/.env` leaks across all three units (`famit-agent`,
`aim-voice-agent`, `famit-caller`) on their next restart. Per-service flags go in
`/etc/systemd/system/<unit>.service.d/*.conf`.

---

## 4. Why `systemctl restart` cuts calls (the load-bearing systemd fact)

A LiveKit worker that receives SIGTERM runs its own `drain()`: it stops accepting
new dispatches and lets in-flight calls finish, up to `drain_timeout` (SDK default
1800s). But systemd SIGKILLs the main process after `TimeoutStopSec` (default 90s).
**If `TimeoutStopSec` < `drain_timeout`, systemd kills the worker mid-drain and
cuts the live calls.** The fix is a one-line unit config: `TimeoutStopSec=1800`
(match `drain_timeout`). `TwoWorkerPlan.systemd_unit()` emits exactly this, and
flags it as the single most important line in the file.

---

## 5. RECOMMENDATION — register a SECOND LiveKit worker (the real fix)

A single worker makes "drain while serving" and a "held synthetic canary"
impossible — there is no second worker to take new calls while the first drains.
**Register a second worker on the same dispatch rules** (`famit-agent@1` /
`famit-agent@2`, ports 8091/8092 via the templated unit `TwoWorkerPlan` emits).
Both register independently with the same `agent_name`; LiveKit distributes new
jobs across all non-draining workers weighted by load.

### Rolling-drain deploy (no call ever cut, real held canary)

0. Precondition: **both** workers registered + healthy; new code already
   atomic-swapped into `current`; flag still OFF.
1. **Drain A** — `systemctl kill -s SIGTERM --kill-who=main famit-agent@1`. A stops
   taking new jobs; **B now serves all new dispatches → no capacity gap**.
2. Wait until A in-flight == 0 (poll its metrics; deadline = `drain_timeout`).
3. **Restart A** onto the new code (`systemctl restart famit-agent@1`).
4. Health-gate A (`/health` 200) + optional **HELD synthetic canary on A** while B
   keeps serving real traffic. The canary can be held as long as needed — it never
   touches the carrier.
5. **Drain B** — same SIGTERM; now A serves all new dispatches.
6. Wait until B in-flight == 0; restart B onto the new code; health-gate B.
7. Both workers on new code → flip the feature flag ON → postflight earner gate.

**Rollback at any step:** re-point `current` → previous release + flag OFF +
restart whichever worker(s) took the bad code; the still-good worker kept serving
throughout. `RollbackGenerator` emits this as one command.

### Atomic-swap layout on disk (prereq for the rolling drain)

```
/opt/famit-agent/
├── current -> releases/<id>/      # symlink, atomically repointed (mv -T)
├── releases/<id>/                 # immutable once swapped (keep last ~3)
├── .env                           # shared; flags NOT here
└── .deploy.lock                   # flock target for the swap
```

The atomic swap stages the new file, asserts its md5 == intended-new-closure, then
`mv -T` the symlink — closing the window where a partial SCP could land a truncated
file.

---

## 6. Operating the tooling (later, when a real re-deploy happens)

These primitives are reusable for the next earner re-deploy (the voice-fix). A
driver wires a real SSH `ExecTransport`, then:

```python
from voice_ops.deploy.closure import compute_intended_md5
from voice_ops.deploy.plan import DeployPlanEngine, EarnerGate
from voice_ops.deploy.drain import DrainOrchestrator, TwoWorkerPlan
from voice_ops.deploy.canary import SyntheticCanary
from voice_ops.deploy.healthwatch import HealthWatcher
from voice_ops.deploy.rollback import RollbackGenerator

intended = compute_intended_md5(golden_bytes, patch_text)   # off-box, up front
engine   = DeployPlanEngine(transport=ssh)
gate     = EarnerGate(expected_md5=GOLDEN, target_path="/opt/famit-agent/agent.py", ...)
record   = engine.deploy_flag_off(gate=gate, intended=intended)   # preflight→backup→stage→swap
rollback = RollbackGenerator.from_record(record, golden_md5=GOLDEN, flag_name="KERNEL_OUTBOUND", ...)
# ... flag-off smoke, drain+restart, flag-on flip ...
watcher  = HealthWatcher(transport=ssh, rollback=rollback,
                         canary=SyntheticCanary.default(ssh, render_url=..., tool_url=...))
outcome  = watcher.watch()     # accepts, or auto-rolls-back to golden
```

The real SSH transport is the only piece to add at deploy time; everything else is
already tested.

---

## 7. Status

- All `voice_ops/deploy/` modules built; 31 dedicated tests green.
- `pytest voice_ops/ voice_kernel/` green (717 passed).
- Zero box mutation, zero `agent.py` import, zero heavy-SDK/droplet import (guarded
  by a test).
- Ledger: `memory/wave_runs/W25-deploy.md`.
