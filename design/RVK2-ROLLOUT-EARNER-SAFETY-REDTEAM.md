# RVK2 — ROLLOUT & EARNER-SAFETY RED-TEAM (Grand Red-Team, pass 2 / rollout dimension)

> DOC-ONLY. No code touched, no box touched. Date 2026-06-18.
> Scope of THIS note: **rollout safety** — building 18 workflows on a branch, then
> cutting over the LIVE earner (`agent.py` outbound + `aim_voice_agent.py` inbound).
> Where could this corrupt the live agent, cause a bad deploy, or a regression that
> only shows on a real PSTN call? Is the inbound-first/outbound-later plan safe?
>
> Companion to `design/RVK2-SECURITY-ISOLATION-MASTER-GAPS.md` (security/isolation
> dimension). This note attacks the **deploy/cutover machinery itself**, not the
> code being deployed.
>
> Grounded in live ground truth (file:line + box state):
> - Plan: `C:\Users\kunal\.claude\plans\you-have-digitalocean-api-imperative-mist.md`
> - `design/RECOVERY-STATE.md` (source map + live flag state)
> - `VOICE_BRAIN_FIX_STATE.md` (last real earner deploy)
> - `CALLBACK_SCHEDULER_REBUILD_STATE.md` (root-owned deploy mechanics + last incident)
> - `droplet_work/redeploy.ps1` (the actual deploy command)
> - `memory/wave_runs/W1-kernel-core.md` (kernel integration seams)

---

## BOTTOM LINE (read this first)

**The plan's earner gate is built around the WRONG invariant.** It treats
"`agent.py` md5 == `9150fabe` and stays byte-identical" as the safety property
(plan line 58, W1 wave-run header). That invariant is **already false on the box**
and the gate is **already not protecting what it claims to**. Three structural
problems make the rollout as-written unsafe, in descending order of how-certain-to-bite:

1. **The frozen baseline is a fiction.** The plan's sacred md5 `9150fabe` is NOT
   what is running. `VOICE_BRAIN_FIX_STATE.md` records that on **2026-06-15 the
   earner was deployed to `98655dbf`** (5 env-gated fixes, flags partially ON).
   The plan, written against `9150fabe`, will "verify" the earner is untouched by
   md5-matching a hash that hasn't been live for days — and either (a) falsely
   pass, or (b) "restore the baseline" and silently *revert the founder's 4 live
   voice fixes*. The rollout's central safety check is comparing against a ghost.

2. **The deploy mechanic is a hard restart, not a drain.** Every real deploy is
   `sudo systemctl restart famit-agent` (`redeploy.ps1`, `VOICE_BRAIN_FIX_STATE.md:49,63`).
   systemd restart **kills the worker process** — and with it **every in-flight
   live call** — instead of LiveKit's supported *drain-then-replace* (old worker
   finishes active calls up to ~1h, rejects new jobs). So the cutover plan's
   "integrated smoke + assert new code loaded" is performed by an operation that,
   if any real call is in progress, **drops a paying customer mid-conversation**.
   This is not a code bug the red-team has to find later; it is baked into the
   deploy command.

3. **The "one box-change at a time" gate has no enforcement and a multi-author
   race.** Deploys are manual scp-to-`/tmp` → `sudo cp` → `systemctl restart`, on a
   **root-owned** file, with **no lock, no CI, no atomic swap**. Multiple sessions/
   worktrees are explicitly expected (global CLAUDE.md "WORKTREES & BRANCHES").
   Two concurrent deploys to the same root file = last-writer-wins corruption with
   no record of who clobbered whom. The repo is **already in proven md5-drift**
   between box and local (RECOVERY-STATE warns "box is live truth; repo can be
   stale"; the callback wave found local caller.py was stale vs box).

**Verdict on inbound-first/outbound-later: directionally correct, but NOT safe as
specified.** Inbound-first is the right *risk order*, but the plan treats inbound as
"lower risk / proves the kernel" while inbound (`aim_voice_agent.py`) is **also a
live, money-touching, customer-facing service** (AI-Manager runs privileged business
mutations) that **shares `prompt.py` with the earner** and was itself deployed/changed
on 2026-06-14. "Inbound first" is being used as a synonym for "safe to be sloppy
first." It is not. See §7.

---

## 1. THE BASELINE-DRIFT TRAP (🔴 highest-certainty blocker)

**Finding.** The plan, the W1 wave-run, and (presumably) every Wave-A agent encode
the earner law as: *`droplet_work/agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5`
stays byte-identical on the box.* This was true at plan-authoring. It is **not true
now**:

- `VOICE_BRAIN_FIX_STATE.md:36` — "DEPLOYED to box (2026-06-15 18:12 UTC). agent.py
  md5 `98655dbf` live; old `9150fabe` backed up `agent.py.bak.20260615-180938`."
- Flags partially ON live: `OPENER_ALREADY_SAID=1, LLM_CLOSE=1, EL_STABILITY=0.55,
  LANG_MIRROR_V2=1` (`:39-40`).
- `RECOVERY-STATE.md:15` still lists box agent.py as `9150fabe`. **The two
  authoritative state files disagree about what is running on the earner right now.**

**Why this corrupts the rollout:**

- **False-pass:** an agent that "verifies earner untouched" by asserting box md5 ==
  `9150fabe` will see `98655dbf`, conclude the earner was tampered with, and either
  panic-revert or hard-stop — when in fact nothing in RVK2 touched it. Wasted waves,
  or worse, an unnecessary "restore."
- **Silent regression of live fixes:** the plan's revert path is "restore the
  `9150fabe` baseline." If any RVK2 cutover step executes that revert, it **erases
  the founder's 4 voice fixes** (double-greeting, language-switch, prosody, LLM
  close) that are live and that only the founder's real call validated. The founder
  will hear his already-fixed bugs come back and not know why.
- **Re-baseline ambiguity:** plan line 114 says "re-baseline md5 of the *intended*
  new closure." But there is no recorded, agreed "intended new closure" hash —
  `98655dbf` isn't in the plan at all. The cutover has no trustworthy "known-good
  current" to diff against.

**MUST CHANGE:**
1. **Reconcile the earner baseline BEFORE Wave 0 finishes.** One authoritative,
   founder-acknowledged record: *the live earner is `98655dbf` with flags X,Y,Z ON;
   that — not `9150fabe` — is the protected baseline.* Pull the live `agent.py` and
   the live `.env` flag set, hash both, write them to `DECISIONS.md`, and make
   **the flag set part of the baseline** (a byte-identical file with a flipped env
   flag is a *different running behavior* — md5 of the file is necessary but not
   sufficient).
2. **The earner-gate invariant becomes "matches the CURRENT reconciled baseline +
   the recorded flag set," not a hardcoded constant.** Every wave reads the
   baseline from `DECISIONS.md`, never from the plan's literal `9150fabe`.
3. **Kill the "restore `9150fabe`" revert path.** Revert target = the dated box
   backup of *the current live build* (`agent.py.bak.20260615-180938` or newer),
   never the plan's stale constant.

---

## 2. THE DEPLOY IS A KILL, NOT A DRAIN (🔴 corrupts real calls on every cutover)

**Finding.** The only deploy primitive in the repo is a hard restart:
- `redeploy.ps1`: `scp agent.py prompt.py place_call.py` → `sudo systemctl restart
  famit-agent`.
- `VOICE_BRAIN_FIX_STATE.md:49`: "Each is one env flip + `sudo systemctl restart
  famit-agent`."
- `CALLBACK_SCHEDULER_REBUILD_STATE.md:29`: caller deploy = `sudo cp` →
  `sudo systemctl restart famit-caller`.

LiveKit's own model (verified, docs): a worker is a **stateful** process; the safe
update path is **graceful drain** — SIGTERM makes the worker stop accepting new jobs
but **stay alive to finish active calls** (up to ~1h on Cloud; self-host honours
`shutdown_process_timeout`, default 60s). `systemctl restart` does **stop→start**,
sending SIGTERM then (after `TimeoutStopSec`, default 90s) **SIGKILL**, and
immediately starting the new process. Result on a self-hosted single worker:

- Any **in-flight live call is cut off** at restart (or at the 90s kill if it runs
  long). The customer hears dead air mid-sentence.
- The brand-new build comes up and **registers as the worker**; the very next real
  PSTN call lands on **untested-on-real-telephony code** with no canary buffer.

**Why the plan misses it:** the plan's cutover recipe (line 114) is "backup →
flag-flip → integrated smoke → assert new code loaded → re-baseline → revert-on-
failure." Every one of those steps **requires a restart to take effect**, and the
plan never says *how* to restart without dropping live calls. "One box-change at a
time" controls *what* changes, not *whether the change murders an active call.*

**This is also why a regression "only shows on a real call":** a code path that is
byte-identical at rest and passes an offline smoke can still (a) fail to register the
worker after restart (W1 wave-run already cites issue #3104 class: "registration
hangs after process initialized"), (b) prewarm-crash silently (issue #3841 class:
"workers dying silently after prewarm → all jobs fail"), or (c) change cold-start
latency so the FIRST real call after deploy times out. None of these appear in an
offline pytest; all appear on the founder's next ring.

**MUST CHANGE:**
1. **Deploy only into a drained worker.** Add a deploy procedure that: (a) puts the
   current worker into drain (stop new jobs, keep active calls), (b) waits for
   `active_jobs == 0` (or a hard ceiling), (c) THEN swaps the file + starts the new
   worker. Never `systemctl restart` while `active_jobs > 0`. This must be a
   **pre-deploy gate**, checked and logged, not a hope.
2. **Two-worker cutover for the earner.** Stand up the new build as a **second
   registered worker** (different port/`agent_name`), send it the held synthetic
   canary + the founder's ring-test, and only after it passes do you drain-and-stop
   the OLD worker. This is the only way to validate "new code on real telephony"
   **without** the next real customer being the guinea pig. The plan's "held
   synthetic canary, never an unsolicited real PSTN burn" (line 115) is right but is
   undeliverable on a single-worker hard-restart model — it needs the second worker.
3. **Verify worker registration as a deploy postcondition, with auto-revert.** After
   start: assert "registered worker" in logs AND a synthetic job is accepted within
   N seconds; if not, auto-restore the backup and restart. redeploy.ps1 already
   greps for "registered worker" — make that a *gate that reverts on absence*, not a
   line of console output.

---

## 3. ONE FILE, MANY AUTHORS, NO LOCK (🟠 corruption-by-race)

**Finding.** The earner files (`agent.py`, `caller.py`) are **root-owned** and
deployed by **manual `scp`→`sudo cp`→restart** (`CALLBACK_SCHEDULER_REBUILD_STATE.md:29`).
There is:
- **No deploy lock.** Nothing prevents two sessions/worktrees from deploying to
  `/opt/famit-agent/agent.py` seconds apart. Last `cp` wins; the loser's change is
  gone with no error and no record.
- **Proven drift already.** RECOVERY-STATE's whole reason to exist is that the repo
  and box silently diverged; the callback wave caught local `caller.py` `ef9ae696`
  != box `32e6062f` and had to pull-before-edit. The plan runs **18 parallel
  workflows** — drift pressure goes up ~18×.
- **Backups are ad-hoc dated copies in-place** (`agent.py.bak.<ts>`). There is no
  guarantee a backup was taken before a given deploy, no manifest of which backup
  corresponds to which known-good, and `/opt` fills with `.bak.*` siblings the
  worker's own glob/import logic could in theory pick up.

**The shared-`prompt.py` landmine:** `redeploy.ps1` scp's **`prompt.py`** alongside
`agent.py`, and **`aim_voice_agent.py` (inbound) ALSO imports `prompt.py`**
(W1 wave-run: L0 source = `prompt.py SHARED_RULES`; RECOVERY-STATE tracks a single
`prompt.LIVEBOX.py`). So an outbound deploy that ships a new `prompt.py`
**simultaneously mutates inbound behavior** — the "inbound-first, outbound-later"
isolation the plan promises is **broken by a shared file the deploy script always
ships together.** A regression introduced "for outbound" silently changes the live
inbound AI-Manager prompt.

**MUST CHANGE:**
1. **A single deploy gateway with a lock.** One script/runbook is the ONLY way code
   reaches the box; it takes a flock on the box (e.g. `flock /opt/famit-agent/.deploy.lock`),
   pulls-and-hashes the live file first (detect drift → abort), backs up with a
   manifest entry (`who/when/from-sha/to-sha`), then swaps. Concurrent deploy =
   blocked, not raced.
2. **Pin `prompt.py` as a shared contract.** Either (a) split the shared
   `SHARED_RULES`/L0 source into its own module so outbound and inbound can ship
   independently, or (b) treat ANY `prompt.py` change as a change to BOTH services
   and gate it with **both** an outbound ring-test AND an inbound ring-test. The
   plan must stop pretending inbound and outbound are isolated while they share a
   deployed file.
3. **Atomic swap, not in-place cp.** `cp new /tmp/agent.py.new && mv` (same
   filesystem, atomic rename) so a half-copied file can never be the one the next
   restart imports. Keep a `current → <sha>` symlink so "what's live" is one
   `readlink`, not archaeology across `.bak.*`.

---

## 4. THE KERNEL IS NEW CODE IN THE SAME PROCESS — "ADDITIVE" IS A HALF-TRUTH (🟠)

**Finding.** The plan and W1 wave-run repeat that the kernel is "additive,
flag-gated default-OFF, never imports/edits the live agent." That is true at the
*file* level today (W1 builds `voice_kernel/` as separate files). But the cutover
**necessarily ends with the live `agent.py` / `aim_voice_agent.py` `import`ing and
calling `voice_kernel`** at the seams the wave-run names (agent.py:416/431 outbound,
aim_voice_agent.py:1436/581 inbound). The moment that import line lands:

- **A flag default-OFF protects behavior, NOT import-time crashes.** If
  `voice_kernel/__init__.py` (or any transitive import: contracts, packet, config)
  throws at import — bad dep, syntax error on the box's Python, a missing env the
  module reads at import — the **whole worker fails to start**, flag or no flag. The
  earner is down even though "the flag is off." Import-time and module-top-level
  code execute regardless of the feature flag.
- **A pure offline pytest does not exercise the box's import environment.** Box
  Python version, installed package versions, and present/absent env vars differ
  from the dev box. "pytest green locally" (W1 DoD) is necessary, not sufficient;
  the first proof the import is safe on the box is a restart — which (per §2) is the
  dangerous operation.
- **Shared global state.** `null_impls.py`, a Redis client, a tokenizer, or a model
  load done at module import adds **cold-start time and memory** to the worker even
  when the flag is OFF. A slower cold start = the first real call after restart can
  time out. This is the canonical "only shows on a real call" regression.

**MUST CHANGE:**
1. **Import the kernel behind a lazy guard, not at module top.** The integration
   seam must be `if KERNEL_OUTBOUND/INBOUND: from voice_kernel import ...` **inside
   the call path**, so OFF means *the import never executes*. Then "flag OFF =
   byte-identical behavior AND zero import-time risk" is actually true. The W1 DoD's
   `test_adapter_off_identity` must be extended to **`test_off_does_not_import`**
   (assert `voice_kernel` is not in `sys.modules` when the flag is off).
2. **A "dark import" canary on the box BEFORE the behavior cutover.** Deploy the
   integrated file with the flag OFF, restart into the drained/second worker, and
   prove: worker registers, cold-start latency within budget, memory within budget,
   `sys.modules` clean — i.e. the *import* is safe — as a SEPARATE box-change from
   *enabling* the flag. The plan collapses "ship the wiring" and "turn it on" into
   one gate; they must be two.

---

## 5. FLAG SPRAWL IS THE REAL ROLLOUT RISK SURFACE (🟠 — and it has already bitten)

**Finding.** The live `.env` is the true control plane, and it is **already drifted
and under-documented**:
- RECOVERY-STATE §2 flags `CTX_CACHE` "NOT IN .env — VERIFY", `INBOUND_PROV_LOCK`
  "absent from live .env" though "wave A committed flip to 1" — i.e. **a wave
  *thinks* it shipped a flag that is not actually live.** That is a silent
  rollout failure: the code path is dead because its env flag was never set.
- The voice-fix wave runs **7 env flags** with a red-team-mandated *deploy order*
  (C → A+B → D last) because the interactions are non-obvious
  (`VOICE_BRAIN_FIX_STATE.md:59`). RVK2 adds `KERNEL_ENABLED / KERNEL_INBOUND /
  KERNEL_OUTBOUND_SHADOW` plus per-wave flags (`RAG_INJECT_ENABLED`,
  `RETRY_SCHEDULER_ENABLED`, …). The combinatorial flag space is becoming
  un-reasoned-about.
- **The founder already got burned by a flag-gated path running unbounded:** the
  runaway callback spam (`6aa1f32`) — a scheduler loop that re-enqueued forever.
  The fix was a *kill-switch flag default-OFF*. So the precedent is established:
  flag-gated "off by default" paths get turned ON and then misbehave on the live
  box in ways offline tests didn't show.

**Why this is a rollout (not just config) risk:** the plan's entire safety story is
"default-OFF, flip per box-change." But there is **no single source of truth for the
live flag set, no validation that a deploy's flags actually landed, and no record of
flag×flag interactions.** A wave can be "deployed and verified" while its flag is
silently unset (dead code) — or two flags can be individually safe and jointly
catastrophic (e.g. `KERNEL_OUTBOUND` ON + a stale `RAG_INJECT_ENABLED=1` pointing at
an un-tenant-scoped `_global` corpus = the cross-tenant leak from the security note,
on the EARNER).

**MUST CHANGE:**
1. **A live flag manifest** (`DECISIONS.md` or a checked-in `FLAGS.md`): every flag,
   its live value, owning wave, default, and "what turning it ON does + what it
   interacts with." Updated on every deploy. RECOVERY-STATE §2 is the seed; make it
   mandatory and complete.
2. **Post-deploy flag assertion.** After any deploy, read back the *effective* env
   the worker loaded (not what you intended to set) and assert it equals the
   manifest. The `INBOUND_PROV_LOCK`/`CTX_CACHE` "committed but not live" class of
   bug must be impossible to ship silently.
3. **Define and TEST the dangerous flag combinations** as part of W17's golden set,
   not discover them on the box. At minimum: every `KERNEL_*` × `RAG_INJECT_ENABLED`
   × `RETRY_SCHEDULER_ENABLED` × `WALLET_ENABLED`/`FIREWALL_ENABLED` combination
   that touches spend or tenant scope.

---

## 6. "VERIFIED ON BRANCH IN ISOLATION" ≠ "WORKS ON A REAL CALL" (🟠 the regression class the plan can't see)

The plan's DoD (line 63) and gate (line 110) lean heavily on "built + verified
on-branch in isolation," "integrated real-flow smoke," "offline-verify." The
**entire category of failures that bit this product before are precisely the ones
that pass branch verification and fail on a real PSTN call:**

| Regression class | Why offline/branch verify misses it | Real example in this repo |
|---|---|---|
| Env captured at import | A stale value is frozen when the module loads; offline test re-imports fresh | Warm transfer "failed on stale SIP trunk (env captured at import)" — plan diagnosis line 36 |
| Worker won't register after restart | pytest never registers a LiveKit worker | LiveKit issue #3104 (cited in W1 wave-run context) |
| Silent prewarm death | offline import succeeds; the prewarm subprocess dies only under the worker | LiveKit issue #3841 |
| Cold-start latency / first-call timeout | offline has no TTFA clock against a live carrier | TTFA P50<1s target is meaningless until measured on the carrier |
| Provider key exhaustion / 498 capacity | offline mocks the provider | plan warns Groq Flex fails fast 498; Sarvam/Groq key round-robin exists *because* keys get rate-limited |
| TTS provider silently wrong | offline asserts the code path, not the audio | "Sarvam TTS silent — disabled, always ElevenLabs" (plan line 32) — a config drift, invisible offline |
| Half-word truncation | only audible | `GROQ_MAX_TOKENS=90` guillotine (plan line 27) — the founder *heard* it |

**MUST CHANGE:** the acceptance bar for any earner-touching cutover is **a real
founder ring-test on the carrier, with the specific listen-for list**, BEFORE merge —
which the plan does say for outbound (line 116) but **NOT for inbound** (line 114
lets inbound "integrate first" as if branch-verify suffices). Make the inbound
cutover gate identical: a real inbound call to the live DID, founder on the line,
listen-for checklist, before the inbound kernel flag stays ON. See §7.

---

## 7. IS INBOUND-FIRST ACTUALLY SAFE? — PARTLY. WHAT MUST CHANGE (🟠)

**The good part (keep it):** inbound first is the correct *sequencing* — outbound is
the primary earner (real PSTN spend, the founder's revenue), so proving the kernel on
inbound before betting the earner is sound risk order.

**The dangerous assumption (fix it):** the plan frames inbound as "lower risk,"
implying it's OK to be less careful. Ground truth says otherwise:
- **Inbound is live, customer-facing, money-touching.** `aim_voice_agent.py` runs the
  AI-Manager that executes **privileged business mutations** (security note #8: PIN
  gate). Breaking inbound = breaking a live capability a real caller hits.
- **Inbound was deployed/changed days ago** (`aim_voice_agent.LIVEBOX.py` `1614be09`,
  2026-06-14 naturalness fix) — it is NOT a quiet, safe sandbox; it has its own live
  baseline that the kernel cutover must respect, on the **same box / same Python /
  possibly same worker host** as the earner.
- **Inbound shares `prompt.py` with outbound** (§3). A kernel change at the inbound
  seam that touches the shared L0/SHARED_RULES source leaks into outbound.
- **"Proves the kernel" overclaims.** Inbound exercises a *different* path (no PSTN
  dial-out, different SIP direction, different provider lock). A green inbound
  cutover does **NOT** prove the outbound hot path, dial loop, wallet hold/settle,
  or carrier TTFA. The plan must not let an inbound pass lower the bar for the
  outbound gate.

**MUST CHANGE:**
1. **Treat the inbound cutover with the FULL gate**, identical to outbound: drained/
   second-worker deploy, dark-import canary, real inbound ring-test by the founder
   with a listen-for list, auto-revert. Not "integrate first" as a euphemism for
   "less rigor."
2. **Isolate the inbound flag from the earner `.env` for real.** The W1 wave-run
   says `KERNEL_INBOUND` is "scoped via systemd drop-in so it can't leak to the
   earner .env" — verify that drop-in is actually a *separate* env file the earner
   service does not read, and prove it (print the earner's effective env, assert
   `KERNEL_*` absent). If inbound and outbound are the **same worker process**, a
   per-call flag (not a process-env flag) is required, because one process can't
   have the kernel ON for inbound jobs and OFF for outbound jobs via a process-level
   env var.
3. **State plainly what inbound CANNOT prove**, so the outbound gate isn't softened:
   carrier TTFA, dial-loop, wallet settle, outbound prompt-cache, barge-in on a real
   PSTN leg — all are outbound-only and require their own real-call proof.

---

## 8. CALLER.PY / CONTROL-PLANE IS A SECOND EARNER THE PLAN UNDER-WEIGHTS (🟡)

The plan's earner law is all about `agent.py`. But **`caller.py` is the FastAPI
control plane** — dispatch, tenant resolution, billing routes, the scheduler
(`RETRY_SCHEDULER_ENABLED`), webhooks, the campaign loader. Many of the 18 waves
(W3 ingestion, W8 events, W10 callback, W12 number-pool, W13 provider config) land
**in or adjacent to `caller.py`**, which is **also root-owned and restart-deployed**
(`CALLBACK_SCHEDULER_REBUILD_STATE.md:29`). Restarting `famit-caller`:
- drops in-flight HTTP requests / dispatch creations,
- can wedge the scheduler (the runaway-spam file lived here),
- is the actual injection point for G-ROOT-1 (tenant in dispatch) — i.e. the most
  security-critical change ALSO rides the riskiest, least-protected deploy path.

**MUST CHANGE:** `caller.py` gets the **same** deploy gateway (lock, drift-check,
atomic swap, backup manifest, post-restart health gate) and the **same** "drain
in-flight before restart" discipline as `agent.py`. The plan's "one box-change at a
time" must count caller.py changes as box-changes, not free.

---

## 9. NO PRODUCTION OBSERVABILITY = BLIND CUTOVER + BLIND ROLLBACK TRIGGER (🟡)

The plan's verification is **human ("founder ring-test") + offline (pytest/golden)**.
There is **no live SLO/alerting that auto-detects a bad cutover in the minutes after
deploy** when the founder is NOT on the line. After a cutover the next 50 real calls
are unobserved: if TTFA regresses, a provider key gets banned, the worker silently
stops accepting jobs (issue #3841 class), or 5xx climbs — nobody knows until a
customer complains. W17 builds the eval harness *on branch*; it does not put a
**live post-deploy watch + auto-rollback trigger** on the box.

**MUST CHANGE:** the cutover gate's "revert-on-failure" needs a *signal*. Define a
**post-deploy soak window** (e.g. first N minutes / first M calls) with concrete
auto-rollback triggers: worker-not-registered, job-accept-rate < threshold, TTFA P50
> budget, 5xx > 0, provider-error spike, recording-finalize failures. Until that
exists, every cutover is "deploy and pray the founder happens to call." (The kill-
switch flags help, but a human has to notice first.)

---

## 10. MIGRATIONS, DATA & DUAL-WRITE — THE NON-CODE CUTOVER (🟡)

Several waves change **persistent state shape**, and DB/state migrations are a
cutover risk the plan's `agent.py`-md5 lens is blind to:
- W4 RAG (new vector stores, `_global`→per-tenant corpus split), W7 lead-memory
  (hot/warm/cold + `STORE_MODES=dual` strangler), W9 recording/retention TTLs, W10
  callback queue shape, W8 event backbone. The live system **already runs a
  dual-write strangler** (`STORE_MODES=dual`, RECOVERY-STATE §2).
- A schema/format change deployed with code but **without a backfill/rollback for the
  data** = the new code reads old-shape rows (or vice-versa) and fails *only on
  records that already exist*, i.e. on real customer data, not test data. Classic
  "only shows in production."
- **Rollback is not just `cp agent.py.bak`** once a migration has run forward —
  reverting the code while the DB is migrated-forward is its own corruption.

**MUST CHANGE:** every wave that touches persistent shape ships an **expand→migrate→
contract** plan (additive columns/stores first, dual-read, backfill, only then
contract) with an explicit **data-rollback** that is decoupled from the code-rollback.
No wave is "done" if its rollback story is "restore the .py backup" while its
migration has already mutated rows.

---

## TOP BLOCKERS (ranked — fix before any RVK2 cutover touches the box)

| # | Blocker | Why it bites | Owning wave / change |
|---|---|---|---|
| B1 | **Earner baseline is a ghost** — gate compares to `9150fabe`; live is `98655dbf` + flags | False-pass OR silent revert of the founder's live voice fixes | **Wave 0** (reconcile baseline + flag set into `DECISIONS.md`); fix the gate in W1 + cutover recipe |
| B2 | **Deploy = `systemctl restart` (kill), not drain** | Every cutover with a call in flight drops a paying customer; first real call hits untested-on-carrier code | **NEW deploy-gateway** + two-worker/drain cutover; rewrite plan line 114-116 |
| B3 | **No deploy lock + root-owned single file + proven drift, ×18 parallel waves** | Concurrent deploys clobber each other silently; box/repo drift already real | **NEW deploy-gateway** (flock + drift-check + atomic swap + backup manifest) |
| B4 | **Shared `prompt.py` ships with outbound but drives inbound too** | "inbound/outbound isolated" is false; an outbound deploy mutates live inbound | **W1 + deploy-gateway**: split shared L0 module OR dual-ring-test any prompt.py change |
| B5 | **Kernel import-time risk under an OFF flag** | Flag-OFF protects behavior, not imports; a bad import = earner won't start | **W1**: lazy in-path import + `test_off_does_not_import` + dark-import canary as its own box-change |
| B6 | **Flag sprawl, no live manifest, no post-deploy flag read-back** | "committed a flag" ≠ "flag is live" (already happened: `INBOUND_PROV_LOCK`); unsafe flag×flag combos | **Wave 0 FLAGS.md manifest** + W17 dangerous-combo golden set + post-deploy assert |
| B7 | **Inbound treated as "low-risk sandbox"** | Inbound is live, money-touching, shares prompt.py; a green inbound pass can't lower the outbound bar | **Plan edit**: full gate on inbound; explicit "what inbound can't prove" |
| B8 | **No live post-deploy soak/auto-rollback signal** | Bad cutover is invisible until a customer complains | **W17 + deploy-gateway**: soak window + concrete auto-rollback triggers |
| B9 | **caller.py is a second earner on the same unprotected deploy path** | The most security-critical change (tenant-in-dispatch) rides the riskiest deploy | **deploy-gateway applies to caller.py**; count caller.py changes as box-changes |
| B10 | **Migrations/data cutover decoupled from code rollback** | New code on old-shape real rows fails only in prod; code-revert ≠ data-revert | **Per-wave expand→migrate→contract + data-rollback** (W4/W7/W8/W9/W10) |

---

## WHAT MUST CHANGE IN THE PLAN (concrete edits)

1. **Add a Wave-0 deliverable: BASELINE RECONCILE.** Pull live `agent.py` +
   `aim_voice_agent.py` + `caller.py` + `prompt.py` + the live `.env` flag set;
   hash each; write the *current* protected baseline + flag manifest to
   `DECISIONS.md`/`FLAGS.md`; founder-acknowledge it. **Replace every literal
   `9150fabe` in the plan and wave-runs with "the reconciled current baseline."**

2. **Add a NET-NEW wave: DEPLOY-GATEWAY (call it W-DEPLOY / NEW-W24).** One locked,
   drift-checking, atomic-swap, backup-manifesting, drain-aware deploy path that is
   the ONLY way code reaches the box, used by `agent.py`, `aim_voice_agent.py`, AND
   `caller.py`. Two-worker/drain cutover for the voice workers. Post-restart
   registration + health gate with **auto-revert**. This wave **gates every other
   wave's deploy** (nothing cuts over until it exists). It is the rollout analogue of
   the security note's NEW-W20 (legacy-token retirement gates W8–W16).

3. **Rewrite DEPLOY GATE (plan lines 110-116)** to:
   (a) deploy file with kernel flag OFF → drained/second worker → **dark-import
   canary** (registers, latency/mem budget, `sys.modules` clean) → soak;
   (b) ONLY THEN flip the behavior flag as a *separate* box-change → synthetic canary
   → **real founder ring-test with listen-for list** → soak with auto-rollback
   triggers;
   (c) inbound gets the SAME (a)+(b), not a softer "integrate first";
   (d) outbound never validated by a single-worker hard restart while calls are live.

4. **Make `prompt.py` a contract.** Split shared L0/SHARED_RULES so outbound and
   inbound deploy independently; until then, any `prompt.py` deploy requires BOTH an
   inbound and an outbound ring-test.

5. **W1 DoD gains two tests:** `test_off_does_not_import` (kernel not in `sys.modules`
   when flag off) and `test_import_safe_on_box_python` (a box-pinned import smoke run
   in the dark-import canary, not just dev pytest).

6. **W17 gains:** dangerous flag-combination golden set; live post-deploy soak +
   auto-rollback trigger definitions; carrier-TTFA-on-real-call as an acceptance
   metric (not just an offline target).

7. **Every state-touching wave (W4/W7/W8/W9/W10)** ships expand→migrate→contract +
   a data-rollback decoupled from the code-rollback. "Restore the .py backup" is not
   a rollback for a forward-migrated DB.

---

## ONE-LINE BOTTOM LINE

The plan's safety story is "one byte-identical file, flag-gated, one change at a
time, founder ring-test." Ground truth breaks all four legs: **the baseline isn't
byte-identical (it's already `98655dbf`+flags), the deploy is a call-killing restart
not a drain, "one change at a time" has no lock against 18 parallel waves on a shared
root file, and the shared `prompt.py` means inbound and outbound aren't isolated.**
Inbound-first is the right order but is being used as cover for lower rigor. Build a
real deploy-gateway (lock + drift-check + atomic swap + drain/two-worker cutover +
dark-import canary + post-deploy soak/auto-rollback), reconcile the true baseline
into durable state, and gate inbound with the same full rigor as outbound — **before**
any RVK2 code cuts over to the box. Otherwise the first regression that "only shows on
a real call" is a near-certainty, and the worst case is dropping live customers
mid-call during a deploy you thought was safe.
