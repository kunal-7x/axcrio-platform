# ARCHITECTURE DECISION — Famit/Axcrio AI Revenue OS

> **What this file is:** the founder asked "what do I do FIRST." This turns the settled
> architecture verdict into THE PLAN. It does not re-open the microservices debate — that is
> settled and is the *input* here, not the deliverable. It reconciles the two prior documents
> (`EXECUTION_PLAN.md`, `.claude/plans/you-have-digitalocean-api-imperative-mist.md`), states what
> STAYS vs CHANGES, names the adopted service boundaries + scale-triggers, and gives the ordered
> build sequence from here.
>
> **Grounding:** `EXECUTION_PLAN.md` (the unit-level strangler sequence), the OCEAN master plan
> (architecture + scale ladder), and live source in `droplet_work/` (`caller.py`, `agent.py`,
> `P1_FOUNDATION_STATE.md`). Every gate cited below is taken verbatim from those — this file
> sequences and commits boundaries; it does not invent gates.

---

## 1. THE VERDICT (one line)

**Run Famit as a small number of COARSE-GRAINED deployment planes — voice/media (already its own
process), an async orchestration spine (Hatchet), and ONE control-plane API that stays a MODULAR
MONOLITH internally — plus the Next.js panel as its own deploy unit; build the ads/video engine as
the one named future service WHEN it ships, and extract anything else ONLY when a named, machine-
observable trigger fires. Do NOT decompose into microservices to scale — replicate and shard.**

This **ratifies** the existing plan (`EXECUTION_PLAN.md` line 7: "STRANGLE & EVOLVE. Modular
monolith." / master plan line 41: "modular monolith over 4 planes"). It does not overturn it. The
decision's job is to *commit the boundary names*, *harmonize the scale-triggers into one list*, and
*resolve where `caller.py` modularization lives in the sequence*. Structurally, almost everything
STAYS. See §2.

---

## 2. STAYS vs CHANGES under the decided architecture

| Concern | Verdict | Why |
|---|---|---|
| Strangle & evolve, never rebuild | **STAYS** | Live site earns; ~80% of `/api` shipped. A rebuild repeats the 90k-line mistake. |
| Modular monolith control plane | **STAYS** | Already the plan. Decision commits it as *the* boundary, not a temporary state. |
| Voice/media plane separate process | **STAYS** | `agent.py` already runs `agents.cli.run_app` — the one hard-to-scale part is *already* isolated. Keep it. |
| Postgres + RLS as the data substrate | **STAYS** | The keystone migration (P1). Unchanged. |
| Hatchet as the async spine | **STAYS** | Adopted as a *coarse plane*. Engine deploy is parallel-startable; write-path cutovers gate on P1 (status corrected below). |
| Next.js panel as own deploy unit | **STAYS** | Already separate (panel box `143.110.247.249`). Leave it. |
| Scale via single Postgres ladder | **STAYS** | Master-plan ladder is correct. Decision merges its numbers into one trigger list (§5). |
| **`caller.py` → domain modules** | **CHANGES — *where* in the sequence** | Master plan listed it as "evolve." Decision commits: it happens **AS the P1 seam-rewire (U3–U9), with per-domain APIRouters/schemas baked in** — NOT a separate prior pass, and NEVER ahead of the secrets-gate. Do it once, with boundaries baked in, not twice. |
| **Extraction triggers** | **CHANGES — harmonized** | Two trigger lists existed (master plan §scale-ceiling; verdict ladder). Decision merges them into ONE numbered, metric-fired list (§5). |
| **Ads/video/render engine** | **CHANGES — named as the one future service** | Was "Phase 8 feature." Decision commits it as the **first deliberate new service** — GPU/batch runtime trips the divergent-runtime trigger *by construction*. Build it separate when it ships. |

**Net:** nothing structural is being torn up. The decision adds three things — (a) committed coarse-
plane boundary names, (b) one harmonized extraction-trigger list, (c) `caller.py` modularization
folded into the P1 seam instead of floating as its own phase.

---

## 3. THE FINAL ARCHITECTURE — named services / boundaries adopted NOW

```
                    ┌──────────────────────────────────┐
   Next.js panel ── │  CONTROL-PLANE API (1 deployable) │  MODULAR MONOLITH internally
   (own deploy,     │  campaigns · credit ledger ·      │  stateless · N replicas
    panel box)      │  auth/RLS · tenant cfg · /api/v1  │  Postgres (RLS, per-domain schema)
                    └──────┬──────────────────┬─────────┘
                           │ enqueue          │ enqueue
              ┌────────────▼─────────┐  ┌──────▼──────────────────────┐
              │ ASYNC ORCHESTRATION  │  │ ADS / VIDEO / AUTOMATION     │
              │ SPINE — Hatchet      │  │ ENGINE  (the ONE named       │
              │ durable runs/retries │  │ FUTURE service — GPU/batch   │
              │ engine: parallel now │  │ = divergent runtime by       │
              │ cutovers: gate on P1 │  │ construction; build separate)│
              └────────┬─────────────┘  └─────────────────────────────┘
                       │ dispatch
              ┌────────▼─────────────┐
              │ VOICE / MEDIA PLANE  │  latency-critical, stateful, scales on concurrent calls
              │ LiveKit agent.py·SIP │  own runtime — ALREADY a separate process ✓
              └──────────────────────┘
```

**The four boundaries committed today:**

1. **Voice/media plane** — LiveKit `agent.py` + SIP/Vobiz on `168.144.153.145`. *Already its own
   process.* The single genuinely-hard scaling problem (concurrent live sessions) is already
   isolated here. Crash-isolated from everything else. **STAYS as-is.**

2. **Async orchestration spine — Hatchet.** Durable runs / retries / crons that must survive an API
   restart. The ONE unavoidable network boundary in the design is a **queue** — the most forgiving,
   auto-retryable, observable boundary there is. **Status (corrected, per `EXECUTION_PLAN.md` Phase
   3): the ENGINE deploy (H1/H2) is parallel-startable on its own $6 droplet now; the write-path
   cutovers (H5 `retry-callback`, H7 `campaign-run`) are BLOCKED on P1's full finalize write-set.**
   Not "in flight" wholesale — engine-ready, cutovers-gated.

3. **Control-plane API — ONE deployable, modular monolith internally.** campaigns + credit ledger +
   auth/RLS + tenant config all read/write the **same Postgres in the same transactions**.
   Stateless → scales by horizontal replicas behind a DO load balancer. Fragmenting it only converts
   atomic in-process calls into distributed sagas — the exact thing an unattended AI agent gets
   subtly, catastrophically wrong on a financial ledger. Internally it becomes per-domain
   `APIRouter`s + per-domain Postgres schemas (dial, finalize, scheduler, credit-ledger, auth,
   tenant) — built *as* the P1 seam-rewire.

4. **Panel / BFF (Next.js)** — already its own deploy unit on the panel box `143.110.247.249`.
   **STAYS.**

**The one named FUTURE service:** the **ads/video/render/automation engine** (master-plan Phase 8).
Ships as its own service *when built*, because GPU/batch runtime + a bursty third-party-API scaling
curve trip the divergent-runtime trigger by construction. The answer is never "never split" — it is
"split *that*, *when it arrives*, for *that* reason," exactly as voice already is.

**The enforcement clause (non-negotiable):** "modular monolith" only pays off if boundaries are
*actually enforced*. Add an **import-linter** (Famit's Packwerk) in CI so a module cannot reach
across its boundary. Without this, the monolith rots into the mud-ball microservices advocates
rightly fear. The enforcement is the deal.

---

## 4. THE ORDERED BUILD SEQUENCE FROM HERE (what's FIRST, what's parallel, dependencies)

**The keystone fact that dictates everything (`EXECUTION_PLAN.md` §0 fact 1):** P1-Postgres is the
dominant blocker and it is NOT done — `store.py` does not exist on disk; `P1_FOUNDATION_STATE.md`
shows **U1 IN PROGRESS**. Four subsystems hard-gate on it (credit ledger, dynamic-RAG, the Hatchet
write-path cutovers, auth JIT-provision). So "what to do first" is dominated by *clearing P1*.

### THE FIRST 3 BUILD STEPS (start now)

**STEP 1 — Secrets-gate → git → CI.** *(no creds, irreversible, instant, blocks nothing)*
`EXECUTION_PLAN.md` §3 steps 1–4 + Track-A A0–A3. Author `caps/.gitignore`, run `gitleaks` as the
net BEFORE `git init`, commit gitignore-first then snapshot, stand up `backend.yml`/`frontend.yml`
CI (ruff + pytest + gitleaks, pinned py3.12). **Gate:** gitleaks clean on the staged tree before the
first commit; no `.env`/key/`ALL_CREDENTIALS.md`/`fortress/*` ever tracked. This box was compromised
once — a committed secret is an irreversible production incident.

**STEP 2 — Drive the P1-Postgres keystone U1→U9 to `shadow_diff==0`.** *(the unblocker — the
sequential spine, opus, one unit at a time)* `EXECUTION_PLAN.md` Phase 1, executing the
`P1_FOUNDATION_STATE.md` U-list. **This is where `caller.py` gets modularized:** U3 builds `store.py`
+ rewires the `_read`/`_write` seam, and U2–U9 carve the per-domain schemas — so the APIRouter/
package split lands *with the migration*, baking in the boundaries once, not twice. **Gates (from
spec):** U3 byte-identical writes + all 200s + md5 stable; U4/U9 `shadow_diff==0` (the cutover
invariant — never declare a store cutover-ready on a silently-diverged mirror); U9 RLS cross-tenant
read blocked. Reaching `shadow_diff==0` is what unblocks the gated four.

**STEP 3 — Voice quick-wins behind a flag, after the B-DRIFT local↔box reconcile.** *(parallel, own
worktree `[WT:voice]`, opus)* `EXECUTION_PLAN.md` Track-B. **B-DRIFT FIRST (hard gate):** the live
box has FORTRESS Groq(6)/Sarvam(5) key-rotation that local `agent.py` lacks — md5/diff local vs box
(CRLF-normalized), pull box → make local a superset BEFORE any scp, or a deploy silently regresses
live rotation. Then ship the semantic turn-detector (flag `TURN_DETECTION`, default `vad`) +
adaptive barge-in behind flags. **Gate:** flag OFF = byte-identical current behavior; a real
bidirectional call shows lower eou + no mid-sentence cuts + no latency regression; instant `vad`
rollback verified available. This directly attacks priority #1 (human-feel voice).

### WHAT RUNS IN PARALLEL FROM DAY ONE (no P1 dependency)

These run concurrently in their own worktrees/boxes the moment the session starts — they touch no
product code on the spine:

- **`[WT:infra]`** — terraform-import to no-diff (DO + Cloudflare), OBS-S* security units. New files / read-only-on-box.
- **`[WT:voice]`** — STEP 3 above (gated only on B-DRIFT, not on P1).
- **`[WT:eval]`** — the eval/replay harness (E1–E6). Fully offline, reads `var/` only, zero hot-path edits — **startable on day one**, the most independent track there is.
- **`[WT:hatchet]`** — Hatchet ENGINE deploy (H1/H2) on its own $6 droplet, 127.0.0.1-bound. Engine only; cutovers wait.
- **`[WT:obs-infra]`** — Prometheus/Grafana on the panel box.

### THE SEQUENTIAL SPINE (main thread, opus, one unit at a time)

Everything that edits the 3,422-line `caller.py` serializes here — two agents on `caller.py` = lost
writes. Order (`EXECUTION_PLAN.md` §2): **P0-curation → P1 U3–U9 → RAG-3 → Hatchet H3/H6/H5/H7 →
auth AU0 → wallet W2/W4 → obs OBS-V1/V2/C2.** New-file authoring (`store.py`, `wallet.py`, `rag.py`,
etc.) happens in worktrees; each WIRE-IN to `caller.py` rejoins this spine.

### DEPENDENCY CHAIN (critical path)

```
STEP 1 (secrets/git/CI)  ──►  STEP 2 (P1 U1→U9, shadow_diff==0)  ──►  unblocks:
                                                                       ├─ credit/wallet ledger (Phase 4)
                                                                       ├─ dynamic-context RAG schema (Phase 2)
                                                                       ├─ Hatchet write-path cutovers H5/H7 (Phase 3)
                                                                       └─ auth JIT-provision (Phase 4)
STEP 3 (voice, gated only on B-DRIFT)  ──►  Phase 2 dynamic-context RAG on the voice path
[WT:eval], [WT:infra], [WT:hatchet-engine], [WT:obs] ── all parallel, day one ──►  feed later phases
```

### HOW THE LIVE SYSTEM KEEPS EARNING THROUGHOUT (the strangler guarantee)

Every unit is additive, behind a flag, non-breaking — `panel.famit.in` keeps earning the whole time.
The cross-cutting gates that enforce this (`EXECUTION_PLAN.md` §4) are the mechanism, not a promise:

- **FLAG-OFF-IS-BYTE-IDENTICAL** — every new capability defaults OFF/`json`/`vad`; flag off = provably byte-for-byte current behavior, and is the rollback path. Flip ON only after that unit's own gate is green in prod.
- **REGRESSION-GATE 200 (every unit, FIRST after deploy)** — legacy X-Auth → 200 on `/campaigns`, `/leads`, `/run`, `/billing/overview`, `/me`; famit-caller + famit-agent active. Non-200 → restore on-box `.bak.<ts>` + restart, re-run to known-good, THEN diagnose.
- **DRIFT-GATE (before EVERY box deploy)** — md5/diff local vs box for the exact file; box ahead → pull → reconcile → superset before scp. Prevents silently regressing the live FORTRESS key-rotation.
- **CRASH-SAFE PER-UNIT** — backup → small edit → instantiate-test → deploy → regression-gate → build_log → commit → flip DONE. A kill costs ≤1 unit.

---

## 5. HOW IT SCALES TO $500M ARR (one merged scale story)

**The target arithmetic.** $500M ARR ⇒ ~4–8M calls/day (master plan). Under the TRAI 9am–9pm
window, 8M/day ≈ **185 call-starts/sec** at peak and, at ~3–4 min/call, **~39,000 concurrent live
media sessions**. **That entire 39k-session load lands on the voice/media plane — which is already
its own service.** The control plane's share is ~5–10 DB ops per call lifecycle ≈ **~1–2k DB
ops/sec** — trivial for a handful of stateless FastAPI replicas over a partitioned Postgres.

**The punchline:** the one genuinely hard scaling problem is already isolated in the voice plane.
Shattering the *control plane* into microservices adds **zero** headroom to the hard part while
multiplying 2am failure modes with no human SRE awake. Scale comes from **replication + sharding**,
not decomposition.

**The ONE ladder (verdict ladder × master-plan trigger numbers, merged):**

| Rung | Action | Fires at (named, machine-observable trigger) |
|---|---|---|
| 0 | Voice plane already separate | (today) |
| 1 | Control-plane app → **horizontal replicas** behind DO LB | control-API p99 breaches SLO |
| 2 | **Separate the Hatchet/orchestration DB from the OLTP/voice-read DB** | **>60k calls/day OR p95 lead-memory read >50ms** (master plan — the FIRST trigger, noisy-neighbor guard) |
| 3 | **Postgres read replica** for panel/reporting reads | analytics reads contend with the OLTP write path |
| 4 | **PgBouncer** connection pooling | connection count approaches Postgres limits |
| 5 | **DB-per-large-tenant / read-fleet**, then **shard Postgres by `tenant_id`** | single-Postgres ceiling **~100k calls/day (~$6–13M ARR)** approached (master plan). `tenant_id` is baked into every table now, in the P1 migration — so this is config later, not a rewrite. |
| 6 | **Cells/pods** — a full replicable slice per region | a data-residency/compliance boundary (DPDP-India, GDPR-EU) forces region-pinning. Also the fault-isolation answer — no service mesh. |

At no rung does "split the control plane into microservices" appear. This ladder is how Shopify,
Instagram, GitHub, and Notion reached scale orders of magnitude past $500M — replicate the unit,
shard the data.

**Surgical extraction triggers (extract ONE component to its own service ONLY when its trigger
fires — never a big-bang rewrite):**

1. **Control-API p99 breaches SLO** *after* replicas + read-replica already added → extract the slow domain (likely analytics/reporting) to its own service + datastore.
2. **A domain's CPU/GPU profile diverges >~3–5× the core** per request → extract. **The ads/video/render engine trips this by construction — it is the named, expected first new service.**
3. **Postgres contention localizes to one table-family** (e.g., the credit ledger becomes the hot lock) → extract the ledger with its own shard/partition. (Most likely *control-plane* peel by $500M — different scaling profile + financial-correctness isolation.)
4. **A data-residency/compliance boundary** forces region-pinning a tenant class → answer with a **cell/shard**, not a service shatter.
5. **AI-agent merge-conflict rate on one module stays high** despite clean package boundaries → Famit's native version of Conway's-law team friction; extract that module behind a contract. (Evidence-triggered, not anticipated.)
6. **You hire a real human engineering team** → *then* team-independence becomes a genuine benefit; split along team lines and let Conway's Law work *for* you.

Until a trigger fires with data, splitting further is premature complexity — the documented startup-
killer. Microservices buy team-independence at an ops cost your AI agents and your uptime pay — not
scale. Scale you already have, where it's hard, in the voice plane.

---

## 6. WHY (the honest one paragraph)

Microservices are an **organizational** technology — they let many human teams deploy independently
(Conway's Law). Famit has **zero human teams**: its engineers are AI agents, its operator is one
non-technical founder with no SRE. So the single biggest reason microservices exist does not apply,
and what's left of microservices-now is pure operational cost — network partitions, partial
failures, retry storms, distributed sagas, version-skew across N deploys — every one of which is
hardest to diagnose from the stack-trace-shaped reasoning AI agents actually do, with no human to
escalate to at 2am. The repo proves this tax at N=1: `design/orchestration-hatchet.md` §0.3–0.4
documents that the moment *one* extra process appears, `_STORE_LOCK` (`caller.py:259`) "does not
span processes" and in-RAM state diverges per process — the distributed-systems tax appearing in
full from a single boundary, so dangerous the plan gates the whole cutover on Postgres-first. Scale,
meanwhile, comes from replication and sharding, and the one genuinely hard scaling problem (39k
concurrent voice sessions) is *already* isolated in its own process. So we keep the coarse planes
we have, finish the Postgres keystone that unblocks everything, modularize `caller.py` into enforced
package boundaries *as* that migration (collision-free parallel agent surfaces, zero network tax),
and extract a service only when a named metric pulls it out — the ads/video engine first, by
construction. This decision survives the founder's strongest argument ("AI agents need collision-
free surfaces") head-on: that parallelism comes from **code modularity, not network separation** —
and we deliver it with packages, not hops.

---

*Reconciled by the Chief Architect from `EXECUTION_PLAN.md`, the OCEAN master plan
(`.claude/plans/you-have-digitalocean-api-imperative-mist.md`), and live `droplet_work/` source.
This file commits boundaries and harmonizes triggers; it sequences the existing verified specs and
does not re-design them. The microservices debate is the settled input, not the deliverable.*
