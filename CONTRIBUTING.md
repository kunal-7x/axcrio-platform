# Contributing — branch / worktree / PR model

This repo follows a **worktree → `feat/*` → PR → squash → protected `main`** model.
The live system at `https://panel.famit.in` keeps earning throughout; every change is
additive, flag-gated, and non-breaking.

## Branch model

- **`main` is protected.** No direct pushes. Changes land via PR + green CI + squash-merge only.
  (Protection rules are applied on the GitHub remote — see "Founder step" below; they cannot be
  set until a remote exists.)
- **One workstream = one branch off `main`**, ideally built in a **git worktree** for isolation:
  ```bash
  git switch -c feat/<workstream>
  # or Claude-managed isolation:  claude --worktree <name>   (creates .claude/worktrees/<name>)
  ```
  `.claude/worktrees/` is gitignored. `.worktreeinclude` lists the gitignored files
  (`.env.local`, `backend/.env`, `frontend/.env.local`) that a fresh worktree needs copied in to
  deploy.

## The ONE serialization rule

`droplet_work/caller.py` (the live ~3,422-line backend) is the **single serialization
bottleneck**. **Never run two agents on `caller.py` at once** (lost writes — see
`brain/mistakes.md`). Every unit that edits it runs sequentially in `main`. New-file authoring
(`store.py`, `wallet.py`, etc.) happens in worktrees; each wire-in to `caller.py` rejoins the
sequential spine.

## Per-unit loop (crash-safe)

1. Mark the unit **IN PROGRESS** in the relevant STATE/TASKS file.
2. Small, targeted edit (never rewrite a whole large file).
3. Verify: `gitleaks git --staged` clean (the pre-commit hook enforces this) +
   the unit's own test (`ruff` / `pytest` / `pnpm build` once `backend/`/`frontend/` exist).
4. **Conventional commit, one verified unit = one commit:**
   `feat(area): … — verified <how>` / `chore: …` / `fix(area): …`.
   End every commit message with:
   ```
   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
   ```
5. Flip the STATE line to **DONE**.

## Pull requests

- `gh pr create --fill --base main`.
- CI (`backend`, `frontend`, `secrets`) must be green.
- Squash-merge; keep history linear.

## Secrets gate (every commit, forever)

- `.gitignore` is intent; **`gitleaks` is the net.** The `.githooks/pre-commit` hook runs
  `gitleaks git --staged` and **blocks** any commit that stages a secret. CI re-runs gitleaks on
  every push/PR over full history.
- Enable the hook locally (once per clone):
  ```bash
  git config core.hooksPath .githooks
  ```
- Never commit `.env*` (except `*.env.example`), keys, `fortress/*`, `**/cred.md`,
  `**/ALL_CREDENTIALS.md`, `*.bak*`, `*.tgz`, `.next/`, `.venv/`.

## Founder step (deferred — not done in this phase)

Creating the GitHub remote, pushing, and applying branch protection are **founder actions**
(this phase commits locally only and does not push to an unknown remote):
```bash
gh repo create famit-revenue-os --private --source . --remote origin
# re-scan full history before the push leaves the machine:
gitleaks git . --config .gitleaks.toml --redact --no-banner --exit-code 1   # must exit 0
git push -u origin main
# then protect main: require PR, require status checks (backend, frontend, secrets),
# no force-push, linear history (gh api .../branches/main/protection).
```
See `HUMAN_TASKS` / the build log for the exact recipe.
