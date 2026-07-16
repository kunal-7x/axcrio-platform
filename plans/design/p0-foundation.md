# PHASE 0 — FOUNDATION & SECRETS-GATE — Execution-Ready Design Spec

> **Audience:** a build agent that implements this verbatim.
> **Scope (this spec ONLY):** monorepo layout (`/backend` uv, `/frontend` pnpm, `/infra` terraform),
> the SECRETS-GATE (comprehensive `.gitignore` → gitleaks raw scan → `git init` → staged-scan gate →
> first commit), monorepo curation (git mv, recipe updates), CI (GitHub Actions: ruff+pytest+gitleaks /
> build+Playwright), **private** GitHub repo + worktree/branch/PR/protected-main model, and Terraform
> **import → no-diff plan** of the existing DO + Cloudflare infra.
> **OUT OF SCOPE (separate specs):** voice semantic-turn-detector / barge-in (P0 voice unit); Postgres
> migration (Phase 1); any change to caller.py internal structure (Phase 1).
>
> **VERDICT (settled):** STRANGLE & EVOLVE. The live system at `https://panel.famit.in` keeps earning.
> Every step here is **local / git / CI / terraform-read-only**. **The live boxes are NOT touched by this
> phase** (except ONE optional, reversible read-only `md5sum` health probe). That IS the rollback model.

---

## RED-TEAM FIXES (folded) — verified against live source 2026-06-09; apply ALL before executing

> Adversarial principal review. Each item below was confirmed by reading the actual source under
> `droplet_work/` (not memory). **These OVERRIDE the body of the spec where they conflict.** Verdict
> after fixes: **GO (with these fixes)** — none invalidates STRANGLE & EVOLVE or the local-only model.

**[BLOCKER-1 — `import caller` CRASHES in CI and locally; the headline acceptance test cannot pass as written].**
`caller.py` has **module-level** required-env reads that run at import time:
`droplet_work/caller.py:102 LK_KEY = cfg_require("LIVEKIT_API_KEY")`, `:103 LK_SECRET = cfg_require("LIVEKIT_API_SECRET")`,
`:106 GROQ_KEY = cfg_require("GROQ_API_KEY")`. `cfg_require` is a **hard `os.environ[key]`** (raises
`KeyError` on miss — verified `:65-66`), and `load_dotenv("/opt/famit-agent/.env")` (`:53`) is a **silent
no-op off the prod box** (that absolute Linux path doesn't exist in GitHub Actions or on the local Windows
machine). **Therefore `uv run python -c "import caller"` (Step 8 + §10.2 acceptance) and `pytest` collection
of `test_imports.py` (backend.yml CI) FAIL with `KeyError: 'LIVEKIT_API_KEY'` on every machine without those
env vars.** This is the single step that would fail on the real box.
- **FIX (mandatory):** `backend/tests/conftest.py` MUST set dummy env **before any import of caller**:
  ```python
  import os, sys
  from pathlib import Path
  for k in ("LIVEKIT_API_KEY","LIVEKIT_API_SECRET","GROQ_API_KEY"):
      os.environ.setdefault(k, "test-dummy")   # caller.py reads these at MODULE level via cfg_require
  sys.path.insert(0, str(Path(__file__).parent.parent))
  ```
  and `backend.yml` MUST export the same three before the `python -c "import caller"` smoke (or drop that
  bare smoke and rely on pytest, which loads conftest first). These are throwaway non-secret values — they
  never authenticate anything; they only get past the module-level `os.environ[...]` lookup. Update §4.4,
  §5.1, §6.1, Step 8, and §10.2 to reflect this. **Without this fix the whole CI is red on day one.**

**[BLOCKER-2 — the "flat-import contract" test is weaker than claimed AND stricter than runtime; both directions matter].**
Every sibling import in `caller.py` is wrapped `try: import X except Exception: X=None` — verified:
`whatsapp` (`:34-37`), `vendors/*` (`:40-48`), `config` (`:59-66`), `auth` (`:71-74`), `audit` (`:77-80`),
`ratelimit` (`:83-86`), `obs` (`:88-92`). Consequences:
- A bare `import caller` **succeeds even if a sibling/`vendors/` was never moved into `backend/`** (it
  silently degrades to `None`). So `import caller` ALONE is NOT a curation-completeness gate.
- **FIX:** `test_imports.py` must (a) import each sibling **directly** (`import auth, audit, ratelimit, obs,
  whatsapp, config, memory, langdetect`; `from vendors import vobiz, elevenlabs, groq_meter, sarvam_meter`),
  AND (b) assert caller actually **wired** the optional handles — proving the try/except *succeeded*, not
  silently fell back to `None`:
  ```python
  import caller
  assert caller._auth_mod and caller._audit_mod and caller._rl_mod and caller._obs_mod
  assert caller.wa_mod and caller.v_vobiz and caller.v_elevenlabs
  ```
- **Inverse risk:** a direct `import auth` is **stricter than the live box**, which tolerates a missing
  sibling (degrades to `None`). So `backend/pyproject.toml` MUST carry **every transitive dep of every
  sibling** or CI fails where prod runs. Before locking deps, grep `whatsapp.py` + `vendors/*.py` imports
  and confirm nothing beyond the listed set (pyjwt/prometheus-client/redis/httpx) is needed.
- **VERIFIED 2026-06-09 (AST, this review):** all 8 siblings + all 6 `vendors/*.py` are **import-clean
  under a bare env** — ZERO module-level `os.environ[]`/`cfg_require`, ZERO top-level redis/connect/network
  call. Critically `ratelimit.py` opens redis **lazily** (NOT at import), so `import ratelimit` and the
  `assert caller._rl_mod` above hold in CI with **no redis on :6380**. ⇒ the 3-key conftest shim (BLOCKER-1)
  is **complete**: no sibling needs an extra env key at import. (`agent` and `prompt` are intentionally NOT
  in the direct-import set — `agent` pulls heavy `livekit.plugins.{silero,turn-detector}` that may touch
  fs/network at import; keep it out of the import-contract test. Re-run this AST check if P1/P2 adds a new
  sibling.)

**[BLOCKER-3 — CONCURRENT P1 Postgres workstream is actively editing the SAME files + the SAME box. Hidden coupling + breaking-change + md5-race].**
`droplet_work/P1_FOUNDATION_STATE.md` shows **U1 IN PROGRESS** (owner DB-ARCHITECT). P1 will: add `store.py`
+ `db/models.py`, add deps (`sqlalchemy[asyncio]`, `asyncpg`, `psycopg2-binary`, `alembic`, `greenlet`),
**rewire `_read`/`_write`/`_awrite` inside `caller.py`**, edit the box `.env` (PG_DSN), and **restart
famit-caller**. Global CLAUDE.md warns sessions run in parallel on this repo/box. This breaks the spec in
three concrete places:
- §4.1 include-list is a **frozen enumeration already going stale** (no `store.py`/`db/`).
- §5.1 `pyproject.toml` omits the SQLAlchemy/asyncpg/alembic stack → a P0 `backend/` will **fail to import a
  P1-edited `caller.py`** the moment P1 lands `import store`.
- §10.2 / Step-8 `md5(backend/caller.py) == deployed` **races any P1 deploy**: a mid-flight P1 push gives P0
  a false RED for reasons unrelated to P0 (P1 already pinned its own baseline `a60b8a9e…`).
- **FIX (coordination gate, not a code change):** (1) Pin curation to a **named snapshot** of `droplet_work/`
  — record the local `caller.py` md5 at curation start in `backend/DEPLOY.md` and state "`store.py`/`db/`
  land via **P1's** PR, not P0." (2) Change the §4.1 include rule from a hardcoded list to **"the live
  import graph of `caller.py`/`agent.py` as of the pinned snapshot"** (re-derive with the AST/grep used in
  this review). (3) Make §10.2 md5 a **point-in-time RECORD, not a gate** (it already says "record drift,
  don't fix prod" — make that explicit: a P1 deploy moving prod is EXPECTED, not a P0 failure). (4) Serialize:
  P0 backend curation and P1 must not both edit `backend/caller.py` — P1 owns `caller.py` evolution; P0 only
  *relocates* it. If P1 lands first, P0 curates the post-P1 tree (and adds the PG deps).

**[MINOR-1] Wrong dep.** §5.1 lists `google-api-core` "for protobuf Duration." `Duration` comes from
**`protobuf`** (already listed); `caller.py:29 from google.protobuf.duration_pb2 import Duration` is satisfied
by `protobuf` alone. **Remove `google-api-core`** (drops a needless transitive tree).

**[MINOR-2] Python version drift undermines "local == prod."** Box is **py3.12.3**; local `__pycache__` is
**cpython-3.14** (`droplet_work/__pycache__/*.cpython-314.pyc`). `requires-python=">=3.10"` is fine, but
**`target-version`/CI/uv must pin 3.12** (`uv python pin 3.12`; `setup-uv` with `python-version: 3.12`;
ruff `target-version="py312"`) so the tests that back the non-breaking claim run on the prod interpreter, not
a 3.14 that prod never uses. (`caller.py` uses no 3.13/3.14-only syntax — checked — so 3.12 is safe.)

**[MINOR-3] CF zone-id provenance is wrong.** §0/§7.1 say "zone id in `fortress/STATE.md` U8 line." It is
**NOT there** (only a derived HSTS note). The real source is the **API discover** in §7.5
(`/client/v4/zones?name=famit.in`). CF token present: `fortress/cred.md` holds `cfat_…2` (read scope is
enough for import+plan). Strike the false "in STATE.md" claim; §7.5 is authoritative.

**[MINOR-4] `uv sync --frozen` ordering.** backend.yml runs `uv sync --frozen` — this **hard-fails if
`uv.lock` is absent or stale**. Ensure Step 8 commits `backend/uv.lock` (from `uv lock`) in the SAME unit
that adds `pyproject.toml`, BEFORE any push that triggers CI. (Same for `pnpm install --frozen-lockfile`
needing a committed `pnpm-lock.yaml` from §5.3.)

**[MINOR-5] Duplicate header fixed in place.** The two `### 7.4` headers (import loop / no-diff offenders)
are renumbered §7.4 and §7.4b — the second is the fake-diff reference, not a second loop.

**[NOTE] Over-engineering check — PASS, with one trim.** `.gitattributes` `eol=lf` is correct and load-
bearing (md5 local-vs-deployed needs identical line endings — the editing happens on Windows, prod is
Linux). `.worktreeinclude` references `backend/.env`/`frontend/.env.local` that don't exist yet — harmless
(copy-if-present), but note they're created by the curation steps, not pre-existing. Everything else in the
gate is proportionate; do not add more.

---

## 0. GROUND TRUTH (verified 2026-06-09 against disk + live tooling — cite before trusting memory)

**Repo state:** `C:\Users\kunal\Desktop\caps` is **NOT a git repo** (`git status` → fatal). A thin
`caps\.gitignore` (8 lines) exists but is **dangerously incomplete** — it does NOT cover `fortress/`,
`ALL_CREDENTIALS.md`, SSH keys, `*.tgz`, `var/`, or the real backup suffixes.

**Secrets on disk that MUST NOT be committed (confirmed present):**
| Path | What | Gate must catch via |
|---|---|---|
| `caps\.env.local` | LIVE GROQ / ELEVEN / LIVEKIT keys (40+ keys) | `.gitignore` `.env*` + gitleaks |
| `caps\.env.example` | template (KEEP — re-included) | `!.env.example` |
| `caps\famit-panel\.env.local` | frontend env | `.gitignore` `**/.env.local` + gitleaks |
| `caps\fortress\cred.md` | DO token ref, CF tokens, Telegram bot token | `fortress/` wholesale ignore |
| `caps\fortress\cloud-init.yaml` | injected secrets | `fortress/` wholesale ignore |
| `caps\fortress\HUMAN_TASKS.md` | secret-bearing | `fortress/` wholesale ignore |
| `C:\Users\kunal\Desktop\lead\ALL_CREDENTIALS.md` | DO API token, Vobiz creds | **outside repo** (lead/ is NOT under caps — not staged; gitignore guards in case) |
| `caps\famit-panel.tgz` | 43 MB build artifact | `.gitignore` `*.tgz` |
| backups: `caller.py.bak.*`, `.w3bak.unit1`, `.waveA.unit0`, `.P0bak.*`, `.waveA2bak.*`, `.fallbackbak.*`, `.VFIXbak.*`, `.BRAINbak*`, `.p2ts`, `.p0ts` | may embed secrets; noise | `.gitignore` patterns + **staged scan is the real net** |

> **🚨 The `.gitignore` glob is the first line, NOT the net.** The backup suffixes prove it: a naive
> `*.bak.*` catches `caller.py.bak.1780515036` but **misses** `.w3bak.unit1` / `.waveA.unit0` /
> `.P0bak.1780614722`. **The guarantee is: `git add` the intended set → `gitleaks git --staged` → push
> only on GREEN → PRIVATE repo.** Do not chase glob perfection; the staged scan catches what globs miss.

**Tooling present (verified live):** gitleaks **8.30.1**, terraform **1.15.3**, uv **0.11.14**,
gh **2.93.0**, pnpm **10.33.2**, node **v22.11.0**. (gitleaks 8.x verbs differ from old docs — see §3.)

**Backend reality (the non-breaking lynchpin):** the live backend is a **FLAT** Python app. `caller.py`
(3422 lines) imports its siblings flat:
- `from prompt import build_system_prompt` (`droplet_work/caller.py:32`)
- `import whatsapp as wa_mod` (`:35`), `from vendors import elevenlabs ...` (`:41-45`)
- `from config import get ...` (`:60`), `import auth` (`:72`), `import audit` (`:78`),
  `import ratelimit` (`:84`), `import obs` (`:90`)
- `agent.py`: `import memory as mem` (`:26`), `import langdetect as ld` (`:31`)

On the live box these all sit flat in `/opt/famit-agent/`, run as `uvicorn caller:app --port 8209`
(systemd `famit-caller`) + the agent (systemd `famit-agent`). **THEREFORE: `/backend` MUST keep these
modules FLAT (siblings, no package nesting, no caller.py split).** Deploy = `scp` the same flat files.
A package refactor would break `uvicorn caller:app` and every flat import. That refactor is **Phase 1**.

**Two Python projects exist — do NOT confuse them:**
- `caps\droplet_work\` = the **LIVE, deployed** backend (caller/agent/prompt/vendors/auth/...). **This is `/backend`.**
- `caps\pyproject.toml` (`livekit-agent-capsy`, `package=false`) + `caps\src\{agent,knowledge}.py` +
  `caps\selfhost\` + `caps\scripts\` = an **older standalone LiveKit skeleton**, NOT what's deployed.
  **Leave it where it is** (do not delete, do not promote to `/backend`). Optionally note it under
  `/backend/legacy_skeleton_NOTES.md` as a pointer. It is not load-bearing for the live system.

**Frontend reality:** `caps\famit-panel` = Next.js "core-2", React 19, **requires `--legacy-peer-deps`**
with npm. We standardize on **pnpm** for the monorepo (pnpm handles peer deps without the flag; verify
build before declaring done). Deployed at `/opt/famit-panel` (systemd `famit-panel`, `next -p 3001`) on
`famit-panel-2 143.110.247.249`. `next.config.ts` already has `eslint.ignoreDuringBuilds` +
`typescript.ignoreBuildErrors` (KEEP).

**Live infra inventory (for §6 Terraform import — transcribe IDs EXACTLY):**
| Resource | Terraform type | Import ID |
|---|---|---|
| Droplet `famit-livekit` (backend+voice) | `digitalocean_droplet` | `574914961` |
| Droplet `famit-panel-2` (frontend) | `digitalocean_droplet` | `576010005` |
| VPC `default-blr1` (`10.122.0.0/20`) | `digitalocean_vpc` | `61f1950d-a7c4-4144-99b9-f1cda3d4c627` |
| Cloud Firewall (fortress, egress-locked, CF-CIDR inbound) | `digitalocean_firewall` | `c0e34e18-b696-4912-a3a4-566102e0945c` |
| SSH key `c13-blr-test-key` | `digitalocean_ssh_key` | `56622232` |
| CF zone `famit.in` (active) | `cloudflare_zone` | zone id in `fortress/STATE.md` U8 line / discover via API |
| CF DNS `A panel.famit.in → 143.110.247.249` (proxied) | `cloudflare_dns_record` | `<zone_id>/<record_id>` |
| CF DNS apex/www/app records | `cloudflare_dns_record` | per-record `<zone_id>/<record_id>` |

- DO region **blr1**. DO account `kunalkumar7x@gmail.com`, `droplet_limit=3`.
- DO API token + CF tokens live in `lead\ALL_CREDENTIALS.md` and `fortress\cred.md` (3 CF tokens; #3
  `cfat_…` had edit, #1/#2 read-only). **Import+plan needs only READ scope** → even a read-only CF token
  suffices (this dissolves master-plan blocker #6 for P0).

---

## 1. TARGET MONOREPO LAYOUT (what exists today → where it goes)

```
caps/                                  # becomes the git repo root (private GitHub: famit-revenue-os)
├─ .gitignore                          # REWRITTEN (§2) — comprehensive, shipped BEFORE first add
├─ .gitleaks.toml                      # gitleaks config (allowlist .env.example template only)
├─ .gitattributes                      # enforce LF for .py/.ts/.tf/.sh (md5 local-vs-deployed sanity)
├─ .worktreeinclude                    # gitignored files to copy into each worktree (.env.local etc.)
├─ README.md                           # repo root readme (monorepo map + the secrets-gate rule)
├─ CONTRIBUTING.md                     # worktree→feat/*→PR→squash→protected main model
│
├─ backend/                            # uv-managed. FLAT modules (mirror /opt/famit-agent EXACTLY).
│  ├─ pyproject.toml                   # uv project (deps from live venv; py>=3.10)
│  ├─ uv.lock
│  ├─ ruff.toml                        # scoped ruff config the 3422-line file actually passes (§5)
│  ├─ caller.py  agent.py  prompt.py  memory.py  langdetect.py  whatsapp.py
│  ├─ config.py  auth.py  audit.py  ratelimit.py  obs.py
│  ├─ vendors/                         # __init__.py, _http.py, vobiz.py, elevenlabs.py, groq_meter.py, sarvam_meter.py
│  ├─ tests/                           # pytest: test_imports.py, test_smoke_instantiate.py, test_health.py
│  │                                   # (wraps existing _smoke_pool.py / _smoke_prompt.py logic)
│  ├─ .env.example                     # template ONLY (copied/curated from caps\.env.local KEYS, NO values)
│  └─ DEPLOY.md                        # the scp+restart recipe (moved from HANDOFF, paths updated)
│
├─ frontend/                           # pnpm-managed Next.js (the famit-panel app)
│  ├─ package.json  pnpm-lock.yaml     # pnpm-lock generated by `pnpm import` from package-lock then build-verified
│  ├─ next.config.ts                   # KEEP ignoreDuringBuilds/ignoreBuildErrors
│  ├─ app/  components/  lib/  constants/  public/  ...   # existing tree
│  ├─ tests/e2e/login.spec.ts          # ONE Playwright smoke (login page renders / 200)
│  ├─ playwright.config.ts
│  └─ .env.local.example               # template (NO values)
│
├─ infra/                              # terraform. IMPORT-ONLY in P0 (never apply).
│  ├─ versions.tf                      # required_providers digitalocean + cloudflare (pin majors) + backend
│  ├─ providers.tf                     # provider config; tokens via env (TF_VAR_/DIGITALOCEAN_TOKEN/CLOUDFLARE_API_TOKEN)
│  ├─ variables.tf
│  ├─ digitalocean.tf                  # droplets, vpc, firewall, ssh_key resources (HCL matched to live)
│  ├─ cloudflare.tf                    # zone, dns_record(s) resources (HCL matched to live)
│  ├─ (NO imports.tf in P0)            # import is done via the apply-free CLI `terraform import` (§7.4); `import {}` blocks are apply-only — used only transiently for -generate-config-out scaffolding (§7.3), then deleted
│  ├─ terraform.tfstate*               # GITIGNORED (local state in P0; remote backend = follow-up)
│  └─ README.md                        # "import + plan ONLY. apply is FORBIDDEN in P0. no-diff is iterative."
│
├─ .github/
│  └─ workflows/
│     ├─ backend.yml                   # ruff + pytest (uv) on backend/** changes
│     ├─ frontend.yml                  # pnpm build + Playwright smoke on frontend/** changes
│     ├─ secrets.yml                   # gitleaks on every push/PR (full history scan)
│     └─ infra.yml                     # terraform fmt -check + validate on infra/** (NO plan in CI; no creds)
│
├─ docs/
│  └─ design/p0-foundation.md          # THIS FILE (already here)
│
├─ droplet_work/   →  (CONTENT git mv'd into backend/; the DIR itself + baks/STATE/.sh stay UNtracked/removed-from-index)
├─ famit-panel/    →  (CONTENT git mv'd into frontend/)
├─ fortress/       →  STAYS ON DISK, **git-ignored wholesale** (playbook also preserved in memory/)
├─ src/ selfhost/ scripts/ pyproject.toml uv.lock  →  legacy skeleton; leave as-is OR move under backend/legacy/ (low priority, do LAST)
└─ AUTONOMY_OS.md FEATURE_ROADMAP.md VOICE_ARCHITECTURE_RESEARCH.md ...  →  move to docs/ (optional, low priority)
```

> **CURATE, do not bulk-move.** `droplet_work/` contains deployable `.py` + tests **and** 30+ junk
> files (`*.bak.*`, `*.w3bak.*`, `STATE*.md`, `*.sh`, `*.sql`, `*.ps1`, `__pycache__`, `shapoorji_*.json`).
> Only the deployable modules + a curated test set go into `backend/`. See §4 for the exact include/exclude.

---

## 2. THE COMPREHENSIVE `.gitignore` (ship FIRST — before any `git add`)

**File: `C:\Users\kunal\Desktop\caps\.gitignore`** (REWRITE the existing 8-line file with this):

```gitignore
# ============================================================================
#  SECRETS / CREDS — NEVER COMMIT.  (gitleaks staged-scan is the real net; this is line 1.)
# ============================================================================
.env
.env.*
!.env.example
!*/.env.example
!*/.env.local.example
*.pem
*.key
*.p12
*.pfx
id_ed25519
id_ed25519.*
id_rsa
id_rsa.*
*.ppk
**/ALL_CREDENTIALS.md
**/cred.md
**/credentials*
**/secret
**/secrets.json
**/*secret*.toml
cloudflare.ini
.npmrc

# ----- fortress: secret-bearing playbook dir — IGNORE WHOLESALE (task mandate) -----
fortress/
fortress/**

# ============================================================================
#  RUNTIME DATA / SERVER STATE / BACKUPS  (broad — backup suffixes are inconsistent)
# ============================================================================
**/var/
**/transcripts/
**/*.bak
**/*.bak.*
**/*bak[0-9]*
**/*.w3bak*
**/*.waveA*
**/*.waveA2*
**/*.P0bak*
**/*.P2*bak*
**/*.VFIXbak*
**/*.BRAINbak*
**/*.fallbackbak*
**/*.pretenant.bak
**/.p0ts
**/.p2ts
*.tgz
*.tar.gz
*.zip

# ============================================================================
#  TERRAFORM  (state can contain secrets; never commit)
# ============================================================================
**/.terraform/
**/.terraform.lock.hcl        # (optional: many teams DO commit this; we ignore in P0 to avoid churn)
*.tfstate
*.tfstate.*
*.tfvars
!*.tfvars.example
crash.log
crash.*.log
tfplan
*.tfplan

# ============================================================================
#  NODE / NEXT  (frontend)
# ============================================================================
node_modules/
.next/
out/
.pnpm-store/
.turbo/
*.log
npm-debug.log*
pnpm-debug.log*

# ============================================================================
#  PYTHON  (backend)
# ============================================================================
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.ruff_cache/
*.egg-info/
.mypy_cache/

# ============================================================================
#  CLAUDE WORKTREES / EDITOR / OS
# ============================================================================
.claude/worktrees/
.DS_Store
Thumbs.db
.idea/
.vscode/
*.swp
```

**File: `C:\Users\kunal\Desktop\caps\.gitleaks.toml`** (extend defaults; allow ONLY the template):

```toml
title = "famit-revenue-os gitleaks config"

[extend]
useDefault = true   # all built-in rules (AWS, GCP, generic API keys, private keys, JWT, etc.)

# Paths that are templates / pure structure (KEYS only, no values) — exempt from findings.
[[allowlists]]
description = "env + tfvars templates contain key names only, never values"
paths = [
  '''.*\.env\.example$''',
  '''.*\.env\.local\.example$''',
  '''.*\.tfvars\.example$''',
]
```

**File: `C:\Users\kunal\Desktop\caps\.gitattributes`** (LF normalization so md5 local-vs-deployed holds):

```gitattributes
* text=auto eol=lf
*.py   text eol=lf
*.ts   text eol=lf
*.tsx  text eol=lf
*.tf   text eol=lf
*.sh   text eol=lf
*.png  binary
*.jpg  binary
*.lock text eol=lf
```

**File: `C:\Users\kunal\Desktop\caps\.worktreeinclude`** (gitignored files copied into each worktree):

```
.env.local
backend/.env
frontend/.env.local
```

---

## 3. THE SECRETS-GATE — exact command ORDER (the irreversible step; do EXACTLY this)

> Run from `C:\Users\kunal\Desktop\caps`. PowerShell. **Do NOT run `git init && git add .` blind** — the
> whole point is the gate runs BEFORE any commit and the repo is PRIVATE.

**STEP A — write the three gate files** (§2): `.gitignore`, `.gitleaks.toml`, `.gitattributes`,
`.worktreeinclude`. (Edit/Write tools.)

**STEP B — RAW pre-init scan of the entire working tree** (catches anything, tracked or not):
```powershell
gitleaks dir . --config .gitleaks.toml --redact --no-banner --report-format json --report-path gitleaks-raw.json --exit-code 1
```
- Exit 0 → no secrets in scannable files (note: this scans EVERYTHING incl. files we'll ignore; expect
  it to FLAG `.env.local`, `fortress/cred.md`, etc. — **that is correct and expected**).
- **This raw scan is DIAGNOSTIC**, not the gate. Its job: produce the inventory of where secrets live so
  you can confirm `.gitignore` covers each. Review `gitleaks-raw.json` (redacted) → every finding's path
  MUST be matched by a `.gitignore` rule. If a finding is in a file that SHOULD be tracked → STOP, fix.

**STEP C — `git init` + stage the gate file first** (so the very first thing tracked is the ignore rules):
```powershell
git init
git add .gitignore .gitleaks.toml .gitattributes .worktreeinclude
git commit -m "chore: secrets-gate scaffolding before tracking anything

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**STEP D — stage the intended tree, then verify nothing secret got staged** (THE GATE):
```powershell
git add .
# THE GATE — scan ONLY what is staged for commit:
gitleaks git --staged --config .gitleaks.toml --redact --no-banner --exit-code 1
```
- **Exit 0 (GREEN) → proceed.** Exit 1 (RED) → a secret is staged. **STOP.** `git restore --staged <file>`,
  add the path to `.gitignore`, re-stage, re-scan. Loop until GREEN. **Never commit on RED.**
- Sanity cross-check the staged set excludes the danger files:
```powershell
git diff --cached --name-only | Select-String -Pattern "\.env\.local$|fortress/|cred\.md|ALL_CREDENTIALS|id_ed25519|\.tgz$|/var/|\.bak"
# EXPECT: no output. Any match = RED, unstage it.
```

**STEP E — first real commit** (only on GREEN gate):
```powershell
git commit -m "chore: initial crash-safe snapshot (gitleaks staged-scan GREEN)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git branch -M main
```

**STEP F — create the PRIVATE GitHub repo and push** (private is a hard requirement — defense in depth):
```powershell
gh repo create famit-revenue-os --private --source . --remote origin --description "Famit/Axcrio AI Revenue OS (strangler monorepo)"
# Re-scan FULL history one more time before the push leaves the machine:
gitleaks git . --config .gitleaks.toml --redact --no-banner --exit-code 1
# GREEN → push:
git push -u origin main
```

**STEP G — install a local pre-commit hook** (belt-and-suspenders for future commits):

**File: `C:\Users\kunal\Desktop\caps\.githooks\pre-commit`** (then `git config core.hooksPath .githooks`):
```bash
#!/usr/bin/env bash
# Block any commit that stages a secret. Fails the commit on a gitleaks finding.
set -e
echo "[pre-commit] gitleaks staged scan…"
gitleaks git --staged --config .gitleaks.toml --redact --no-banner --exit-code 1
echo "[pre-commit] clean."
```
```powershell
git config core.hooksPath .githooks
# Windows: ensure the hook is executable via git (bash runs it). Verify with a throwaway staged secret test (§ acceptance).
```

> **gitleaks 8.30.1 verb reference (VERIFIED live, not from memory):**
> - `gitleaks dir <path> [--config] [--report-format json --report-path f] [--exit-code 1]` — scan a raw
>   directory/file tree (replaces old `detect --no-git --source`).
> - `gitleaks git <repo> [--staged] [--pre-commit] [--log-opts]` — scan a git repo; `--staged` = scan the
>   index (the pre-commit gate); no flag = scan full history.
> - `--redact` redacts secret values from output; `--exit-code 1` = nonzero on any finding (CI/gate).

---

## 4. MONOREPO CURATION — exact include / exclude + recipe updates (non-breaking)

> Done AFTER the first commit (so every move is a reviewable diff). Use `git mv` to preserve history.
> **One unit per directory.** After each, re-run the staged gate (§3 D) before committing.

### 4.1 `backend/` — INCLUDE (deployable + tests only)
`git mv` these FROM `droplet_work/` TO `backend/` (keep FLAT — do not nest):
```
caller.py  agent.py  prompt.py  memory.py  langdetect.py  whatsapp.py
config.py  auth.py  audit.py  ratelimit.py  obs.py
vendors/__init__.py  vendors/_http.py  vendors/vobiz.py  vendors/elevenlabs.py
vendors/groq_meter.py  vendors/sarvam_meter.py
```
**EXCLUDE (do NOT move into `backend/`):**
`*.bak.*`, `*.w3bak.*`, `*.waveA*`, `*.waveA2*`, `*.P0bak*`, `*.P2*`, `*.VFIXbak*`, `*.BRAINbak*`,
`*.fallbackbak*`, `*.pretenant.bak`, `STATE*.md`, `WAVE*_STATE.md`, `P0_*.md`, `P1_*.md`, `*.sh`,
`*.sql`, `*.ps1`, `__pycache__/`, `*.pyc`, `.p0ts`, `.p2ts`, `shapoorji_*.json`, `_smoke_*.py` (→ wrap
into `backend/tests/`, see 4.4), `_inspect_td.py`, `_provision_pg.sh`, `place_call.py`, `comp_test.py`,
`base.py`, `campaign.py`, `models.py`, `va2_models.py`, `real_agent.py`, `llm_router_processor.py`,
`bridge.py` (these are old/experimental — verify none is imported by `caller.py`/`agent.py` before
excluding; grep confirms they are NOT in the live import graph).

> **⚠️ Disposition of the leftovers (the `git mv` moves the deployables OUT, but the junk stays TRACKED
> unless you act — `droplet_work/` is NOT in `.gitignore`):** after moving the deployables, the remaining
> `droplet_work/` files are still in the index. Pick ONE:
> - **(a) Preferred — `git rm` the junk** so it leaves the repo entirely (history keeps it; backups are
>   noise we don't want tracked): `git rm -r droplet_work/` AFTER the deployables are safely under
>   `backend/` and import-verified. The most valuable `STATE*.md` notes are already preserved in `memory/`.
> - **(b) Conservative — add `droplet_work/` to `.gitignore` then `git rm -r --cached droplet_work/`**
>   (untrack but keep the files on disk as a local scratch ref). Either way: re-run the staged-gate (§3 D)
>   after, and confirm `git status` is clean.

> **NON-BREAKING PROOF (do this in the same unit):** after the move, `cd backend; uv run python -c "import caller"`
> must succeed (all flat imports resolve). And `md5sum backend/caller.py` must equal the deployed
> `/opt/famit-agent/caller.py` md5 (read-only ssh; CRLF-normalize first). If md5 differs, the local copy
> drifted from prod — **do NOT "fix" prod from here**; record the drift and proceed (P0 doesn't deploy).

### 4.2 `frontend/` — move the app
`git mv famit-panel/* frontend/` (and dotfiles). Exclude `node_modules/`, `.next/`, `famit-panel.tgz`
(already ignored). Keep `next.config.ts` flags.

### 4.3 Update EVERY path reference (same unit as the move — grep-driven)
The HANDOFF, deploy recipes, and scripts reference `caps\droplet_work\…` and `caps\famit-panel`. Grep
and update (these are DOCS, not live code — safe to edit):
```powershell
# find references:
Select-String -Path C:\Users\kunal\Desktop\caps\**\*.md -Pattern "droplet_work|famit-panel" -List
```
Update `backend/DEPLOY.md` (moved from HANDOFF §"DEPLOY RECIPES") so the scp source is `backend/*.py`:
```
scp -i <do-blr-test key> backend\caller.py backend\agent.py backend\prompt.py backend\memory.py `
    famit@168.144.153.145:/opt/famit-agent/
ssh ... 'sudo systemctl restart famit-caller famit-agent'
```
> **The deploy TARGET (`/opt/famit-agent/`, flat) does NOT change.** Only the local SOURCE path changes.
> This is why FLAT layout is mandatory — the recipe stays a 1:1 file copy.

### 4.4 `backend/tests/` — wrap the existing smoke tests (so pytest in CI is real, not empty)
The repo already has `_smoke_pool.py` and `_smoke_prompt.py` (instantiate-style smoke tests — the kind
that catches the `groq.LLM(max_tokens=…)` TypeError that ast.parse misses, per brain/mistakes). Convert:
- `tests/test_imports.py` — `import caller, agent, prompt, memory, langdetect, whatsapp, config, auth, audit, ratelimit, obs` and `from vendors import ...` all succeed (the flat-import contract).
- `tests/test_smoke_prompt.py` — wrap `_smoke_prompt.py`: `build_system_prompt(GODREJ_FIELDS)` returns a
  non-empty str; default-len assertion loose (>2000).
- `tests/test_smoke_instantiate.py` — wrap `_smoke_pool.py` logic where it doesn't need network/keys
  (guard vendor-client instantiation behind `pytest.importorskip` / `skipif no key in env`). The point:
  catch constructor-signature regressions, not make live calls.
- `tests/conftest.py` — set dummy env for the THREE module-level required keys **before** `sys.path` /
  any caller import (see RED-TEAM FIX BLOCKER-1: `caller.py:102/103/106` call `cfg_require` at import time,
  so without these `import caller`/pytest-collection crash with `KeyError`):
  ```python
  import os, sys
  from pathlib import Path
  for k in ("LIVEKIT_API_KEY","LIVEKIT_API_SECRET","GROQ_API_KEY"):
      os.environ.setdefault(k, "test-dummy")
  sys.path.insert(0, str(Path(__file__).parent.parent))
  ```
- `test_imports.py` — per RED-TEAM FIX BLOCKER-2: import each sibling DIRECTLY *and* assert caller wired the
  optional handles (`assert caller._auth_mod and caller._audit_mod and caller._rl_mod and caller._obs_mod and
  caller.wa_mod and caller.v_vobiz`) — a bare `import caller` passes even with siblings missing (try/except→None).

---

## 5. `/backend` uv + ruff + `/frontend` pnpm CONFIG (CI must ship GREEN or it's red forever)

### 5.1 `backend/pyproject.toml`
```toml
[project]
name = "famit-backend"
version = "0.1.0"
description = "Famit AI tele-calling backend (FastAPI /api + LiveKit voice agent). FLAT modules; mirrors /opt/famit-agent."
requires-python = ">=3.10"
dependencies = [
  # Pin to what the LIVE venv (/opt/capsy-agent/.venv, py3.12.3) actually has.
  # Discover exact versions read-only:  ssh famit@168.144.153.145 '/opt/capsy-agent/.venv/bin/pip freeze'
  "fastapi",
  "uvicorn[standard]",
  "httpx",
  "python-dotenv",
  "livekit-api>=1.0.0",
  "livekit-agents[elevenlabs,groq,sarvam,silero,turn-detector]~=1.3",
  "protobuf",
  "pyjwt",
  "prometheus-client",
  "redis",
  "google-api-core",   # for protobuf Duration import used in caller.py
]

[dependency-groups]
dev = ["ruff", "pytest"]

[tool.uv]
package = false   # FLAT app, not an installable package — matches the live deploy model.
```
> Generate the lock + verify imports:
> ```powershell
> cd backend; uv lock; uv sync; uv run python -c "import caller; print('flat imports OK')"
> ```
> **Pin versions from the live venv** (`pip freeze` read-only) so local == prod and tests are meaningful.

### 5.2 `backend/ruff.toml` (a config the 3422-line legacy file PASSES — curated select)
```toml
# P0: keep CI GREEN on legacy code. Start narrow (real bug classes only), widen in later phases.
line-length = 120
target-version = "py310"

[lint]
# Only high-signal, near-zero-false-positive rules the legacy file already satisfies (or trivially can):
select = ["F", "E9"]      # pyflakes (undefined names, unused imports that matter) + syntax errors
ignore = [
  "F401",  # unused import — legacy has intentional re-exports / optional imports; don't fail CI on it
  "F841",  # unused local — legacy has some; not a P0 blocker
  "E722",  # bare except — legacy uses defensive bare excepts in hot paths (intentional)
]
exclude = ["tests/_*", "**/__pycache__"]
```
> **Verify GREEN BEFORE wiring CI:** `cd backend; uv run ruff check .` must exit 0. If a real
> undefined-name (`F821`) surfaces, that's a genuine latent bug — fix it (it's already in prod) and note
> it; do NOT silence `F` wholesale. The goal: CI fails only on real breakage, never on style.

### 5.3 `frontend/` — pnpm
```powershell
cd frontend
pnpm import          # convert existing package-lock.json → pnpm-lock.yaml (preserves resolved versions)
pnpm install
pnpm run build       # MUST exit 0 (React 19 peer-deps: pnpm resolves without --legacy-peer-deps; verify!)
```
> If `pnpm run build` fails on a peer-dep that npm only tolerated via `--legacy-peer-deps`, add a
> `.npmrc` with `legacy-peer-deps=true` **OR** a `pnpm.overrides` / `pnpm.peerDependencyRules` block in
> `package.json` — whichever makes the build pass. **A failing frontend build = do not proceed**; the
> existing app builds today, so a green build is achievable. (`.npmrc` is gitignored only if it holds a
> token; a peer-deps-only `.npmrc` is safe to commit — adjust §2 if you commit it.)

### 5.4 Playwright — ONE smoke spec (not E2E)
`frontend/tests/e2e/login.spec.ts`:
```ts
import { test, expect } from '@playwright/test';
test('login page renders', async ({ page }) => {
  await page.goto('/login');
  await expect(page.locator('input[type="password"]')).toBeVisible();
});
```
`frontend/playwright.config.ts`: `webServer` runs `pnpm run build && pnpm run start -p 3001`,
`baseURL: 'http://localhost:3001'`, single chromium project, `timeout` generous. **No live-backend
dependency** (login page must render without the API).

---

## 6. CI — GitHub Actions (`.github/workflows/`)

> **Path-filtered** so backend changes don't run frontend jobs. **No secrets/creds in any workflow.**
> **No `terraform plan` in CI** (no DO/CF creds in CI; plan is run locally by the agent — §7).

### 6.1 `.github/workflows/backend.yml`
```yaml
name: backend
on:
  push: { paths: ["backend/**", ".github/workflows/backend.yml"] }
  pull_request: { paths: ["backend/**"] }
jobs:
  lint-test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen          # needs committed backend/uv.lock (RED-TEAM FIX MINOR-4)
      - run: uv run ruff check .
      - run: uv run pytest -q          # conftest sets dummy LIVEKIT_API_KEY/_SECRET/GROQ_API_KEY (BLOCKER-1)
```

### 6.2 `.github/workflows/frontend.yml`
```yaml
name: frontend
on:
  push: { paths: ["frontend/**", ".github/workflows/frontend.yml"] }
  pull_request: { paths: ["frontend/**"] }
jobs:
  build-e2e:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 10 }
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm, cache-dependency-path: frontend/pnpm-lock.yaml }
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec playwright install --with-deps chromium
      - run: pnpm run build
      - run: pnpm exec playwright test
```

### 6.3 `.github/workflows/secrets.yml` (gitleaks on every push/PR — the CI net)
```yaml
name: secrets
on: [push, pull_request]
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }   # full history so a secret in ANY commit is caught
      - uses: gitleaks/gitleaks-action@v2
        env: { GITLEAKS_CONFIG: .gitleaks.toml }
```

### 6.4 `.github/workflows/infra.yml` (fmt + validate only — NO plan, NO creds)
```yaml
name: infra
on:
  push: { paths: ["infra/**"] }
  pull_request: { paths: ["infra/**"] }
jobs:
  fmt-validate:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: infra } }
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform fmt -check -recursive
      - run: terraform init -backend=false
      - run: terraform validate
```

---

## 7. TERRAFORM — IMPORT → NO-DIFF PLAN (can destroy the live earner → strict guardrails)

> **🚨 P0 RULE: use the apply-free `terraform import` CLI + `plan` ONLY. `terraform apply` is FORBIDDEN
> this phase.**
>
> **CRITICAL MECHANISM NOTE (do not get this wrong):** the **CLI command `terraform import <addr> <id>`**
> reads the live resource and writes it into LOCAL STATE — it touches **NO infrastructure** and needs
> **NO `apply`**. That is the apply-free path. **Do NOT use config-driven `import {}` blocks for the
> actual import**, because those blocks execute **only during `apply`** — with apply forbidden, state
> stays empty and `plan` would forever print `N to import` and can NEVER reach `No changes`. (Block-style
> import is used in this spec for ONE narrow, apply-free purpose only: `-generate-config-out` HCL
> scaffolding — see §7.3.)
>
> No-diff is achieved **iteratively** (CLI-import each resource → `plan` → fix HCL to match reality →
> re-`plan`), never first-try. **Acceptance = `terraform plan` reports `No changes. Your infrastructure
> matches the configuration.`** Any line containing **`must be replaced`**, **`will be destroyed`**, or
> **`-/+`** is a **RED STOP** — the HCL is wrong, NOT something to apply. Fix the HCL; never let plan
> converge by destroying a resource.
>
> **30-second sanity proof before doing the full set:** add an `import {}` block for JUST the VPC and run
> `terraform plan` — it will say **"1 to import"**, NOT "No changes". That proves blocks need apply.
> Then delete that block and use the CLI `terraform import digitalocean_vpc.default_blr1 <id>` instead →
> `plan` can now reach "No changes". This is the difference the whole section hinges on.

### 7.1 Provider versions (VERIFIED resource names — do not guess)
`infra/versions.tf`:
```hcl
terraform {
  required_version = ">= 1.5"   # 1.5+ for the (scaffolding-only) `-generate-config-out` flow; CLI import works on any version
  required_providers {
    digitalocean = { source = "digitalocean/digitalocean", version = "~> 2.0" }
    cloudflare   = { source = "cloudflare/cloudflare",   version = "~> 5.0" }  # v5: cloudflare_dns_record
  }
}
```
> **Cloudflare provider is v5** (confirmed via context7): the DNS resource is **`cloudflare_dns_record`**
> (NOT the old `cloudflare_record`), import id **`<zone_id>/<dns_record_id>`**, proxied records use
> `proxied = true` + `ttl = 1`. Zone settings in v5 are a separate resource — discover its exact name +
> schema from the provider docs at implement-time (`cloudflare_zone_setting` family); **do NOT hand-write
> zone-setting HCL from memory** (a wrong schema = hours of fake diffs). If zone-settings import is
> fiddly, scope P0 import to **zone + dns_records only** and flag zone-settings as a follow-up (still
> no-diff for what's imported).

### 7.2 Provider config — tokens from env, never hardcoded
`infra/providers.tf`:
```hcl
provider "digitalocean" {}                       # reads DIGITALOCEAN_TOKEN from env
provider "cloudflare" {}                          # reads CLOUDFLARE_API_TOKEN from env (read scope suffices)
```
Set locally (PowerShell, per session — NEVER commit):
```powershell
$env:DIGITALOCEAN_TOKEN = "<DO token from lead\ALL_CREDENTIALS.md>"
$env:CLOUDFLARE_API_TOKEN = "<CF token from fortress\cred.md (read-only is fine for import+plan)>"
```

### 7.3 Scaffold HCL apply-free with `-generate-config-out` (optional but recommended — kills the v5-schema guesswork)
> `terraform plan -generate-config-out=gen.tf` **with** an `import {}` block runs at **PLAN time** — it
> writes NO state and changes NO infra — and **auto-generates HCL matching the live resource**. This is
> the ONLY use of `import {}` blocks in P0, and it's purely to avoid hand-writing the Cloudflare v5
> zone-settings / record schema (open-risk #2) from memory.

Temporary `infra/_gen_imports.tf` (used ONLY for scaffolding, then DELETED before the real import):
```hcl
import { to = digitalocean_vpc.default_blr1,        id = "61f1950d-a7c4-4144-99b9-f1cda3d4c627" }
import { to = digitalocean_ssh_key.c13_blr_test,    id = "56622232" }
import { to = digitalocean_droplet.famit_livekit,   id = "574914961" }
import { to = digitalocean_droplet.famit_panel_2,   id = "576010005" }
import { to = digitalocean_firewall.fortress,       id = "c0e34e18-b696-4912-a3a4-566102e0945c" }
import { to = cloudflare_zone.famit_in,             id = "<ZONE_ID>" }
import { to = cloudflare_dns_record.panel,          id = "<ZONE_ID>/<RECORD_ID>" }
# ...one per CF DNS record discovered (§7.5).
```
```powershell
cd infra
terraform init
terraform plan -generate-config-out=gen.tf    # PLAN-time: writes gen.tf (HCL for every live resource); NO state, NO apply
```
Then: clean `gen.tf` into the real `digitalocean.tf` / `cloudflare.tf` (drop read-only computed
attributes terraform marks, keep the real config), and **DELETE `_gen_imports.tf` + `gen.tf`** so no
`import {}` block remains in the committed config. (If you'd rather hand-write the HCL, skip this and go
straight to §7.4 — the CLI import + plan loop still gets you to no-diff; this step just saves typing the
fiddly v5 schema.)

### 7.4 The APPLY-FREE import → no-diff loop (CLI `terraform import` — writes state, NOT infra)
With the `resource "..." "..." {}` stubs present (from §7.3 or hand-written), import each resource into
state via the **CLI** (this is the apply-free import — no `import {}` block, no `apply`):
```powershell
cd infra
terraform init

# --- DigitalOcean FIRST (the live earner) ---
terraform import digitalocean_vpc.default_blr1      61f1950d-a7c4-4144-99b9-f1cda3d4c627
terraform import digitalocean_ssh_key.c13_blr_test  56622232
terraform import digitalocean_droplet.famit_livekit 574914961
terraform import digitalocean_droplet.famit_panel_2 576010005
terraform import digitalocean_firewall.fortress     c0e34e18-b696-4912-a3a4-566102e0945c

# --- Cloudflare (IDs from §7.5) ---
terraform import cloudflare_zone.famit_in           <ZONE_ID>
terraform import cloudflare_dns_record.panel        "<ZONE_ID>/<RECORD_ID>"
# ...one CLI import per CF DNS record.

# --- THE NO-DIFF LOOP ---
terraform plan
# → for every "~ update in place" / "must be replaced": edit the resource HCL to MATCH the live value
#   (firewall rule ORDER, the 15 CF inbound CIDRs, ports, droplet size/region/vpc_uuid/tags/backups,
#    CF proxied=true/ttl=1), then re-plan. Repeat until:
#   "No changes. Your infrastructure matches the configuration."
```
> Each `terraform import` line **mutates only `terraform.tfstate` (local, gitignored)** — it does not
> create, modify, or destroy anything in DO/Cloudflare. `plan` then compares that state+HCL against live
> reality and prints the drift, which is your oracle for fixing the HCL. **Never run `apply`.**

### 7.4b No-diff offenders reference (the fake-diff oracle — same loop as 7.4)
```powershell
cd infra
terraform init
# DISCOVER real attribute values read-only (so HCL matches), e.g. via DO/CF API or:
terraform plan            # first plan AFTER import blocks: shows what TF would change to make reality match HCL
# → read each proposed change. For every "~ update" or "must be replaced":
#    edit the resource HCL to MATCH the live value (size, region, vpc_uuid, firewall rule order, the 15
#    CF inbound CIDRs, proxied/ttl, tags) until plan shrinks.
terraform plan            # repeat until:  "No changes. Your infrastructure matches the configuration."
```
> **No-diff offenders to transcribe EXACTLY from the live API (these cause fake diffs):**
> firewall **inbound/outbound rule ORDER** + the **15 Cloudflare CIDRs** + ports (22/80/443 + the 7-rule
> egress allow-list); droplet `size` (`s-4vcpu-8gb` livekit / `s-1vcpu-2gb` panel), `region=blr1`,
> `image`, `vpc_uuid`, `tags=["fortress"]`, `backups`/`monitoring` booleans; CF record `proxied=true`,
> `ttl=1`. Use `terraform plan` output itself as the diff oracle — it prints the live value vs your HCL.

### 7.5 Discover Cloudflare zone + record IDs (read-only)
```powershell
# zone id (also in fortress\STATE.md U8 line):
curl.exe -s -H "Authorization: Bearer $env:CLOUDFLARE_API_TOKEN" "https://api.cloudflare.com/client/v4/zones?name=famit.in"
# records for the zone:
curl.exe -s -H "Authorization: Bearer $env:CLOUDFLARE_API_TOKEN" "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/dns_records"
```

### 7.6 State handling
`terraform.tfstate*` is **gitignored** (it embeds resource detail). P0 uses **local state**. A remote
backend (DO Spaces / TF Cloud) is a **follow-up**, not P0. Commit only the `.tf` HCL + `imports.tf`,
never state.

---

## 8. GIT WORKFLOW — worktree → feat/* → PR → squash → PROTECTED main

`CONTRIBUTING.md` (repo root) documents and the agent follows:
- **main is protected** (set after first push, §9). No direct pushes; PR + green CI + squash-merge only.
- **One workstream = one branch off main**, built in a **git worktree** for isolation:
  ```powershell
  git switch -c feat/<workstream>
  # OR Claude-managed isolation:  claude --worktree <name>   (creates .claude/worktrees/<name>)
  ```
  Worktrees auto-exclude via `.gitignore` `.claude/worktrees/`; `.worktreeinclude` copies `.env.local`
  etc. into each.
- **Per-unit loop inside a branch:** backup (n/a — git is the backup now) → small edit → `uv run ruff
  check` / `pytest` / `pnpm build` green → commit (conventional: `feat(area): … — verified <how>`) →
  next. One file = one owner; **`caller.py` is serialized in main, never two agents at once** (3422-line
  shared file — brain/mistakes rule).
- **PR:** `gh pr create --fill --base main`; CI (the 4 workflows) must be green; squash-merge.
- **Branch protection** (§9): require PR, require status checks (`backend`, `frontend`, `secrets`),
  no force-push to main, linear history.

> **Rollback (this whole phase):** every change is local/git. Rollback = `git revert`/`git reset` on a
> branch, or simply don't merge the PR. **Terraform never `apply`s, so infra rollback is N/A** (state is
> read-only-derived). **The live boxes are untouched** → there is nothing in production to roll back.

---

## 9. STEP ORDER (the spine) — each step has an ACCEPTANCE TEST + model routing

| # | Step | Acceptance test (PROVE it; no live-box break) | Model | Rollback |
|---|---|---|---|---|
| **1** | Write `.gitignore` + `.gitleaks.toml` + `.gitattributes` + `.worktreeinclude` (§2) | Files exist; `.gitignore` matches `.env.local`, `fortress/`, `*.tgz`, `var/`, backup suffixes (spot-check `git check-ignore -v caps\.env.local` after init) | **opus** (secrets-gate review) | delete files |
| **2** | RAW gitleaks scan `gitleaks dir .` (§3 B) | Command runs; `gitleaks-raw.json` produced; EVERY finding's path is covered by a `.gitignore` rule (manual confirm) | opus | n/a (read-only) |
| **3** | `git init` + commit gate files (§3 C) | `git log` shows 1 commit containing ONLY the 4 gate files | sonnet | `rm -rf .git` |
| **4** | `git add .` → **`gitleaks git --staged`** GATE (§3 D) | gitleaks exits **0**; `git diff --cached --name-only` has NO `.env.local`/`fortress/`/`cred.md`/`*.tgz`/`.bak` match | **opus** | `git restore --staged`, fix ignore |
| **5** | First real commit (§3 E) | `git log` 2 commits; `git status` clean | sonnet | `git reset --soft HEAD~1` |
| **6** | `gh repo create --private` + full-history scan + push (§3 F) | `gh repo view` shows **private**; gitleaks full-history exit 0; `git push` succeeds; GitHub repo has no secret files (spot-check the web tree) | **opus** | delete the GitHub repo, it's private |
| **7** | Install pre-commit hook (§3 G) | Plant a secret of a format gitleaks' default rules ACTUALLY catch, e.g. a fake AWS pair `AKIAIOSFODNN7EXAMPLE` + a 40-char secret `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`, OR a generic high-entropy `api_key = "sk_live_0123456789abcdef0123456789abcdef"` → `git add` it → `git commit` is **BLOCKED** by the hook (nonzero exit). Remove the test file. (A weak fake that gitleaks ignores would "pass" by NOT detecting — proving nothing; use a real-format fake.) | sonnet | `git config --unset core.hooksPath` |
| **8** | Curate `backend/` via `git mv` (§4.1) + `backend/tests/` (§4.4) + wire `pyproject.toml`/`ruff.toml` (§5.1-5.2) | `cd backend; uv sync; uv run python -c "import caller"` OK; `uv run ruff check .` exit 0; `uv run pytest -q` green; staged-gate still GREEN; `backend/caller.py` md5 == deployed (read-only ssh, CRLF-normalized) | **sonnet** (haiku for the mechanical mv) | `git mv` back / revert branch |
| **9** | Curate `frontend/` via `git mv` (§4.2) + pnpm (§5.3) + Playwright (§5.4) | `cd frontend; pnpm install; pnpm run build` exit 0; `pnpm exec playwright test` green; staged-gate GREEN | **sonnet** | revert branch |
| **10** | Update all `droplet_work`/`famit-panel` path refs in docs + `backend/DEPLOY.md` (§4.3) | `Select-String droplet_work\|famit-panel` shows only intended/historical hits; DEPLOY.md scp source = `backend\*.py`, target unchanged `/opt/famit-agent/` | haiku | revert |
| **11** | Add the 4 CI workflows (§6); open a PR to trigger them | PR shows `backend` + `frontend` + `secrets` + `infra` checks; ALL green | **sonnet** | delete workflow files |
| **12** | Protect `main` (§8) | `gh api repos/:owner/famit-revenue-os/branches/main/protection` shows required checks + PR required + no force-push | sonnet | `gh api … -X DELETE` |
| **13** | Terraform scaffold (§7.1-7.3): `versions/providers/variables/digitalocean/cloudflare/imports.tf` | `terraform init` OK; `terraform validate` OK; `terraform fmt -check` clean | **sonnet** (authors HCL) | delete infra branch |
| **14** | Apply-free CLI `terraform import` → NO-DIFF loop, **DO resources FIRST** (§7.4) | `terraform plan` → **"No changes"** for DO droplets/vpc/firewall/ssh_key. **Zero** `must be replaced`/`destroyed`/`-/+`. (NOT "N to import" — that'd mean you wrongly used apply-only `import {}` blocks instead of the CLI.) | **opus** (plan-diff verdict) | CLI import writes only LOCAL state (gitignored) — never touches prod; rollback = `rm terraform.tfstate*` |
| **15** | Terraform CF zone + dns_records import → no-diff (§7.5) | `terraform plan` → "No changes" for CF zone + records (or zone-settings flagged as follow-up) | **opus** | plan-only |
| **16** | Final phase verification (§10) | Full §10 checklist green; live site STILL up (`curl https://panel.famit.in/api/stats` 200 — read-only) | opus (one-time review) | n/a |

---

## 10. PHASE-0 ACCEPTANCE (the global gate — all must pass)

1. **Secrets:** `gh repo view famit-revenue-os --json visibility` = `private`; `gitleaks git .` on the
   pushed repo exits 0; GitHub web tree contains NO `.env.local`, `fortress/*`, `cred.md`,
   `ALL_CREDENTIALS.md`, SSH key, `*.tgz`, `var/`, or `*.bak*`. Pre-commit hook blocks a planted secret.
2. **Backend non-breaking:** `cd backend; uv run pytest -q` green (conftest sets the 3 dummy module-level
   keys — RED-TEAM FIX BLOCKER-1; a bare `python -c "import caller"` only works with those env vars exported).
   `backend/caller.py` md5 vs `/opt/famit-agent/caller.py` is **RECORDED, not gated** (RED-TEAM FIX BLOCKER-3:
   P1 is mid-flight on the box and may legitimately move prod; drift ≠ P0 failure). **No file was deployed; no
   service restarted.**
3. **Frontend:** `cd frontend; pnpm run build` exit 0; Playwright login smoke green.
4. **CI:** a PR shows `backend`, `frontend`, `secrets`, `infra` workflows ALL green.
5. **Terraform no-diff:** `cd infra; terraform plan` → **"No changes. Your infrastructure matches the
   configuration."** for all imported resources, with **zero** destroy/replace lines. **`apply` was never
   run.**
6. **Live system untouched & earning:** `curl -H "X-Auth: FamitCall2026" https://panel.famit.in/api/stats`
   → 200 with real data; `ssh famit@168.144.153.145 'systemctl is-active famit-caller famit-agent'`
   → active/active. (Read-only checks; this phase changed nothing on the boxes.)
7. **Git hygiene:** `main` protected; worktree/branch/PR/squash model documented in `CONTRIBUTING.md`;
   commit history clean (conventional commits).

---

## 11. DEPENDENCIES & ORDER CONSTRAINTS (what blocks what)

- **Steps 1→6 are STRICTLY SEQUENTIAL and gate everything** (no `backend/`/`frontend/` curation, no CI,
  no push until the secrets-gate is GREEN and the repo is private). **This is the hard prerequisite.**
- Steps 8 (backend) and 9 (frontend) are **independent** → can be **two worktrees in parallel** (different
  dirs, no shared files). Step 10 (doc path updates) touches shared docs → do **after** 8+9 land, in main.
- Step 11 (CI) needs 8+9+13 files present to be meaningful (but workflows can be added before infra; the
  `infra` job just no-ops until `infra/` exists). Step 12 (protection) after the first green CI run.
- Steps 13→15 (terraform) are **independent of backend/frontend** → can run in their own worktree in
  parallel with 8/9, BUT require the secrets-gate done (token handling) and **must stay import/plan-only**.
- **External prerequisites the agent needs (no founder action required for P0):** DO API token (in
  `lead\ALL_CREDENTIALS.md`), a CF token with **read** scope (in `fortress\cred.md`), a GitHub auth for
  `gh` (already authed: `gh 2.93.0`). If `gh` is not logged in → `gh auth login` (one-time, founder may
  need to approve in browser → if blocked, log it in HUMAN_TASKS, don't stall the rest).

---

## 12. MODEL ROUTING SUMMARY (for the implementing agent)

- **opus** — the secrets-gate raw+staged scan review (steps 1,2,4,6), the terraform **plan-diff verdict**
  (steps 14,15: deciding "no-diff vs RED-STOP" is the high-stakes judgment), final phase review (16).
- **sonnet** — author scaffolding (pyproject/ruff/pnpm/Playwright configs), the 4 CI workflows, the
  terraform HCL (versions/providers/resources/imports), git workflow setup, frontend curation.
- **haiku** — mechanical `git mv` moves, doc path-reference find/replace (step 10), status polling.
- **Serialization rule:** `caller.py`/`backend/*` curation is ONE owner in main (never two agents on the
  3422-line file). Backend(8) ∥ Frontend(9) ∥ Terraform(13-15) may parallelize as separate worktrees.

---

## 13. OPEN RISKS / FLAGGED FOR ATTENTION

1. **md5 local-vs-deployed drift (backend):** the local `droplet_work/caller.py` may NOT byte-match the
   deployed `/opt/famit-agent/caller.py` (many waves deployed edited copies). P0 does NOT reconcile this —
   it only RECORDS drift. **If they differ, `backend/` is the local truth for the repo; prod is unchanged.
   Reconciliation is a Phase-1 concern** (the Postgres wave already plans an md5 baseline). Do not "fix"
   prod from this phase.
2. **Cloudflare v5 zone-settings schema:** the v5 provider reworked zone settings; the exact resource
   name/schema must be read from provider docs at implement-time, not guessed. If import is fiddly, scope
   P0 CF import to **zone + dns_records** and flag zone-settings as a no-diff follow-up.
3. **pnpm vs npm peer-deps (React 19):** if `pnpm run build` fails where npm needed `--legacy-peer-deps`,
   resolve via `.npmrc`/`pnpm overrides` (the app builds today, so green is achievable) — do not ship a
   red frontend build.
4. **gitleaks on the legacy backups:** the staged scan (the gate) is authoritative; the raw `gitleaks dir`
   will (correctly) flag ignored secret files — that is expected, not a failure. The ONLY failure that
   matters is a secret in the **staged/pushed** set.
5. **`.terraform.lock.hcl` committed-or-not:** §2 ignores it in P0 to avoid churn; many teams commit it.
   Low-stakes — revisit when a remote backend is added.
6. **The legacy `caps\src` / `pyproject.toml` / `selfhost`:** older standalone skeleton, NOT the live
   backend. Left in place (low priority to relocate). Don't let it confuse `/backend` = `droplet_work`.
7. **GitHub `gh auth`:** if not pre-authed, the founder may need a one-time browser approval — log to
   HUMAN_TASKS if it blocks, but it should not block the local steps (1-5, 8-10, 13-15).
8. **Scope creep guard:** voice quick-wins (semantic turn-detector, barge-in) are a SEPARATE P0 spec —
   keep them OUT of this foundation work. Phase 1 (Postgres) and any caller.py module-split are OUT.

---

## APPENDIX A — file manifest this spec creates (for the agent's checklist)
```
caps/.gitignore (rewrite)   caps/.gitleaks.toml   caps/.gitattributes   caps/.worktreeinclude
caps/.githooks/pre-commit   caps/README.md (root)   caps/CONTRIBUTING.md
backend/pyproject.toml  backend/ruff.toml  backend/DEPLOY.md  backend/.env.example
backend/tests/{conftest.py,test_imports.py,test_smoke_prompt.py,test_smoke_instantiate.py}
  (+ git mv of the flat .py modules + vendors/ from droplet_work/)
frontend/playwright.config.ts  frontend/tests/e2e/login.spec.ts  frontend/.env.local.example
  (+ pnpm-lock.yaml via pnpm import; + git mv of the app from famit-panel/)
infra/{versions,providers,variables,digitalocean,cloudflare,imports}.tf  infra/README.md
.github/workflows/{backend,frontend,secrets,infra}.yml
```

## APPENDIX B — the ONE-LINE health probe (read-only; the only thing that touches a live box)
```powershell
curl.exe -s -o NUL -w "%{http_code}" -H "X-Auth: FamitCall2026" https://panel.famit.in/api/stats   # expect 200
ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145 "systemctl is-active famit-caller famit-agent"  # active / active
```
Used only to PROVE the phase changed nothing in production. Never write/restart anything on the boxes in P0.
