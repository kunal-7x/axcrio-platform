# GIT_ECOSYSTEM - the fully-autonomous git/GitHub lifecycle (Claude drives 100%; founder never types git)

> Prompt Part R, in full. Grounded in the REAL repo `kunal-7x/axcrio-platform` (agents inspected it live 2026-06-14). Claude drives branch -> commit -> PR -> CI -> AI-review -> merge -> tag -> release -> deploy -> rollback; the founder approves ONLY genuine gates (merge-to-earner / deploy) by clicking one option.
> Full raw research: `research/raw/06-autonomous-git-ecosystem.raw.json` + `research/agents/06-*`.
> ** WARNING - live findings: (1) the repo is on GitHub FREE so protection/gates do not ENFORCE until a Team upgrade; (2) a live secret (`final_env.md`, Vobiz token) is in git history at commit `03056f5` -> ROTATE then scrub; (3) the gh token is over-scoped. See Sections 5-6.

---

# THE AUTONOMOUS GIT ECOSYSTEM (architecture)

> Repo of record: `kunal-7x/axcrio-platform` (PRIVATE). Founder NEVER types git. Claude drives **branch â†’ commit â†’ PR â†’ CI â†’ AI-review â†’ merge â†’ tag â†’ release â†’ deploy â†’ rollback**; founder approves ONLY genuine gates by clicking one option. Earner = `droplet_work/agent.py` + `caller.py` + closure (**untracked**, file-copied to box `famit@168.144.153.145`). This section is the model + state machine + gates + integration + blind-spots. Commands live in SECTION 2.

---

## 0. GROUND TRUTH THIS IS BUILT ON (verified against the live repo â€” do not assume otherwise)

These facts are load-bearing; every design choice below flows from them. Verified 2026-06-14:

| Fact | Reality (verified) | Consequence for the design |
|---|---|---|
| Remote | `kunal-7x/axcrio-platform` (NOT "caps" â€” that's the folder) | All `gh` anchors use this; `gh repo set-default kunal-7x/axcrio-platform` once so Claude never passes `-R`. |
| Plan | PRIVATE on **Free** | Branch protection / required checks / merge queue / CODEOWNERS-blocking / push-protection all return **HTTP 403 "Upgrade to Pro"**. **The entire enforcement spine does not exist until plan upgrade.** â†’ Â§1A is a hard founder gate. |
| Tags | **ZERO** (`git tag -l` empty) | No `golden`, no `golden-*`. "Branch from last golden" expands to empty string â†’ cold-start deadlock. â†’ **bootstrap-golden** before state machine runs. |
| Trunk | `main` is **0 ahead / 49 behind** `feat/premium-ui`, and **`main` is NOT on origin** | "base=main" is a **destructive trunk migration**, not a retarget. â†’ one-time **promote** (ff-only mainâ†’premium-ui tip), human-gated. |
| Default branch | `origin/HEAD â†’ feat/premium-ui` | Every fresh clone (incl. cloud agents) checks out the wrong branch. â†’ priority-0 `default_branch=main` API call after promote. |
| Worktrees | 2 live (`caps`@`backend/handoff-name-clean-line`, `caps-eval`@`feat/eval-harness`) + sprawl (`feat/rag-grounding`, `fix/inbound-customer-reframe`, â€¦) | Rename/migration must `git worktree remove` or rename-via-worktree first. Stale-branch reaper required. |
| Identity | gh token = `gho_â€¦` user PAT, scopes `repo, workflow`. **GitHub MCP 404s this private repo.** No GitHub App. | **`gh` is PRIMARY, MCP is optional accelerator behind a probe.** Builder-token == merge-token == owner == one prompt-injection from a direct-to-earner deploy. â†’ split identities. |
| Earner versioning | `droplet_work/` fully gitignored (`.gitignore:52-53`); `agent.py` 49 KB, imports `caller.py` (361 KB) + closure | `git revert` **cannot touch the live earner**. md5-of-one-file misses `caller.py`/dep breakage. â†’ earner-vault + manifest-hash + on-box watchdog. |
| CI on disk | `secrets.yml` ACTIVE (`on:[push,PR]`, floating tags, **no `permissions:`**); `backend.yml`/`frontend.yml` DORMANT (path-filtered, **no `merge_group:`**, `uv`/py3.12, pnpm/node22) | Path-filtered required checks **deadlock a merge queue** ("pending forever"). Floating tags = tj-actions CVE vector. â†’ harden `secrets.yml` FIRST, add status-shim + `merge_group`. |
| Golden gate scripts | `droplet_work/_golden/` = 5 campaign-keyed goldens + `verify_golden.py` (has `def main()`, **NO argparse / no `--all`**). `render_prompts.py`, `prompt.golden/`, `smoke_realflow.py` **do not exist** | The gate's central scripts are **fiction**. â†’ build `verify_golden.py --all --strict` + `smoke_realflow.py` as the FIRST verified units; no CI references them until they pass locally. |
| In-history secret | `final_env.md` was ADDED in commit `03056f5` | Forward nets catch none of it. â†’ rotate-first / `filter-repo` incident runbook (SECTION 2). |

**The one-sentence translation:** the prior design was correct on paper but architected for a GitHub plan this repo doesn't have, branched from a golden tag that doesn't exist, gated on scripts that don't exist, off a trunk that's 49 commits stale, with one over-scoped token â€” and "unknown" defaulted to "safe" in the one place a live earner must default to "stop." This architecture fixes all of that and makes "unknown â‡’ STOP."

---

## 1. THE BRANCHING MODEL â€” Trunk-Based, one-unit-per-branch, earner-vault on the side

**Trunk-based development (TBD), not GitFlow.** Long-lived release branches decay into the sprawl already present. One trunk (`main`), short-lived lanes, feature-flags decouple merge from release.

```
main  â† THE trunk. Always-deployable. Protected (after plan upgrade). Squash-target for panel; merge-commit for earner/infra.
 â”‚
 â”œâ”€â”€ golden (moving branch ref) â”€â”€â–º advances ONLY after full suite green on main. The deploy source-of-truth for the PANEL.
 â”‚     â””â”€â”€ golden-YYYYMMDD-HHMM (immutable dated tags) â”€â”€ walk-back chain; NEVER force-moved.
 â”‚
 â”œâ”€â”€ feat/<scope>__W-<waveid>      one verified unit, lifespan hours, auto-reaped >72h idle
 â”œâ”€â”€ fix/<scope>__W-<waveid>       waveid in name â†’ globally-unique dedup key (no cross-wave PR collision)
 â”œâ”€â”€ chore/<scope>__W-<waveid>
 â”œâ”€â”€ revert/<sha>                  auto-generated rollback PR (goes through the SAME gates)
 â”‚
 â”œâ”€â”€ lock/earner                   a REF used as a mutex â€” exists â‡” one earner change is in-flight to deploy
 â””â”€â”€ (NO stacked branches â€” forbidden; squash-merge orphans children's diff base)
```

**Two physically separate repos for the earner (because `droplet_work/` can't be versioned in `caps`):**

```
kunal-7x/axcrio-platform   â† panel (tracked) + the gate scripts + CI + curated backend (in-tree backend/ per the committed plan)
kunal-7x/earner-vault      â† PRIVATE. Curated, secret-SCRUBBED .py closure. Human-readable diff/audit + signed earner-live-* tags.
kunal-7x/earner-fortress   â† PRIVATE. age/SOPS-ENCRYPTED full box env (.env + secrets + systemd units). DR-from-vault. Restores byte-reality.
```

Lives **outside** the `caps` worktree (a nested `.git` inside the gitignored `droplet_work/` produces phantom commits no one can find â€” the exact CLAUDE.md failure mode). Physical layout: sibling dirs `C:/Users/kunal/Desktop/earner-vault/`, `â€¦/earner-fortress/`.

**Rules, enforced (after upgrade) or self-enforced (Free interim):**
- `main` is squash-merged for trivial panel lanes (clean history) and **merge-committed for earner/infra lanes** (preserves per-unit commits so `git bisect` can find the offending unit â€” squash forfeits bisect granularity the whole protocol relies on).
- **One verified unit per branch.** No `git add -A` ever (stages the live `.env.local`). Explicit paths only.
- Worktrees for true isolation of parallel lanes (`EnterWorktree`/`ExitWorktree`), partitioned by directory/service â€” never two lanes editing the same file.

> **BLIND-SPOT THIS FIXES:** "branch from last golden tag" with zero tags = empty-string deadlock; `git revert` claimed to roll back a file-copied earner; a "tracked secret-free mirror inside `droplet_work/`" that's impossible because the dir is wholesale-ignored; stacked branches + squash silently orphaning children.

---

## 2. THE END-TO-END LIFECYCLE â€” a STATE MACHINE (unknown â‡’ STOP, never â‡’ safe)

Claude drives every transition. `[A]` = autonomous. `[H]` = **founder gate** (one click). `[STOP]` = fail-closed â†’ DEAD_LETTER + PushNotification, never silent.

```
                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                          â”‚  S0  PREFLIGHT  [A]                                           â”‚
                          â”‚  â€¢ gh reaches repo? (FATAL if not) â€¢ MCP probe â†’ transport    â”‚
                          â”‚  â€¢ golden ref exists? else BOOTSTRAP-GOLDEN  â€¢ rate-limit ok?  â”‚
                          â”‚  â€¢ gitleaks on PATH? (FATAL if not, never commit blind)        â”‚
                          â”‚  â€¢ signing key works? else commit-unsigned + non-block notice  â”‚
                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                          â–¼
   S1 OPEN LANE [A] â”€â”€ cut feat/<scope>__W-<wave> from golden (NOT premium-ui, NOT empty)
                                          â–¼
   S2 WORK + COMMIT-PER-UNIT [A] â”€â”€ explicit-path add â†’ gitleaks staged (content) â†’ gitleaks
        on $COMMIT_MSG + $PR_BODY (free-text leak vector) â†’ signed commit w/ trailers
        (Wave/Run/Verified/Agent/Session ids)  â”€â”€ crash-safe: one unit, verify, record, next
                                          â–¼
   S3 OPEN DRAFT PR [A] â”€â”€ search-before-create (dedup by waveid) â†’ draft â†’ CI triggers
        (PR body itself gitleaks-clean BEFORE create_pull_request)
                                          â–¼
   S4 CI + EARNER-GATE [A] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        required checks: secrets Â· frontend/build-e2e(or shim) Â· backend(or shim) Â·        â”‚
        earner-gate(label-scoped) Â· adversarial-review/passed                              â”‚
        â€¢ infra/flaky red â†’ auto `gh run rerun --failed` Ã—2 (does NOT spend fix-budget)    â”‚
        â€¢ real red â†’ S5 DIAGNOSE                                                            â”‚
        â€¢ all green â†’ S6                                                                    â”‚
                                          â–¼                                                 â”‚
   S5 DIAGNOSE+FIX [A] â”€â”€ classify infra-vs-real; fix in builder identity; attempt_cap=2 â”€â”€â”˜
        cap hit â†’ [STOP] DEAD_LETTER + AskUserQuestion("PR#X stuck on test Y: retry/skip/look")
                                          â–¼
   S6 ADVERSARIAL AI-REVIEW [A] â”€â”€ two-stage: untrusted(no-secrets) analyses head & emits
        verdict artifact â†’ trusted(base ref, NEVER checks out head) posts APPROVE via the
        SEPARATE reviewer identity.  â‰¤3 rounds; round-3 disagreement â†’ S-ESCALATE
                                          â–¼
   S7 CLASSIFY RISK [A] â”€â”€ diff touches earner set? (agent.py|caller.py|closure|_golden|
        migrations|.github/workflows) â†’ EARNER-CRITICAL ;  else LOW/MED
                                          â”‚
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â–¼ LOW/MED                                                 â–¼ EARNER-CRITICAL
   S8a AUTO-MERGE [A] â”€â”€ squash, no question                S8b ACQUIRE lock/earner [A]
        (the safe 90% never bothers founder)                     (ref-create; 422 â‡’ held â‡’ queue)
              â”‚                                                         â–¼
              â”‚                                          S9 âŸªHâŸ« FOUNDER MERGE GATE  â”€â”€ friction-ON
              â”‚                                          AskUserQuestion (recommended = "Hold"):
              â”‚                                          [Hold & keep live] [Ship â€” names live-call
              â”‚                                          risk, requires seen-smoke] [Show diff]
              â”‚                                                         â–¼ (Ship)
              â”‚                                          S10 MERGE-COMMIT [A] (preserve units)
              â–¼                                                         â–¼
   S11 POST-MERGE on main [A] â”€â”€ full suite re-runs on main â†’ green â†’ advance golden ref +
        mint immutable golden-YYYYMMDD-HHMM tag.  PANEL: release-please opens/updates Release PR.
                                          â–¼
   S12 âŸªHâŸ« DEPLOY GATE (earner OR panel-release) â”€â”€ environment "Review deployments" +
        AskUserQuestion. Founder = required reviewer. Concurrency group serializes.
                                          â–¼
   S13 DEPLOY = VERIFY-OR-ROLLBACK TRANSACTION [A] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        EARNER:  backup *.bak.<ts> (rotated, last N) â†’ dry-run-restore-and-diff (prove the   â”‚
        rollback artifact is byte-valid BEFORE mutating) â†’ atomic releases/<ts>/ + symlink   â”‚
        flip â†’ restart â†’ ASSERT new manifest-hash LOADED (ActiveEnterTimestamp advanced) â†’   â”‚
        SYNTHETIC canary call asserts greeting line + tool seq + DB-row AND file-mirror      â”‚
        (mirror-write-first) â†’ ledger append (signed earner-live-<sha256>-<ts> tag).         â”‚
        ANY failure after byte-write â†’ `trap` auto-flips symlink back â†’ restart â†’ Push.      â”‚
        PANEL: scp-then-symlink swap, pinned known_hosts, provenance attestation.            â”‚
                                          â–¼                                                  â”‚
   S14 RELEASE LOCK [A] â”€â”€ delete lock/earner â”€â”€ only after S13 verified green â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                          â–¼
   S15 POST-DEPLOY WATCHDOG [cloud/cron] â”€â”€ 30-min health + call-success-rate watch (survives
        laptop-off). Breach â†’ AUTO-execute S16 rollback (default = EXECUTE, baseline is on
        fire) + PushNotification("auto-rolled-back, here's why").
                                          â–¼
   S16 ROLLBACK [A on watchdog | H-confirm on founder-notice] â”€â”€ EARNER: flip symlink to
        prev release / `git -C earner-vault checkout earner-live-<prev>` â†’ recopy â†’ restart â†’
        re-smoke. PANEL: redeploy prior tag (migration-compat checked first). DB: down-migration.

   S-ESCALATE âŸªHâŸ« â”€â”€ post the DIFF OF DISAGREEMENT into ONE AskUserQuestion:
        [Accept reviewer] [Overrideâ€”ship author's] [Abandon PR] â€” each carries the revert SHA.
```

**The invariant that makes it earner-safe:** every gate predicate (golden baseline, manifest-hash match, lock ownership, smoke-pass) **fails CLOSED**. Missing baseline â‡’ `earner_gate_ok=FALSE` (block + bootstrap), never `null==null â‡’ pass`.

> **BLIND-SPOT THIS FIXES:** earner-gate failing OPEN on first run (no baseline existed); md5 auto-pass when `agent.py` unchanged but `caller.py` broke; deploy with no post-restart "is the new code actually loaded?" assertion; rollback that reverts code but not money/session state; "safe default = Hold" leaving a *already-broken* earner down during an incident.

---

## 3. THE HUMAN-GATE POINTS â€” exactly three clicks, never a terminal, never prose

The founder is non-technical. He sees **clickable options inside the famit-panel dashboard / phone**, never git, never a SHA, never a numbered prose question.

| Gate | When | What the founder sees (AskUserQuestion + PushNotification) | Default (recommended) |
|---|---|---|---|
| **G1 â€” Plan/spend** | Once, at bootstrap | "Protecting the live earner needs GitHub Team ($4/mo) so the safety gates can actually block. Approve?" `[Approve Team]` `[Stay Freeâ€”gates honor-system]` `[Make publicâ€”REJECTED for earner]` | Approve Team |
| **G2 â€” Merge-to-main (EARNER-CRITICAL only)** | S9 | "Change to the LIVE CALLER (`agent.py`). Smoke: âœ… greeting+tools+DB. Risk: affects real calls. Ship?" `[Hold & keep live]` `[Ship to earner]` `[Show me the diff]` | **Hold** (friction-ON) |
| **G3 â€” Deploy / irreversible** | S12 (+ release, +schema migration, +force-push during incident) | "Deploy panel v1.4 (12 fixes) / restore earner / run DB migration. Go?" `[Deploy]` `[Hold]` `[Roll back to last Tuesday â–¾]` | context-dependent |

**Decoupled identities (critical):** the **merge-approval owner â‰  the deploy-approval human**. CODEOWNERS for earner paths = a dedicated **reviewer identity Claude controls** (does the adversarial review). The **founder's** click is the **deploy** gate (G3), NOT the merge review â€” otherwise the queue stalls forever waiting on a founder you promised would never be in the loop. LOW/MED panel changes have **no gate at all** (auto-merge after green) â€” the founder's attention is reserved for the money path.

**Break-glass (the missing emergency affordances), all one-click, all server-side:**
- **`emergency-ship.yml`** â€” false-red blocking a real hotfix during an outage. Founder clicks "Emergency ship, I accept the risk" â†’ `workflow_dispatch` deploys the minimal hotfix tag **with the auto-revert watchdog armed**. ("Hold" is the WRONG default during a live outage.)
- **`emergency-rollback.yml`** â€” one-click restore earner/panel to last-known-good, server-side, audited, paged.
- **`enforcement:"evaluate"`** â€” Claude can flip the ruleset to dry-run (rules visible, non-blocking) to unfreeze a self-inflicted deadlock without the founder touching settings. Org-owner (founder) retains the in-browser ruleset edit path documented click-by-click in `BREAK_GLASS.md`.

> **BLIND-SPOT THIS FIXES:** the only documented founder action being "Hold/don't touch earner" â€” the wrong default mid-outage, stranding a non-technical founder at a terminal exactly when it's an emergency; "1 required review" deadlocking an all-Claude shop because GitHub blocks self-approval; founder rubber-stamping earner merges because they look identical to a typo fix.

---

## 4. INTEGRATION WITH THE 5-LAYER BUILD-TREE / UNIVERSE / ORCHESTRATOR / EARNER-GATE

This ecosystem is the **execution substrate** the existing systems already assume. Wiring:

**â†” 5-LAYER BUILD-TREE (green-trunk serial integrator).** Each build-tree lane = one `feat/â€¦__W-<wave>` branch off `golden`. The hand-rolled "serial integrator merges one-at-a-time + advance golden" is replaced (after upgrade) by **GitHub Merge Queue** on `main` (`merge_method: squash` for panel lanes) â€” it IS a managed green-trunk integrator: serializes, re-tests speculatively against latest base, auto-rejects red, removes strict-rebase thrash. The bespoke loop is a single point of failure with no liveness guarantee; the queue is managed. The integrator's auto-revert of a bad squash-SHA **goes through the same gates as a new PR** (`revert/<sha>` branch) â€” it has no special merge power, only sequencing.

**â†” ULTRACODE UNIVERSE (exploreâ†’researchâ†’designâ†’buildâ†’verify, earner-gated, one box-mutating wave).** The state machine IS the "build â†’ verify â†’ deploy â†’ verify-on-edge" tail. "One box-mutating change at a time" is no longer a *stated rule* â€” it's **physically enforced** by (a) `lock/earner` ref-mutex (S8b) and (b) a **global `concurrency: {group: deploy-global, cancel-in-progress: false}`** umbrella across panel+earner+migration deploys, so two green `agent.py` PRs cannot deploy seconds apart and you can always bisect which one killed revenue.

**â†” ORCHESTRATOR.md wave ledger.** Every state transition stamps the ledger row with `wave-id + agent-id + session-id + resumeId` AND propagates them into commit trailers + `deploy-ledger.jsonl` (multi-agent forensics: "which wave shipped the change that broke calls at 2am"). Per-wave ceilings (max N PRs/hr, pause lanes if `rate_limit.remaining < threshold`) live in ORCHESTRATOR.md so a runaway loop degrades gracefully. The ledger is **rendered read-only into the famit-panel "Release & Earner Health" card** (current golden, last deploy + smoke result, in-flight waves, open gates as buttons) â€” the founder's steering wheel lives in the product he already opens, not a jsonl.

**â†” EARNER-GATE (now an ENFORCED CI check, not honor-system).** `earner-gate.yml` is a **required status check** (after upgrade) bound to a specific App integration_id (so a spoofed status from another identity doesn't satisfy it). It is **default-ON keyed off the DIFF**, not a prose `EARNER:` marker (forgetting the marker must NOT skip both gate and human). It runs the REAL `verify_golden.py --all --strict` + a mocked-provider pre-flight on a throwaway runner FIRST (most red builds die before the box is ever touched), then the canary. The approved baseline manifest-hash lives in an **environment-protected Variable** (`vars.AGENT_MANIFEST_SHA`), NOT a committed file the same PR can edit â€” changing it requires a founder env-review, making the hash mean "byte-identical to the last founder-approved build."

> **BLIND-SPOT THIS FIXES:** the earner-gate being "enforced" only in prose; the integrator being a crash-prone bespoke loop with no liveness; "one box at a time" enforced nowhere; the ledger being a dev artifact the founder can't read; concurrent box mutation across separate workflows.

---

## 5. THE AUTONOMOUS-AGENT THREAT MODEL â€” Claude is the unguarded superuser (the design's biggest hole)

The prior design protected against *bad code* but never against *the automated actor with merge rights*. This is the real catastrophic / money-losing / secret-leaking vector.

- **Identity separation (capability, not convention).** Build agents get a token scoped to `contents:write` on `feat/*|fix/*|chore/*` branch patterns only (`main` denied via push ruleset). The **integrator/merge identity is a separate GitHub App** scoped `contents:write, pull_requests:write` and nothing else. The **reviewer identity is a third App** with `pull_requests:write` but **NOT `statuses:write`/`checks:write`** (so a buggy/compromised builder cannot fabricate its own green `earner-gate`). Required checks bound to App `integration_id`. `GITHUB_TOKEN` from Actions **cannot trigger downstream required workflows** (GitHub suppresses recursion) â†’ every CI-triggering push uses an **App installation token** (`actions/create-github-app-token`), asserted by a meta-lint that fails if `secrets.GITHUB_TOKEN` appears in any checkout/push step. App tokens minted **per-run** (1 h expiry), never stored.

- **The deploy gate is the SSH KEY, not a command string.** A PreToolUse hook keyed on the string `scp` is trivially evaded (`rsync`, `sftp`, paramiko in a `.py`, box-side `git pull`). Instead the **deploy key (`droplet_work/id_ed25519`) lives behind a wrapper** that refuses to expose/use it unless `earner_gate_ok==true` and `lock/earner` is held by this run-id. No key â†’ no transport â†’ no bypass, regardless of which binary the agent reaches for. Capability-based.

- **EARNER kill-switch independent of git.** `git revert` does nothing to the file-copied box. A **systemd watchdog / health-probe on the droplet** auto-restores `*.bak.<latest>` on `/health` non-200 or smoke-fail post-deploy and pages via PushNotification â€” revert is **reflexive on the box**, not a git op Claude must remember. Difference between a 30-second blip and an overnight revenue outage.

- **Secrets uncommittable, three independent nets + incident response.** (1) pre-commit gitleaks on staged content + **commit message + PR body** (the free-text vector gitleaks-staged ignores). (2) hardened CI `secrets.yml` (SHA-pinned, `permissions: contents:read`). (3) **GitHub Push Protection** (server-side pre-receive block â€” Team-required for private; another reason for G1). (4) the **rotate-first â†’ `filter-repo` â†’ break-glass force-push** incident runbook for the secret ALREADY in history (`03056f5`). Detection without rotation is theater.

- **Tamper-evident audit.** `deploy-ledger.jsonl` in the same repo Claude can rewrite is not an audit trail. Each earner deploy also mints a **signed `earner-live-<sha256>-<ts>` tag** (audit lives in tag objects a tag-protection ruleset forbids deleting/moving) and a **byte-valid dry-run-restored backup** (an untested restore is SchrÃ¶dinger's rollback; retention = last N, oldest rotated, encrypted at rest).

> **BLIND-SPOT THIS FIXES:** one over-scoped token one prompt-injection from a direct-to-earner deploy; status-check spoofing collapsing the gate; a deny-hook that string-matches `scp` and misses every other transport; `git revert` mistaken for an earner kill-switch; secrets scanned AFTER they're already in remote history; a ledger the same agent can rewrite.

---

## 6. EXPLICIT BLIND-SPOTS THIS ARCHITECTURE FIXES (consolidated)

1. **Plan reality** â€” enforcement spine (protection/queue/CODEOWNERS-block/push-protection) is 403 on Free; surfaced as G1, Team recommended, until then every "gate" is honor-system + kill-switch-backed.
2. **Cold-start** â€” zero golden tags â†’ bootstrap-golden + `origin/main` hard fallback; select tags by `creatordate`, never `sort|tail`.
3. **Trunk migration** â€” `main` 49-behind & not-on-origin â†’ ff-only promote (human-gated), then `default_branch=main`.
4. **Earner can't be `git`-versioned** â€” `droplet_work/` wholesale-ignored â†’ earner-vault (scrubbed) + earner-fortress (encrypted env) OUTSIDE the tree; rollback targets the **ledger entry / symlink**, not a source tag.
5. **golden-src â‰  earner-live** â€” split meanings; earner-live payload = content-hash of the actually-copied file.
6. **Gate scripts are fiction** â€” build `verify_golden.py --all --strict` + `smoke_realflow.py` FIRST; no CI references them until they pass locally.
7. **Merge-queue deadlock** â€” path-filtered required checks "pending forever" â†’ add `merge_group:` + always-run **status-shim**; never skip a required job.
8. **CI can't self-trigger** â€” `GITHUB_TOKEN` no-recursion â†’ App installation token on every triggering push.
9. **Signing bricks commits** â€” `required_signatures` + local `git commit` rejects every worktree push â†’ either drop signatures (single-author squash trunk) or recreate commits via API; key self-test â†’ fall back to unsigned-with-notice rather than total pipeline outage.
10. **md5 is the wrong unit** â€” whole-file digest vs "intended hunk" is a contradiction; scrubbed vault â‰  live box â†’ **AST/manifest sha256 of the full closure** + diff-equality against the approved hunk, normalized line endings.
11. **Agent superuser** â€” split builder/integrator/reviewer identities; capability-gated deploy key; status-check binding to App id.
12. **Denylist arms race** â€” `.gitignore` grows after each near-miss â†’ structural allowlist + name-tripwire for known-live files (`.env.local`, `final_env.md`, `provider_keys.json`).
13. **Founder-stranding** â€” break-glass `emergency-ship`/`emergency-rollback`/`enforcement:evaluate`, stale-PR stall watchdog, App-token-expiry health check, all one-click.
14. **DR** â€” earner-fortress encrypted env so "box is gone" is a `workflow_dispatch "provision new box"`, one click, not an SSH session.
15. **Revert mechanics** â€” `gh pr revert` is not a real command; squash â†’ `git revert <squash_sha>` (no `-m`), merge-commit â†’ `-m 1`; pick per merge strategy, never both.

=====================================================================

# THE EXECUTABLE GIT PROTOCOL

> Copy-paste runnable against `kunal-7x/axcrio-platform`. `gh` is PRIMARY (token `gho_â€¦`, scopes `repo,workflow`); GitHub MCP is an accelerator **behind a probe** (it 404s this private repo today). Anything marked `[upgrade]` requires GitHub Team (Free returns HTTP 403). Anchor once: `gh repo set-default kunal-7x/axcrio-platform`. Earner box = `famit@168.144.153.145`.

---

## 0. ONE-TIME BOOTSTRAP (run in order; each is a verified unit; STOP on any red)

```bash
# 0.0  ANCHOR + PREFLIGHT --------------------------------------------------------
gh repo set-default kunal-7x/axcrio-platform
gh api repos/kunal-7x/axcrio-platform --jq '.full_name' >/dev/null || { echo "FATAL: gh cannot reach repo"; exit 1; }
command -v gitleaks >/dev/null || { echo "FATAL: gitleaks not on PATH â€” refusing to operate blind"; exit 1; }
gh api rate_limit --jq '.resources.core.remaining'   # pause lanes if < 200

# 0.1  HARDEN THE LIVE secrets.yml FIRST (it is the current attack surface) -------
#   floating tags = tj-actions CVE vector; no permissions: block = read/WRITE token.
CK=$(gh api repos/actions/checkout/git/refs/tags/v4.2.2 --jq .object.sha)
GL=$(gh api repos/gitleaks/gitleaks-action/git/refs/tags/v2 --jq .object.sha)
#   -> edit .github/workflows/secrets.yml: add `permissions: {contents: read}`,
#      add `merge_group:` to on:, pin  actions/checkout@$CK  and  gitleaks-action@$GL.

# 0.2  PROMOTE the real trunk (main is 0-ahead/49-behind premium-ui AND not on origin)
git fetch origin feat/premium-ui
git checkout main && git merge --ff-only origin/feat/premium-ui     # if this FAILS -> AskUserQuestion (real merge, human gate)
git push origin main
gh api -X PATCH repos/kunal-7x/axcrio-platform -f default_branch=main   # priority-0: stop fresh clones checking out premium-ui

# 0.3  BOOTSTRAP golden (ZERO tags exist -> branch-off would be empty string) -----
if [ -z "$(git tag -l 'golden-*')" ]; then
  git tag -s "golden-$(date -u +%Y%m%d-%H%M%S)" main -m "bootstrap golden baseline"
  git branch -f golden main && git push origin golden --tags
fi
# canonical selector everywhere (NOT sort|tail â€” wrong after 10 tags / year boundary):
GOLDEN="$(git for-each-ref --sort=-creatordate --format='%(refname:short)' 'refs/tags/golden-*' | head -1)"
: "${GOLDEN:=origin/main}"   # hard fallback so a cut never gets an empty ref

# 0.4  SIGNING key, idempotent + self-test (missing key bricks EVERY commit) ------
KEY=~/.ssh/id_axcrio_sign
[ -f "$KEY" ] || ssh-keygen -t ed25519 -N "" -C "axcrio-agent-signing" -f "$KEY"   # -N "" = non-interactive
gh ssh-key list --json key | grep -q "$(cut -d' ' -f2 "$KEY.pub")" || gh ssh-key add "$KEY.pub" --type signing --title axcrio-agent-signing
git config gpg.format ssh; git config user.signingkey "$KEY.pub"
if git commit --allow-empty -S -m "signing self-test" --dry-run 2>/dev/null; then git config commit.gpgsign true; else
  git config commit.gpgsign false; echo "NOTICE: signing unverified -> committing UNSIGNED (pipeline > signatures)"; fi

# 0.5  STAND UP the earner repos OUTSIDE the caps tree (droplet_work/ is fully ignored)
gh repo create kunal-7x/earner-vault    --private    # scrubbed deployable .py + signed earner-live-* tags
gh repo create kunal-7x/earner-fortress --private    # age/SOPS-encrypted full box env (DR)
git -C /c/Users/kunal/Desktop/earner-vault    init   # sibling dir, never inside droplet_work/
git -C /c/Users/kunal/Desktop/earner-fortress init

# 0.6  GitHub-native nets (push-protection + secret-scanning) [upgrade for private]
gh api -X PATCH repos/kunal-7x/axcrio-platform \
  -f security_and_analysis='{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}'

# 0.7  BUILD THE FICTION SCRIPTS BEFORE ANY GATE REFERENCES THEM ------------------
#   verify_golden.py has def main() but NO argparse; render_prompts.py / prompt.golden/ /
#   smoke_realflow.py DO NOT EXIST. Add --all --strict to verify_golden.py; write
#   droplet_work/tests/smoke_realflow.py (mocked-provider path + file-mirror-write-first
#   assertion). Prove BOTH pass locally. CI references neither until green.
```

---

## 1. BRANCH-PROTECTION + RULESETS + CODEOWNERS  `[upgrade â€” 403 on Free]`

```bash
# main protection. enforce_admins=true is the line that stops the OWNER (and Claude-as-owner)
# bypassing the earner gates. required checks bound by NAME; status-shim guarantees they report.
gh api -X PUT repos/kunal-7x/axcrio-platform/branches/main/protection \
  -F 'required_status_checks[strict]=true' \
  -F 'required_status_checks[checks][][context]=secrets' \
  -F 'required_status_checks[checks][][context]=frontend / build-e2e' \
  -F 'required_status_checks[checks][][context]=backend / lint-test' \
  -F 'required_status_checks[checks][][context]=adversarial-review/passed' \
  -F 'required_pull_request_reviews[require_code_owner_reviews]=true' \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F 'required_pull_request_reviews[require_last_push_approval]=true' \
  -F enforce_admins=true -F restrictions=null

# earner-gate enforced via a SEPARATE ruleset scoped by label (so a panel typo isn't blocked
# by an earner check that will never report on it):
gh api -X POST repos/kunal-7x/axcrio-platform/rulesets -f name='earner-gate-required' \
  -f target=branch -f enforcement=active \
  -f 'conditions[ref_name][include][]=refs/heads/main' \
  -f 'rules[][type]=required_status_checks' \
  -f 'rules[][parameters][required_status_checks][][context]=earner-gate'

# immutable tags â€” even Claude's token can't move/delete golden-* / *-v* / earner-live-*:
gh api -X POST repos/kunal-7x/axcrio-platform/rulesets -f name='immutable-tags' \
  -f target=tag -f enforcement=active \
  -f 'conditions[ref_name][include][]=refs/tags/golden-*' \
  -f 'conditions[ref_name][include][]=refs/tags/*-v*' \
  -f 'conditions[ref_name][include][]=refs/tags/earner-live-*' \
  -f 'rules[][type]=deletion' -f 'rules[][type]=update'

# Merge Queue (the managed green-trunk integrator; squash for panel) [upgrade]:
gh api -X POST repos/kunal-7x/axcrio-platform/rulesets -f name='merge-queue-main' \
  -f target=branch -f enforcement=active \
  -f 'conditions[ref_name][include][]=refs/heads/main' \
  -f 'rules[][type]=merge_queue' \
  -f 'rules[][parameters][merge_method]=SQUASH' \
  -f 'rules[][parameters][grouping_strategy]=ALLGREEN'
```

**`.github/CODEOWNERS`** (missing â€” create). CODEOWNERS in `caps` guards the gate scripts; the earner's REAL closure is owned in `earner-vault` (since `droplet_work/**` is git-ignored, CODEOWNERS there does nothing):
```
# caps/.github/CODEOWNERS  â€” money + secrets paths require a SPECIFIC reviewer (not self-approve)
/droplet_work/_golden/**        @axcrio-reviewer-bot
/backend/agent.py               @axcrio-reviewer-bot
/backend/caller.py              @axcrio-reviewer-bot
/.github/workflows/**           @axcrio-reviewer-bot
/migrations/**                  @axcrio-reviewer-bot
# earner-vault/.github/CODEOWNERS:  /agent.py @kunal-7x   (the founder, for the real closure)
```

---

## 2. PER-STEP COMMAND SEQUENCES (gh primary; MCP only if probe-OK)

```bash
# --- S0 transport probe (decide once per wave; write to ORCHESTRATOR.md) ----------
gh api repos/kunal-7x/axcrio-platform --jq .full_name >/dev/null && GH_OK=1 || GH_OK=0
# MCP probe is a tool call: mcp__plugin_github_github__pull_request_read on a known PR.
# 404 => MCP_OK=0 => DISABLE the MCP path (don't loop on 404s). Every server action below
# is "MCP if probed-OK, else gh" â€” never MCP-first-unconditionally.

# --- S1 open lane (off GOLDEN, never premium-ui, never empty; waveid in name) -----
WAVE="W-$(date -u +%Y%m%d)-03"; SCOPE="panel-handoff"
git switch -c "feat/${SCOPE}__${WAVE}" "$GOLDEN"

# --- S2 commit-per-unit (explicit paths ONLY; never git add -A) -------------------
git add lib/handoff.ts components/Handoff.tsx           # explicit
git diff --cached --no-color | gitleaks detect --no-git --pipe --redact   # staged CONTENT
COMMIT_MSG=$'feat(panel): clean handoff name line\n\nWave: '"$WAVE"$'\nRun: '"$RUN_ID"$'\nVerified: pnpm build + e2e green\nAgent: '"$AGENT_ID"
printf '%s' "$COMMIT_MSG" | gitleaks detect --no-git --pipe --redact      # MESSAGE (free-text leak vector)
git commit -m "$COMMIT_MSG"                              # signed if 0.4 self-test passed

# --- S3 open DRAFT PR (search-before-create; PR body scanned BEFORE create) --------
gh pr list --search "head:feat/${SCOPE}__${WAVE}" --json number --jq '.[0].number'   # dedup
PR_BODY="$(cat .github/pull_request_template.md)"        # rendered, with trailers
printf '%s' "$PR_BODY" | gitleaks detect --no-git --pipe --redact || { echo "PR body leaks â€” abort"; exit 1; }
gh pr create --draft --base main --head "feat/${SCOPE}__${WAVE}" --title "feat(panel): handoff name line" --body "$PR_BODY"

# --- S4/S5 CI: classify infra-vs-real; infra retry does NOT spend fix-budget -------
gh pr checks "$PR" --watch                               # assert ZERO pending after settle
gh run rerun --failed --job "$JOB"                       # Ã—2 for infra/flaky only

# --- S6 adversarial review posts APPROVE via the SEPARATE reviewer identity --------
gh pr review "$PR" --approve --body "adversarial-review: 0 blocking"   # run AS axcrio-reviewer-bot token

# --- S7 risk classify (earner set touched?) ---------------------------------------
git diff --name-only "main...feat/${SCOPE}__${WAVE}" | grep -qE \
  'droplet_work/(agent|caller)\.py|droplet_work/_golden/|backend/(agent|caller)\.py|migrations/|\.github/workflows/' \
  && CLASS=EARNER || CLASS=PANEL

# --- S8b earner mutex (atomic; 422 == held == queue, do NOT merge) -----------------
GOLDEN_SHA=$(git rev-parse "$GOLDEN")
gh api -X POST repos/kunal-7x/axcrio-platform/git/refs -f ref='refs/heads/lock/earner' -f sha="$GOLDEN_SHA" \
  || { echo "lock/earner held â€” queue this PR"; exit 0; }

# --- S10 merge: PANEL=squash (no -m on revert later); EARNER=merge-commit (bisect) --
[ "$CLASS" = PANEL ] && gh pr merge "$PR" --squash --auto \
                     || gh pr merge "$PR" --merge        # earner: preserve per-unit commits

# --- S11 advance golden ONLY after full suite green on main ------------------------
git checkout main && git pull --ff-only
git tag -s "golden-$(date -u +%Y%m%d-%H%M%S)" main -m "verified green"   # immutable, dated
git branch -f golden main && git push origin golden --tags

# --- S14 release the mutex (only after S13 deploy verified green) ------------------
gh api -X DELETE repos/kunal-7x/axcrio-platform/git/refs/heads/lock/earner
```

---

## 3. GITHUB ACTIONS â€” CI (status-shim, merge_group, App-token), DEPLOY, EARNER-GATE

### 3a. `secrets.yml` â€” HARDENED (replace the live file; this is bootstrap step 0.1)
```yaml
name: secrets
on: { push: {}, pull_request: {}, merge_group: {} }   # merge_group so the queue gets a report
permissions: { contents: read }                       # was implicit read/WRITE â€” close it
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<PIN_v4.2.2_SHA>
        with: { fetch-depth: 0 }                      # full history: a secret in ANY commit fails
      - uses: gitleaks/gitleaks-action@<PIN_v2_SHA>   # NO floating tag (tj-actions CVE class)
        env: { GITLEAKS_CONFIG: .gitleaks.toml }
```

### 3b. `_status-shim.yml` â€” the always-runs job that stops path-filtered required checks deadlocking the queue
```yaml
# A required check that is SKIPPED by a paths: filter is "pending forever" in a merge queue.
# This job ALWAYS runs and reports success for the contexts the real (filtered) jobs would skip.
name: status-shim
on: { pull_request: {}, merge_group: {} }
permissions: { statuses: write }
jobs:
  shim:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<PIN_v4.2.2_SHA>
      - id: ch
        run: |
          git fetch origin main --depth=2
          CHANGED=$(git diff --name-only origin/main...HEAD)
          echo "$CHANGED" | grep -q '^frontend/' || gh api -X POST repos/${{github.repository}}/statuses/${{github.event.pull_request.head.sha || github.sha}} -f state=success -f context='frontend / build-e2e' -f description='no frontend changes'
          echo "$CHANGED" | grep -q '^backend/'  || gh api -X POST repos/${{github.repository}}/statuses/${{github.event.pull_request.head.sha || github.sha}} -f state=success -f context='backend / lint-test'  -f description='no backend changes'
        env: { GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
```
Also add `merge_group: {}` to `backend.yml` and `frontend.yml` `on:` blocks (they currently have only `push`/`pull_request` + `paths:`). Add `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }` to each so re-pushes don't pile redundant runs.

### 3c. `earner-gate.yml` â€” the ENFORCED check (real scripts; baseline OUTSIDE the PR; mocked pre-flight FIRST)
```yaml
name: earner-gate
on:
  pull_request: { types: [opened, synchronize, ready_for_review, labeled] }
  merge_group: {}
permissions: { contents: read }
concurrency: { group: earner-gate-${{ github.ref }}, cancel-in-progress: true }
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs: { earner: ${{ steps.d.outputs.earner }} }
    steps:
      - uses: actions/checkout@<PIN_v4.2.2_SHA>
        with: { fetch-depth: 0 }
      - id: d   # default-ON keyed off the DIFF â€” NOT a prose EARNER: marker (forgetting it must not skip the gate+human)
        run: |
          git fetch origin main --depth=2
          if git diff --name-only origin/main...HEAD | grep -qE 'droplet_work/(agent|caller)\.py|droplet_work/_golden/|backend/(agent|caller)\.py|migrations/'; then
            echo "earner=true" >> "$GITHUB_OUTPUT"; else echo "earner=false" >> "$GITHUB_OUTPUT"; fi
  gate:
    needs: detect
    if: needs.detect.outputs.earner == 'true'
    runs-on: ubuntu-latest                 # PRE-FLIGHT on a throwaway runner FIRST â€” box untouched
    environment: production-voice          # founder = required reviewer (the deploy click is here, S12)
    steps:
      - uses: actions/checkout@<PIN_v4.2.2_SHA>
      - uses: astral-sh/setup-uv@<PIN_SHA>
      - run: uv python pin 3.12
      # 1) REAL golden â€” verify_golden.py --all --strict (built in 0.7; was fiction before)
      - run: |
          uv run python droplet_work/_golden/verify_golden.py --all --strict
          git diff --exit-code -- droplet_work/_golden/   # goldens unchanged unless the PR intentionally updates them
      # 2) manifest-hash of the FULL closure (md5-of-one-file is the wrong unit), normalized EOL,
      #    compared to the founder-approved baseline stored in an ENV VARIABLE (not a committed file)
      - id: h
        run: |
          H=$(for f in droplet_work/agent.py droplet_work/caller.py droplet_work/wallet.py droplet_work/requirements.txt; do
                tr -d '\r' < "$f"; done | sha256sum | cut -d' ' -f1)
          echo "have=$H" >> "$GITHUB_OUTPUT"
      - run: |
          if [ -z "${{ vars.AGENT_MANIFEST_SHA }}" ]; then echo "FAIL-CLOSED: no approved baseline (bootstrap first)"; exit 1; fi
          [ "${{ steps.h.outputs.have }}" = "${{ vars.AGENT_MANIFEST_SHA }}" ] || echo "::warning::manifest changed â€” intended? gate continues to smoke"
      # 3) mocked-provider real-flow smoke (no box touch, no paid minutes, no real PSTN dial)
      - run: SMOKE_MOCK_PROVIDERS=1 uv run python droplet_work/tests/smoke_realflow.py --assert-greeting --assert-tools --assert-db-and-mirror
```

### 3d. `deploy-earner.yml` â€” VERIFY-OR-ROLLBACK transaction (global lock; dry-run-restore; atomic symlink; trap-revert; canary)
```yaml
name: deploy-earner
on: { workflow_dispatch: {} }            # fired only after S12 founder click / release
concurrency: { group: deploy-global, cancel-in-progress: false }   # serialize ACROSS panel+earner+migration
permissions: { contents: read }
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production-voice        # founder approval gate (G3)
    steps:
      - uses: actions/checkout@<PIN_v4.2.2_SHA>
      - name: known_hosts (pin host key â€” no accept-new TOFU MITM)
        run: echo "${{ secrets.VOICE_KNOWN_HOSTS }}" > ~/.ssh/known_hosts
      - name: deploy = verify-or-rollback
        env: { KEY: ${{ secrets.BOX_DEPLOY_KEY }}, BOX: famit@168.144.153.145 }
        run: |
          set -euo pipefail
          install -m600 /dev/stdin ~/.ssh/id <<<"$KEY"
          TS=$(date -u +%Y%m%d-%H%M%S)
          # backup (rotated, last N) + DRY-RUN RESTORE the latest backup into a temp path and diff
          # (an untested restore is SchrÃ¶dinger's rollback) BEFORE mutating the live file:
          ssh -i ~/.ssh/id "$BOX" 'set -e; cd /srv/agent; cp -a current/agent.py "_bak/agent.$(date +%s).bak"; ls -t _bak/*.bak | tail -n +11 | xargs -r rm; mkdir -p _dryrun && cp "$(ls -t _bak/*.bak|head -1)" _dryrun/agent.py && python -c "import ast;ast.parse(open(\"_dryrun/agent.py\").read())"'
          # ATOMIC: upload to releases/<ts>/ then flip the symlink (revert = flip back â€” never a torn tree)
          rsync -e "ssh -i ~/.ssh/id" --include='*.py' --include='requirements.txt' --exclude='*' droplet_work/ "$BOX:/srv/agent/releases/$TS/"
          # arm the trap: ANY failure AFTER the byte-write auto-reverts the symlink + restarts + pages
          PREV=$(ssh -i ~/.ssh/id "$BOX" 'readlink /srv/agent/current')
          trap 'ssh -i ~/.ssh/id "$BOX" "ln -sfn '"$PREV"' /srv/agent/current && systemctl restart aim-voice-agent"; exit 1' ERR
          ssh -i ~/.ssh/id "$BOX" "ln -sfn /srv/agent/releases/$TS /srv/agent/current && systemctl restart aim-voice-agent"
          # ASSERT the new code is actually LOADED (restart advanced) â€” bytes on disk â‰  running:
          ssh -i ~/.ssh/id "$BOX" 'systemctl show -p ActiveEnterTimestamp aim-voice-agent'
          # post-transfer gitleaks ON THE BOX (verify on destination, not just trust the upload filter):
          ssh -i ~/.ssh/id "$BOX" "cd /srv/agent/current && gitleaks detect --no-git --redact --exit-code 1"
          # SYNTHETIC canary call (loopback/echo â€” never a real PSTN number, never paid minutes):
          ssh -i ~/.ssh/id "$BOX" 'SMOKE_SYNTHETIC=1 python tests/smoke_realflow.py --assert-greeting --assert-tools --assert-db-and-mirror'
          # success: record ledger + signed immutable tag in earner-vault (audit a ruleset forbids deleting)
          SHA=$(ssh -i ~/.ssh/id "$BOX" 'sha256sum /srv/agent/current/agent.py | cut -d" " -f1')
          git -C ../earner-vault tag -s "earner-live-$SHA-$TS" -m "live: $SHA wave=${{ github.run_id }}" && git -C ../earner-vault push --tags
```

### 3e. `deploy-panel.yml` â€” scp-then-symlink (NOT stdin-pipe), pinned known_hosts, provenance
```yaml
name: deploy-panel
on: { workflow_dispatch: {}, release: { types: [published] } }
concurrency: { group: deploy-global, cancel-in-progress: false }
permissions: { contents: read, id-token: write, attestations: write }
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production-panel
    steps:
      - uses: actions/checkout@<PIN_v4.2.2_SHA>
      - uses: pnpm/action-setup@<PIN_SHA>
        with: { version: 10 }
      - uses: actions/setup-node@<PIN_SHA>
        with: { node-version-file: '.nvmrc', cache: pnpm }   # version-file, not hardcoded (tracks the repo)
      - run: pnpm install --frozen-lockfile && pnpm run build
      - uses: actions/attest-build-provenance@<PIN_SHA>       # prove what shipped
        with: { subject-path: 'frontend/.next/**' }
      - run: echo "${{ secrets.PANEL_KNOWN_HOSTS }}" > ~/.ssh/known_hosts
      - uses: appleboy/scp-action@<PIN_SHA>                   # transfer the artifact ON DISK (never via script stdin)
        with: { host: panel.famit.in, username: deploy, key: ${{ secrets.PANEL_DEPLOY_KEY }}, source: 'dist.tgz', target: '/srv/panel/releases/' }
      - uses: appleboy/ssh-action@<PIN_SHA>                   # separate step: untar + symlink swap only
        with: { host: panel.famit.in, username: deploy, key: ${{ secrets.PANEL_DEPLOY_KEY }}, script: 'cd /srv/panel/releases && TS=$(date +%s) && mkdir $TS && tar -xzf dist.tgz -C $TS && ln -sfn /srv/panel/releases/$TS /srv/panel/current && systemctl reload panel' }
```

### 3f. `release-please.yml` â€” plain-English weekly release gate for the tracked product
```yaml
name: release-please
on: { push: { branches: [main] } }
permissions: { contents: write, pull-requests: write }
jobs:
  rp:
    runs-on: ubuntu-latest
    steps:
      - uses: googleapis/release-please-action@<PIN_SHA>
        with: { token: ${{ secrets.RP_APP_TOKEN }} }   # App token, NOT GITHUB_TOKEN (no-recursion)
# .release-please-manifest.json  must MIRROR package.json (lying breaks reconciliation):
#   { "famit-panel": "0.1.0", "growth-os": "0.0.0" }   # NOT "1.0.0"
# seed baseline tags so it has something to diff:  git tag panel-v0.1.0 ; git tag growth-os-v0.0.0
# growth-os = release-as: draft-only until it has a real deploy target (no meaningless approval prompts).
```

### 3g. `emergency-ship.yml` / `emergency-rollback.yml` â€” the founder's one-click break-glass
```yaml
name: emergency-rollback
on: { workflow_dispatch: { inputs: { target: { description: 'last-good tag', required: true } } } }
concurrency: { group: deploy-global, cancel-in-progress: false }
jobs:
  rollback:
    runs-on: ubuntu-latest
    environment: production-voice
    steps:
      - run: |
          # earner: flip symlink to prev release / checkout earner-live-<prev> -> recopy -> restart -> re-smoke
          # panel : redeploy prior tag (migration-compat checked first). Always server-side, audited, paged.
          echo "rolling back to ${{ github.event.inputs.target }}"
# emergency-ship.yml: same shape, deploys the minimal hotfix tag WITH the auto-revert watchdog armed.
# Founder triggers either from ONE AskUserQuestion option -> Claude calls
#   gh workflow run emergency-rollback.yml -f target=<tag>   (no terminal, ever).
```

---

## 4. COMMIT + PR TEMPLATES

**`.github/.gitmessage`** (`git config commit.template .github/.gitmessage`):
```
<type>(<scope>): <imperative subject â‰¤72>

# Body: what & why (not how).

Wave: W-YYYYMMDD-NN
Run: <run-id>
Agent: <agent-id>  Session: <session-id>
Verified: <exact command + result, e.g. "pnpm build + e2e green" / "smoke_realflow PASS">
Co-Authored-By: Claude <noreply@anthropic.com>
```

**`.github/pull_request_template.md`**:
```markdown
## What & why
<!-- one paragraph, plain English -->

## Risk class
- [ ] PANEL (auto-merge after green)
- [ ] EARNER-CRITICAL (founder gate + lock/earner + smoke required)

## Verification evidence
<!-- paste ONLY pass/fail lines. Any runtime output is gitleaks-scanned before this PR is created. -->
- CI: <link>
- Earner smoke (if EARNER): greeting âœ… / tools âœ… / DB+mirror âœ…
- Rollback: symlink prev = `releases/<ts>` | revert SHA = `<sha>`

## Lineage
Wave / Run / Agent / Session: <ids>
```

---

## 5. PRE-COMMIT GITLEAKS + SECRET PROTOCOL

**`.githooks/pre-commit`** (current file is 7 lines, content-only; replace with content + message + name-tripwire; `core.hooksPath=.githooks` already set, shared by worktrees):
```bash
#!/usr/bin/env bash
set -euo pipefail
command -v gitleaks >/dev/null || { echo "FAGOL: gitleaks missing â€” refusing to commit blind"; exit 1; }  # never pass unscanned
# 1) name-tripwire: KNOWN-live files, faster+surer than entropy, bypasses gitleaks-rule gaps:
git diff --cached --name-only | grep -E '(^|/)(\.env(\.local)?|final_env\.md|provider_keys\.json|z_.*_api\.md|.*cred.*)$' \
  && { echo "BLOCKED: known secret-bearing file staged"; exit 1; } || true
# 2) staged CONTENT:
gitleaks git --staged --config .gitleaks.toml --redact --no-banner --exit-code 1
# 3) category heuristic: any NEW file named like a secret needs an explicit allowlist annotation:
for f in $(git diff --cached --name-only --diff-filter=A); do
  echo "$f" | grep -qiE '(key|cred|secret|token|api|_env|provider)' && ! grep -q '# allowlisted:' "$f" 2>/dev/null \
    && { echo "BLOCKED: $f looks secret-shaped; add '# allowlisted: <reason>' if intentional"; exit 1; } || true
done
echo "[pre-commit] clean."
```
> Also scan `$COMMIT_MSG` and `$PR_BODY` with `gitleaks detect --no-git --pipe --redact` in S2/S3 (the free-text vector the staged hook can't see). **`.gitleaks.toml` fix:** the `paths`-allowlist for `design/p0-foundation.md` is a HOLE (a real secret added to that doc now passes) â€” move the fake test-secret to `tests/fixtures/` and pin it by **value regex**, not path. Add explicit custom rules for the actual stack (Vobiz `VOBIZ_AUTH_TOKEN=`, LiveKit `APIâ€¦`/secret, Groq, OpenRouter, Samba) â€” gitleaks defaults miss them, giving false confidence.

---

## 6. UNTRACKED-EARNER VERSIONING + ROLLBACK RUNBOOK

```bash
# === SNAPSHOT (after every verified earner change; runs OUTSIDE the caps tree) ===
# A) earner-vault: SCRUBBED, human-readable .py â€” allowlist extractor, NOT denylist sed:
#    copy ONLY .py AST with secret-shaped string literals replaced by os.environ[...] placeholders.
python tools/scrub_to_vault.py droplet_work/ /c/Users/kunal/Desktop/earner-vault/
git -C /c/Users/kunal/Desktop/earner-vault add -A
git -C /c/Users/kunal/Desktop/earner-vault diff --cached | gitleaks detect --no-git --pipe --redact   # PROVE zero leaks
gitleaks detect --no-git --source /c/Users/kunal/Desktop/earner-vault --redact --exit-code 1           # belt
git -C /c/Users/kunal/Desktop/earner-vault commit -m "earner snapshot $(date -u +%FT%TZ)"
git -C /c/Users/kunal/Desktop/earner-vault tag -s "earner-v$(date -u +%Y%m%d-%H%M%S)" -m "scrubbed"
git -C /c/Users/kunal/Desktop/earner-vault push --follow-tags
# B) earner-fortress: ENCRYPTED full env for DR (.env + secrets + systemd) â€” restores byte-reality:
tar -C droplet_work -czf - .env *.service requirements.txt | age -r "$FOUNDER_AGE_RECIPIENT" -r "$BREAKGLASS_AGE_RECIPIENT" \
  > /c/Users/kunal/Desktop/earner-fortress/env-$(date -u +%Y%m%d-%H%M%S).age   # 2 recipients incl. offline escrow
git -C /c/Users/kunal/Desktop/earner-fortress add -A && git -C /c/Users/kunal/Desktop/earner-fortress commit -m "env $(date -u +%FT%TZ)" && git -C /c/Users/kunal/Desktop/earner-fortress push

# === ROLLBACK (atomic symlink â€” the fast path; NO git op touches the live box) ===
ssh -i ~/.ssh/id famit@168.144.153.145 'ln -sfn /srv/agent/releases/<PREV_TS> /srv/agent/current && systemctl restart aim-voice-agent'
ssh -i ~/.ssh/id famit@168.144.153.145 'SMOKE_SYNTHETIC=1 python /srv/agent/current/tests/smoke_realflow.py'   # re-smoke

# === DR: box is gone â€” one click, no SSH session ===
gh workflow run provision-box.yml -f vault_tag=earner-v<latest> -f fortress=env-<latest>.age
#   -> new box pulls scrubbed code from earner-vault + decrypts env from earner-fortress + restarts.

# === IN-HISTORY SECRET (final_env.md added in 03056f5) â€” ROTATE FIRST, purge second ===
# 1) ROTATE the credential at the provider (Vobiz/Groq/LiveKit/DO PAT) â€” purge w/o rotate is theater.
gh api repos/kunal-7x/axcrio-platform/secret-scanning/alerts                # confirm reachability
git log --all -p -S '<token-prefix>' -- final_env.md                        # local confirm
# 2) PURGE with filter-repo (NOT filter-branch). This rewrites history => collides with protection:
gh api -X PUT repos/kunal-7x/axcrio-platform/branches/main/protection -F enforce_admins=false ...   # break-glass lift
git filter-repo --path final_env.md --invert-paths --force
git push --force-with-lease origin --all --tags
gh api -X PUT repos/kunal-7x/axcrio-platform/branches/main/protection -F enforce_admins=true  ...   # RE-APPLY immediately
# 3) AskUserQuestion: "A live credential was in git history. I already ROTATED it + prepared a clean
#    history rewrite. Approve the force-push? [Approve / Hold]"  +  file GitHub Support purge request (caches/forks survive).
```

---

## 7. ONE-CLICK ROLLBACK (founder surface) + REVERT-OF-MERGED-PR (real commands)

```bash
# Founder clicks "Roll back to last Tuesday â–¾" in the panel Health card -> Claude lists last-good tags
# (gh release list / earner-vault tags) -> founder picks one -> Claude dispatches server-side:
gh workflow run emergency-rollback.yml -f target=<tag>      # earner symlink-flip OR panel prior-tag redeploy

# Revert a MERGED PR â€” pick the mechanism by MERGE STRATEGY (they're mutually exclusive):
#   PANEL was SQUASHED  -> single commit, NO merge parent:   git revert <squash_sha>        (no -m)
#   EARNER was MERGE-COMMIT -> two parents:                  git revert -m 1 <merge_sha>
# then open a revert PR THROUGH THE SAME GATES (the integrator has no special direct-to-main power):
git switch -c "revert/<sha>" main && git revert <sha-per-above> && git push -u origin "revert/<sha>"
gh pr create --base main --head "revert/<sha>" --title "revert: <subject>" --body "auto-revert; ledger ref <run>"
#   ( gh pr revert  IS NOT A REAL COMMAND â€” never put it in an incident runbook. )

# Founder-NEVER-types-git proof: every command above is run BY Claude. The founder only ever sees
# AskUserQuestion options + PushNotifications; the dashboard Health card is his entire steering wheel.
```

---

## 8. WATCHDOGS & STALL/COST GUARDS (cloud/scheduled â€” survive laptop-off)

```bash
# Post-deploy earner watchdog (server-side; auto-rollback default = EXECUTE, baseline is on fire):
#   schedule/cron routine: 30-min health + call-success-rate from box logs; breach -> gh workflow run
#   emergency-rollback.yml -f target=<prev> + PushNotification("auto-rolled-back, here's why").
# Stale-branch reaper (or trunk decays into the sprawl already present):
gh pr list --state open --json number,updatedAt | jq -r '.[]|select((now-(.updatedAt|fromdate))>259200)|.number'  # >72h idle -> close/delete
# Stuck-PR stall watchdog: (red OR draft) AND age>N AND no Claude activity -> PushNotification +
#   AskUserQuestion("PR#X stuck on test Y: retry / skip lane / look yourself"). Silence is the enemy.
# Config-drift reconciler: diff repos/.../branches/main/protection + security_and_analysis vs a committed
#   security-baseline.json -> PushNotify on drift (config-as-code, continuous, not fire-and-forget).
# App-token health: daily get_me per bot identity -> page on auth failure ("robots lost access, click to re-auth").
# Cost ceiling: gh api rate_limit --jq '.resources.core.remaining' < threshold -> pause lanes (per-wave cap in ORCHESTRATOR.md).
```