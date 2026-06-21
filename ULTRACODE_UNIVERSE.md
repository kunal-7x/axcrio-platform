# 🌌 THE ULTRACODE UNIVERSE — building an entire product with many workflows

> The full doctrine for the "father of the father" architecture: how to build an *entire product* (many
> modules, in parallel) by having the **main conversation loop act as a durable CONDUCTOR that launches
> MANY independent top-level workflows over many turns** — NOT by nesting workflows infinitely (which the
> platform forbids). Source: 15-agent research run wf_ad1e4bc5-eac (archived in `research/raw/05-*` and
> `research/agents/05-*`). This is prompt Part Q in full. Read before attempting a universe-scale build.

---

# PART 1 — THE ULTRACODE UNIVERSE (architecture)

The universe is how you build an *entire product* — many modules, parallel — instead of one workflow's worth of work. It is NOT "infinite nested workflows." It is a **single durable conductor (the main conversation loop) launching MANY independent top-level workflows over many turns**, each fanning out phases × agents, plus exactly ONE allowed level of sub-workflows, plus the 5-deep Task subagent tree inside agents — all coordinating through a durable **disk blackboard that ONLY the conductor and agents touch (never the workflow script)**.

## 0. THE ONE LIE TO UNLEARN FIRST
**Workflows nest only ONE level, and a nested child shares the parent's everything** — the same 16-concurrency pool, the same 1000-agent counter, the same token budget, the same abort signal. So `workflow()`-inside-`workflow()` buys you **organization, not horsepower**: zero extra concurrency, zero extra agents, zero isolation. **All real scale comes from the conductor launching independent TOP-LEVEL runs**, each of which gets its OWN fresh 16-pool, OWN fresh 1000-counter, OWN token budget, OWN abort signal. If you ever catch yourself drawing a "conductor workflow that launches node workflows," stop — that is the trap; the conductor is the main loop and is **never itself a workflow.**

## 1. GROUND-TRUTH CAPABILITY MAP (honest, with the corrections baked in)
| # | Claim people make | The truth | Consequence for building |
|---|---|---|---|
| 1 | "Workflows can use the filesystem." | **The orchestration SCRIPT cannot** — sandboxed JS host, no `fs`/`child_process`/`fetch`/`require`. Its ONLY I/O is `agent()`/`parallel()`/`pipeline()`/`phase()`/`workflow()` and the **values** they pass/return. **Agents it spawns DO have Bash/Read/Write/Edit** and (with `isolation:'worktree'`) their own checkout. | The script is **pure compute over values**. Contracts go IN as **string args**; results come OUT as **return values**. Only **L0 (main loop) and agents** touch disk. |
| 2 | "1000 agents/run is the ceiling." | **False in practice — the per-run TOKEN budget binds first and ABORTS the run when exceeded.** A heavy build agent burns ~100k–400k tokens; the budget caps a heavy run at **~30–150 real agents**, not 1000. | Size runs by **tokens and wall-clock**, not agent count. Treat 1000 as a distant rail; the token budget is the cliff. |
| 3 | "N runs × 1000 = unlimited scale." | The agent counter is per-run (real multiplier). But **all N runs bill against ONE plan account** — shared per-family ITPM/OTPM + weekly/5-hour Max. Ten runs collectively wall into the rate limit and **429-throttle ALL at once.** | The conductor needs a **global token governor**: `active_runs × per_run_burn < plan_TPM × 0.7`. Width = TPM headroom, not partition count. |
| 4 | "16 concurrent per run." | True but **CPU-gated**: effective width = `min(16, cores − 2)`. 8-core laptop = **6**, not 16. 3 runs = `3×6 = 18` real concurrent, not 48. | Publish the real number for the machine. Never plan 16-wide on a laptop. |
| 5 | "Subagents nest infinitely." | Task subagents nest **~5 deep on CC ≥ 2.1.172** (version-gated; probe it). A depth-≤4 foreground subagent CAN launch a workflow but **double-counts CPU/TPM** and is auto-denied (background) or human-gated (foreground). | Use the subagent tree for **interactive** hierarchy. **Hoist ALL workflow launches to the top-level main loop.** Never cross the two trees under load. |
| 6 | "`resumeFromRunId` makes it crash-safe." | **Resume is SESSION-SCOPED.** Exit Claude Code mid-run → next session starts it **fresh**. A cron tick / sleep / limit-reset = a new session = run **restarts from agent zero and re-bills.** | Durability lives **on disk, L0-owned, at the NODE grain** — not the runtime cache. Cross-session continuity = **re-launch nodes whose on-disk acceptance probe still fails**, never "resume a run." |
| 7 | "Workflows can ask the user / merge / replay." | **No mid-run user input** (for sign-off, run each stage as its own workflow). Script has no git/shell. Sub-agent **Writes don't always persist** (partial sandboxing). | Human gates are **workflow boundaries** (run returns `NEEDS_HUMAN` → L0 asks via AskUserQuestion → launches next). Merge/replay/verify are **named agents**. Every DONE is **L0-reverified against real disk.** |

## 2. THE DEFINITIVE LAYER → MECHANISM STACK
| Layer | What it IS | Mechanism | Disk? | Multiplies scale? | Mortality |
|---|---|---|---|---|---|
| **L0 — Conductor** | The **main conversation loop**. The real root. Holds plan/DAG/ledgers; launches runs; reconciles; reality-gates. | Its own Read/Write/Edit/Bash + workflow invocations + completion-notify + AskUserQuestion, **across turns**. | **YES** — the ONLY layer that owns the blackboard. | Indirectly — the sole launcher of independent top-level runs. | **Mortal & session-bound.** Dies on sleep/limit/close. State MUST be a fold over on-disk logs. |
| **L1 — Workflow run (node)** | One **independent top-level workflow** = one bounded build unit (a module / slice / the kernel / the integrator). | `workflow run` returning a small JSON manifest; own 16-pool, own 1000-counter, own budget, own abort. | **NO** (script). Its **agents do.** | **YES — the ONLY scale multiplier.** Universe width = number of independent L1 runs. | Ephemeral; ends on return. No cross-session resume. |
| **L1.5 — Sub-workflow** | `workflow()` from inside a run for an *inseparable* dependent sub-phase. | One nested level, **sharing parent's pool/counter/budget/abort.** | NO. | **NO** — organization only. Debits parent's 1000. | Dies with parent. |
| **L2 — Phases & agents** | `phase()` checkpoints + `agent()`/`parallel()` fan-out. Does the product work. | `parallel(width≤effective)` → reduce; agents have full tools + optional worktree. | **Agents: YES.** Script: no. | Within a run (16/budget bound). | Per-agent; cached **within the session only.** |
| **L3 — Task subtree** | An agent decomposing further via Task subagents, ~5 deep (CC≥2.1.172). | Foreground Task tree inside one agent. | Yes (each a full agent). | **Budget-OPAQUE inside workflows** — may not count vs 1000 but burns tokens/concurrency. | Per-task. |

**The disk/value boundary (the rule that makes it buildable):**
```
L0 (has FS) ── reads contract from disk ── passes as STRING arg ──▶ L1 workflow (script, NO FS)
                                                                      │ spawns AGENT (has FS):
                                                                      │   writes code + git commit to its worktree
                                                                      │   returns a CONCLUSION string
                                                                      ▼
                          L1 returns {module, status, contractDigest, gaps, artifactRef} VALUE
L0 ◀── persists manifest to /blackboard, updates ORCHESTRATOR.md, reverifies on real disk ──┘
```

## 3. HOW SCALE *REALLY* COMES (the arithmetic, honestly)
- **The single multiplier is L0 launching many independent top-level runs over turns.** Each run = fresh 16-pool + fresh 1000-counter + fresh token budget + own abort. That is the whole game.
- **Real concurrent agents** ≈ `active_runs × min(16, cores−2)`. (8-core laptop, 3 runs → **18**, not 48.) Publish this.
- **Real ceilings, in binding order:** (1) **per-run token budget** (caps a heavy run at ~30–150 agents and aborts it) → (2) **shared plan TPM / weekly Max across ALL runs** (throttles every run at once) → (3) **the return-value funnel** (wide fan-outs + upward returns dump into script memory and ultimately L0's context) → (4) **partial-failure/idempotency** (orphan worktrees, non-idempotent resume, stragglers holding the 16-pool).
- **The agent counter is NOT a universe cap.** There is **no platform-level universe agent ceiling**: N runs = up to `1000·N` agents = `~$400·N` Opus with nothing stopping it. `MAX_UNIVERSE_AGENTS` and a dollar ceiling are numbers **L0 must invent and enforce** in a ledger.
- **What bounds N is L0's own context window**, not the runtime. → **L0 holds an INDEX, never the payloads:** each returned manifest is written to `/blackboard/contracts/<node>.json` and **dropped from working memory**, keeping one line in `ORCHESTRATOR.md`. N is bound by disk, not context.
- **Abort is per-run and lossy** — siblings don't share an abort. A universe-wide stop = a **loop over `TaskStop` across every persisted `runId`**, and in-flight waves (`≈16N × atom`) still finish and bill. The honest guarantee is **"bounded overshoot," not "instant universe halt."**

## 4. WHEN TO DEPLOY THE UNIVERSE vs A SINGLE WORKFLOW vs THE PLAIN TREE
| Use… | When | Why / honest caveat |
|---|---|---|
| **Plain Task subagent tree** (no workflows) | Interactive, in-conversation work: exploration, a feature or two, anything you watch; any step that may need human approval. | Cheapest; no script sandbox; human can approve foreground prompts. **The only mode where mid-task human gating works.** ~5 deep; no scripted scale. |
| **A single top-level workflow** | One bounded, well-specified unit fitting **one token budget + acceptable crash-loss wall-clock**: a module, a migration, a wide map-reduce, an eval grid. ~30–150 heavy agents or a swarm of trivial ones. | Deterministic fan-out, results in script vars not context, in-session `resumeFromRunId`. Don't exceed one budget/sitting — a killed run restarts whole. |
| **The full UNIVERSE** (L0 conducts many runs) | An **entire product**: many modules with a shared contract surface, built parallel, integrated, reality-gated — work exceeding one run's budget AND spanning turns/sessions. | The only way past 1000 agents / one budget. **Requires the control plane (Part 2).** Skip it and it's a happy-path demo that throttles and strands work the first night. |
| **Scheduled cloud agents / cron Warden** | True 24/7 "works while you sleep" — reconcile/reap/re-drive while the laptop is off. | The **only** real background path. Local L0 dies with the laptop; cron re-launches nodes whose on-disk probe still fails (cannot resume in-flight runs). |

## 5. THE UNIVERSE TOPOLOGY (one screen)
```
                         ┌──────────────────────────────────────────────┐
                         │  L0 CONDUCTOR  = main conversation loop        │
                         │  • owns /blackboard (DAG, ledgers, contracts)  │
                         │  • launches top-level runs across turns        │
                         │  • reconciles on every turn (disk = truth)     │
                         │  • reality-gate + AskUserQuestion at boundaries│
                         │  • MORTAL: state = fold over on-disk JSONL     │
                         └───────────────┬──────────────────────────────-┘
        launches (each = fresh 16-pool, fresh 1000, own budget, own abort)
   ┌───────────────┬───────────────┬───────────────┬───────────────┐
[Kernel run]   [auth run]      [billing run]   [webhooks run] ...  (N independent TOP-LEVEL runs)
 returns        returns         returns          returns           ← small JSON manifests only
   │  each run internally: phase()→parallel(agents ≤ min(16,cores−2))→reduce ; maybe ONE workflow() sublevel
   │  each agent: full tools + own worktree ; may Task-fan ~5 deep (budget-opaque)
   ▼
[Integrator run] ── merges branches in DAG order in a STAGING universe ── emits machine-checkable e2e suite
   ▼
L0 reality-gate (runs the real product) → serial canary promotion to the live heart, one revertible box at a time
   ▲
[cron Warden] (cloud) ── reconciles dead leases, reaps zombie worktrees, re-launches failed-probe nodes 24/7
```

## 6. NON-NEGOTIABLE INVARIANTS
1. **The script touches no disk and asks no human.** Contracts in as args, manifests out as returns; disk and humans are L0-only.
2. **Scale = many top-level runs, never nesting.** `workflow()` is for inlining a dependent sub-phase only.
3. **Durability is a checkpointed node artifact on disk, written by L0; runId is ephemeral + session-scoped.** Resume = re-launch nodes whose acceptance probe fails.
4. **One worktree per concurrent run, one agent per file within it.** Shared-seam files (lockfiles, migration counter, route/DI/OpenAPI registry) are a **serialized lane**, never parallel; migration numbers **pre-allocated** at DAG time.
5. **Every DONE is L0-reverified against real disk** (re-run the test, stat the files, check the tag). A green isolated manifest is a *claim*. **Missing verdict = dead-letter, never pass.**
6. **Returns are handles + small structured summaries, never bulk** — keep a top-level run's return < ~2KB so it never bloats L0's context. Reduce as you ascend.
7. **Three caps the platform does NOT give free, all enforced in L0 ledgers:** `MAX_UNIVERSE_AGENTS`, per-family TPM governors, hierarchical per-run sub-budgets — plus a **verification reserve** build phases cannot draw from.

---

# PART 2 — THE UNIVERSE EXECUTION PROTOCOL

The control plane lives **outside both runtimes** — in L0 (the main loop) and on disk — because every durable, cross-run, cross-session concern is by design invisible to the workflow runtime.

## 0. WHO RUNS WHICH LAYER
| Layer | Identity | Write disk? | Launch top-level runs? | Ask a human? |
|---|---|---|---|---|
| **L0** | the **main conversation loop** | **YES** (own tools) | **YES** | **YES** (AskUserQuestion) |
| **L1 run** | a top-level workflow **script** | no | no | no |
| **L1 agent** | a spawned Claude agent | **YES** | no | no |
| **L1.5** | nested `workflow()` | no | no | no |

The conductor **is not a workflow and never becomes one.** Its "atomic write" is a main-thread `Write`/`Edit`; its "launch node" is a main-thread workflow invocation returning a `runId`; its "poll" is completion-notify + a `Monitor`/`ScheduleWakeup` cadence.

## 1. THE BLACKBOARD (on-disk control plane, L0-owned)
```
/blackboard/
  ORCHESTRATOR.md     # human-readable: one line/node {id, status, runId, contractRef, attempts}
  build.state.json    # the DAG: nodes {id, deps[], owns[], status, runId, contractPath, attempts, epoch, est}
  contracts/          # contract.lock per seam = TYPED interface stubs / OpenAPI / schema (the frozen kernel)
  RUNS/<runId>/events.jsonl   # append-only, one event/line, the durability log
  LEDGER.json         # {budget_usd, spent_usd, reserved, MAX_UNIVERSE_AGENTS, agents_spent, runs:[{id,est,actual,epoch}]}
  OWNERS/<glob-hash>.json     # per-partition file leases (sharded, NOT one hot file)
  OWNERS/WAITERS.jsonl        # FIFO of denied ownership requests
  SHARED_SEAMS.md     # every cross-cutting file forbidden to parallel modules
  QUARANTINE.md       # nodes that struck out → routed around
  HUMAN_TASKS.md      # open forks for the user to steer
```
**Rules:** only L0 writes the shared markdown/state (single-writer). Agents inside runs **return** status; if an agent must record to shared state it does so via a dedicated **Scribe agent** writing **append-only JSONL** keyed `(runId, node, phase)` so concurrent writes stay reconcilable + idempotent. **L0 holds the INDEX in context, the payloads on disk** — drop each manifest from working memory after persisting it.

## 2. THE CONDUCTOR CONTROL-LOOP (runs every L0 turn; survives compaction)
```
ON EACH TURN (and on every completion-notify):
1. RECONCILE FIRST (trust disk, not memory):
   - read build.state.json + fold each RUNS/<id>/events.jsonl into live status
   - for every non-terminal run: check GROUND TRUTH — expected commits / passing test / git tag present?
       • probe passes  → mark node DONE-VERIFIED (L0 reverified, not self-reported)
       • probe fails & no heartbeat > T turns → presume dead → resumeFromRunId IF same session, ELSE relaunch only the unfinished slice
       • runId lost (compaction) → recover from LEDGER.json (every runId persisted at launch) and re-probe
2. REAP: `git worktree prune` + delete branches/worktrees of dead/aborted runs (the script can't; L0 must). Fence zombies: write FENCED tombstone keyed to old claim_token; the per-agent commit primitive aborts if its run is fenced.
3. BUILD READY SET: nodes whose deps are DONE-VERIFIED and whose owns[] don't overlap any in-flight node's owns[]. Apply AGING (a waiting node's priority rises) so a wide node can't be starved by cheap leaves.
4. ADMIT under the governor: for each candidate reserve at p90/ceiling cost; admit only if it fits LEDGER headroom AND active_runs < width cap AND per-family TPM headroom AND MAX_UNIVERSE_AGENTS not breached. Else queue.
5. LAUNCH admitted nodes as INDEPENDENT TOP-LEVEL runs; persist {runId, est, epoch} to LEDGER.json BEFORE the run can spend.
6. On a returned manifest: persist to contracts/, append event, update ORCHESTRATOR.md, reconcile reserved→actual, DROP payload from context.
7. On NEEDS_HUMAN: AskUserQuestion (options + custom + a NOTE/option); on no-response default safely + log to HUMAN_TASKS.md. Never end a turn typing questions as prose.
8. If READY≠∅ but nothing admits for K ticks (all blocked on ownership) → STUCK: break the tie deterministically + log HUMAN_TASK; never spin.
9. YIELD; rely on completion-notify to re-enter THIS session. Post-crash there is NO notify — the cron Warden re-drives via disk probes.
```

## 3. FRACTAL DECOMPOSITION INTO A WORKFLOW-DAG
**Recursion = L0 re-launching the primitive, NOT `workflow()` nesting.** The product is a **kernel → parallel-slices → reduce** DAG, minimum 3 stages — never a flat map.
1. **Phase 0 — the Shared-Kernel node (built FIRST, frozen).** One L1 run produces ONLY the shared surface: API contracts, shared types, DB schema, design tokens, event contracts. **Compile it:** emit `contract.lock` as typed stubs/OpenAPI + a build-only skeleton (all seams stubbed) that **must typecheck and link** before any other node launches. A seam with no consumer = unused export (lint); no producer = unresolved import (compiler); a mismatch = type error. "Seam closure" becomes a **compiler-checked invariant**, not an LLM assertion — the one oracle that doesn't share the planner's blind spot.
2. **Topologically sort and REJECT CYCLES** before launching (gateway-needs-auth while auth-needs-gateway is a DAG bug — fix the contract).
3. **Slice the rest.** Each feature slice receives the **frozen kernel as read-only args**, forbidden to redefine it — converting "independent siblings" (false) into "siblings sharing a frozen kernel" (true), so reduce is a **wiring** job, not a **reconciliation** job.
4. **Size each slice by CRASH-LOSS, not agent count.** A killed slice re-runs whole and re-bills, so target: **reaches a committable contract in ≤2–3 agent-waves, ≤~150 lifetime agents, finishes within one sitting's wall-clock.** Prefer **shallow-wide (2–3 phases: fan-out-build → reduce-verify)** over deep 7-phase chains (you can't checkpoint mid-run). Scale phase-count to node size.
5. **fits_one_run() pre-flight:** estimate `expected_agents × p75_tokens × 1.5`; if over budget OR wall-clock, **split the node** and record the split in the DAG. Re-slice **reactively** from per-run telemetry.
6. **One legal `workflow()` level** only for genuinely inseparable in-slice sub-steps; everything separable re-launches from L0.

## 4. ECONOMICS, SCHEDULING & GLOBAL STOP-LOSS (the real arithmetic)
- **Atom & linearity.** `atom = (in_tokens + out_tokens) × family_rate`. Heavy build agent ≈ 100k–400k tokens. A 1000-agent Opus run ≈ **$400**. No universe agent cap → N runs = up to **$400·N** unless L0 caps it.
- **Reserve at the CEILING, reconcile to actual.** Enforcement is poll-based with up to one-cadence lag → reserve at **p90 atom (or `in + max_tokens_out`)**, never the mean. Feed a trailing `actual/est` ratio per role back into the next estimate.
- **Global token governor (per-family).** ITPM/OTPM are **separate buckets per family**, and **cached input tokens are exempt**. Keep **three rolling counters (Opus/Sonnet/Haiku)**; throttle the hot family; credit caching against ITPM. Admission: `active_runs × per_run_burn < plan_TPM × 0.7`; near ceiling, drop run-width cap to 1 and prefer cheap nodes.
- **Hierarchical budgets.** Delegate `run_budget = priority_share × pool`; each run's ceiling draws from ITS sub-budget. Reserve a **verification floor (≈30% tokens + a fixed agent-count)** build phases **cannot draw from** — else you abort exactly at the gate that decides correctness.
- **Agent counter as a reserved resource.** A retry storm / deep Task tree can exhaust the per-run 1000 without blowing dollars and hard-stop mid-critical-path. Cap coordination agents at **≤10% of a run's budget** (batch claims; one long-lived warden heartbeats all leases).
- **Cross-run cache staggering.** Account-wide prompt cache, ~5-min TTL. Pin a **canonical frozen prefix** and **stagger launches inside the TTL** so the warm prefix is paid **once per universe**.
- **Global stop-loss — honest.** No shared abort across siblings. A universe stop = **loop `TaskStop` over every persisted `runId`**; in-flight waves still drain and bill `≈ 16N × atom` (N=6 all-Opus ≈ **~$38** unstoppable overshoot — hold as headroom). Guarantee = **"bounded overshoot," provided every runId was persisted at launch.**
- **Batch −50% is a SEPARATE universe.** Batches are async (≤24h) — incompatible with the live conductor. Use only for the **offline/eval universe** driven by a cron agent. For the interactive build, batch is off the table.

## 5. UNIVERSE-SCALE VERIFICATION & FAILURE-CONTAINMENT
**Epistemics:** evidence > assertion; agreement ≠ truth; a green isolated component is NOT success. The only truth is the user's real integrated flow working.
- **Compile the contract** (3.1) so Layer-0 closure has a real oracle.
- **VERIFY is a SEPARATE top-level run** launched by L0, never `workflow()`-nested (nesting shares abort+budget = no isolation). Build run returns evidence as *input data* to a fresh Verify run with its own budget.
- **All hands-on work is a NAMED agent, never the script:** a **Replayer** (decorrelated lineage) re-runs each evidence bundle verbatim in a clean worktree and diffs observed vs claimed; an **Integrator** merges branches in **seam topo-order** (producers before consumers) treating **any merge conflict as a Layer-0 ownership defect** (fix the contract, not the conflict); a **Scribe** is the single writer of shared state.
- **Positive-attestation (no-news-is-bad-news):** a node advances **only on a present, completed, signed verdict.** Missing verdict = **auto-dead-letter**, never pass — a crashed verifier auto-quarantines instead of reading as "no objection → pass."
- **Replay-N + flake quarantine:** spine-seam evidence must **replay K times (≈3) stably**; a varying result is **FLAKY → dead-lettered.** Pin seeds/clocks/network mocks.
- **Risk-tiered depth (budget-driven):** rank seams by transitive blast-radius. **Spine seams** (auth, shared schema, data contract) get decorrelated multi-prompt + adversarial + audit; **leaf seams** get single execution-grounded fail-to-pass. Fan a 300-seam product across ~6 build+verify run pairs so no run nears 1000.
- **Decorrelation ladder, honest ceiling:** within one model family true independence is bounded. (1) **context isolation** (verifier never sees the builder's tests/reasoning — strongest) → (2) adversarial role inversion → (3) temperature/seed diversity → (4) cross-family only where wired. For spine seams, **escalate to the human gate** rather than trust intra-family agreement.
- **Flow-controlled human gate:** human accepts **≤ K items (≈7)**, ranked by `blast-radius × disagreement-anomaly`; overflow auto-quarantines. Never DoS the one human.
**Failure containment:** transactional leaf (artifacts in isolated worktrees, one Integrator promotes, resume re-runs only un-promoted work) · per-agent timeout + k-of-N gating (proceed when ≥k return) · contract-drift firewall (a contract change is a first-class event: bump `contracts/v2/`, compute blast radius, force re-verify of downstream; only `breaking` forces rebase) · quarantine/circuit-breaker (N strikes → route around, ship the slice without it, escalate) · **staging-universe/canary split** (full assembly + integration smoke in an ephemeral staging universe, NEVER live; promotion to the live heart re-serialized seam-by-seam in topo-order, each with a revert path) · **release-gate predicate:** ship ⇔ `(all ship-blocking seams green) AND (no dead-lettered seam is consumed by a shipped seam) AND (degraded set ≤ threshold)`.

## 6. THE 24/7 WARDEN (the only true background tier)
The local L0 dies with the laptop. Stand up a **scheduled cloud agent / cron Warden** (server-side) that periodically: reconciles dead leases, rebuilds the index from event logs, fences zombie worktrees, and **re-launches every node whose on-disk acceptance probe still fails** (it cannot resume in-flight runs). Add **epoch/generation numbers**: bump `epoch` each conductor restart, embed it in every lease/claim_token/branch; after a restart, anything from `epoch < current` is provably abandoned and bulk-reclaimable. Without the Warden, recovery only happens when the user manually types "continue."

## 7. CONTROL FLOW (one screen)
```
PLAN  → decompose product into kernel→slices→reduce DAG; pre-allocate migration numbers; list SHARED_SEAMS; topo-sort; reject cycles
KERNEL→ launch Kernel run; compile contract.lock; skeleton must typecheck+link  ── GATE: no slice launches until kernel frozen
LOOP  → every turn: RECONCILE(disk) → REAP+FENCE → READY(deps+owns+aging) → ADMIT(governor+ledger+TPM+universe-cap) → LAUNCH top-level runs → persist manifests, drop payloads
VERIFY→ each slice's evidence → separate Verify run → Replayer re-runs K× → positive-attestation (missing=dead-letter)
REDUCE→ Integrator merges in topo-order in STAGING; conflict=contract defect; consumer contract-check per step
GATE  → integration smoke emits machine-checkable e2e suite → L0 reality-gate runs the REAL product → AskUserQuestion at boundaries
SHIP  → release-gate predicate true → serial canary promotion to live heart, one revertible box at a time; quarantine routes around broken nodes
WATCH → cron Warden re-drives failed-probe nodes 24/7; epochs reclaim abandoned work
```

## 8. WORKED EXAMPLE — a SaaS (auth + billing + webhooks + dashboard) on an 8-core laptop
- **Real concurrency:** `min(16, 6)` = **6 agents/run**; L0 runs **≤3** top-level runs at once → **~18 real concurrent agents**, not 48.
- **T0 PLAN.** L0 writes `build.state.json`: nodes = `kernel, auth, billing, webhooks, dashboard, integrator`. Edges: feature nodes `dep: kernel`; `integrator dep: {all features}`. Pre-allocate migrations: auth `0001–0003`, billing `0004–0008`, webhooks `0009–0010`. `SHARED_SEAMS.md`: `package.json, pnpm-lock.yaml, migrations/_journal, routes/registry.ts, openapi.yaml`. Topo-sort OK.
- **T1 KERNEL.** Launch Kernel run; agents emit typed stubs + OpenAPI + Prisma schema + design tokens; a stubbed skeleton must **typecheck + link** → contract **frozen** (a missing consumer would surface as an unused-export lint error here).
- **T2.. BUILD (parallel, governed).** L0 launches `auth`,`billing`,`webhooks` as three independent top-level runs, **each in its own worktree**, each fed the frozen kernel as read-only args, shallow-wide (~120 agents). `dashboard` admits after a slot frees (cap=3). Each persists `{runId, est, epoch}` to LEDGER before spending. Manifests return small; L0 writes them to `contracts/` and **drops them from context**.
- **Mid-build reality:** webhooks run dies silently at agent ~110 (socket). Next turn RECONCILE probes its worktree, sees commits but no completion + no heartbeat → presumes dead → same session, `resumeFromRunId` finishes the un-promoted slice. billing strikes out twice on a flaky external-pricing test → **replay-N flags FLAKY → quarantined**, routed around, logged to HUMAN_TASKS.md.
- **VERIFY.** Each green slice → a **separate Verify run**; a **Replayer** (fresh, context-isolated, never sees the builder's tests) re-runs each evidence bundle K=3×. Spine `auth` also gets adversarial + audit; leaf `webhooks` gets single execution-grounded check. Any slice with **no completed verdict is dead-lettered.**
- **REDUCE in STAGING.** **Integrator** merges worktrees in topo-order on an ephemeral staging branch; webhooks-vs-billing both touch `routes/registry.ts` → conflict → treated as a **Layer-0 ownership defect** → L0 moves `registry.ts` to the **serialized shared-seam lane** and regenerates it.
- **Contract-drift event.** Reality-gate finds webhooks expects `event.v2` but billing emits `v1` → bump `contracts/v2/` marked `breaking`, blast radius `{billing, webhooks}`, **force-reverify only those two.**
- **GATE + SHIP.** Integrator emits a machine-checkable e2e suite; L0 **reality-gates by running the real wired product**; release-gate predicate true (billing-pricing degradable-quarantined, no shipped seam consumes it) → promote to the live heart **seam-by-seam, each revertible**, pricing left as a HUMAN_TASK.
- **Honest close:** the per-module manifests being green proved nothing on their own — **only L0 re-running the integrated product proved the build**, and only the user's own real use proves it ships.
