# P0 INFRA — Track A (secrets-gate + git + CI) — STATE ledger

Owner: INFRA-ENG. Spec: design/p0-foundation.md. Plan: EXECUTION_PLAN.md Track A.
Scope (this session, per orchestrator narrowing + advisor):
- Secrets-gate (.gitignore/.gitleaks.toml/.gitattributes/.worktreeinclude) FIRST.
- gitleaks raw scan → git init → staged-scan GATE → local commits only.
- Monorepo baseline = git + dir AS-IS + README noting intended /backend /frontend /infra layout.
  NO git mv curation of caller.py this unit (serializes with P1 later).
- CI = backend.yml + frontend.yml (dormant scaffolding) + secrets.yml. NO infra.yml (Terraform DROPPED).
- Branch model documented in CONTRIBUTING.md (push/protect = founder step; do NOT push to unknown remote).
- pre-commit gitleaks hook (LF).

## UNITS
- U0 read spec+plan+brain, inventory secrets on disk ......... DONE
- U1 write 4 gate files (.gitignore/.gitleaks.toml/.gitattributes/.worktreeinclude) ... DONE
- U2 raw gitleaks dir scan → confirm every finding is ignored ... DONE (50 findings, ALL in ignored paths: .env.local/.next/fortress/droplet_work; design-doc FP allowlisted)
- U3 git init + commit gate files ALONE ... DONE (root commit cd54871, 4 files)
- U4 git add . → gitleaks git --staged GATE (must be 0) → snapshot commit ... DONE
     GATE RESULT: gitleaks git --staged = "no leaks found" EXIT 0 (406 files, 2.99MB scanned). Sanity cross-check: 0 danger paths staged.
     Commits: cd54871 (gate files) + 03056f5 (snapshot, 406 files). Tree clean.
- U5 pre-commit hook + prove it blocks a planted real-format secret ... DONE
     Hook committed 97facc9 (LF, core.hooksPath=.githooks). PROOF: planted fake GitHub PAT (ghp_...)
     -> hook "leaks found: 1" -> commit EXIT 1, BLOCKED, HEAD unchanged. (NOTE: AWS AKIAIOSFODNN7EXAMPLE
     is gitleaks-ALLOWLISTED as a doc example -> first test falsely "passed"; corrected to ghp_ which is caught.)
- U6 README.md (monorepo map) + CONTRIBUTING.md (branch model) ... IN PROGRESS
- U7 CI workflows (backend/frontend/secrets) + validate YAML
- U8 final proof: gitleaks git . on committed repo = 0 ; git status clean
- U9 build_log + HANDOFF + brain append

## PROOF ANCHORS (fill as we go)
- gitleaks version: 8.30.1
- raw scan report: gitleaks-raw.json (diagnostic; expected to flag ignored .env.local/fortress/.venv)
- staged-scan result: <pending>
- committed-repo scan result: <pending>

## DANGER FILES ON DISK (must never be staged) — verified 2026-06-09
- .env.local , famit-panel/.env.local  (LIVE keys)        → .env.*
- fortress/ (cred.md, cloud-init.yaml, HUMAN_TASKS.md, STATE.md, ...) → fortress/ wholesale
- droplet_work/*.bak.* *.P0bak.* *.w3bak.* *.waveA2bak.* *.P2recon.bak → backup patterns
- famit-panel.tgz , famit-panel/famit-panel.tgz           → *.tgz
- .venv/ (bundled cacert.pem/roots.pem/client_secrets.py)  → .venv/
- NOTE: id_ed25519 lives at C:\Users\kunal\.ssh (OUTSIDE repo). lead/ALL_CREDENTIALS.md OUTSIDE repo.
- final_env.md = EMPTY (0 lines, harmless). request.md/train.md/P0_IMPLEMENTATION_PLAN.md = no secret indicators.
