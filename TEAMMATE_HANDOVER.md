# TEAMMATE HANDOVER — axcrio-platform

Welcome. This is the Famit / Axcrio platform repo. It is a **private** GitHub
repo. Below is everything you need to clone, branch, and start — plus the list of
secret files you must get **separately** (they are deliberately NOT in git).

## 1. Clone + branch (never push to `main`)
```bash
git clone <REPO_URL>          # the private repo URL (see top of this file once filled)
cd <repo>
git checkout -b feat/<your-name>   # always work on your own branch
# ...do work, commit per verified unit...
git push -u origin feat/<your-name>
# then open a Pull Request on GitHub for review/merge.
```
Do **not** commit directly to `main`. Open PRs.

## 2. Read these first
- `CLAUDE.md` — the repo map (frontend / backend / monorepo, infra, working rules).
- `ARCHITECTURE.md` — the detailed system map.
- `design/` + the root `*_MASTER_PROMPT.md` specs for whatever feature you touch.

## 3. SECRETS — give/get these SEPARATELY, NEVER on GitHub
These files are gitignored and are NOT in the repo. The founder will share them
over a one-time-secret link or an encrypted channel. Drop each one back into the
path shown, then you are runnable. **Never commit any of them.**

| File (path in repo) | What it holds |
|---|---|
| `.env` | Backend/runtime env (LiveKit, providers, DSNs). |
| `.env.local` | Frontend local env — includes `GEMINI_API_KEY`. |
| `final_env.md` | The live `VOBIZ_AUTH_TOKEN` (telephony auth). |
| `**/ALL_CREDENTIALS.md` | Aggregated credentials sheet. |
| `ai_manager_cred.md` | AI Manager telephony creds (Vobiz auth + SIP user/pass). |
| `infra/logto/app_id_secret_m2m.md` (+ `app_id_secret*`) | Logto M2M app id/secret. |
| `groq_api.md` | Groq API key(s). |
| `fortress/cred.md` (whole `fortress/` dir) | Box access + hardening secrets. |
| `id_ed25519` (SSH private key) | SSH access to the DigitalOcean boxes. |

After placing the `.env*` files, the frontend (`famit-panel/`) and backend
(`droplet_work/`, also shared separately — it is not tracked) will run.

## 4. Box access
The live infra is DigitalOcean (blr1): frontend `famit-panel-2`
`143.110.247.249`, the voice box (`caller.py` + `agent.py`), and `famit-hatchet`
`68.183.94.38` (Hatchet + Logto). Get the `id_ed25519` SSH key + the
`fortress/` access notes from the founder, then follow `fortress/` playbooks.
Box access details live in `fortress/` (shared separately, not in git).

## 5. Safety rule (everyone)
Before committing: `git add -A`, then run `gitleaks protect --staged --no-banner`
and confirm it reports **0 leaks**. A leaked secret on GitHub is irreversible.
If in doubt, stop and ask — do not push.
